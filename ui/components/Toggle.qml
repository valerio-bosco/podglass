// iOS-style 51 x 31 switch.
import QtQuick
import ".."

Rectangle {
    id: sw
    property bool checked: false
    signal toggled(bool value)

    width: 51; height: 31; radius: 15.5
    color: checked ? Theme.switchOn : Theme.fill
    Behavior on color { ColorAnimation { duration: 150 } }

    Rectangle {
        width: 27; height: 27; radius: 13.5
        y: 2
        x: sw.checked ? sw.width - width - 2 : 2
        color: "#FFFFFF"
        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: sw.toggled(!sw.checked)
    }
}
