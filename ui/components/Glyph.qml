// Picture of a part: "left", "right", "case", "pair". Uses the renders when they exist,
// otherwise the placeholder SVGs.
import QtQuick
import QtQuick.Effects
import ".."

Item {
    id: glyph
    property string part: "case"
    readonly property string file: ({ left: "pod-left", right: "pod-right", "case": "case-small", pair: "pods-pair" })[part] || "case-small"

    Item {
        id: pic
        anchors.fill: parent
        Image {
            id: render
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            source: Paths.hasRenders ? Paths.assets + "renders/" + glyph.file + ".png" : ""
            visible: status === Image.Ready
        }
        Image {
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            smooth: true
            sourceSize: Qt.size(width * 2, height * 2)
            source: Paths.assets + "placeholder/" + glyph.file + ".svg"
            visible: render.status !== Image.Ready
        }
    }

    // white parts on a light background need a soft outline to stay visible
    MultiEffect {
        visible: !Theme.dark
        anchors.fill: pic
        source: pic
        autoPaddingEnabled: true
        shadowEnabled: true
        shadowColor: "#000000"
        shadowOpacity: 0.5
        shadowBlur: 0.3
        shadowVerticalOffset: 1
        shadowHorizontalOffset: 0
    }
    Component.onCompleted: pic.visible = Qt.binding(() => Theme.dark)
}
