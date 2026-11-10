// Window of the proximity card: placement, enter/exit motion, Esc. Content: CardView.qml.
import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win

    required property var layout
    property bool shown: false
    property alias kind: card.kind
    property alias device: card.device
    property alias error: card.error

    signal connectClicked()
    signal dismissed()
    signal editRequested()
    signal settingsRequested()

    readonly property int pad: 24  // room for the shadow around the card
    readonly property point pos: layout.place("card", card.width, card.height, screen)

    screen: Quickshell.screens[0]
    visible: false
    color: "transparent"
    WlrLayershell.namespace: "podglass-card"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors.top: true
    anchors.left: true
    margins.left: Math.max(0, pos.x - pad)
    margins.top: Math.max(0, pos.y - pad)
    implicitWidth: card.width + 2 * pad
    implicitHeight: card.height + 2 * pad
    mask: Region { item: card }

    onShownChanged: {
        if (shown) {
            exitAnim.stop();
            visible = true;
            enterAnim.restart();
            card.forceActiveFocus();
        } else if (visible) {
            enterAnim.stop();
            exitAnim.restart();
        }
    }

    ParallelAnimation {
        id: enterAnim
        NumberAnimation { target: card; property: "slide"; from: Theme.reduceMotion ? 0 : 60; to: 0; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
        NumberAnimation { target: card; property: "scale"; from: Theme.reduceMotion ? 1 : 0.96; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
        NumberAnimation { target: card; property: "opacity"; from: 0; to: 1; duration: 420; easing.type: Easing.OutCubic }
    }
    SequentialAnimation {
        id: exitAnim
        ParallelAnimation {
            NumberAnimation { target: card; property: "slide"; to: Theme.reduceMotion ? 0 : 40; duration: 220; easing.type: Easing.InCubic }
            NumberAnimation { target: card; property: "opacity"; to: 0; duration: 220; easing.type: Easing.InCubic }
        }
        ScriptAction { script: { win.visible = false; card.closeMenu(); } }
    }

    CardView {
        id: card
        property real slide: 0
        x: win.pad
        y: win.pad + slide
        playing: win.visible
        onConnectClicked: win.connectClicked()
        onDismissed: win.dismissed()
        onEditRequested: win.editRequested()
        onSettingsRequested: win.settingsRequested()
    }
}
