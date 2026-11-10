#!/usr/bin/env python3
"""Talk AAP to connected AirPods and log every packet (P0.3, docs/PLAN.md).

Connects an L2CAP socket to PSM 0x1001, sends the startup sequence (docs/PROTOCOL.md 2.1) and logs
each packet both ways to tests/fixtures/aap/session-<date>.jsonl as
{"t", "dir": "tx"|"rx", "hex", "event"}. Keys received are stored in keys.json and redacted in the
log. Raw sessions also hold the serial number, so they are gitignored: commit trimmed fixtures only.

Commands (type and press Enter):
  1 off   2 anc   3 transparency   4 adaptive   c on / c off (conversation awareness)
  k request keys   x <hex> send raw packet   q quit

Usage: capture_aap.py <MAC> [--out FILE]
"""

import argparse
import datetime
import json
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from podglass import aap  # noqa: E402
from podglass.keys import DeviceKeys, add_device, default_path  # noqa: E402

PSM = 0x1001
MODE_KEYS = {"1": "off", "2": "anc", "3": "transparency", "4": "adaptive"}


class Session:
    def __init__(self, mac: str, out: Path):
        self.mac = mac.upper()
        self.out = out.open("a")
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        self.lock = threading.Lock()
        self.handshake_ok = threading.Event()

    def log(self, direction: str, data: bytes, event=None):
        hex_ = data.hex()
        if isinstance(event, aap.Keys):  # never write the keys to a fixture
            hex_ = data[:7].hex() + "<redacted>"
            event = "Keys(<redacted>)"
        line = {"t": round(time.time(), 3), "dir": direction, "hex": hex_,
                "event": repr(event) if event is not None else None}
        with self.lock:
            self.out.write(json.dumps(line) + "\n")
            self.out.flush()
        if direction == "rx":
            print(f"<- {event if isinstance(event, str) else repr(event)}"
                  if event is not None and not isinstance(event, aap.Unknown)
                  else f"<- {data.hex()}")

    def send(self, data: bytes):
        self.sock.send(data)
        self.log("tx", data)
        print(f"-> {data.hex()}")

    def reader(self):
        while True:
            try:
                data = self.sock.recv(1024)
            except OSError as e:
                print(f"socket closed: {e}")
                return
            if not data:
                print("socket closed by the AirPods")
                return
            event = aap.parse_packet(data)
            self.log("rx", data, event)
            if isinstance(event, aap.Ack) and event.kind == "handshake":
                self.handshake_ok.set()
            if isinstance(event, aap.Keys):
                add_device(self.mac, DeviceKeys(irk=event.irk, enc_key=event.enc_key))
                print(f"keys stored in {default_path()}")

    def start(self):
        print(f"connecting to {self.mac} PSM 0x{PSM:04x} ...")
        self.sock.connect((self.mac, PSM))
        threading.Thread(target=self.reader, daemon=True).start()
        self.send(aap.HANDSHAKE)
        if not self.handshake_ok.wait(3):
            print("warning: no handshake ack within 3 s, continuing")
        self.send(aap.FEATURES)
        time.sleep(0.3)
        self.send(aap.NOTIFICATIONS)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mac")
    p.add_argument("--out")
    args = p.parse_args()
    out = Path(args.out or f"tests/fixtures/aap/session-{datetime.date.today()}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    s = Session(args.mac, out)
    try:
        s.start()
    except OSError as e:
        print(f"cannot connect: {e}. Are the AirPods connected in bluetoothctl?")
        return 1
    print(f"logging to {out}. Commands: 1-4 mode, c on|off, k keys, x <hex>, q quit")
    for line in sys.stdin:
        cmd = line.strip()
        try:
            if cmd == "q":
                break
            elif cmd in MODE_KEYS:
                s.send(aap.set_mode(MODE_KEYS[cmd]))
            elif cmd in ("c on", "c off"):
                s.send(aap.set_ca(cmd == "c on"))
            elif cmd == "k":
                s.send(aap.request_keys())
            elif cmd.startswith("x "):
                s.send(bytes.fromhex(cmd[2:].replace(" ", "")))
            elif cmd:
                print("unknown command")
        except (OSError, ValueError) as e:
            print(f"error: {e}")
    s.sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
