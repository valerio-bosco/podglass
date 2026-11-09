"""User settings from ~/.config/podglass/config.toml, with defaults."""

import logging
import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

log = logging.getLogger(__name__)

AUTOCONNECT = ("in-ear", "lid-open", "never")
THEMES = ("auto", "light", "dark")


@dataclass(frozen=True)
class Config:
    autoconnect: str = "in-ear"
    ear_pause: bool = True
    ca_duck: bool = True
    ca_duck_volume: float = 0.3
    battery_widget: bool = False
    card_timeout_s: float = 0  # 0 = stay while the lid is open
    theme: str = "auto"


def _valid(name: str, value) -> bool:
    if name == "autoconnect":
        return value in AUTOCONNECT
    if name == "theme":
        return value in THEMES
    if name in ("ear_pause", "ca_duck", "battery_widget"):
        return isinstance(value, bool)
    if name == "ca_duck_volume":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1
    if name == "card_timeout_s":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    return False


def parse_config(text: str) -> Config:
    """Parse TOML text. Bad syntax, unknown keys and bad values are logged and replaced by defaults."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        log.warning("config: %s, using defaults", e)
        return Config()
    known = {f.name for f in fields(Config)}
    changes = {}
    for key, value in data.items():
        if key not in known:
            log.warning("config: unknown key %r ignored", key)
        elif not _valid(key, value):
            log.warning("config: bad value %r for %r, using the default", value, key)
        else:
            changes[key] = value
    return replace(Config(), **changes)


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "podglass" / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or default_path()
    try:
        return parse_config(path.read_text())
    except FileNotFoundError:
        return Config()
