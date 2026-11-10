"""BLE scanner yielding adverts of our AirPods. See docs/PROTOCOL.md 1 and docs/SPIKE.md.

`Classifier` is pure (tests feed it bytes); `scan()` wires it to bleak. Strategy from P0.5:
passive scan through the BlueZ advertisement monitor, always on; active scan only when the
monitor API is missing.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from .adv import Advert, Precise, parse_advert, parse_precise
from .crypto import decrypt_payload, resolve_rpa
from .keys import DeviceKeys

log = logging.getLogger(__name__)

APPLE = 0x004C
DEDUPE_S = 1.0  # the same payload from the same address within this time is dropped
UNKNOWN_RSSI = -60  # without keys, only this close AirPods count as "probably mine"
RPA_CACHE_MAX = 256


@dataclass(frozen=True)
class Seen:
    adv: Advert
    known: bool  # resolved with our IRK
    precise: Precise | None = None  # decrypted payload, only when known
    device: str | None = None  # public MAC from keys.json, only when known


class Classifier:
    """Decides which adverts are ours and decrypts them. No I/O."""

    def __init__(self, keys: dict[str, DeviceKeys]):
        self.keys = keys
        self._rpa: dict[str, str | None] = {}  # rotating address -> public MAC (None = not ours)
        self._last: dict[str, tuple[bytes, float]] = {}

    def _owner(self, addr: str) -> str | None:
        addr = addr.upper()
        if addr not in self._rpa:
            if len(self._rpa) >= RPA_CACHE_MAX:
                self._rpa.clear()
            self._rpa[addr] = next((mac for mac, k in self.keys.items() if resolve_rpa(addr, k.irk)), None)
        return self._rpa[addr]

    def classify(self, addr: str, payload: bytes, rssi: int, now: float) -> Seen | None:
        if not payload or payload[0] != 0x07:
            return None
        last = self._last.get(addr)
        if last and last[0] == payload and now - last[1] < DEDUPE_S:
            return None
        self._last[addr] = (payload, now)

        adv = parse_advert(payload, rssi, addr)
        if adv is None:
            return None
        if not adv.paired:  # pairing mode: anybody's, the policy decides by RSSI
            return Seen(adv, known=False)
        if not self.keys:  # no keys yet: close enough Pro 2 count as "probably mine"
            if adv.model.startswith("pro2") and rssi > UNKNOWN_RSSI:
                return Seen(adv, known=False)
            return None
        owner = self._owner(addr)
        if owner is None:
            return None  # somebody else's AirPods
        precise = None
        if adv.encrypted is not None and adv.primary_left is not None:
            plain = decrypt_payload(adv.encrypted, self.keys[owner].enc_key)
            precise = parse_precise(plain, adv.primary_left) if plain else None
        return Seen(adv, known=True, precise=precise, device=owner)


async def scan(keys: dict[str, DeviceKeys], mode: str = "passive") -> AsyncIterator[Seen]:
    """Yield `Seen` for our AirPods (and pairing-mode AirPods) until cancelled."""
    from bleak import BleakScanner
    from bleak.args.bluez import AdvertisementDataType, OrPattern

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Seen] = asyncio.Queue(maxsize=256)
    classifier = Classifier(keys)

    def on_advert(device, data) -> None:
        payload = data.manufacturer_data.get(APPLE)
        if not payload:
            return
        seen = classifier.classify(device.address, payload, data.rssi, loop.time())
        if seen is not None and not queue.full():
            queue.put_nowait(seen)

    pattern = OrPattern(0, AdvertisementDataType.MANUFACTURER_SPECIFIC_DATA, b"\x4c\x00\x07")
    scanner = None
    if mode == "passive":
        try:
            scanner = BleakScanner(on_advert, scanning_mode="passive", bluez={"or_patterns": [pattern]})
            await scanner.start()
        except Exception as e:  # monitor API missing: BlueZ Experimental is off
            log.warning("passive scan unavailable (%s), using active scan", e)
            scanner = None
    if scanner is None:
        scanner = BleakScanner(on_advert)
        await scanner.start()
    try:
        while True:
            yield await queue.get()
    finally:
        await scanner.stop()


async def debug(seconds: float = 20) -> int:
    """`podglass debug scan`: print what the scanner yields."""
    from .keys import load_keys

    keys = load_keys()
    print(f"{len(keys)} device(s) in keys.json; scanning {seconds:.0f} s")

    async def run():
        async for s in scan(keys):
            a, p = s.adv, s.precise
            bat = (f"L{p.left} R{p.right} case {p.case} busy={p.busy} host={p.host_tail.hex()}"
                   if p else f"~L{a.left} R{a.right} case {a.case}")
            lid = "?" if not a.lid_known else ("open" if a.lid_open else "closed")
            print(f"{'mine' if s.known else 'other':5} {a.addr} {a.rssi:>4} {a.model} lid={lid} "
                  f"ear L={a.left_in_ear} R={a.right_in_ear} {bat}")

    try:
        await asyncio.wait_for(run(), seconds)
    except asyncio.TimeoutError:
        pass
    return 0
