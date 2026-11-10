// 52 px round listening mode button with its label under it.
import QtQuick
import ".."

Column {
    id: mb
    property string mode: "off"
    property string label: ""
    property bool selected: false
    signal clicked()
    spacing: 6

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 52; height: 52; radius: 26
        color: mb.selected ? Theme.accent : Theme.fill
        Behavior on color { ColorAnimation { duration: 150 } }
        ModeIcon {
            anchors.centerIn: parent
            mode: mb.mode
            color: mb.selected ? "#FFFFFF" : Theme.label
            hole: mb.selected ? Theme.accent : Theme.glass
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: mb.clicked()
        }
    }
    Label {
        anchors.horizontalCenter: parent.horizontalCenter
        style: Theme.caption
        color: mb.selected ? Theme.label : Theme.secondary
        text: mb.label
    }
}
