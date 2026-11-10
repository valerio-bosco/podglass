"""Unix socket between the daemon and its clients, JSON lines. See docs/PLAN.md 3.1.

Server -> client: the latest `config` and `state` lines on connect, then every state and event.
Client -> server: one command per line, `{"cmd": "mode", "arg": "anc"}` or plain `mode anc`.
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

MODES = ("off", "transparency", "adaptive", "anc")
# verb -> validator for the argument (None = takes no argument)
VERBS: dict[str, Callable[[str], bool] | None] = {
    "connect": None,
    "disconnect": None,
    "dismiss-card": None,
    "show-card": None,
    "popover": None,
    "edit": None,
    "mode": lambda a: a in MODES,
    "ca": lambda a: a in ("on", "off"),
    "adaptive-level": lambda a: a.isdigit() and 0 <= int(a) <= 100,
    "layout": lambda a: _is_json_object(a),
}


def _is_json_object(text: str) -> bool:
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return Path(runtime) / "podglass.sock" if runtime else Path(f"/tmp/podglass-{os.getuid()}.sock")


def parse_command(line: str) -> tuple[str, str | None] | None:
    """`(verb, arg)` for a valid command line, else None. Pure."""
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except ValueError:
            return None
        if not isinstance(obj, dict):
            return None
        words = str(obj.get("cmd", "")).split(None, 1)
        arg = obj.get("arg", words[1] if len(words) > 1 else None)
        if arg is not None and not isinstance(arg, str):
            arg = json.dumps(arg)
        verb = words[0] if words else ""
    else:
        verb, _, rest = line.partition(" ")
        arg = rest.strip() or None
    if verb not in VERBS:
        return None
    check = VERBS[verb]
    if check is None:
        return (verb, None) if arg is None else None
    return (verb, arg) if arg is not None and check(arg) else None


class IpcServer:
    def __init__(self, on_command: Callable[[str, str | None], None], path: Path | None = None):
        self.path = path or socket_path()
        self.on_command = on_command
        self.state_line: str | None = None
        self.config_line: str | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self.path.unlink(missing_ok=True)
        old = os.umask(0o177)  # socket readable only by this user
        try:
            self._server = await asyncio.start_unix_server(self._client, path=str(self.path))
        finally:
            os.umask(old)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        try:
            for line in (self.config_line, self.state_line):
                if line:
                    writer.write(line.encode() + b"\n")
            try:
                await writer.drain()
            except ConnectionError:
                pass  # a one-shot `podglass set` may hang up at once: still read its command
            while line := await reader.readline():
                cmd = parse_command(line.decode(errors="replace"))
                if cmd is None:
                    log.warning("ipc: ignored command %r", line[:200])
                    continue
                self.on_command(*cmd)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._clients.discard(writer)
            writer.close()

    def _broadcast(self, line: str) -> None:
        data = line.encode() + b"\n"
        for w in list(self._clients):
            if w.is_closing():
                self._clients.discard(w)
                continue
            w.write(data)

    def publish_state(self, line: str) -> None:
        if line != self.state_line:
            self.state_line = line
            self._broadcast(line)

    def publish_config(self, line: str) -> None:
        self.config_line = line
        self._broadcast(line)

    def publish_event(self, name: str) -> None:
        self._broadcast(json.dumps({"type": "event", "name": name}, separators=(",", ":")))

    async def close(self) -> None:
        # close the clients first: since Python 3.12 wait_closed() waits for every connection
        for w in list(self._clients):
            w.close()
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 2)
            except asyncio.TimeoutError:
                log.warning("ipc: clients did not close in time")
        self.path.unlink(missing_ok=True)


# --- client side (CLI) --------------------------------------------------------------------------

async def _open(path: Path | None):
    return await asyncio.open_unix_connection(str(path or socket_path()))


async def send(verb: str, arg: str | None = None, path: Path | None = None) -> None:
    reader, writer = await _open(path)
    writer.write(json.dumps({"cmd": verb, "arg": arg} if arg is not None else {"cmd": verb}).encode() + b"\n")
    writer.write_eof()
    # read what the server sent until it hangs up: closing a unix socket with unread data resets
    # the connection and the server could lose the command
    await asyncio.wait_for(reader.read(), 2)
    writer.close()


async def watch(path: Path | None = None, out: Callable[[str], None] = print) -> None:
    """Print every line from the daemon until it goes away."""
    reader, _ = await _open(path)
    while line := await reader.readline():
        out(line.decode().rstrip("\n"))


async def status(path: Path | None = None, timeout: float = 2) -> dict | None:
    """The current device state, or None if the daemon sent none within `timeout`."""
    reader, writer = await _open(path)
    try:
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout)
            if not line:
                return None
            msg = json.loads(line)
            if msg.get("type") == "state":
                return msg.get("device")
    except (asyncio.TimeoutError, ValueError):
        return None
    finally:
        writer.close()
