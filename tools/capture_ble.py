#!/usr/bin/env python3
"""Record Apple proximity pairing adverts (P0.2, docs/PLAN.md).

Keeps only manufacturer data with company id 0x004C whose payload starts with 07, and writes one
JSON line per advert: {"t", "addr", "rssi", "hex", "label"}. A short decoded summary is printed so
the person running the capture can see that it works.

Usage: capture_ble.py --label lid-open --seconds 30 [--out FILE] [--mode passive|active]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakScanner  # noqa: E402
from bleak.args.bluez import AdvertisementDataType, OrPattern  # noqa: E402

from podglass.adv import parse_advert  # noqa: E402

APPLE = 0x004C
# AD structure content for manufacturer data: company id (little endian) then the message type
PATTERN = OrPattern(0, AdvertisementDataType.MANUFACTURER_SPECIFIC_DATA, b"\x4c\x00\x07")


def summary(adv) -> str:
    if adv is None:
        return "unparsed"
    if not adv.paired:
        return f"{adv.model} PAIRING MODE"
    lid = "?" if not adv.lid_known else ("open" if adv.lid_open else "closed")
    return (f"{adv.model} L={adv.left} R={adv.right} case={adv.case} "
            f"ear L={adv.left_in_ear} R={adv.right_in_ear} lid={lid} conn={adv.conn_state}")


async def run(args) -> int:
    out = Path(args.out or f"tests/fixtures/adv/{args.label}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    fh = out.open("w")

    def on_advert(device, data):
        nonlocal count
        payload = data.manufacturer_data.get(APPLE)
        if not payload or payload[0] != 0x07:
            return
        count += 1
        line = {"t": round(time.time(), 3), "addr": device.address, "rssi": data.rssi,
                "hex": payload.hex(), "label": args.label}
        fh.write(json.dumps(line) + "\n")
        fh.flush()
        print(f"{device.address} {data.rssi:>4} dBm  {summary(parse_advert(payload, data.rssi, device.address))}")

    mode = args.mode
    try:
        if mode == "passive":
            scanner = BleakScanner(on_advert, scanning_mode="passive", bluez={"or_patterns": [PATTERN]})
        else:
            scanner = BleakScanner(on_advert)
        await scanner.start()
    except Exception as e:  # passive needs BlueZ Experimental = true
        if mode != "passive":
            raise
        print(f"warning: passive scan failed ({e}); falling back to active scan", file=sys.stderr)
        mode = "active"
        scanner = BleakScanner(on_advert)
        await scanner.start()

    print(f"scanning ({mode}) for {args.seconds} s, label '{args.label}' -> {out}")
    try:
        await asyncio.sleep(args.seconds)
    finally:
        await scanner.stop()
        fh.close()
    print(f"{count} adverts written to {out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True, help="what the user is doing, e.g. lid-open")
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--out", help="default: tests/fixtures/adv/<label>.jsonl")
    p.add_argument("--mode", choices=["passive", "active"], default="passive")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
