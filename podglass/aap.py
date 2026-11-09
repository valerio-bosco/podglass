"""AAP packet builders and parser (pure). See docs/PROTOCOL.md 2."""

from dataclasses import dataclass

HEADER = bytes.fromhex("04000400")
HANDSHAKE = bytes.fromhex("00000400010002000000000000000000")
FEATURES = bytes.fromhex("040004004d00ff00000000000000")
NOTIFICATIONS = bytes.fromhex("040004000f00ffffffff")
REQUEST_KEYS = bytes.fromhex("0400040030000500")
HANDSHAKE_ACK_PREFIX = bytes.fromhex("01000400")

OP_BATTERY = 0x0004
OP_EAR = 0x0006
OP_CONTROL = 0x0009
OP_DEVICE_INFO = 0x001D
OP_FEATURES_ACK = 0x002B
OP_KEYS = 0x0031
OP_CA_VOLUME = 0x004B

SETTING_MODE = 0x0D
SETTING_CA = 0x28
SETTING_ADAPTIVE_LEVEL = 0x2E

MODES = {"off": 0x01, "anc": 0x02, "transparency": 0x03, "adaptive": 0x04}
MODE_NAMES = {v: k for k, v in MODES.items()}

COMPONENTS = {0x04: "left", 0x02: "right", 0x08: "case"}
BATTERY_STATUS = {0x00: "unknown", 0x01: "charging", 0x02: "discharging", 0x04: "disconnected"}
EAR = {0x00: "in-ear", 0x01: "out", 0x02: "in-case"}


# --- events ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Component:
    level: int | None  # None when the pod is missing
    status: str  # unknown | charging | discharging | disconnected


@dataclass(frozen=True)
class Battery:
    left: Component | None = None  # None = not in this packet
    right: Component | None = None
    case: Component | None = None


@dataclass(frozen=True)
class Ear:
    primary: str  # in-ear | out | in-case | unknown
    secondary: str


@dataclass(frozen=True)
class Mode:
    mode: str | None  # off | anc | transparency | adaptive, None = unknown value


@dataclass(frozen=True)
class ConversationAwareness:
    on: bool


@dataclass(frozen=True)
class AdaptiveLevel:
    level: int


@dataclass(frozen=True)
class CaVolume:
    level: int

    @property
    def speaking(self) -> bool:
        return self.level in (0x01, 0x02)


@dataclass(frozen=True)
class Keys:
    irk: bytes
    enc_key: bytes


@dataclass(frozen=True)
class DeviceInfo:
    name: str | None
    model_number: str | None
    firmware: str | None


@dataclass(frozen=True)
class Ack:
    kind: str  # handshake | features


@dataclass(frozen=True)
class Unknown:
    opcode: int | None
    raw: bytes


AapEvent = Battery | Ear | Mode | ConversationAwareness | AdaptiveLevel | CaVolume | Keys | DeviceInfo | Ack | Unknown


# --- builders -------------------------------------------------------------------------------

def _control(setting: int, value: int) -> bytes:
    return HEADER + bytes([0x09, 0x00, setting, value, 0x00, 0x00, 0x00])


def set_mode(mode: str) -> bytes:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    return _control(SETTING_MODE, MODES[mode])


def set_ca(on: bool) -> bytes:
    return _control(SETTING_CA, 0x01 if on else 0x02)


def set_adaptive_level(n: int) -> bytes:
    if not 0 <= n <= 100:
        raise ValueError(f"adaptive level must be 0..100, got {n}")
    return _control(SETTING_ADAPTIVE_LEVEL, n)


def request_keys() -> bytes:
    return REQUEST_KEYS


# --- parser ---------------------------------------------------------------------------------

def _battery(b: bytes, raw: bytes) -> AapEvent:
    if len(b) < 7:
        return Unknown(OP_BATTERY, raw)
    count = b[6]
    if len(b) < 7 + 5 * count:
        return Unknown(OP_BATTERY, raw)
    parts: dict[str, Component] = {}
    for i in range(count):
        comp, _, level, status, _ = b[7 + 5 * i: 12 + 5 * i]
        name = COMPONENTS.get(comp)
        if name is None:
            continue
        status_name = BATTERY_STATUS.get(status, "unknown")
        ok = status_name != "disconnected" and level <= 100
        parts[name] = Component(level if ok else None, status_name)
    return Battery(**parts)


def _control_event(b: bytes, raw: bytes) -> AapEvent:
    if len(b) < 8:
        return Unknown(OP_CONTROL, raw)
    setting, value = b[6], b[7]
    if setting == SETTING_MODE:
        return Mode(MODE_NAMES.get(value))
    if setting == SETTING_CA and value in (0x01, 0x02):
        return ConversationAwareness(value == 0x01)
    if setting == SETTING_ADAPTIVE_LEVEL and value <= 100:
        return AdaptiveLevel(value)
    return Unknown(OP_CONTROL, raw)


def _keys(b: bytes, raw: bytes) -> AapEvent:
    if len(b) < 47:
        return Unknown(OP_KEYS, raw)
    found: dict[int, bytes] = {}
    i = 7
    while i + 4 <= len(b):
        kind, length = b[i], b[i + 2] | b[i + 3] << 8
        value = b[i + 4: i + 4 + length]
        if len(value) != length:
            break
        if kind in (0x01, 0x04):
            if length != 16:
                return Unknown(OP_KEYS, raw)
            found[kind] = bytes(value)
        i += 4 + length
    if 0x01 not in found or 0x04 not in found:
        return Unknown(OP_KEYS, raw)
    return Keys(irk=found[0x01], enc_key=found[0x04])


def _device_info(b: bytes) -> DeviceInfo:
    # NUL-terminated strings after some header bytes: keep the printable ones, in order.
    # VERIFY in P0.3 with a real packet.
    strings = []
    for chunk in b[6:].split(b"\x00"):
        text = chunk.decode("utf-8", errors="replace")
        if text and text.isprintable() and "�" not in text:
            strings.append(text)
    pick = lambda i: strings[i] if len(strings) > i else None  # noqa: E731
    return DeviceInfo(name=pick(0), model_number=pick(1), firmware=pick(4))


def parse_packet(b: bytes) -> AapEvent | None:
    """Parse one host-bound packet. None if it is not AAP at all; never raises."""
    raw = bytes(b)
    if raw.startswith(HANDSHAKE_ACK_PREFIX):
        return Ack("handshake")
    if len(raw) < 6 or not raw.startswith(HEADER):
        return None
    opcode = raw[4] | raw[5] << 8
    if opcode == OP_BATTERY:
        return _battery(raw, raw)
    if opcode == OP_EAR:
        if len(raw) < 8:
            return Unknown(opcode, raw)
        return Ear(EAR.get(raw[6], "unknown"), EAR.get(raw[7], "unknown"))
    if opcode == OP_CONTROL:
        return _control_event(raw, raw)
    if opcode == OP_CA_VOLUME:
        if len(raw) < 10:
            return Unknown(opcode, raw)
        return CaVolume(raw[9])
    if opcode == OP_KEYS:
        return _keys(raw, raw)
    if opcode == OP_DEVICE_INFO:
        return _device_info(raw)
    if opcode == OP_FEATURES_ACK:
        return Ack("features")
    return Unknown(opcode, raw)
