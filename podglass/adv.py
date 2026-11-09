"""Parser for the Apple proximity pairing advertisement (pure). See docs/PROTOCOL.md 1."""

from dataclasses import dataclass

MODELS = {
    0x2420: "pro2-usbc",
    0x1420: "pro2-lightning",
    0x0E20: "pro1",
    0x0F20: "airpods2",
    0x1320: "airpods3",
    0x1920: "airpods4",
    0x1B20: "airpods4-anc",
    0x0A20: "max",
    0x1F20: "max",
}

PAIRED_LEN = 11  # offsets 0..10 of the paired layout
ENCRYPTED_LEN = 16


@dataclass(frozen=True)
class Advert:
    addr: str
    rssi: int
    model: str
    paired: bool
    primary_left: bool | None = None
    left: int | None = None  # percent in steps of 10, None = unknown / not in reach
    right: int | None = None
    case: int | None = None
    left_charging: bool | None = None
    right_charging: bool | None = None
    case_charging: bool | None = None
    left_in_ear: bool | None = None
    right_in_ear: bool | None = None
    lid_open: bool | None = None
    lid_known: bool | None = None  # lid bit is meaningful only when the broadcasting pod is in the case
    lid_counter: int | None = None
    conn_state: int | None = None
    encrypted: bytes | None = None  # last 16 bytes, see crypto.decrypt_payload


def model_name(model_id: int) -> str:
    return MODELS.get(model_id, f"unknown-{model_id:04x}")


def _level(nibble: int) -> int | None:
    return None if nibble == 15 else min(nibble * 10, 100)


def parse_advert(data: bytes, rssi: int, addr: str) -> Advert | None:
    """Parse the manufacturer payload after the 0x004C company id. None if it is not ours."""
    if len(data) < 5 or data[0] != 0x07:
        return None
    model = model_name(data[3] << 8 | data[4])
    if data[2] == 0x00:
        return Advert(addr=addr, rssi=rssi, model=model, paired=False)
    if data[2] != 0x01 or len(data) < PAIRED_LEN:
        return None

    s = data[5]
    primary_left = bool(s & 0x20)
    flipped = not primary_left
    this_in_case = bool(s & 0x40)

    hi, lo = (data[6] >> 4) & 0xF, data[6] & 0xF
    left_nib, right_nib = (hi, lo) if flipped else (lo, hi)

    flags = (data[7] >> 4) & 0xF
    if flipped:
        left_charging, right_charging = flags & 0x02, flags & 0x01
    else:
        left_charging, right_charging = flags & 0x01, flags & 0x02

    if flipped != this_in_case:
        left_in_ear, right_in_ear = s & 0x08, s & 0x02
    else:
        left_in_ear, right_in_ear = s & 0x02, s & 0x08

    return Advert(
        addr=addr,
        rssi=rssi,
        model=model,
        paired=True,
        primary_left=primary_left,
        left=_level(left_nib),
        right=_level(right_nib),
        case=_level(data[7] & 0xF),
        left_charging=bool(left_charging),
        right_charging=bool(right_charging),
        case_charging=bool(flags & 0x04),
        left_in_ear=bool(left_in_ear),
        right_in_ear=bool(right_in_ear),
        # VERIFY in P0.3: which value of bit 3 means open
        lid_open=((data[8] >> 3) & 0x01) == 0,
        lid_known=this_in_case,
        lid_counter=data[8] & 0x07,
        conn_state=data[10],
        encrypted=bytes(data[-ENCRYPTED_LEN:]) if len(data) >= PAIRED_LEN + ENCRYPTED_LEN else None,
    )
