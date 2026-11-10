"""The podglass daemon: wires scanner, AAP, BlueZ, policy, IPC, tray and media together.

Everything runs in one asyncio loop. Inputs (adverts, AAP events, BlueZ changes, commands, user
activity, ticks) update `DeviceState` and go through `Policy.step()`; the returned actions are run
here. See docs/PLAN.md 3.
"""

import asyncio
import json
import logging
import os
from dataclasses import replace
from pathlib import Path

from . import aap
from .aap_session import AapSession, run_sessions
from .bluez import Bluez, BluezError, Device
from .config import Config, default_path as config_path, load_config
from .ipc import IpcServer
from .keys import load_keys
from .media import Media
from .policy import (Action, AdvertSeen, Bluez as BluezEvent, CaVolumeChanged, Command, ConnectFailed,
                     EarChanged, InputActivity, Policy, Tick)
from .scanner import Classifier, Seen, scan
from .state import DeviceState, apply_aap, apply_advert, to_json
from .tray import Tray

log = logging.getLogger(__name__)

TICK_S = 0.5
PRESENT_S = 10  # not seen for this long and not connected: no longer present
FIND_DEVICE_S = 10  # retry interval while BlueZ does not know the AirPods yet
ACTIVITY_POLL_S = 15


class Daemon:
    def __init__(self, config: Config, replay: Path | None = None):
        self.config = config
        self.replay = replay
        self.keys = load_keys()
        self.state = DeviceState(known=bool(self.keys))
        self.policy = Policy(config)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ipc = IpcServer(self.on_command)
        self.tray = Tray(lambda: self.ipc.publish_event("popover"), self.on_command)
        self.media = Media()
        self.bluez: Bluez | None = None
        self.device: Device | None = None
        self.session: AapSession | None = None
        self.aap_task: asyncio.Task | None = None
        self.battery = None  # BlueZ BatteryProvider
        self.last_seen: float | None = None
        self.tasks: set[asyncio.Task] = set()

    # --- plumbing -------------------------------------------------------------------------------

    def now(self) -> float:
        return self.loop.time()

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("task failed", exc_info=task.exception())

    def step(self, event) -> None:
        self.run_actions(self.policy.step(event, self.now()))

    def publish(self) -> None:
        self.ipc.publish_state(to_json(self.state))
        b = self.state.battery
        self.tray.update(self.state.name or "AirPods Pro", b.left.level, b.right.level, b.case.level,
                         self.state.mode)
        pods = [x for x in (b.left.level, b.right.level) if x is not None]
        if self.battery is not None and pods:
            self.battery.set_percentage(min(pods))

    def set_state(self, **changes) -> None:
        self.state = replace(self.state, **changes)
        self.publish()

    # --- actions --------------------------------------------------------------------------------

    def run_actions(self, actions: list[Action]) -> None:
        for a in actions:
            log.debug("action %s %s", a.name, a.arg or "")
            match a.name:
                case "show_card":
                    self.ipc.publish_event("show-card", card=a.arg or "normal")
                case "hide_card":
                    self.ipc.publish_event("hide-card")
                case "emit":
                    self.ipc.publish_event(a.arg)
                case "connect":
                    self.spawn(self.connect())
                case "disconnect":
                    self.spawn(self.disconnect())
                case "start_aap":
                    self.start_aap()
                case "stop_aap":
                    self.stop_aap()
                case "show_tray":
                    self.spawn(self.tray.show())
                case "hide_tray":
                    self.spawn(self.tray.hide())
                case "pause_media":
                    self.spawn(self.media.pause())
                case "resume_media":
                    self.spawn(self.media.resume())
                case "duck_volume":
                    self.spawn(self.media.duck(a.arg))
                case "restore_volume":
                    self.spawn(self.media.restore())

    async def connect(self) -> None:
        if self.bluez is None or self.device is None:
            self.step(ConnectFailed())
            return
        self.set_state(connecting=True)
        try:
            await self.bluez.connect(self.device.path)
        except (BluezError, asyncio.TimeoutError) as e:
            log.info("connect failed: %s", e or "timeout")
            self.set_state(connecting=False)
            self.step(ConnectFailed())
            return
        self.set_state(connecting=False)
        self.on_bluez_connected(True)  # the signal may arrive later; the policy ignores repeats

    async def disconnect(self) -> None:
        if self.bluez is not None and self.device is not None:
            try:
                await self.bluez.disconnect(self.device.path)
            except (BluezError, asyncio.TimeoutError) as e:
                log.info("disconnect failed: %s", e or "timeout")

    def start_aap(self) -> None:
        if self.aap_task is not None or self.device is None:
            return

        async def connected() -> bool:
            return self.state.connected

        def on_session(session: AapSession | None) -> None:
            self.session = session

        self.aap_task = self.spawn(run_sessions(self.device.address, connected, self.on_aap, on_session))
        self.aap_task.add_done_callback(lambda _t: setattr(self, "aap_task", None))

    def stop_aap(self) -> None:
        if self.aap_task is not None:
            self.aap_task.cancel()
            self.aap_task = None
        self.session = None

    # --- inputs ---------------------------------------------------------------------------------

    def on_command(self, verb: str, arg: str | None) -> None:
        log.info("command %s %s", verb, arg or "")
        if verb in ("connect", "disconnect", "dismiss-card"):
            self.step(Command(verb))
        elif verb in ("mode", "ca", "adaptive-level"):
            packet = {"mode": lambda: aap.set_mode(arg), "ca": lambda: aap.set_ca(arg == "on"),
                      "adaptive-level": lambda: aap.set_adaptive_level(int(arg))}[verb]()
            if self.session is None:
                log.info("%s ignored: no AAP session", verb)
                return
            self.spawn(self.session.send(packet))
        elif verb == "show-card":
            self.ipc.publish_event("show-card", card="normal")
        elif verb in ("popover", "edit"):
            self.ipc.publish_event(verb)
        elif verb == "layout":
            path = config_path().parent / "layout.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(json.loads(arg), indent=2) + "\n")
            os.replace(tmp, path)

    def on_seen(self, seen: Seen) -> None:
        self.last_seen = self.now()
        if seen.known and seen.device and not self.state.known:
            self.state = replace(self.state, known=True)
        self.state = apply_advert(self.state, seen.adv, seen.precise)
        self.publish()
        self.step(AdvertSeen(seen.adv, seen.known, seen.precise))

    def on_aap(self, event: aap.AapEvent) -> None:
        if isinstance(event, aap.Unknown):
            log.debug("aap unknown opcode %s: %s", event.opcode, event.raw.hex())
        elif not isinstance(event, aap.Keys):
            log.debug("aap %s", event)
        self.state = apply_aap(self.state, event)
        self.publish()
        if isinstance(event, aap.Ear):  # the policy compares with the previous ear state itself
            pods = (event.primary, event.secondary)
            self.step(EarChanged(pods.count("in-ear"), pods.count("in-case")))
        elif isinstance(event, aap.CaVolume):
            self.step(CaVolumeChanged(event.level))
        elif isinstance(event, aap.Keys):
            self.keys = load_keys()  # aap_session stored them

    def on_bluez_connected(self, connected: bool) -> None:
        if connected != self.state.connected:
            self.set_state(connected=connected, connecting=False)
        self.step(BluezEvent(connected))

    # --- loops ----------------------------------------------------------------------------------

    async def ticker(self) -> None:
        while True:
            await asyncio.sleep(TICK_S)
            if (self.state.present and not self.state.connected and self.last_seen is not None
                    and self.now() - self.last_seen > PRESENT_S):
                self.set_state(present=False, lid="unknown")
            self.step(Tick())

    async def scanner(self) -> None:
        if self.replay is not None:
            await self.replay_file(self.replay)
            return
        while True:
            try:
                async for seen in scan(self.keys):
                    self.on_seen(seen)
            except Exception as e:  # BlueZ restarted, adapter off ...
                log.warning("scanner stopped (%s), restarting in 5 s", e)
                await asyncio.sleep(5)

    async def replay_file(self, path: Path) -> None:
        """Feed a capture (tests/fixtures/adv/*.jsonl) with its original timing."""
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        classifier = Classifier(self.keys)
        start = rows[0]["t"] if rows else 0
        t0 = self.now()
        for r in rows:
            await asyncio.sleep(max(0.0, (r["t"] - start) - (self.now() - t0)))
            seen = classifier.classify(r["addr"], bytes.fromhex(r["hex"]), r["rssi"], self.now())
            if seen is not None:
                self.on_seen(seen)
        log.info("replay finished")

    async def activity(self) -> None:
        """User activity on this PC: the cursor or the focused window changed (Hyprland)."""
        last = None
        while True:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "sh", "-c", "hyprctl -j cursorpos; hyprctl -j activewindow",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await proc.communicate()
                if last is not None and out != last:
                    self.step(InputActivity())
                last = out
            except FileNotFoundError:
                return
            await asyncio.sleep(ACTIVITY_POLL_S)

    async def find_device(self) -> None:
        while self.device is None:
            try:
                self.device = await self.bluez.find_airpods(set(self.keys))
            except BluezError as e:
                log.warning("BlueZ: %s", e)
            if self.device is None:
                await asyncio.sleep(FIND_DEVICE_S)
        log.info("AirPods %s at %s", self.device.address, self.device.path)
        self.set_state(paired=self.device.paired, name=self.state.name or self.device.name)
        self.bluez.watch_connected(self.device.path, self.on_bluez_connected)
        try:
            self.battery = await self.bluez.register_battery(self.device.path)
        except BluezError as e:
            log.warning("battery provider not registered: %s", e)
        self.on_bluez_connected(await self.bluez.is_connected(self.device.path))

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        await self.ipc.start()
        self.ipc.publish_config(json.dumps({"type": "config", "theme": self.config.theme,
                                            "batteryWidget": self.config.battery_widget}))
        self.publish()
        try:
            await self.tray.start()
        except Exception as e:  # no session bus: run without tray
            log.warning("tray unavailable: %s", e)
        try:
            self.bluez = await Bluez.open()
            self.policy.adapter_tail = await self.bluez.adapter_tail()
            self.spawn(self.find_device())
        except Exception as e:
            log.warning("BlueZ unavailable: %s", e)
        self.spawn(self.scanner())
        self.spawn(self.activity())
        log.info("podglass daemon running on %s", self.ipc.path)
        try:
            await self.ticker()
        finally:
            for t in list(self.tasks):
                t.cancel()
            await self.ipc.close()
            self.tray.close()
            if self.bluez is not None:
                self.bluez.close()


def main(replay: Path | None = None, verbose: bool = False) -> int:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(Daemon(load_config(), replay).run())
    except KeyboardInterrupt:
        pass
    return 0
