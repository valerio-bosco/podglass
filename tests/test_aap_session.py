import asyncio
import socket

from podglass import aap
from podglass.aap_session import AapSession, run_sessions
from podglass.keys import DeviceKeys, add_device

MAC = "2C:32:6A:BC:8F:5D"
BATTERY = bytes.fromhex("040004000400030201640201040163010108011102 01".replace(" ", ""))
KEYS = (bytes.fromhex("04000400310002") + bytes.fromhex("01001000") + bytes(range(16))
        + bytes.fromhex("04001000") + bytes(range(16, 32)))


def pair():
    """(our end, fake AirPods end), both non-blocking SEQPACKET like L2CAP."""
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    a.setblocking(False)
    b.setblocking(False)
    return a, b


async def fake_airpods(sock, reply_handshake=True, extra=()):
    """Answer like the AirPods: ack the handshake, then send `extra` packets. Returns what we got."""
    loop = asyncio.get_running_loop()
    got = []
    while True:
        try:
            data = await asyncio.wait_for(loop.sock_recv(sock, 1024), 0.5)
        except asyncio.TimeoutError:
            return got
        if not data:
            return got
        got.append(data)
        if data == aap.HANDSHAKE and reply_handshake:
            await loop.sock_sendall(sock, bytes.fromhex("01000400"))
        if data == aap.NOTIFICATIONS:
            for p in extra:
                await loop.sock_sendall(sock, p)


def test_startup_sequence_events_and_keys(tmp_path):
    async def main():
        ours, theirs = pair()

        async def connect(mac):
            return ours

        peer = asyncio.create_task(fake_airpods(theirs, extra=[BATTERY, KEYS]))
        s = AapSession(MAC, tmp_path / "keys.json", connect)
        await s.open()
        events = []
        async for e in s.events():
            events.append(e)
            if isinstance(e, aap.Keys):
                break
        await s.close()
        return events, await peer

    events, sent = asyncio.run(main())
    assert sent[:3] == [aap.HANDSHAKE, aap.FEATURES, aap.NOTIFICATIONS]
    assert sent[3] == aap.request_keys()  # no keys stored yet
    assert any(isinstance(e, aap.Battery) for e in events)
    from podglass.keys import load_keys
    assert load_keys(tmp_path / "keys.json")[MAC].irk == bytes(range(16))


def test_no_key_request_when_keys_known(tmp_path):
    add_device(MAC, DeviceKeys(bytes(16), bytes(16)), tmp_path / "keys.json")

    async def main():
        ours, theirs = pair()
        peer = asyncio.create_task(fake_airpods(theirs))

        async def connect(mac):
            return ours

        s = AapSession(MAC, tmp_path / "keys.json", connect)
        await s.open()
        await asyncio.sleep(0.1)
        await s.close()
        return await peer

    assert aap.request_keys() not in asyncio.run(main())


def test_handshake_timeout_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("podglass.aap_session.STARTUP_TIMEOUT_S", 0.1)

    async def main():
        ours, theirs = pair()

        async def connect(mac):
            return ours

        try:
            await AapSession(MAC, tmp_path / "k.json", connect).open()
        except asyncio.TimeoutError:
            return True
        return False

    assert asyncio.run(main())


def test_run_sessions_retries_then_stops_when_disconnected(tmp_path):
    async def main():
        calls, sleeps, sessions = [], [], []
        connected = iter([True, True, False])

        async def is_connected():
            return next(connected)

        async def connect(mac):
            calls.append(mac)
            if len(calls) == 1:
                raise OSError("busy")
            ours, theirs = pair()
            theirs.close()  # AirPods hang up right away
            return ours

        async def sleep(s):
            sleeps.append(s)

        await run_sessions(MAC, is_connected, lambda e: None, sessions.append,
                           tmp_path / "k.json", connect, sleep)
        return calls, sleeps, sessions

    calls, sleeps, sessions = asyncio.run(main())
    assert len(calls) == 2 and sleeps == [1, 2]  # second socket hung up: retried with backoff
    assert sessions == []  # second session never finished the handshake
