// Text with the theme font. `style` is one of the Theme size pairs, e.g. Theme.body.
import QtQuick
import ".."

Text {
    property var style: Theme.body
    property bool tabular: false
    color: Theme.label
    font.family: Theme.font
    font.pixelSize: style[0]
    font.weight: style[1]
    font.features: tabular ? { "tnum": 1 } : {}
    renderType: Text.NativeRendering
}
