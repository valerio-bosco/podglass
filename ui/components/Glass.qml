// Translucent rounded panel with a hairline border and a soft shadow. The blur behind it comes
// from Hyprland (layerrule blur, podglass-.*).
import QtQuick
import QtQuick.Effects
import ".."

Item {
    id: g
    property real radius: 24
    default property alias content: inner.data

    RectangularShadow {
        anchors.fill: bg
        radius: g.radius
        offset.y: 20
        blur: 60
        spread: -10
        color: Theme.shadow
    }
    Rectangle {
        id: bg
        anchors.fill: parent
        radius: g.radius
        color: Theme.glass
        border.width: 1
        border.color: Theme.hairline
    }
    Item {
        id: inner
        anchors.fill: parent
    }
}
