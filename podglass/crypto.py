"""RPA resolution and payload decryption (pure). See docs/PROTOCOL.md 1.1 and 1.3."""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _aes(key: bytes, mode, data: bytes, decrypt: bool = False) -> bytes:
    cipher = Cipher(algorithms.AES(key), mode)
    ctx = cipher.decryptor() if decrypt else cipher.encryptor()
    return ctx.update(data) + ctx.finalize()


def _check_key(key: bytes, name: str) -> None:
    if len(key) != 16:
        raise ValueError(f"{name} must be 16 bytes, got {len(key)}")


def ah(irk: bytes, prand: bytes) -> bytes:
    """Bluetooth Core Spec random address hash: AES(irk, 13 zero bytes || prand), last 3 bytes.

    Values are most significant byte first, as printed in the spec and in "AA:BB:..." addresses.
    """
    _check_key(irk, "irk")
    if len(prand) != 3:
        raise ValueError(f"prand must be 3 bytes, got {len(prand)}")
    return _aes(irk, modes.ECB(), bytes(13) + prand)[-3:]


def _parse_addr(addr: str) -> bytes | None:
    parts = addr.split(":")
    if len(parts) != 6 or any(len(p) != 2 for p in parts):
        return None
    try:
        return bytes(int(p, 16) for p in parts)
    except ValueError:
        return None


def resolve_rpa(addr: str, irk: bytes) -> bool:
    """True if `addr` ("AA:BB:CC:DD:EE:FF") is a resolvable private address made with `irk`.

    The byte order of the IRK sent by the AirPods over AAP is not verified yet (P0.4), so both
    orders are tried. A false match needs a 24-bit hash collision.
    """
    _check_key(irk, "irk")
    raw = _parse_addr(addr)
    if raw is None or raw[0] >> 6 != 0b01:
        return False
    prand, hash_ = raw[:3], raw[3:]
    return ah(irk, prand) == hash_ or ah(irk[::-1], prand) == hash_


def decrypt_payload(payload16: bytes, key: bytes) -> bytes | None:
    """AES-128-CBC decrypt with a zero IV (key used as is). None if the payload is not 16 bytes."""
    _check_key(key, "key")
    if len(payload16) != 16:
        return None
    return _aes(key, modes.CBC(bytes(16)), payload16, decrypt=True)
