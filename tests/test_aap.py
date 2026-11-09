import random

import pytest

from podglass import aap
from podglass.aap import (
    Ack, AdaptiveLevel, Battery, CaVolume, Component, ConversationAwareness, DeviceInfo, Ear, Keys,
    Mode, Unknown, parse_packet,
)

h = bytes.fromhex


def test_startup_packets_match_protocol():
    assert aap.HANDSHAKE == h("00 00 04 00 01 00 02 00 00 00 00 00 00 00 00 00")
    assert aap.FEATURES == h("04 00 04 00 4D 00 FF 00 00 00 00 00 00 00")
    assert aap.NOTIFICATIONS == h("04 00 04 00 0F 00 FF FF FF FF")
    assert aap.request_keys() == h("04 00 04 00 30 00 05 00")


def test_acks():
    assert parse_packet(h("01 00 04 00 00 00 00 00")) == Ack("handshake")
    assert parse_packet(h("04 00 04 00 2B 00 01 02")) == Ack("features")


def test_battery_example():
    pkt = h("04 00 04 00 04 00 03 02 01 64 02 01 04 01 63 01 01 08 01 11 02 01")
    assert parse_packet(pkt) == Battery(
        left=Component(99, "charging"),
        right=Component(100, "discharging"),
        case=Component(17, "discharging"),
    )


def test_battery_missing_pod_and_partial_packet():
    pkt = h("04 00 04 00 04 00 02 04 01 00 04 01 08 01 32 00 01")
    assert parse_packet(pkt) == Battery(left=Component(None, "disconnected"), case=Component(50, "unknown"))


def test_battery_truncated_is_unknown():
    pkt = h("04 00 04 00 04 00 03 02 01 64 02 01")
    assert isinstance(parse_packet(pkt), Unknown)


@pytest.mark.parametrize("p,s,expected", [
    (0x00, 0x01, Ear("in-ear", "out")),
    (0x02, 0x00, Ear("in-case", "in-ear")),
    (0x07, 0x02, Ear("unknown", "in-case")),
])
def test_ear(p, s, expected):
    assert parse_packet(h("04 00 04 00 06 00") + bytes([p, s])) == expected


@pytest.mark.parametrize("mode,byte", [("off", 0x01), ("anc", 0x02), ("transparency", 0x03), ("adaptive", 0x04)])
def test_mode_round_trip(mode, byte):
    pkt = aap.set_mode(mode)
    assert pkt == h("04 00 04 00 09 00 0D") + bytes([byte]) + h("00 00 00")
    assert parse_packet(pkt) == Mode(mode)


def test_unknown_mode_value():
    assert parse_packet(h("04 00 04 00 09 00 0D 09 00 00 00")) == Mode(None)


def test_set_mode_rejects_unknown():
    with pytest.raises(ValueError):
        aap.set_mode("loud")


@pytest.mark.parametrize("on", [True, False])
def test_ca_round_trip(on):
    pkt = aap.set_ca(on)
    assert pkt == h("04 00 04 00 09 00 28") + bytes([0x01 if on else 0x02]) + h("00 00 00")
    assert parse_packet(pkt) == ConversationAwareness(on)


@pytest.mark.parametrize("n", [0, 50, 100])
def test_adaptive_level_round_trip(n):
    pkt = aap.set_adaptive_level(n)
    assert pkt == h("04 00 04 00 09 00 2E") + bytes([n]) + h("00 00 00")
    assert parse_packet(pkt) == AdaptiveLevel(n)


@pytest.mark.parametrize("n", [-1, 101])
def test_adaptive_level_out_of_range(n):
    with pytest.raises(ValueError):
        aap.set_adaptive_level(n)


def test_other_control_setting_is_unknown():
    assert parse_packet(h("04 00 04 00 09 00 1A 0F 00 00 00")) == Unknown(0x09, h("04 00 04 00 09 00 1A 0F 00 00 00"))


@pytest.mark.parametrize("level,speaking", [(1, True), (2, True), (3, False), (8, False), (9, False)])
def test_ca_volume(level, speaking):
    ev = parse_packet(h("04 00 04 00 4B 00 02 00 01") + bytes([level]))
    assert ev == CaVolume(level) and ev.speaking is speaking


IRK = bytes(range(16))
ENC = bytes(range(16, 32))
KEYS_PKT = h("04 00 04 00 31 00 02") + h("01 00 10 00") + IRK + h("04 00 10 00") + ENC


def test_keys():
    assert len(KEYS_PKT) == 47
    assert parse_packet(KEYS_PKT) == Keys(irk=IRK, enc_key=ENC)


def test_keys_wrong_length_rejected():
    bad = h("04 00 04 00 31 00 02") + h("01 00 0F 00") + IRK[:15] + h("04 00 10 00") + ENC + b"\x00"
    assert isinstance(parse_packet(bad), Unknown)


def test_keys_short_rejected():
    assert isinstance(parse_packet(KEYS_PKT[:40]), Unknown)


def test_device_info():
    pkt = h("04 00 04 00 1D 00") + b"AirPods Pro\x00A3047\x00Apple Inc.\x00XYZ123\x007A305\x00"
    assert parse_packet(pkt) == DeviceInfo(name="AirPods Pro", model_number="A3047", firmware="7A305")


def test_unknown_opcode():
    assert parse_packet(h("04 00 04 00 77 00 01")) == Unknown(0x77, h("04 00 04 00 77 00 01"))


@pytest.mark.parametrize("pkt", [b"", h("04 00 04"), h("05 00 04 00 04 00"), h("04 00 04 00 06 00 00")])
def test_not_aap_or_truncated(pkt):
    ev = parse_packet(pkt)
    assert ev is None or isinstance(ev, Unknown)


def test_garbage_never_raises():
    rnd = random.Random(2)
    for _ in range(5000):
        tail = bytes(rnd.randrange(256) for _ in range(rnd.randrange(60)))
        op = bytes([rnd.choice([0x04, 0x06, 0x09, 0x1D, 0x2B, 0x31, 0x4B, 0x00]), 0x00])
        parse_packet(aap.HEADER + op + tail)
        parse_packet(tail)
