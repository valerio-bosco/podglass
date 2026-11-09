"""Per-device keys (IRK, encryption key) in $XDG_STATE_HOME/podglass/keys.json, mode 0600."""

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceKeys:
    irk: bytes
    enc_key: bytes
    model: str | None = None
    name: str | None = None


def default_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "podglass" / "keys.json"


def load_keys(path: Path | None = None) -> dict[str, DeviceKeys]:
    """Address (upper case) -> keys. Missing file: empty. Broken entries are skipped with a warning."""
    path = path or default_path()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("keys: cannot read %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        log.warning("keys: %s is not a JSON object", path)
        return {}
    out = {}
    for addr, entry in data.items():
        try:
            keys = DeviceKeys(bytes.fromhex(entry["irk"]), bytes.fromhex(entry["enc_key"]),
                              entry.get("model"), entry.get("name"))
        except (KeyError, TypeError, ValueError, AttributeError):
            log.warning("keys: broken entry for %s skipped", addr)
            continue
        if len(keys.irk) != 16 or len(keys.enc_key) != 16:
            log.warning("keys: wrong key size for %s, skipped", addr)
            continue
        out[addr.upper()] = keys
    return out


def save_keys(keys: dict[str, DeviceKeys], path: Path | None = None) -> None:
    """Write atomically: temp file with mode 0600 in the same directory, then rename."""
    path = path or default_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = {
        addr.upper(): {"irk": k.irk.hex(), "enc_key": k.enc_key.hex(), "model": k.model, "name": k.name}
        for addr, k in keys.items()
    }
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".keys-", suffix=".json")  # created 0600
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def add_device(addr: str, keys: DeviceKeys, path: Path | None = None) -> None:
    all_keys = load_keys(path)
    all_keys[addr.upper()] = keys
    save_keys(all_keys, path)
