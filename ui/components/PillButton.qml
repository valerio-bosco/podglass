// Full-width button of the card: accent fill, or fill token when `busy`.
import QtQuick
import ".."

Rectangle {
    id: b
    property string text: ""
    property bool busy: false
    property bool primary: true
    signal clicked()

    height: 50
    radius: 14
    color: busy || !primary ? Theme.fill : Theme.accent
    opacity: area.pressed ? 0.75 : 1

    Row {
        anchors.centerIn: parent
        spacing: 8
        Spinner { visible: b.busy; anchors.verticalCenter: parent.verticalCenter }
        Label {
            style: Theme.button
            color: b.busy || !b.primary ? Theme.label : "#FFFFFF"
            text: b.text
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        enabled: !b.busy
        cursorShape: Qt.PointingHandCursor
        onClicked: b.clicked()
    }
}
