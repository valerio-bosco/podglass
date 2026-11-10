import QtQuick
import QtQuick.Shapes
import ".."

Item {
    id: sp
    property color color: Theme.label
    width: 18; height: 18

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        RotationAnimator on rotation { from: 0; to: 360; duration: 900; loops: Animation.Infinite; running: sp.visible }
        ShapePath {
            fillColor: "transparent"
            strokeColor: sp.color
            strokeWidth: 2
            capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: 9; centerY: 9; radiusX: 7.5; radiusY: 7.5; startAngle: 0; sweepAngle: 270 }
        }
    }
}
