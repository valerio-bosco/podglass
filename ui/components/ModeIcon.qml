// 24 px listening mode icons (from the mockup): off, transparency, adaptive, anc.
import QtQuick
import QtQuick.Shapes

Shape {
    id: icon
    property string mode: "off"
    property color color: "white"
    property color hole: "black"  // background for the ANC inner ring
    width: 24; height: 24
    preferredRendererType: Shape.CurveRenderer

    // off: plain ring
    ShapePath {
        strokeColor: icon.mode === "off" || icon.mode === "adaptive" ? icon.color : "transparent"
        strokeWidth: 2; fillColor: "transparent"
        PathAngleArc { centerX: 12; centerY: 12; radiusX: icon.mode === "off" ? 7.5 : 8; radiusY: radiusX; sweepAngle: 360 }
    }
    // adaptive: right half filled
    ShapePath {
        strokeColor: "transparent"
        fillColor: icon.mode === "adaptive" ? icon.color : "transparent"
        startX: 12; startY: 4
        PathArc { x: 12; y: 20; radiusX: 8; radiusY: 8 }
        PathLine { x: 12; y: 4 }
    }
    // transparency: dot and dashed ring
    ShapePath {
        strokeColor: "transparent"
        fillColor: icon.mode === "transparency" ? icon.color : "transparent"
        PathAngleArc { centerX: 12; centerY: 12; radiusX: 4; radiusY: 4; sweepAngle: 360 }
    }
    ShapePath {
        strokeColor: icon.mode === "transparency" ? icon.color : "transparent"
        strokeWidth: 2; fillColor: "transparent"
        strokeStyle: ShapePath.DashLine
        dashPattern: [1.5, 1.55]
        PathAngleArc { centerX: 12; centerY: 12; radiusX: 9; radiusY: 9; sweepAngle: 360 }
    }
    // anc: filled disc with an inner ring
    ShapePath {
        strokeColor: "transparent"
        fillColor: icon.mode === "anc" ? icon.color : "transparent"
        PathAngleArc { centerX: 12; centerY: 12; radiusX: 9; radiusY: 9; sweepAngle: 360 }
    }
    ShapePath {
        strokeColor: icon.mode === "anc" ? icon.hole : "transparent"
        strokeWidth: 2; fillColor: "transparent"
        PathAngleArc { centerX: 12; centerY: 12; radiusX: 4.5; radiusY: 4.5; sweepAngle: 360 }
    }
}
