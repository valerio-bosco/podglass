#!/usr/bin/env python3
"""Fake daemon for building the UI without AirPods.

Prints the same JSON lines as `podglass watch` (docs/PLAN.md 3.1) for a scripted scenario and
answers commands read from stdin (one `{"cmd": ...}` JSON object or `verb args` per line), so the
UI buttons do something. Usage: demo_state.py <scenario>   (--list for the names)
"""

import copy
import json
import os
import select
import sys
import time
from pathlib import Path

BASE = {
    "present": True, "connected": False, "connecting": False, "paired": True, "known": True,
    "name": "AirPods Pro", "model": "pro2-usbc", "firmware": "7A305",
    "battery": {
        "left": {"level": 80, "charging": False},
        "right": {"level": 80, "charging": False},
        "case": {"level": 60, "charging": False},
        "precise": False,
    },
    "inEar": {"left": False, "right": False},
    "inCase": {"left": True, "right": True},
    "lid": "open", "mode": "anc", "conversationAwareness": True, "adaptiveLevel": 50,
}

CONNECTED = {
    "connected": True, "lid": "closed",
    "battery": {"left": {"level": 82, "charging": False}, "right": {"level": 80, "charging": False},
                "case": {"level": 64, "charging": True}, "precise": True},
    "inEar": {"left": True, "right": True}, "inCase": {"left": False, "right": False},
}

# scenario: list of (delay before the step in seconds, state patch or None, event or None)
SCENARIOS = {
    "lid-open-disconnected": [(0.3, {}, {"name": "show-card", "card": "normal"})],
    "connecting": [(0.3, {"connecting": True}, {"name": "show-card", "card": "normal"})],
    "connected": [(0.3, CONNECTED, {"name": "show-card", "card": "normal"})],
    "popover": [(0.3, CONNECTED, {"name": "popover"})],
    "low-battery": [(0.3, {**CONNECTED, "battery": {
        "left": {"level": 12, "charging": False}, "right": {"level": 9, "charging": False},
        "case": {"level": 18, "charging": False}, "precise": True}}, {"name": "show-card", "card": "normal"})],
    "one-pod": [(0.3, {**CONNECTED, "battery": {
        "left": {"level": 74, "charging": False}, "right": {"level": None, "charging": False},
        "case": {"level": 64, "charging": True}, "precise": True},
        "inEar": {"left": True, "right": False}}, {"name": "show-card", "card": "normal"})],
    "setup": [(0.3, {"paired": False, "known": False, "battery": copy.deepcopy(BASE["battery"]) | {
        "left": {"level": None, "charging": False}, "right": {"level": None, "charging": False},
        "case": {"level": None, "charging": False}}}, {"name": "show-card", "card": "setup"})],
    "error": [(0.3, {}, {"name": "show-card", "card": "normal"}), (0.2, None, {"name": "connect-failed"})],
    "widget": [(0.3, CONNECTED, None)],
    "edit": [(0.3, CONNECTED, {"name": "edit"})],
    # the whole story: lid opens, connect, pods in, lid closes
    "story": [
        (0.5, {"connected": False}, {"name": "lid-opened"}),
        (0.0, None, {"name": "show-card", "card": "normal"}),
        (2.5, {"connecting": True}, None),
        (1.5, {"connecting": False, "connected": True}, {"name": "connected"}),
        (2.0, CONNECTED, {"name": "lid-closed"}),
        (1.5, None, {"name": "hide-card"}),
    ],
}


def merge(dst: dict, patch: dict) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)


class Demo:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.device = copy.deepcopy(BASE)
        self.queue = [(d, p, e) for d, p, e in SCENARIOS[scenario]]
        self.timers: list[tuple[float, dict | None, dict | None]] = []

    def out(self, obj: dict) -> None:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def state(self) -> None:
        self.out({"type": "state", "device": self.device})

    def event(self, ev: dict) -> None:
        self.out({"type": "event", **ev})

    def apply(self, patch: dict | None, ev: dict | None) -> None:
        if patch is not None:
            merge(self.device, patch)
            self.state()
        if ev is not None:
            self.event(ev)

    def later(self, delay: float, patch: dict | None, ev: dict | None = None) -> None:
        self.timers.append((time.monotonic() + delay, patch, ev))

    def command(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            obj = json.loads(line)
            words = str(obj.get("cmd", "")).split(None, 1)
            arg = obj.get("arg", words[1] if len(words) > 1 else None)
            verb = words[0] if words else ""
        except ValueError:
            verb, _, arg = line.partition(" ")
        print(f"demo: command {verb} {arg or ''}", file=sys.stderr)
        d = self.device
        if verb == "connect":
            self.apply({"connecting": True}, None)
            if self.scenario == "error":
                self.later(1.5, {"connecting": False}, {"name": "connect-failed"})
            else:
                self.later(1.5, {"connecting": False, **CONNECTED, "lid": d["lid"]}, {"name": "connected"})
        elif verb == "disconnect":
            self.apply({"connected": False, "connecting": False}, {"name": "disconnected"})
        elif verb == "mode" and arg in ("off", "transparency", "adaptive", "anc"):
            self.later(0.3, {"mode": arg})  # the AirPods echo the change a moment later
        elif verb == "ca" and arg in ("on", "off"):
            self.later(0.2, {"conversationAwareness": arg == "on"})
        elif verb == "adaptive-level":
            try:
                self.later(0.2, {"adaptiveLevel": max(0, min(100, int(arg)))})
            except (TypeError, ValueError):
                pass
        elif verb == "dismiss-card":
            self.event({"name": "hide-card"})
        elif verb == "layout" and arg:
            base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "podglass"
            base.mkdir(parents=True, exist_ok=True)
            layout = arg if isinstance(arg, str) else json.dumps(arg)
            (base / "layout.json").write_text(layout + "\n")
            self.event({"name": "layout-saved"})

    def run(self) -> None:
        self.state()
        t = time.monotonic()
        for delay, patch, ev in self.queue:
            t += delay
            self.timers.append((t, patch, ev))
        stdin_open = True
        while True:
            self.timers.sort(key=lambda x: x[0])
            now = time.monotonic()
            while self.timers and self.timers[0][0] <= now:
                _, patch, ev = self.timers.pop(0)
                self.apply(patch, ev)
            timeout = max(0.0, self.timers[0][0] - now) if self.timers else None
            if not stdin_open:
                if timeout is None:
                    while True:  # keep the stream open like the real daemon
                        time.sleep(3600)
                time.sleep(timeout)
                continue
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if ready:
                line = sys.stdin.readline()
                if line == "":
                    stdin_open = False
                else:
                    self.command(line)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        print("usage: demo_state.py <scenario>\nscenarios: " + ", ".join(SCENARIOS), file=sys.stderr)
        return 0 if sys.argv[1:] == ["--list"] else 2
    try:
        Demo(sys.argv[1]).run()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
