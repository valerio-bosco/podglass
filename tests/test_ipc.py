import asyncio
import json

from podglass import ipc
from podglass.ipc import IpcServer, parse_command


def test_parse_command():
    assert parse_command("mode anc") == ("mode", "anc")
    assert parse_command('{"cmd": "mode anc"}') == ("mode", "anc")
    assert parse_command('{"cmd": "mode", "arg": "adaptive"}') == ("mode", "adaptive")
    assert parse_command('{"cmd": "layout", "arg": {"HDMI-A-1": {}}}') == ("layout", '{"HDMI-A-1": {}}')
    assert parse_command("connect") == ("connect", None)
    assert parse_command("adaptive-level 70") == ("adaptive-level", "70")
    for bad in ("", "mode loud", "connect now", "adaptive-level 101", "rm -rf", "{bad json", "layout [1]", "ca"):
        assert parse_command(bad) is None, bad


def test_server_sends_state_on_connect_and_broadcasts(tmp_path):
    async def main():
        got_cmds = []
        server = IpcServer(lambda v, a: got_cmds.append((v, a)), tmp_path / "s.sock")
        await server.start()
        server.publish_config('{"type":"config","theme":"dark"}')
        server.publish_state('{"type":"state","device":{"connected":false}}')

        lines = []
        watcher = asyncio.create_task(ipc.watch(server.path, lines.append))
        await asyncio.sleep(0.05)
        server.publish_state('{"type":"state","device":{"connected":true}}')
        server.publish_state('{"type":"state","device":{"connected":true}}')  # unchanged: not resent
        server.publish_event("lid-opened")
        await ipc.send("mode", "anc", server.path)
        status = await ipc.status(server.path)
        await asyncio.sleep(0.05)
        watcher.cancel()
        await server.close()
        return lines, got_cmds, status, server.path.exists()

    lines, cmds, status, exists = asyncio.run(main())
    types = [json.loads(line)["type"] for line in lines]
    assert types == ["config", "state", "state", "event"]
    assert cmds == [("mode", "anc")]
    assert status == {"connected": True}
    assert not exists


def test_bad_commands_are_ignored(tmp_path):
    async def main():
        cmds = []
        server = IpcServer(lambda v, a: cmds.append(v), tmp_path / "s.sock")
        await server.start()
        r, w = await asyncio.open_unix_connection(str(server.path))
        w.write(b"mode loud\nhello\nconnect\n")
        await w.drain()
        await asyncio.sleep(0.05)
        w.close()
        await server.close()
        return cmds

    assert asyncio.run(main()) == ["connect"]


def test_cli_status_format_and_validation(capsys):
    from podglass.__main__ import _format_status, main

    text = _format_status({"name": "AirPods Pro", "model": "pro2-lightning", "connected": True,
                           "battery": {"left": {"level": 82}, "right": {"level": 80},
                                       "case": {"level": 1, "charging": True}, "precise": True},
                           "mode": "anc", "lid": "closed"})
    assert "connected" in text and "case 1% (charging)" in text and "approx" not in text
    assert main(["set", "mode", "loud"]) == 2


def test_hyprland_signature(tmp_path):
    import os
    import time

    from podglass.daemon import _hyprland_signature

    assert _hyprland_signature(tmp_path / "missing") is None
    old, new, empty = tmp_path / "old", tmp_path / "new", tmp_path / "empty"
    for d in (old, new, empty):
        d.mkdir()
    (old / ".socket.sock").touch()
    (new / ".socket.sock").touch()
    t = time.time()
    os.utime(old, (t - 100, t - 100))
    os.utime(new, (t, t))
    assert _hyprland_signature(tmp_path) == "new"
