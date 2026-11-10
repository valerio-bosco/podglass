// Window positions. `layout.json` (written by the daemon from edit mode) stores, per monitor and
// window, an anchor on the screen plus an offset, so positions survive resolution changes:
//   {"HDMI-A-1": {"card": {"anchor": "bottom-center", "dx": 0, "dy": -24}}}
import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: lay

    property var saved: ({})
    readonly property int barHeight: Number(Quickshell.env("PODGLASS_BAR_HEIGHT") || 56)
    readonly property var defaults: ({
        card: { anchor: "bottom-center", dx: 0, dy: -24 },
        popover: { anchor: "top-right", dx: -12, dy: barHeight + 8 },
        widget: { anchor: "bottom-left", dx: 24, dy: -24 }
    })
    readonly property string path: (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/podglass/layout.json"

    FileView {
        path: lay.path
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: { try { lay.saved = JSON.parse(text()) || {}; } catch (e) { lay.saved = {}; } }
        onLoadFailed: lay.saved = {}
    }

    function entry(name, screenName) {
        const s = saved[screenName];
        return (s && s[name]) || defaults[name];
    }

    function toXY(e, w, h, sw, sh) {
        const a = e.anchor || "top-left";
        const bx = a.endsWith("left") ? 0 : a.endsWith("right") ? sw - w : (sw - w) / 2;
        const by = a.startsWith("top") ? 0 : a.startsWith("bottom") ? sh - h : (sh - h) / 2;
        return Qt.point(Math.round(bx + (e.dx || 0)), Math.round(by + (e.dy || 0)));
    }

    // the anchor is the screen third the window center falls in
    function fromXY(x, y, w, h, sw, sh) {
        const cx = x + w / 2, cy = y + h / 2;
        const hz = cx < sw / 3 ? "left" : cx > sw * 2 / 3 ? "right" : "center";
        const vt = cy < sh / 3 ? "top" : cy > sh * 2 / 3 ? "bottom" : "center";
        const anchor = vt === "center" && hz === "center" ? "center-center" : vt + "-" + hz;
        const base = toXY({ anchor: anchor, dx: 0, dy: 0 }, w, h, sw, sh);
        return { anchor: anchor, dx: Math.round(x - base.x), dy: Math.round(y - base.y) };
    }

    function place(name, w, h, screen) {
        if (!screen) return Qt.point(0, 0);
        return toXY(entry(name, screen.name), w, h, screen.width, screen.height);
    }

    function defaultPlace(name, w, h, screen) {
        return toXY(defaults[name], w, h, screen.width, screen.height);
    }
}
