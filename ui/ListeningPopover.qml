// Window of the listening popover: placement, outside click and Esc close it. Content: PopoverView.qml.
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland

PanelWindow {
    id: win

    required property var layout
    property bool open: false
    property alias device: panel.device

    signal dismissed()
    signal command(string verb, var arg)

    readonly property int pad: 24
    readonly property point placed: layout.place("popover", panel.width, panel.height, screen)
    // keep the whole panel inside the screen with a 12 px margin
    readonly property point pos: Qt.point(
        Math.max(12, Math.min(placed.x, screen.width - panel.width - 12)),
        Math.max(12, Math.min(placed.y, screen.height - panel.height - 12)))

    screen: Quickshell.screens[0]
    visible: open
    color: "transparent"
    WlrLayershell.namespace: "podglass-popover"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: open ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors.top: true
    anchors.left: true
    margins.left: Math.max(0, pos.x - pad)
    margins.top: Math.max(0, pos.y - pad)
    implicitWidth: panel.width + 2 * pad
    implicitHeight: panel.height + 2 * pad
    mask: Region { item: panel }

    onOpenChanged: if (open) panel.forceActiveFocus()

    HyprlandFocusGrab {
        windows: [win]
        active: win.open
        onCleared: win.dismissed()
    }

    PopoverView {
        id: panel
        x: win.pad
        y: win.pad
        onClosed: win.dismissed()
        onCommand: (verb, arg) => win.command(verb, arg)
    }
}
