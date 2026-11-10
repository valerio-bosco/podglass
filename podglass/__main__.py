"""Command line entry point."""

import argparse
import asyncio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="podglass", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    debug = sub.add_parser("debug", help="talk to one subsystem directly")
    dsub = debug.add_subparsers(dest="what", required=True)
    bz = dsub.add_parser("bluez", help="show the AirPods as BlueZ sees them")
    bz.add_argument("--connect", action="store_true")
    bz.add_argument("--disconnect", action="store_true")
    bz.add_argument("--battery", type=int, metavar="PERCENT", help="register a test battery provider")

    sc = dsub.add_parser("scan", help="print adverts of your AirPods")
    sc.add_argument("--seconds", type=float, default=20)

    args = parser.parse_args(argv)
    if args.cmd == "debug" and args.what == "bluez":
        from .bluez import debug as bluez_debug

        return asyncio.run(bluez_debug(args.connect, args.disconnect, args.battery))
    if args.cmd == "debug" and args.what == "scan":
        from .scanner import debug as scan_debug

        return asyncio.run(scan_debug(args.seconds))
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
