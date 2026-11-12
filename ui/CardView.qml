// Content of the proximity card (docs/UI.md "Card"); ProximityCard.qml puts it in a window.
import QtQuick
import QtQuick.Layouts
import "components"

Glass {
    id: view

    property string kind: "normal"  // normal | setup
    property var device: ({})
    property bool error: false
    property bool playing: true  // render animation

    signal connectClicked()
    signal dismissed()
    signal editRequested()
    signal settingsRequested()

    readonly property var battery: device.battery || {}
    readonly property string cardState: kind === "setup" ? "setup"
        : error ? "error"
        : device.connected ? "connected"
        : device.connecting ? "connecting"
        : "disconnected"

    function closeMenu() { menu.visible = false; }
    // lid closed while the card is up: play the closing render, the window waits `closeMs` before it exits
    readonly property int closeMs: render.closeMs
    function playClose() { render.close(); }

    width: 360
    height: column.implicitHeight + 40
    radius: 38
    focus: true
    Keys.onEscapePressed: view.dismissed()

    ColumnLayout {
        id: column
        x: 20; y: 20
        width: parent.width - 40
        spacing: 0

        // title + close
        Item {
            Layout.fillWidth: true
            implicitHeight: 30
            Label {
                anchors.centerIn: parent
                width: parent.width - 80
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                style: Theme.title
                text: view.device.name || Strings.defaultName
            }
            Rectangle {
                anchors.right: parent.right
                width: 30; height: 30; radius: 15
                color: Theme.fill
                Label {
                    anchors.centerIn: parent
                    style: [12, Font.Bold]
                    color: Theme.secondary
                    text: "✕"
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: view.dismissed()
                }
            }
        }

        Render {
            id: render
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 280
            Layout.preferredHeight: 230
            lidOpen: view.device.lid !== "closed"
            waiting: view.cardState !== "connected"
            playing: view.playing
        }

        // bottom area by state
        Item {
            Layout.fillWidth: true
            Layout.topMargin: 12
            implicitHeight: bottom.implicitHeight
            Loader {
                id: bottom
                width: parent.width
                sourceComponent: ({ connected: rings, setup: setupView, error: errorView })[view.cardState] || connectView
            }
        }
    }

    // right-click menu
    MouseArea {
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.RightButton
        onClicked: mouse => { menu.x = mouse.x; menu.y = mouse.y; menu.visible = true; }
    }
    Rectangle {
        id: menu
        visible: false
        z: 10
        width: 170
        height: menuCol.implicitHeight + 12
        radius: 12
        color: Theme.dark ? "#2C2C2E" : "#FFFFFF"
        border.width: 1
        border.color: Theme.hairline
        Column {
            id: menuCol
            x: 6; y: 6
            width: parent.width - 12
            Repeater {
                model: [
                    { label: Strings.editPosition, act: () => view.editRequested() },
                    { label: Strings.settings, act: () => view.settingsRequested() }
                ]
                Rectangle {
                    required property var modelData
                    width: menuCol.width
                    height: 32
                    radius: 8
                    color: itemArea.containsMouse ? Theme.fill : "transparent"
                    Label { x: 10; anchors.verticalCenter: parent.verticalCenter; style: Theme.small; text: parent.modelData.label }
                    MouseArea {
                        id: itemArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: { menu.visible = false; parent.modelData.act(); }
                    }
                }
            }
        }
    }

    Component {
        id: connectView
        PillButton {
            busy: view.cardState === "connecting"
            text: busy ? Strings.connecting : Strings.connect
            onClicked: view.connectClicked()
        }
    }
    Component {
        id: setupView
        Column {
            spacing: 12
            Label {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                style: Theme.small
                color: Theme.secondary
                text: Strings.notPaired
            }
            PillButton { width: parent.width; text: Strings.setUp; onClicked: view.connectClicked() }
        }
    }
    Component {
        id: errorView
        Column {
            spacing: 12
            Label {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                style: Theme.small
                color: Theme.batteryLow
                text: Strings.couldNotConnect
            }
            PillButton { width: parent.width; text: Strings.tryAgain; onClicked: view.connectClicked() }
        }
    }
    Component {
        id: rings
        Item {
            readonly property var l: view.battery.left || {}
            readonly property var r: view.battery.right || {}
            readonly property var c: view.battery["case"] || {}
            readonly property bool both: l.level != null && r.level != null && Math.abs(l.level - r.level) <= 10
            implicitHeight: row.implicitHeight
            Row {
                id: row
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: parent.both ? 64 : 40
                BatteryRing {
                    visible: parent.parent.both
                    part: "pair"
                    label: Strings.airpods
                    level: parent.parent.both ? Math.min(parent.parent.l.level, parent.parent.r.level) : null
                    charging: !!(parent.parent.l.charging && parent.parent.r.charging)
                }
                BatteryRing {
                    visible: !parent.parent.both
                    part: "left"; label: Strings.left
                    level: parent.parent.l.level ?? null; charging: !!parent.parent.l.charging
                }
                BatteryRing {
                    visible: !parent.parent.both
                    part: "right"; label: Strings.right
                    level: parent.parent.r.level ?? null; charging: !!parent.parent.r.charging
                }
                BatteryRing {
                    part: "case"; label: Strings.caseLabel
                    level: parent.parent.c.level ?? null; charging: !!parent.parent.c.charging
                }
            }
        }
    }
}
