// Content of the battery widget (docs/UI.md "Battery widget"); BatteryWidget.qml puts it in a window.
import QtQuick
import QtQuick.Layouts
import "components"

Glass {
    id: view

    property var device: ({})

    readonly property var battery: device.battery || {}
    readonly property bool live: !!(device.connected || device.present)
    property string lastSeen: ""
    onLiveChanged: if (!live) lastSeen = Qt.formatTime(new Date(), "hh:mm")

    width: 340
    height: 160
    radius: 24

    RowLayout {
        anchors.fill: parent
        anchors.margins: 16
        anchors.bottomMargin: view.live ? 16 : 26
        Repeater {
            model: ["left", "right", "case"]
            Item {
                required property string modelData
                readonly property var b: view.battery[modelData] || {}
                Layout.fillWidth: true
                Layout.fillHeight: true
                BatteryRing {
                    anchors.centerIn: parent
                    size: 60
                    part: parent.modelData
                    level: parent.b.level ?? null
                    charging: view.live && !!parent.b.charging
                    muted: !view.live
                }
            }
        }
    }
    Label {
        visible: !view.live && view.lastSeen !== ""
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
        style: Theme.caption
        color: Theme.secondary
        text: Strings.lastSeen.arg(view.lastSeen)
    }
}
