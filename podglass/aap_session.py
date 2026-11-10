"""Async AAP session over L2CAP PSM 0x1001. See docs/PROTOCOL.md 2.

`AapSession` is one connection: startup sequence, `send()`, `events()`. `run_sessions()` keeps one
open while BlueZ says the AirPods are connected, reconnecting with backoff.
"""

import asyncio
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from . import aap
from .keys import DeviceKeys, add_device, load_keys

log = logging.getLogger(__name__)

PSM = 0x1001
STARTUP_TIMEOUT_S = 3.0
BACKOFF_S = (1, 2, 4, 8, 15, 30)

SocketFactory = Callable[[str], Awaitable[socket.socket]]


async def l2cap_connect(mac: str) -> socket.socket:
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    sock.setblocking(False)
    try:
        await asyncio.wait_for(asyncio.get_running_loop().sock_connect(sock, (mac, PSM)), 10)
    except BaseException:
        sock.close()
        raise
    return sock


class AapSession:
    def __init__(self, mac: str, keys_path: Path | None = None, connect: SocketFactory = l2cap_connect):
        self.mac = mac.upper()
        self.keys_path = keys_path
        self._connect = connect
        self._sock: socket.socket | None = None
        self._queue: asyncio.Queue[aap.AapEvent | None] = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self._handshake = asyncio.Event()

    async def open(self) -> None:
        """Connect and run the startup sequence. Raises OSError / TimeoutError on failure."""
        self._sock = await self._connect(self.mac)
        self._reader = asyncio.create_task(self._read())
        await self.send(aap.HANDSHAKE)
        ack = asyncio.ensure_future(self._handshake.wait())
        done, _ = await asyncio.wait({ack, self._reader}, timeout=STARTUP_TIMEOUT_S,
                                     return_when=asyncio.FIRST_COMPLETED)
        if ack not in done:
            ack.cancel()
            closed = self._reader in done
            await self.close()
            if closed:
                raise ConnectionError("AirPods closed the AAP connection during the handshake")
            raise asyncio.TimeoutError
        await self.send(aap.FEATURES)  # its ack may never come (PROTOCOL.md 2.1): do not wait
        await self.send(aap.NOTIFICATIONS)
        if self.mac not in load_keys(self.keys_path):
            await self.send(aap.request_keys())

    async def send(self, data: bytes) -> None:
        if self._sock is None:
            raise ConnectionError("AAP session is not open")
        await asyncio.get_running_loop().sock_sendall(self._sock, data)

    async def _read(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                data = await loop.sock_recv(self._sock, 1024)
                if not data:
                    break
                event = aap.parse_packet(data)
                if event is None:
                    continue
                if isinstance(event, aap.Ack) and event.kind == "handshake":
                    self._handshake.set()
                if isinstance(event, aap.Keys):
                    self._store_keys(event)
                self._queue.put_nowait(event)
        except OSError as e:
            log.info("AAP socket closed: %s", e)
        finally:
            self._queue.put_nowait(None)

    def _store_keys(self, event: aap.Keys) -> None:
        if self.mac in load_keys(self.keys_path):
            return
        add_device(self.mac, DeviceKeys(irk=event.irk, enc_key=event.enc_key), self.keys_path)
        log.info("stored keys for %s", self.mac)

    async def events(self) -> AsyncIterator[aap.AapEvent]:
        """Every event the AirPods send, until the connection closes."""
        while (event := await self._queue.get()) is not None:
            yield event

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None


async def run_sessions(mac: str, is_connected: Callable[[], Awaitable[bool]],
                       on_event: Callable[[aap.AapEvent], None],
                       on_session: Callable[[AapSession | None], None] = lambda s: None,
                       keys_path: Path | None = None, connect: SocketFactory = l2cap_connect,
                       sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    """Keep an AAP session open while `is_connected()` is true. Returns when it turns false.

    `on_session(session)` is called with the live session (for `send`) and with None when it ends.
    """
    attempt = 0
    while await is_connected():
        session = AapSession(mac, keys_path, connect)
        try:
            await session.open()
        except (OSError, asyncio.TimeoutError) as e:
            delay = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
            log.info("AAP connect failed (%s), retry in %s s", e or "timeout", delay)
            attempt += 1
            await sleep(delay)
            continue
        attempt = 0
        on_session(session)
        try:
            async for event in session.events():
                on_event(event)
        finally:
            on_session(None)
            await session.close()


async def debug(mac: str | None, seconds: float, mode: str | None) -> int:
    """`podglass debug aap`: open a session, print events, optionally set the listening mode."""
    if mac is None:
        from .bluez import Bluez

        bz = await Bluez.open()
        dev = await bz.find_airpods(set(load_keys()))
        bz.close()
        if dev is None or not dev.connected:
            print("AirPods not connected (podglass debug bluez --connect)")
            return 1
        mac = dev.address
    session = AapSession(mac)
    try:
        await session.open()
    except (OSError, asyncio.TimeoutError) as e:
        print(f"cannot open AAP session: {e or 'handshake timeout'}")
        return 1
    print(f"AAP session open with {mac}")
    if mode:
        await session.send(aap.set_mode(mode))

    async def show():
        async for event in session.events():
            if isinstance(event, aap.Keys):
                print("Keys(<redacted>)")
            elif not isinstance(event, aap.Unknown):
                print(event)

    try:
        await asyncio.wait_for(show(), seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        await session.close()
    return 0
