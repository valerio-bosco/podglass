import json
import logging
import stat

from podglass.keys import DeviceKeys, add_device, default_path, load_keys, save_keys

K = DeviceKeys(irk=bytes(range(16)), enc_key=bytes(range(16, 32)), model="pro2-usbc", name="AirPods Pro")


def test_round_trip_and_mode(tmp_path):
    p = tmp_path / "state" / "podglass" / "keys.json"
    save_keys({"aa:bb:cc:dd:ee:ff": K}, p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert stat.S_IMODE(p.parent.stat().st_mode) == 0o700
    assert load_keys(p) == {"AA:BB:CC:DD:EE:FF": K}
    assert [f.name for f in p.parent.iterdir()] == ["keys.json"]  # no temp file left


def test_add_device_keeps_others(tmp_path):
    p = tmp_path / "keys.json"
    add_device("11:22:33:44:55:66", K, p)
    add_device("AA:BB:CC:DD:EE:FF", K, p)
    assert set(load_keys(p)) == {"11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"}


def test_missing_file_is_empty(tmp_path):
    assert load_keys(tmp_path / "keys.json") == {}


def test_broken_file_and_entries(tmp_path, caplog):
    p = tmp_path / "keys.json"
    p.write_text("{not json")
    with caplog.at_level(logging.WARNING):
        assert load_keys(p) == {}
    p.write_text(json.dumps({
        "AA:AA:AA:AA:AA:AA": {"irk": "00" * 16, "enc_key": "11" * 16},
        "BB:BB:BB:BB:BB:BB": {"irk": "zz"},
        "CC:CC:CC:CC:CC:CC": {"irk": "00" * 15, "enc_key": "11" * 16},
        "DD:DD:DD:DD:DD:DD": "nope",
    }))
    assert list(load_keys(p)) == ["AA:AA:AA:AA:AA:AA"]


def test_default_path_uses_xdg_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert default_path() == tmp_path / "podglass" / "keys.json"
