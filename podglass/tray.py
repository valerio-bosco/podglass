"""Tray icon (StatusNotifierItem + com.canonical.dbusmenu) on the session bus.

The serpantinum bar shows tray items (its watcher is Quickshell). The item is registered only while
the AirPods are connected: `show()` takes the bus name and registers, `hide()` releases it.
"""

import logging
import os
from collections.abc import Callable

from dbus_fast import BusType, Message, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import RequestNameReply
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method, signal

log = logging.getLogger(__name__)

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
SIZE = 22
MODES = [("off", "Off"), ("transparency", "Transparency"), ("adaptive", "Adaptive"),
         ("anc", "Noise Cancellation")]
# menu ids: 1-4 modes, 5 separator, 6 disconnect, 7 edit layout
ID_DISCONNECT, ID_EDIT = 6, 7


def pods_pixmap(size: int = SIZE) -> bytes:
    """ARGB32 (network byte order) glyph of two pods: round head, stem down. Pure."""
    px = bytearray(size * size * 4)
    s = size / 22

    def inside(x: float, y: float) -> bool:
        for cx, stem_x in ((6.5, 7.5), (15.5, 13.0)):
            if ((x - cx) / (4.2 * s)) ** 2 + ((y - 6 * s) / (3.8 * s)) ** 2 <= 1:
                return True
            if abs(x - (stem_x + 1.0) * s) <= 1.4 * s and 6 * s <= y <= 19 * s:
                return True
        return False

    for j in range(size):
        for i in range(size):
            # 2x2 supersampling for soft edges
            hits = sum(inside(i + dx, j + dy) for dx in (0.25, 0.75) for dy in (0.25, 0.75))
            if hits:
                o = (j * size + i) * 4
                px[o:o + 4] = bytes((hits * 255 // 4, 255, 255, 255))
    return bytes(px)


def tooltip_text(name: str, left: int | None, right: int | None, case: int | None) -> str:
    def p(v):
        return "-" if v is None else f"{v}%"
    return f"{name} - L {p(left)} R {p(right)} Case {p(case)}"


class Item(ServiceInterface):
    def __init__(self, on_activate: Callable[[], None]):
        super().__init__("org.kde.StatusNotifierItem")
        self.on_activate = on_activate
        self.title = "AirPods"
        self.tip = "AirPods"
        self.pixmap = pods_pixmap()

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":  # noqa: F821, N802 - D-Bus names
        return "Hardware"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":  # noqa: F821, N802
        return "podglass"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":  # noqa: F821, N802
        return self.title

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":  # noqa: F821, N802
        return "Active"

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":  # noqa: F821, N802
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def IconPixmap(self) -> "a(iiay)":  # noqa: F821, N802
        return [[SIZE, SIZE, self.pixmap]]

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":  # noqa: F821, N802
        return ["", [], self.title, self.tip]

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":  # noqa: F821, N802
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":  # noqa: F821, N802
        return MENU_PATH

    @method()
    def Activate(self, x: "i", y: "i"):  # noqa: F821, N802
        self.on_activate()

    @method()
    def SecondaryActivate(self, x: "i", y: "i"):  # noqa: F821, N802
        self.on_activate()

    @method()
    def ContextMenu(self, x: "i", y: "i"):  # noqa: F821, N802
        pass  # hosts show the dbusmenu themselves

    @method()
    def Scroll(self, delta: "i", orientation: "s"):  # noqa: F821, N802
        pass

    @signal()
    def NewToolTip(self):  # noqa: N802
        pass

    @signal()
    def NewTitle(self):  # noqa: N802
        pass


class Menu(ServiceInterface):
    """com.canonical.dbusmenu with the 4 listening modes, Disconnect and Edit Layout."""

    def __init__(self, on_click: Callable[[str, str | None], None]):
        super().__init__("com.canonical.dbusmenu")
        self.on_click = on_click
        self.mode: str | None = None
        self.revision = 1

    def _props(self, item_id: int) -> dict:
        if 1 <= item_id <= 4:
            key, label = MODES[item_id - 1]
            return {"label": Variant("s", label), "toggle-type": Variant("s", "radio"),
                    "toggle-state": Variant("i", 1 if key == self.mode else 0)}
        if item_id == 5:
            return {"type": Variant("s", "separator")}
        if item_id == ID_DISCONNECT:
            return {"label": Variant("s", "Disconnect")}
        if item_id == ID_EDIT:
            return {"label": Variant("s", "Edit Position...")}
        return {"children-display": Variant("s", "submenu")}

    def layout(self) -> list:
        children = [Variant("(ia{sv}av)", [i, self._props(i), []]) for i in range(1, 8)]
        return [0, self._props(0), children]

    def set_mode(self, mode: str | None) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        self.revision += 1
        self.LayoutUpdated(self.revision, 0)

    @method()
    def GetLayout(self, parent_id: "i", depth: "i", names: "as") -> "u(ia{sv}av)":  # noqa: F821, N802
        return [self.revision, self.layout()]

    @method()
    def GetGroupProperties(self, ids: "ai", names: "as") -> "a(ia{sv})":  # noqa: F821, N802
        return [[i, self._props(i)] for i in (ids or range(0, 8))]

    @method()
    def GetProperty(self, item_id: "i", name: "s") -> "v":  # noqa: F821, N802
        return self._props(item_id).get(name, Variant("s", ""))

    @method()
    def Event(self, item_id: "i", event_id: "s", data: "v", timestamp: "u"):  # noqa: F821, N802
        if event_id == "clicked":
            self.click(item_id)

    def click(self, item_id: int) -> None:
        if 1 <= item_id <= 4:
            self.on_click("mode", MODES[item_id - 1][0])
        elif item_id == ID_DISCONNECT:
            self.on_click("disconnect", None)
        elif item_id == ID_EDIT:
            self.on_click("edit", None)

    @method()
    def EventGroup(self, events: "a(isvu)") -> "ai":  # noqa: F821, N802
        for item_id, event_id, _data, _ts in events:
            if event_id == "clicked":
                self.click(item_id)
        return []

    @method()
    def AboutToShow(self, item_id: "i") -> "b":  # noqa: F821, N802
        return False

    @method()
    def AboutToShowGroup(self, ids: "ai") -> "aiai":  # noqa: F821, N802
        return [[], []]

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":  # noqa: F821, N802
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":  # noqa: F821, N802
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":  # noqa: F821, N802
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":  # noqa: F821, N802
        return []

    @signal()
    def LayoutUpdated(self, revision, parent) -> "ui":  # noqa: N802
        return [revision, parent]


class Tray:
    def __init__(self, on_activate: Callable[[], None], on_command: Callable[[str, str | None], None]):
        self.item = Item(on_activate)
        self.menu = Menu(on_command)
        self.bus: MessageBus | None = None
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.visible = False

    async def start(self) -> None:
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self.bus.export(ITEM_PATH, self.item)
        self.bus.export(MENU_PATH, self.menu)

    async def show(self) -> None:
        if self.visible or self.bus is None:
            return
        reply = await self.bus.request_name(self.name)
        if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
            log.warning("tray: cannot own %s", self.name)
            return
        await self.bus.call(Message(destination="org.kde.StatusNotifierWatcher", path="/StatusNotifierWatcher",
                                    interface="org.kde.StatusNotifierWatcher",
                                    member="RegisterStatusNotifierItem", signature="s", body=[self.name]))
        self.visible = True

    async def hide(self) -> None:
        if not self.visible or self.bus is None:
            return
        await self.bus.release_name(self.name)  # the watcher drops items whose name goes away
        self.visible = False

    def update(self, name: str, left: int | None, right: int | None, case: int | None, mode: str | None) -> None:
        tip = tooltip_text(name, left, right, case)
        if (name, tip) != (self.item.title, self.item.tip):
            self.item.title, self.item.tip = name, tip
            if self.bus is not None:
                self.item.NewTitle()
                self.item.NewToolTip()
        self.menu.set_mode(mode)

    def close(self) -> None:
        if self.bus is not None:
            self.bus.disconnect()


async def debug(seconds: float) -> int:
    """`podglass debug tray`: show the icon, print clicks and menu choices."""
    import asyncio

    tray = Tray(lambda: print("activate (would open the popover)", flush=True),
                lambda verb, arg: print(f"menu: {verb} {arg or ''}"))
    await tray.start()
    await tray.show()
    tray.update("AirPods Pro", 82, 80, 64, "anc")
    print(f"tray icon shown as {tray.name} for {seconds:.0f} s: click it and try the menu")
    await asyncio.sleep(seconds)
    await tray.hide()
    tray.close()
    return 0
