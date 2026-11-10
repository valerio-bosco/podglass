// Content of the listening popover (docs/UI.md "Popover"); ListeningPopover.qml puts it in a window.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Glass {
    id: view

    property var device: ({})

    signal closed()
    signal command(string verb, var arg)

    readonly property var battery: device.battery || {}

    // the selected mode follows the daemon echo; a click highlights for at most 2 s meanwhile
    property string pendingMode: ""
    readonly property string shownMode: pendingMode || device.mode || ""
    onDeviceChanged: if (pendingMode && device.mode === pendingMode) pendingMode = ""
    Timer { id: pendingTimer; interval: 2000; onTriggered: view.pendingMode = "" }

    width: 320
    height: col.implicitHeight + 32
    radius: 26
    focus: true
    Keys.onEscapePressed: view.closed()

    ColumnLayout {
        id: col
        x: 16; y: 16
        width: parent.width - 32
        spacing: 14

        // header
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Glyph { part: "pair"; Layout.preferredWidth: 44; Layout.preferredHeight: 44 }
            ColumnLayout {
                spacing: 1
                Layout.fillWidth: true
                Label { style: [15, Font.DemiBold]; text: view.device.name || Strings.defaultName; elide: Text.ElideRight; Layout.fillWidth: true }
                Label { style: Theme.small; color: Theme.secondary; text: view.device.connected ? Strings.connected : (view.device.connecting ? Strings.connecting : "") }
            }
            Label {
                style: Theme.small
                tabular: true
                color: Theme.secondary
                readonly property var c: view.battery["case"] || {}
                text: c.level != null ? c.level + "%" : ""
            }
        }

        // battery
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: [["left", Strings.left], ["right", Strings.right], ["case", Strings.caseLabel]]
                Item {
                    required property var modelData
                    readonly property var b: view.battery[modelData[0]] || {}
                    Layout.fillWidth: true
                    implicitHeight: ring.implicitHeight
                    BatteryRing {
                        id: ring
                        anchors.horizontalCenter: parent.horizontalCenter
                        size: 40
                        part: parent.modelData[0]
                        label: parent.modelData[1]
                        level: parent.b.level ?? null
                        charging: !!parent.b.charging
                    }
                }
            }
        }

        Label { style: Theme.small; color: Theme.secondary; text: Strings.listeningMode }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                // same order as on the iPhone
                model: [["off", Strings.modeOff], ["transparency", Strings.modeTransparency],
                        ["adaptive", Strings.modeAdaptive], ["anc", Strings.modeAnc]]
                Item {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: btn.implicitHeight
                    ModeButton {
                        id: btn
                        anchors.horizontalCenter: parent.horizontalCenter
                        mode: parent.modelData[0]
                        label: parent.modelData[1]
                        selected: view.shownMode === mode
                        onClicked: {
                            view.pendingMode = mode;
                            pendingTimer.restart();
                            view.command("mode", mode);
                        }
                    }
                }
            }
        }

        // adaptive level
        ColumnLayout {
            visible: view.shownMode === "adaptive"
            Layout.fillWidth: true
            spacing: 4
            Label { style: Theme.small; color: Theme.secondary; text: Strings.adaptiveLevel }
            Slider {
                id: slider
                Layout.fillWidth: true
                from: 0; to: 100; stepSize: 1
                value: view.device.adaptiveLevel ?? 50
                onPressedChanged: if (!pressed) view.command("adaptive-level", Math.round(value))
                background: Rectangle {
                    x: slider.leftPadding
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    width: slider.availableWidth; height: 4; radius: 2
                    color: Theme.fill
                    Rectangle { width: slider.visualPosition * parent.width; height: parent.height; radius: 2; color: Theme.accent }
                }
                handle: Rectangle {
                    x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    width: 22; height: 22; radius: 11
                    color: "#FFFFFF"
                    border.width: 1
                    border.color: Qt.rgba(0, 0, 0, 0.1)
                }
            }
        }

        // conversation awareness
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            Label { style: Theme.body; text: Strings.conversationAwareness; Layout.fillWidth: true; elide: Text.ElideRight }
            Toggle {
                checked: !!view.device.conversationAwareness
                onToggled: value => view.command("ca", value ? "on" : "off")
            }
        }

        // footer
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.hairline }
        RowLayout {
            Layout.fillWidth: true
            Label {
                style: [15, Font.Normal]
                color: Theme.accent
                text: Strings.disconnect
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { view.command("disconnect", null); view.closed(); }
                }
            }
            Item { Layout.fillWidth: true }
            Label {
                style: Theme.caption
                color: Theme.secondary
                text: view.device.firmware ? Strings.firmware + " " + view.device.firmware : ""
            }
        }
    }
}
