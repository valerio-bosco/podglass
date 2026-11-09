import pytest

from podglass.crypto import ah, decrypt_payload, resolve_rpa

# Bluetooth Core Spec Vol 3, Part H, D.7
IRK = bytes.fromhex("ec0234a357c8ad05341010a60a397d9b")
PRAND = bytes.fromhex("708194")
HASH = bytes.fromhex("0dfbaa")
RPA = "70:81:94:0D:FB:AA"


def test_ah_core_spec_vector():
    assert ah(IRK, PRAND) == HASH


def test_resolve_rpa_matches():
    assert resolve_rpa(RPA, IRK)
    assert resolve_rpa(RPA.lower(), IRK)


def test_resolve_rpa_reversed_irk_also_matches():
    assert resolve_rpa(RPA, IRK[::-1])


def test_resolve_rpa_wrong_hash():
    assert not resolve_rpa("70:81:94:0D:FB:AB", IRK)


def test_resolve_rpa_wrong_irk():
    assert not resolve_rpa(RPA, bytes(16))


@pytest.mark.parametrize("addr", ["30:81:94:0D:FB:AA", "F0:81:94:0D:FB:AA", "B0:81:94:0D:FB:AA"])
def test_non_rpa_address_is_false(addr):
    # top two bits must be 0b01 for an RPA
    assert not resolve_rpa(addr, IRK)


@pytest.mark.parametrize("addr", ["", "70:81:94:0D:FB", "70:81:94:0D:FB:ZZ", "708194:0D:FB:AA", "70-81-94-0D-FB-AA"])
def test_malformed_address_is_false(addr):
    assert not resolve_rpa(addr, IRK)


@pytest.mark.parametrize("key", [b"", bytes(15), bytes(17), bytes(32)])
def test_wrong_key_sizes_raise(key):
    with pytest.raises(ValueError):
        ah(key, PRAND)
    with pytest.raises(ValueError):
        resolve_rpa(RPA, key)
    with pytest.raises(ValueError):
        decrypt_payload(bytes(16), key)


def test_ah_wrong_prand_size_raises():
    with pytest.raises(ValueError):
        ah(IRK, bytes(4))


def test_decrypt_payload_inverts_cbc_encrypt():
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = bytes(range(16))
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    enc = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).encryptor()
    payload = enc.update(plain) + enc.finalize()
    assert decrypt_payload(payload, key) == plain


@pytest.mark.parametrize("payload", [b"", bytes(15), bytes(17)])
def test_decrypt_payload_wrong_length_is_none(payload):
    assert decrypt_payload(payload, bytes(16)) is None
