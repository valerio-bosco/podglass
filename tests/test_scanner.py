from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from podglass.crypto import ah
from podglass.keys import DeviceKeys
from podglass.scanner import Classifier

IRK = bytes.fromhex("ec0234a357c8ad05341010a60a397d9b")
ENC = bytes(range(16))
MAC = "2C:32:6A:BC:8F:5D"
KEYS = {MAC: DeviceKeys(irk=IRK, enc_key=ENC)}


def rpa(prand=bytes.fromhex("708194")):
    return ":".join(f"{b:02X}" for b in prand + ah(IRK, prand))


def encrypt(plain: bytes) -> bytes:
    e = Cipher(algorithms.AES(ENC), modes.CBC(bytes(16))).encryptor()
    return e.update(plain) + e.finalize()


# real header from tests/fixtures/adv/case-closed.jsonl (status 0x75: primary left, both in case)
PLAIN = bytes.fromhex("04b5ac01c82000bc8f5d000341cebc33")
HEADER = bytes.fromhex("07190114207545b05b0004")


def payload(header=HEADER):
    return header + encrypt(PLAIN)


def test_my_advert_is_known_and_decrypted():
    s = Classifier(KEYS).classify(rpa(), payload(), -60, 0)
    assert s.known and s.device == MAC
    assert (s.precise.left, s.precise.right, s.precise.case) == (53, 44, 1)
    assert s.precise.host_tail == bytes.fromhex("c82000")
    assert s.adv.lid_known and not s.adv.lid_open


def test_other_people_airpods_are_dropped():
    assert Classifier(KEYS).classify("7A:29:46:20:8B:2A", payload(), -40, 0) is None


def test_dedupe_within_one_second():
    c = Classifier(KEYS)
    assert c.classify(rpa(), payload(), -60, 0) is not None
    assert c.classify(rpa(), payload(), -61, 0.5) is None
    assert c.classify(rpa(), payload(), -61, 1.2) is not None


def test_pairing_mode_always_passes():
    pairing = bytes([0x07, 0x19, 0x00, 0x14, 0x20]) + bytes(22)
    s = Classifier(KEYS).classify("11:22:33:44:55:66", pairing, -40, 0)
    assert s is not None and not s.known and not s.adv.paired


def test_without_keys_only_close_pro2_count():
    c = Classifier({})
    assert c.classify("7A:29:46:20:8B:2A", payload(), -50, 0).known is False
    assert c.classify("7A:29:46:20:8B:2B", payload(), -75, 0) is None


def test_garbage_is_ignored():
    c = Classifier(KEYS)
    assert c.classify(rpa(), b"", -50, 0) is None
    assert c.classify(rpa(), b"\x10\x05", -50, 0) is None
    assert c.classify(rpa(), b"\x07\x01", -50, 0) is None
