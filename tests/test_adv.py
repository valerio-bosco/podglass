import json
from pathlib import Path

import pytest

from podglass.adv import parse_advert

ADDR = "70:81:94:0D:FB:AA"
ENC = bytes(range(16))


def payload(status=0x20, pods=0x89, case=0x05, lid=0x00, conn=0x00, model=0x2420, enc=ENC):
    body = bytes([0x01, model >> 8, model & 0xFF, status, pods, case, lid, 0x00, conn]) + enc
    return bytes([0x07, len(body)]) + body


def parse(data, rssi=-50):
    return parse_advert(data, rssi, ADDR)


def test_fields_passed_through():
    a = parse(payload(conn=0x0B), rssi=-42)
    assert (a.addr, a.rssi, a.model, a.paired, a.conn_state, a.encrypted) == (ADDR, -42, "pro2-usbc", True, 0x0B, ENC)


def test_primary_left_battery_and_charging():
    a = parse(payload(status=0x20, pods=0x89, case=0x15))
    assert a.primary_left is True
    assert (a.left, a.right, a.case) == (90, 80, 50)
    assert (a.left_charging, a.right_charging, a.case_charging) == (True, False, False)
    a = parse(payload(status=0x20, case=0x25))
    assert (a.left_charging, a.right_charging) == (False, True)


def test_primary_right_battery_and_charging_are_flipped():
    a = parse(payload(status=0x00, pods=0x89, case=0x15))
    assert a.primary_left is False
    assert (a.left, a.right) == (80, 90)
    assert (a.left_charging, a.right_charging) == (False, True)
    a = parse(payload(status=0x00, case=0x25))
    assert (a.left_charging, a.right_charging) == (True, False)


def test_case_charging():
    a = parse(payload(case=0x46))
    assert a.case_charging is True and a.case == 60
    assert (a.left_charging, a.right_charging) == (False, False)


@pytest.mark.parametrize("nibbles,expected", [(0xF3, (None, 30)), (0x3F, (30, None)), (0xAC, (100, 100)), (0x00, (0, 0))])
def test_battery_levels_unknown_and_clamped(nibbles, expected):
    a = parse(payload(status=0x20, pods=nibbles))
    assert (a.right, a.left) == expected


def test_case_unknown():
    assert parse(payload(case=0x0F)).case is None


@pytest.mark.parametrize(
    "status,left,right",
    [
        (0x20 | 0x02, True, False),  # primary left, out of case: no flip
        (0x20 | 0x08, False, True),
        (0x00 | 0x08, True, False),  # primary right, out of case: flip
        (0x00 | 0x02, False, True),
        (0x60 | 0x08, True, False),  # primary left, in case: flip
        (0x60 | 0x02, False, True),
        (0x40 | 0x02, True, False),  # primary right, in case: flips cancel
        (0x40 | 0x08, False, True),
        (0x20 | 0x0A, True, True),
        (0x20, False, False),
    ],
)
def test_in_ear_bits(status, left, right):
    a = parse(payload(status=status))
    assert (a.left_in_ear, a.right_in_ear) == (left, right)


def test_lid_bits():
    a = parse(payload(status=0x74, lid=0x05))
    assert (a.lid_open, a.lid_known, a.lid_counter) == (True, True, 5)
    a = parse(payload(status=0x74, lid=0x0B))
    assert (a.lid_open, a.lid_counter) == (False, 3)


def test_lid_unknown_when_broadcasting_pod_out_of_case():
    assert parse(payload(status=0x20)).lid_known is False


def test_pod_count_bits_do_not_change_other_fields():
    base = parse(payload(status=0x20))
    for bit in (0x10, 0x04):
        a = parse(payload(status=0x20 | bit))
        assert (a.left, a.right, a.left_in_ear, a.right_in_ear) == (
            base.left, base.right, base.left_in_ear, base.right_in_ear)
        assert a.lid_known is True  # a pod in the case makes the lid bit valid


def test_pairing_mode_only_model():
    a = parse(bytes([0x07, 0x19, 0x00, 0x24, 0x20]) + bytes(22))
    assert a.paired is False and a.model == "pro2-usbc"
    assert a.left is None and a.lid_open is None and a.encrypted is None


def test_unknown_model_id():
    assert parse(payload(model=0x9999)).model == "unknown-9999"


def test_without_encrypted_tail():
    a = parse(payload(enc=b""))
    assert a is not None and a.encrypted is None and a.conn_state == 0


@pytest.mark.parametrize(
    "data",
    [b"", b"\x07", bytes([0x07, 0x19, 0x01, 0x24]), payload()[:10], bytes([0x10]) + payload()[1:],
     bytes([0x07, 0x19, 0x02]) + payload()[3:]],
)
def test_short_or_foreign_input_is_none(data):
    assert parse(data) is None


def test_garbage_never_raises():
    import random

    rnd = random.Random(1)
    for _ in range(2000):
        data = bytes([0x07]) + bytes(rnd.randrange(256) for _ in range(rnd.randrange(40)))
        parse(data)


def test_fixtures_parse():
    for path in sorted(Path(__file__).parent.glob("fixtures/adv/*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                parse_advert(bytes.fromhex(rec["hex"]), rec["rssi"], rec["addr"])


def test_lid_known_while_any_pod_in_case():
    # real status bytes from tests/fixtures/adv: 0x15 both in case, 0x31 one out, 0x2b both in ears
    assert parse(payload(status=0x15)).lid_known is True
    assert parse(payload(status=0x31)).lid_known is True
    assert parse(payload(status=0x2B)).lid_known is False


def test_parse_precise_real_payloads():
    from podglass.adv import parse_precise

    # decrypted from fixtures; AAP reported left 53, right 44, case 1 at the same time
    p = parse_precise(bytes.fromhex("04b5ac01c82000bc8f5d000341cebc33"), primary_left=True)
    assert (p.left, p.right, p.case) == (53, 44, 1)
    assert (p.left_charging, p.right_charging, p.case_charging, p.busy) == (True, True, False, False)
    assert p.host_tail == bytes.fromhex("c82000")
    p = parse_precise(bytes.fromhex("04acb501c82000bc8f5d000341cebc33"), primary_left=False)
    assert (p.left, p.right) == (53, 44)
    p = parse_precise(bytes.fromhex("052c34ff6a7bb6000000071 4be3a63a7".replace(" ", "")), primary_left=False)
    assert (p.left, p.right, p.case, p.busy) == (52, 44, None, True)
    assert parse_precise(b"\x04", True) is None
