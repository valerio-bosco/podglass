// Battery ring: arc by level, part glyph inside, percent and label under it (docs/UI.md).
import QtQuick
import QtQuick.Shapes
import ".."

Column {
    id: ring
    property string part: "case"
    property var level: null  // 0..100 or null
    property bool charging: false
    property string label: ""
    property real size: 52
    property real stroke: size >= 52 ? 5 : 4
    property bool muted: false
    readonly property bool known: level !== null && level !== undefined

    spacing: 6

    Item {
        width: ring.size
        height: ring.size
        anchors.horizontalCenter: parent.horizontalCenter

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: "transparent"
                strokeColor: Theme.fill
                strokeWidth: ring.stroke
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: ring.size / 2; centerY: ring.size / 2
                    radiusX: (ring.size - ring.stroke) / 2; radiusY: radiusX
                    startAngle: 0; sweepAngle: 360
                }
            }
            ShapePath {
                fillColor: "transparent"
                strokeColor: ring.muted ? Theme.secondary : Theme.batteryColor(ring.level)
                strokeWidth: ring.known && ring.level > 0 ? ring.stroke : 0
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: ring.size / 2; centerY: ring.size / 2
                    radiusX: (ring.size - ring.stroke) / 2; radiusY: radiusX
                    startAngle: -90
                    sweepAngle: ring.known ? 360 * Math.max(0, Math.min(100, ring.level)) / 100 : 0
                    Behavior on sweepAngle { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                }
            }
        }
        Glyph {
            anchors.centerIn: parent
            width: ring.size * 22 / 52
            height: width
            part: ring.part
            opacity: ring.known ? 1 : 0.5
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 3
        Label {
            style: [15, Font.DemiBold]
            tabular: true
            color: ring.muted ? Theme.secondary : Theme.label
            text: ring.known ? ring.level + "%" : "-"
        }
        Text {
            visible: ring.charging && ring.known
            anchors.verticalCenter: parent.verticalCenter
            text: "⚡"  // bolt
            color: Theme.batteryOk
            font.pixelSize: 10
        }
    }
    Label {
        visible: ring.label !== ""
        anchors.horizontalCenter: parent.horizontalCenter
        style: Theme.small
        color: Theme.secondary
        text: ring.label
    }
}
