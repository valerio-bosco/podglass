"""podglass: AirPods on this desktop. Commands talk to the running daemon (`podglass daemon`)."""

import argparse
import asyncio
import json
import sys

UI_VERBS = {"show-card": "show the AirPods card", "popover": "open the battery and mode popover",
            "edit": "move the card and widget"}


def _format_status(d: dict) -> str:
    b = d.get("battery", {})

    def pct(part):
        x = b.get(part) or {}
        lvl = "-" if x.get("level") is None else f"{x['level']}%"
        return lvl + (" (charging)" if x.get("charging") else "")

    state = "connected" if d.get("connected") else ("connecting" if d.get("connecting") else "not connected")
    return "\n".join([
        f"{d.get('name') or 'AirPods'} ({d.get('model') or '?'}): {state}",
        f"battery  left {pct('left')}  right {pct('right')}  case {pct('case')}"
        + ("" if b.get("precise") else "  (approx.)"),
        f"mode     {d.get('mode') or '-'}   lid {d.get('lid', 'unknown')}",
    ])


def _run_ui() -> int:
    """Replace this process with the Quickshell UI (the long-running `podglass-ui` service)."""
    import os
    import shutil
    from pathlib import Path

    root = Path(os.environ.get("PODGLASS_ROOT") or Path(__file__).resolve().parent.parent)
    shell = root / "ui" / "shell.qml"
    quickshell = os.environ.get("PODGLASS_QUICKSHELL") or shutil.which("quickshell")
    if not shell.is_file() or not quickshell:
        print(f"cannot start the UI: {'quickshell not found' if not quickshell else shell + ' missing'}",
              file=sys.stderr)
        return 1
    env = dict(os.environ, PODGLASS_ROOT=str(root))
    env.setdefault("PODGLASS_BIN", shutil.which("podglass") or sys.argv[0])
    # Renders are generated per user (never in the store): when the package has none, build a
    # small root whose assets/renders points at $XDG_DATA_HOME/podglass/renders.
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "podglass" / "renders"
    if not (root / "assets" / "renders" / "manifest.json").exists() and (data / "manifest.json").exists():
        overlay = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "podglass-ui-root"
        (overlay / "assets").mkdir(parents=True, exist_ok=True)
        for link, target in ((overlay / "tools", root / "tools"),
                             (overlay / "assets" / "placeholder", root / "assets" / "placeholder"),
                             (overlay / "assets" / "renders", data)):
            if link.is_symlink() and Path(os.readlink(link)) != target:
                link.unlink()
            if not link.is_symlink():
                link.symlink_to(target)
        env["PODGLASS_ROOT"] = str(overlay)
    os.execve(quickshell, [quickshell, "-p", str(shell)], env)


def _client(coro) -> int:
    from .ipc import socket_path

    try:
        return asyncio.run(coro) or 0
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"podglass daemon is not running ({socket_path()})", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="podglass", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    dm = sub.add_parser("daemon", help="run the background service")
    dm.add_argument("--replay", metavar="FILE", help="feed a BLE capture instead of scanning")
    dm.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("watch", help="print state and events as JSON lines (used by the UI)")
    st = sub.add_parser("status", help="show battery, mode and connection")
    st.add_argument("--json", action="store_true")
    s = sub.add_parser("set", help="send a command: connect, disconnect, mode <m>, ca <on|off>, ...")
    s.add_argument("verb")
    s.add_argument("arg", nargs="?")
    sub.add_parser("ui", help="run the Quickshell UI (card, popover, widget)")
    for verb, text in UI_VERBS.items():
        sub.add_parser(verb, help=text)

    debug = sub.add_parser("debug", help="talk to one subsystem directly")
    dsub = debug.add_subparsers(dest="what", required=True)
    bz = dsub.add_parser("bluez", help="show the AirPods as BlueZ sees them")
    bz.add_argument("--connect", action="store_true")
    bz.add_argument("--disconnect", action="store_true")
    bz.add_argument("--battery", type=int, metavar="PERCENT", help="register a test battery provider")

    sc = dsub.add_parser("scan", help="print adverts of your AirPods")
    sc.add_argument("--seconds", type=float, default=20)

    ap = dsub.add_parser("aap", help="open an AAP session and print events")
    ap.add_argument("--mac", help="default: the connected AirPods")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--mode", choices=["off", "transparency", "adaptive", "anc"])

    tr = dsub.add_parser("tray", help="show the tray icon and print clicks")
    tr.add_argument("--seconds", type=float, default=30)

    args = parser.parse_args(argv)
    from . import ipc

    if args.cmd == "daemon":
        from pathlib import Path

        from .daemon import main as daemon_main

        return daemon_main(Path(args.replay) if args.replay else None, args.verbose)
    if args.cmd == "ui":
        return _run_ui()
    if args.cmd == "watch":
        return _client(ipc.watch(out=lambda line: print(line, flush=True)))
    if args.cmd == "status":
        async def show():
            d = await ipc.status()
            if d is None:
                print("no state from the daemon yet", file=sys.stderr)
                return 1
            print(json.dumps(d, indent=2) if args.json else _format_status(d))
        return _client(show())
    if args.cmd == "set":
        line = f"{args.verb} {args.arg}" if args.arg is not None else args.verb
        if ipc.parse_command(line) is None:
            print(f"invalid command: {line}", file=sys.stderr)
            return 2
        return _client(ipc.send(args.verb, args.arg))
    if args.cmd in UI_VERBS:
        return _client(ipc.send(args.cmd))
    if args.cmd == "debug" and args.what == "bluez":
        from .bluez import debug as bluez_debug

        return asyncio.run(bluez_debug(args.connect, args.disconnect, args.battery))
    if args.cmd == "debug" and args.what == "scan":
        from .scanner import debug as scan_debug

        return asyncio.run(scan_debug(args.seconds))
    if args.cmd == "debug" and args.what == "aap":
        from .aap_session import debug as aap_debug

        return asyncio.run(aap_debug(args.mac, args.seconds, args.mode))
    if args.cmd == "debug" and args.what == "tray":
        from .tray import debug as tray_debug

        return asyncio.run(tray_debug(args.seconds))
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
