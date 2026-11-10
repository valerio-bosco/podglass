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

    signal closed()
    signal command(string verb, var arg)

    readonly property int pad: 24
    readonly property point pos: layout.place("popover", panel.width, panel.height, screen)

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
        onCleared: win.closed()
    }

    PopoverView {
        id: panel
        x: win.pad
        y: win.pad
        onClosed: win.closed()
        onCommand: (verb, arg) => win.command(verb, arg)
    }
}
