"""DeviceState and how BLE and AAP updates merge into it (pure). See docs/PLAN.md 3.1.

Precedence: while connected, AAP values win over BLE values. Battery `precise` follows the source
of the last battery update; ear state from BLE is ignored once AAP has reported it.
"""

import json
from dataclasses import dataclass, field, replace

from . import aap
from .adv import Advert, Precise


@dataclass(frozen=True)
class Level:
    level: int | None = None
    charging: bool = False


@dataclass(frozen=True)
class BatteryState:
    left: Level = field(default_factory=Level)
    right: Level = field(default_factory=Level)
    case: Level = field(default_factory=Level)
    precise: bool = False


@dataclass(frozen=True)
class Pair:
    left: bool = False
    right: bool = False


@dataclass(frozen=True)
class DeviceState:
    present: bool = False
    connected: bool = False
    connecting: bool = False
    paired: bool = False
    known: bool = False
    name: str | None = None
    model: str | None = None
    firmware: str | None = None
    battery: BatteryState = field(default_factory=BatteryState)
    in_ear: Pair = field(default_factory=Pair)
    in_case: Pair = field(default_factory=Pair)
    lid: str = "unknown"  # open | closed | unknown
    mode: str | None = None
    conversation_awareness: bool | None = None
    adaptive_level: int | None = None
    # internal, not serialized
    primary_left: bool | None = None
    ear_precise: bool = False


def apply_advert(state: DeviceState, adv: Advert, precise: Precise | None = None) -> DeviceState:
    """`precise` (decrypted payload) gives exact battery without a connection; AAP still wins."""
    if not adv.paired:
        return replace(state, present=True, model=adv.model)
    changes: dict = {"present": True, "model": adv.model, "primary_left": adv.primary_left}
    if state.connected and state.battery.precise:
        pass
    elif precise is not None:
        changes["battery"] = BatteryState(
            left=Level(precise.left, precise.left_charging),
            right=Level(precise.right, precise.right_charging),
            case=Level(precise.case, precise.case_charging),
            precise=True,
        )
    else:
        changes["battery"] = BatteryState(
            left=Level(adv.left, bool(adv.left_charging)),
            right=Level(adv.right, bool(adv.right_charging)),
            case=Level(adv.case, bool(adv.case_charging)),
            precise=False,
        )
    if not (state.connected and state.ear_precise):
        changes["in_ear"] = Pair(bool(adv.left_in_ear), bool(adv.right_in_ear))
        changes["ear_precise"] = False
    changes["lid"] = ("open" if adv.lid_open else "closed") if adv.lid_known else "unknown"
    return replace(state, **changes)


def _level(old: Level, comp: aap.Component | None) -> Level:
    if comp is None:
        return old
    return Level(comp.level, comp.status == "charging")


def apply_aap(state: DeviceState, event: aap.AapEvent) -> DeviceState:
    match event:
        case aap.Battery(left=l, right=r, case=c):
            b = state.battery
            return replace(state, battery=BatteryState(_level(b.left, l), _level(b.right, r), _level(b.case, c), True))
        case aap.Ear(primary=p, secondary=s):
            # unknown primary side: assume right (PROTOCOL.md 2.3)
            left, right = (p, s) if state.primary_left else (s, p)
            return replace(
                state,
                in_ear=Pair(left == "in-ear", right == "in-ear"),
                in_case=Pair(left == "in-case", right == "in-case"),
                ear_precise=True,
            )
        case aap.Mode(mode=m):
            return replace(state, mode=m)
        case aap.ConversationAwareness(on=on):
            return replace(state, conversation_awareness=on)
        case aap.AdaptiveLevel(level=n):
            return replace(state, adaptive_level=n)
        case aap.DeviceInfo(name=name, firmware=fw):
            return replace(state, name=name or state.name, firmware=fw or state.firmware)
    return state


def to_dict(state: DeviceState) -> dict:
    s, b = state, state.battery
    level = lambda x: {"level": x.level, "charging": x.charging}  # noqa: E731
    return {
        "type": "state",
        "device": {
            "present": s.present,
            "connected": s.connected,
            "connecting": s.connecting,
            "paired": s.paired,
            "known": s.known,
            "name": s.name,
            "model": s.model,
            "firmware": s.firmware,
            "battery": {"left": level(b.left), "right": level(b.right), "case": level(b.case), "precise": b.precise},
            "inEar": {"left": s.in_ear.left, "right": s.in_ear.right},
            "inCase": {"left": s.in_case.left, "right": s.in_case.right},
            "lid": s.lid,
            "mode": s.mode,
            "conversationAwareness": s.conversation_awareness,
            "adaptiveLevel": s.adaptive_level,
        },
    }


def to_json(state: DeviceState) -> str:
    return json.dumps(to_dict(state), separators=(",", ":"))


def event_json(name: str) -> str:
    return json.dumps({"type": "event", "name": name}, separators=(",", ":"))
