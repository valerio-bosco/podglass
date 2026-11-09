import logging

from podglass.config import Config, load_config, parse_config


def test_defaults():
    assert parse_config("") == Config(
        autoconnect="in-ear", ear_pause=True, ca_duck=True, ca_duck_volume=0.3,
        battery_widget=False, card_timeout_s=0, theme="auto")


def test_values_read():
    c = parse_config('autoconnect = "lid-open"\near_pause = false\nca_duck_volume = 0.5\ncard_timeout_s = 8\ntheme = "dark"')
    assert (c.autoconnect, c.ear_pause, c.ca_duck_volume, c.card_timeout_s, c.theme) == ("lid-open", False, 0.5, 8, "dark")


def test_unknown_key_ignored_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        c = parse_config('colour = "red"\nbattery_widget = true')
    assert c.battery_widget is True
    assert "unknown key 'colour'" in caplog.text


def test_bad_values_use_defaults(caplog):
    with caplog.at_level(logging.WARNING):
        c = parse_config('autoconnect = "always"\near_pause = "yes"\nca_duck_volume = 2\ncard_timeout_s = -1\ntheme = 3')
    assert c == Config()
    assert caplog.text.count("bad value") == 5


def test_bad_toml_uses_defaults(caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_config("autoconnect = ") == Config()
    assert caplog.text


def test_load_missing_file(tmp_path):
    assert load_config(tmp_path / "nope.toml") == Config()


def test_load_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('autoconnect = "never"\n')
    assert load_config(p).autoconnect == "never"
