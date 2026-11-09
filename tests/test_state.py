import json
from dataclasses import replace

from podglass import aap
from podglass.adv import Advert
from podglass.state import BatteryState, DeviceState, Level, Pair, apply_aap, apply_advert, event_json, to_json


def advert(**kw):
    base = dict(addr="70:81:94:0D:FB:AA", rssi=-50, model="pro2-usbc", paired=True, primary_left=True,
                left=80, right=70, case=60, left_charging=False, right_charging=False, case_charging=True,
                left_in_ear=True, right_in_ear=False, lid_open=True, lid_known=True, lid_counter=1, conn_state=0)
    base.update(kw)
    return Advert(**base)


BATTERY = aap.Battery(left=aap.Component(82, "discharging"), right=aap.Component(81, "charging"),
                      case=aap.Component(64, "discharging"))


def test_advert_fills_coarse_state():
    s = apply_advert(DeviceState(), advert())
    assert s.present and s.model == "pro2-usbc" and s.lid == "open"
    assert s.battery == BatteryState(Level(80), Level(70), Level(60, True), precise=False)
    assert s.in_ear == Pair(True, False)


def test_advert_lid_closed_and_unknown():
    assert apply_advert(DeviceState(), advert(lid_open=False)).lid == "closed"
    assert apply_advert(DeviceState(), advert(lid_known=False)).lid == "unknown"


def test_pairing_mode_advert_only_marks_present():
    s = apply_advert(DeviceState(), Advert(addr="x", rssi=-40, model="pro2-usbc", paired=False))
    assert s.present and s.model == "pro2-usbc" and s.battery == BatteryState()


def test_aap_battery_is_precise():
    s = apply_aap(DeviceState(connected=True), BATTERY)
    assert s.battery == BatteryState(Level(82), Level(81, True), Level(64), precise=True)


def test_aap_battery_wins_over_ble_while_connected():
    s = apply_aap(DeviceState(connected=True), BATTERY)
    s = apply_advert(s, advert())
    assert s.battery.precise and s.battery.left == Level(82)


def test_ble_battery_used_again_after_disconnect():
    s = apply_aap(DeviceState(connected=True), BATTERY)
    s = apply_advert(replace(s, connected=False), advert())
    assert not s.battery.precise and s.battery.left == Level(80)


def test_ble_battery_used_while_connected_until_aap_reports():
    s = apply_advert(DeviceState(connected=True), advert())
    assert s.battery.left == Level(80) and not s.battery.precise


def test_partial_aap_battery_keeps_other_parts():
    s = apply_aap(DeviceState(connected=True), BATTERY)
    s = apply_aap(s, aap.Battery(case=aap.Component(None, "disconnected")))
    assert s.battery.left == Level(82) and s.battery.case == Level(None)


def test_aap_ear_maps_primary_side():
    s = apply_advert(DeviceState(connected=True), advert(primary_left=True))
    s = apply_aap(s, aap.Ear("in-ear", "in-case"))
    assert s.in_ear == Pair(True, False) and s.in_case == Pair(False, True)
    s = replace(s, primary_left=False)
    s = apply_aap(s, aap.Ear("in-ear", "in-case"))
    assert s.in_ear == Pair(False, True) and s.in_case == Pair(True, False)


def test_aap_ear_unknown_primary_assumes_right():
    s = apply_aap(DeviceState(), aap.Ear("in-ear", "out"))
    assert s.in_ear == Pair(False, True)


def test_aap_ear_wins_over_ble_while_connected():
    s = apply_aap(DeviceState(connected=True, primary_left=True), aap.Ear("out", "out"))
    s = apply_advert(s, advert(left_in_ear=True))
    assert s.in_ear == Pair(False, False)


def test_settings_and_device_info():
    s = DeviceState()
    for ev in (aap.Mode("anc"), aap.ConversationAwareness(True), aap.AdaptiveLevel(50),
               aap.DeviceInfo("AirPods Pro", "A3047", "7A305"), aap.CaVolume(1), aap.Ack("features")):
        s = apply_aap(s, ev)
    assert (s.mode, s.conversation_awareness, s.adaptive_level, s.name, s.firmware) == (
        "anc", True, 50, "AirPods Pro", "7A305")


def test_golden_json():
    s = DeviceState(present=True, connected=True, paired=True, known=True, name="AirPods Pro",
                    model="pro2-usbc", firmware="7A305",
                    battery=BatteryState(Level(82), Level(80), Level(64, True), precise=True),
                    in_ear=Pair(True, True), lid="open", mode="anc",
                    conversation_awareness=True, adaptive_level=50)
    assert json.loads(to_json(s)) == {
        "type": "state",
        "device": {
            "present": True, "connected": True, "connecting": False, "paired": True, "known": True,
            "name": "AirPods Pro", "model": "pro2-usbc", "firmware": "7A305",
            "battery": {
                "left": {"level": 82, "charging": False},
                "right": {"level": 80, "charging": False},
                "case": {"level": 64, "charging": True},
                "precise": True,
            },
            "inEar": {"left": True, "right": True},
            "inCase": {"left": False, "right": False},
            "lid": "open", "mode": "anc", "conversationAwareness": True, "adaptiveLevel": 50,
        },
    }
    assert "\n" not in to_json(s)


def test_event_json():
    assert json.loads(event_json("lid-opened")) == {"type": "event", "name": "lid-opened"}
