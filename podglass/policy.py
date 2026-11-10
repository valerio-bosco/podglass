"""What to do when something happens: a pure state machine. See docs/PLAN.md 3.2.

`Policy(config).step(event, now) -> list[Action]`. No I/O: the daemon feeds events, runs the
actions, and calls `step(Tick(), now)` at `next_deadline()` for delayed actions.
"""

from dataclasses import dataclass

from .adv import Advert, Precise
from .config import Config

HIDE_DELAY_S = 1.5  # card stays this long after the lid closes
SETUP_RSSI = -55  # pairing-mode AirPods must be this close to show the setup card
SETUP_REPEAT_S = 300
USER_ACTIVE_S = 600  # a local input event this recent means the user is at this PC
RESUME_WINDOW_S = 60  # reinsert a pod within this time to resume what was paused
CONNECT_RETRY_S = 30  # no automatic connect this long after a failure
SILENCE_S = 3.0  # adverts stop when the lid closes: this much silence counts as "lid closed"


# --- inputs ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class AdvertSeen:
    adv: Advert
    known: bool  # resolved with our IRK; False = no keys yet ("probably mine") or pairing mode
    precise: Precise | None = None  # decrypted payload, only for known AirPods


@dataclass(frozen=True)
class Bluez:
    connected: bool


@dataclass(frozen=True)
class ConnectFailed:
    pass


@dataclass(frozen=True)
class EarChanged:  # from AAP, while connected
    left: bool
    right: bool


@dataclass(frozen=True)
class CaVolumeChanged:  # AAP conversation awareness level
    level: int


@dataclass(frozen=True)
class InputActivity:  # keyboard/mouse used on this PC
    pass


@dataclass(frozen=True)
class Command:  # from the UI or the CLI: connect | disconnect | dismiss-card
    name: str


@dataclass(frozen=True)
class Tick:
    pass


Event = AdvertSeen | Bluez | ConnectFailed | EarChanged | CaVolumeChanged | InputActivity | Command | Tick


# --- outputs --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    # show_card(normal|setup), hide_card, connect, disconnect, start_aap, stop_aap, show_tray,
    # hide_tray, pause_media, resume_media, duck_volume(volume), restore_volume, emit(event name)
    name: str
    arg: object = None


def emit(name: str) -> Action:
    return Action("emit", name)


class Policy:
    def __init__(self, config: Config, adapter_tail: bytes | None = None):
        # adapter_tail: last 3 bytes of this PC's Bluetooth MAC. The AirPods are "busy elsewhere"
        # when the decrypted advert names another host and says audio is streaming (GATE 0).
        self.config = config
        self.adapter_tail = adapter_tail
        self.last_advert: float | None = None  # last advert from my AirPods
        self.connected = False
        self.connecting = False
        self.card: str | None = None  # None | normal | setup
        self.lid_open: bool | None = None
        self.hide_at: float | None = None  # lid closed: hide after HIDE_DELAY_S
        self.timeout_at: float | None = None  # card_timeout_s
        self.last_input: float | None = None
        self.setup_shown_at: float | None = None
        self.retry_after = 0.0
        self.user_disconnected = False  # no autoconnect until the pods leave the ears or the lid closes
        self.ear: tuple[bool, bool] | None = None
        self.paused_at: float | None = None
        self.ducked = False

    def _silence_at(self) -> float | None:
        if self.card != "normal" or self.lid_open is not True or self.last_advert is None:
            return None
        return self.last_advert + SILENCE_S

    def next_deadline(self) -> float | None:
        times = [t for t in (self.hide_at, self.timeout_at, self._silence_at()) if t is not None]
        return min(times) if times else None

    def step(self, event: Event, now: float) -> list[Action]:
        match event:
            case AdvertSeen(adv=adv, known=known, precise=precise):
                return self._advert(adv, known, precise, now)
            case Bluez(connected=connected):
                return self._bluez(connected)
            case ConnectFailed():
                self.connecting = False
                self.retry_after = now + CONNECT_RETRY_S
                return [emit("connect-failed")]
            case EarChanged(left=left, right=right):
                return self._ear(left, right, now)
            case CaVolumeChanged(level=level):
                return self._ca(level)
            case InputActivity():
                self.last_input = now
                return []
            case Command(name=name):
                return self._command(name)
            case Tick():
                return self._tick(now)
        return []

    # --- helpers ---

    def _show(self, kind: str, now: float) -> list[Action]:
        self.card = kind
        self.hide_at = None
        self.timeout_at = now + self.config.card_timeout_s if self.config.card_timeout_s > 0 else None
        return [Action("show_card", kind)]

    def _hide(self) -> list[Action]:
        if self.card is None:
            return []
        self.card = None
        self.hide_at = self.timeout_at = None
        return [Action("hide_card")]

    def _connect(self) -> list[Action]:
        self.connecting = True
        return [Action("connect")]

    def _busy_elsewhere(self, precise: Precise | None) -> bool:
        return (precise is not None and precise.busy and self.adapter_tail is not None
                and precise.host_tail != self.adapter_tail)

    def _may_autoconnect(self, known: bool, precise: Precise | None, now: float) -> bool:
        return (known and not self.connected and not self.connecting and not self.user_disconnected
                and now >= self.retry_after and not self._busy_elsewhere(precise))

    def _user_active(self, now: float) -> bool:
        return self.last_input is not None and now - self.last_input <= USER_ACTIVE_S

    def _advert(self, adv: Advert, known: bool, precise: Precise | None, now: float) -> list[Action]:
        if not adv.paired:
            if adv.rssi > SETUP_RSSI and self.card is None and (
                    self.setup_shown_at is None or now - self.setup_shown_at >= SETUP_REPEAT_S):
                self.setup_shown_at = now
                return self._show("setup", now) + [emit("setup-available")]
            return []

        if known:
            self.last_advert = now
        out: list[Action] = []
        if adv.lid_known and adv.lid_open and self.lid_open is not True:
            self.lid_open = True
            out.append(emit("lid-opened"))
            if self.hide_at is not None:
                self.hide_at = None  # reopened before the card left: keep it
            elif self.card is None:
                out += self._show("normal", now)
            if self.config.autoconnect == "lid-open" and self._may_autoconnect(known, precise, now):
                out += self._connect()
        elif adv.lid_known and not adv.lid_open and self.lid_open is not False:
            was_open = self.lid_open
            self.lid_open = False
            self.user_disconnected = False
            if was_open:
                out.append(emit("lid-closed"))
            if self.card is not None and self.hide_at is None:
                self.hide_at = now + HIDE_DELAY_S

        in_ear = bool(adv.left_in_ear or adv.right_in_ear)
        if not in_ear:
            self.user_disconnected = False
        elif (self.config.autoconnect in ("in-ear", "lid-open") and self._user_active(now)
              and self._may_autoconnect(known, precise, now)):
            out += self._connect()
        return out

    def _bluez(self, connected: bool) -> list[Action]:
        if connected == self.connected:
            return []
        self.connected = connected
        self.connecting = False
        if connected:
            return [Action("start_aap"), Action("show_tray"), emit("connected")]
        self.ear = None
        self.paused_at = None
        out = [Action("stop_aap"), Action("hide_tray"), emit("disconnected")]
        if self.ducked:
            self.ducked = False
            out.append(Action("restore_volume"))
        return out

    def _ear(self, left: bool, right: bool, now: float) -> list[Action]:
        prev, self.ear = self.ear, (left, right)
        if prev is None:
            return []
        removed = (prev[0] and not left) or (prev[1] and not right)
        inserted = (not prev[0] and left) or (not prev[1] and right)
        out: list[Action] = []
        if removed:
            out.append(emit("ear-out"))
            if self.config.ear_pause and self.paused_at is None:
                self.paused_at = now
                out.append(Action("pause_media"))
        if inserted:
            out.append(emit("ear-in"))
            if self.paused_at is not None:
                if now - self.paused_at <= RESUME_WINDOW_S:
                    out.append(Action("resume_media"))
                self.paused_at = None
        return out

    def _ca(self, level: int) -> list[Action]:
        if not self.config.ca_duck:
            return []
        if level in (0x01, 0x02) and not self.ducked:
            self.ducked = True
            return [Action("duck_volume", self.config.ca_duck_volume)]
        if level in (0x03, 0x08, 0x09) and self.ducked:
            self.ducked = False
            return [Action("restore_volume")]
        return []

    def _command(self, name: str) -> list[Action]:
        if name == "connect":
            self.user_disconnected = False
            if self.connected or self.connecting:
                return []
            return self._connect()
        if name == "disconnect":
            self.user_disconnected = True
            if not (self.connected or self.connecting):
                return []
            self.connecting = False
            return [Action("disconnect")]
        if name == "dismiss-card":
            return self._hide()
        return []

    def _tick(self, now: float) -> list[Action]:
        silence = self._silence_at()
        if silence is not None and now >= silence:
            # no adverts: the lid was closed (they stop right after), the 3 s already count as the delay
            self.lid_open = False
            self.user_disconnected = False
            return [emit("lid-closed")] + self._hide()
        deadline = self.next_deadline()
        if deadline is not None and now >= deadline:
            return self._hide()
        return []
