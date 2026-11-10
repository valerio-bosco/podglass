// Window of the optional battery widget, on the Bottom layer. Content: WidgetView.qml.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win

    required property var layout
    property alias device: panel.device

    readonly property int pad: 24
    readonly property point pos: layout.place("widget", panel.width, panel.height, screen)

    screen: Quickshell.screens[0]
    color: "transparent"
    WlrLayershell.namespace: "podglass-widget"
    WlrLayershell.layer: WlrLayer.Bottom
    exclusionMode: ExclusionMode.Ignore
    anchors.top: true
    anchors.left: true
    margins.left: Math.max(0, pos.x - pad)
    margins.top: Math.max(0, pos.y - pad)
    implicitWidth: panel.width + 2 * pad
    implicitHeight: panel.height + 2 * pad
    mask: Region { item: panel }

    WidgetView {
        id: panel
        x: win.pad
        y: win.pad
    }
}
