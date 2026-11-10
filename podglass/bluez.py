"""BlueZ D-Bus client: device lookup, connect, battery provider. See docs/PROTOCOL.md 3."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property

log = logging.getLogger(__name__)

BLUEZ = "org.bluez"
DEVICE = "org.bluez.Device1"
ADAPTER = "org.bluez.Adapter1"
PROPS = "org.freedesktop.DBus.Properties"
CONNECT_TIMEOUT_S = 15
PROVIDER_ROOT = "/org/podglass/battery"
APPLE_MODALIAS = "bluetooth:v004C"


@dataclass(frozen=True)
class Device:
    path: str
    address: str
    name: str
    connected: bool
    paired: bool


def _val(v):
    return v.value if isinstance(v, Variant) else v


def pick_airpods(objects: dict, known: set[str] = frozenset()) -> Device | None:
    """Choose the AirPods among BlueZ managed objects (pure, for tests).

    Prefers an address from keys.json, then a paired Apple device whose name has "AirPods".
    """
    found: list[Device] = []
    for path, ifaces in objects.items():
        props = ifaces.get(DEVICE)
        if not props:
            continue
        p = {k: _val(v) for k, v in props.items()}
        address = str(p.get("Address", "")).upper()
        name = str(p.get("Name") or p.get("Alias") or "")
        apple = str(p.get("Modalias", "")).startswith(APPLE_MODALIAS)
        if address in known or (apple and "AirPods" in name):
            found.append(Device(path, address, name, bool(p.get("Connected")), bool(p.get("Paired"))))
    found.sort(key=lambda d: (d.address not in known, not d.paired))
    return found[0] if found else None


class BatteryProvider(ServiceInterface):
    """org.bluez.BatteryProvider1 object: lets the rest of the desktop see the AirPods battery."""

    def __init__(self, device_path: str):
        super().__init__("org.bluez.BatteryProvider1")
        self._device = device_path
        self._percentage = 0

    @dbus_property(access=PropertyAccess.READ)
    def Device(self) -> "o":  # noqa: F821, N802 - D-Bus names
        return self._device

    @dbus_property(access=PropertyAccess.READ)
    def Percentage(self) -> "y":  # noqa: F821, N802
        return self._percentage

    @dbus_property(access=PropertyAccess.READ)
    def Source(self) -> "s":  # noqa: F821, N802
        return "podglass"

    def set_percentage(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        if value != self._percentage:
            self._percentage = value
            self.emit_properties_changed({"Percentage": value})


class Bluez:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._provider: BatteryProvider | None = None

    @classmethod
    async def open(cls) -> "Bluez":
        return cls(await MessageBus(bus_type=BusType.SYSTEM).connect())

    async def _call(self, path: str, interface: str, member: str, signature: str = "", body=(), timeout=None):
        msg = Message(destination=BLUEZ, path=path, interface=interface, member=member,
                      signature=signature, body=list(body))
        call = self.bus.call(msg)
        reply = await (asyncio.wait_for(call, timeout) if timeout else call)
        if reply.message_type == MessageType.ERROR:
            raise BluezError(reply.error_name, reply.body[0] if reply.body else "")
        return reply.body

    async def objects(self) -> dict:
        (objs,) = await self._call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
        return objs

    async def adapter(self) -> tuple[str, str]:
        """(object path, MAC) of the first adapter."""
        for path, ifaces in (await self.objects()).items():
            if ADAPTER in ifaces:
                return path, str(_val(ifaces[ADAPTER]["Address"])).upper()
        raise BluezError("org.podglass.NoAdapter", "no Bluetooth adapter")

    async def adapter_tail(self) -> bytes:
        """Last 3 bytes of the adapter MAC, as the decrypted advert carries them (PROTOCOL.md 1.3)."""
        _, mac = await self.adapter()
        return bytes.fromhex(mac.replace(":", ""))[-3:]

    async def find_airpods(self, known: set[str] = frozenset()) -> Device | None:
        return pick_airpods(await self.objects(), {a.upper() for a in known})

    async def is_connected(self, path: str) -> bool:
        (v,) = await self._call(path, PROPS, "Get", "ss", (DEVICE, "Connected"))
        return bool(_val(v))

    async def connect(self, path: str, timeout: float = CONNECT_TIMEOUT_S) -> None:
        """Connect all profiles. Raises BluezError or asyncio.TimeoutError.

        Already connected is success. `InProgress` (BlueZ is already connecting, or the AirPods
        connected themselves a moment ago) waits for Connected instead of failing.
        """
        if await self.is_connected(path):
            return
        try:
            await self._call(path, DEVICE, "Connect", timeout=timeout)
        except BluezError as e:
            if e.name not in ("org.bluez.Error.InProgress", "org.bluez.Error.AlreadyConnected"):
                raise
            loop = asyncio.get_running_loop()
            end = loop.time() + timeout
            while not await self.is_connected(path):
                if loop.time() >= end:
                    raise asyncio.TimeoutError from e
                await asyncio.sleep(0.5)

    async def disconnect(self, path: str) -> None:
        await self._call(path, DEVICE, "Disconnect", timeout=CONNECT_TIMEOUT_S)

    def watch_connected(self, path: str, callback: Callable[[bool], None]) -> Callable[[], None]:
        """Call `callback(connected)` on every change of Device1.Connected. Returns an unsubscribe."""
        rule = f"type='signal',sender='{BLUEZ}',interface='{PROPS}',member='PropertiesChanged',path='{path}'"

        def handler(msg: Message) -> None:
            if (msg.message_type == MessageType.SIGNAL and msg.path == path
                    and msg.member == "PropertiesChanged" and msg.body and msg.body[0] == DEVICE):
                changed = msg.body[1]
                if "Connected" in changed:
                    callback(bool(_val(changed["Connected"])))

        self.bus.add_message_handler(handler)
        asyncio.ensure_future(self._add_match(rule))

        def unsubscribe() -> None:
            self.bus.remove_message_handler(handler)

        return unsubscribe

    async def _add_match(self, rule: str) -> None:
        await self.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                    interface="org.freedesktop.DBus", member="AddMatch",
                                    signature="s", body=[rule]))

    async def register_battery(self, device_path: str) -> BatteryProvider:
        """Export a BatteryProvider1 for the device and register it with BlueZ."""
        adapter_path, _ = await self.adapter()
        provider = BatteryProvider(device_path)
        self.bus.export(f"{PROVIDER_ROOT}/{device_path.rsplit('/', 1)[-1]}", provider)
        await self._call(adapter_path, "org.bluez.BatteryProviderManager1", "RegisterBatteryProvider",
                         "o", (PROVIDER_ROOT,))
        self._provider = provider
        return provider

    def close(self) -> None:
        self.bus.disconnect()


class BluezError(Exception):
    def __init__(self, name: str, text: str = ""):
        super().__init__(f"{name}: {text}" if text else name)
        self.name = name


async def debug(connect: bool = False, disconnect: bool = False, battery: int | None = None) -> int:
    """`podglass debug bluez`: print what BlueZ knows, optionally connect/disconnect."""
    from .keys import load_keys

    bz = await Bluez.open()
    try:
        path, mac = await bz.adapter()
        print(f"adapter {path} {mac} (tail {(await bz.adapter_tail()).hex()})")
        dev = await bz.find_airpods(set(load_keys()))
        if dev is None:
            print("no AirPods known to BlueZ (pair them first)")
            return 1
        print(f"device  {dev.path} {dev.address} '{dev.name}' paired={dev.paired} connected={dev.connected}")
        if connect:
            print("connecting ...")
            await bz.connect(dev.path)
            print(f"connected={await bz.is_connected(dev.path)}")
        if disconnect:
            await bz.disconnect(dev.path)
            print(f"connected={await bz.is_connected(dev.path)}")
        if battery is not None:
            provider = await bz.register_battery(dev.path)
            provider.set_percentage(battery)
            print(f"battery provider registered with {battery}%; check `upower -d`. Ctrl+C to stop")
            await asyncio.Event().wait()
        return 0
    except (BluezError, asyncio.TimeoutError) as e:
        print(f"error: {str(e) or 'timed out after 15 s (AirPods in the closed case or out of range?)'}")
        return 1
    finally:
        bz.close()
