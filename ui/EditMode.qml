// Edit mode: drag the podglass windows to new places (docs/UI.md "Edit mode").
import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland
import "components"

PanelWindow {
    id: win

    required property var layout
    property bool active: false
    property var sizes: ({})  // name -> {w, h, label}

    signal done(var positions)  // name -> {anchor, dx, dy} for this screen
    signal cancelled()

    readonly property int grid: 8
    readonly property int edge: 24
    readonly property int snap: 12
    property var guidesX: []
    property var guidesY: []

    screen: Quickshell.screens[0]
    visible: active
    color: "transparent"
    WlrLayershell.namespace: "podglass-edit"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: active ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    anchors { top: true; bottom: true; left: true; right: true }

    onActiveChanged: if (active) { reset(false); root.forceActiveFocus(); }

    function reset(toDefaults) {
        for (let i = 0; i < ghosts.count; i++) {
            const g = ghosts.itemAt(i);
            const p = toDefaults ? layout.defaultPlace(g.name, g.width, g.height, screen)
                                 : layout.place(g.name, g.width, g.height, screen);
            g.x = p.x;
            g.y = p.y;
        }
        guidesX = [];
        guidesY = [];
    }

    function finish() {
        const out = {};
        for (let i = 0; i < ghosts.count; i++) {
            const g = ghosts.itemAt(i);
            out[g.name] = layout.fromXY(g.x, g.y, g.width, g.height, root.width, root.height);
        }
        done(out);
    }

    // snap one axis: grid first, then guides at the center line and 24 px from the edges
    function snapAxis(pos, size, total, guides) {
        let p = Math.round(pos / grid) * grid;
        const targets = [
            { at: total / 2, p: total / 2 - size / 2 },       // center on the center line
            { at: edge, p: edge },                            // near edge
            { at: total - edge, p: total - edge - size }      // far edge
        ];
        for (const t of targets) {
            const value = t.at === total / 2 ? pos + size / 2 : (t.at === edge ? pos : pos + size);
            if (Math.abs(value - t.at) <= snap) { p = t.p; guides.push(t.at); break; }
        }
        return Math.max(0, Math.min(total - size, p));
    }

    Item {
        id: root
        anchors.fill: parent
        focus: true
        Keys.onEscapePressed: win.cancelled()
        Keys.onReturnPressed: win.finish()

        Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, 0.45) }

        // snap guides
        Repeater {
            model: win.guidesX
            Rectangle { required property real modelData; x: modelData; width: 1; height: root.height; color: Theme.accent }
        }
        Repeater {
            model: win.guidesY
            Rectangle { required property real modelData; y: modelData; height: 1; width: root.width; color: Theme.accent }
        }

        Repeater {
            id: ghosts
            model: Object.keys(win.sizes)
            Item {
                id: ghost
                required property string modelData
                readonly property string name: modelData
                readonly property var info: win.sizes[name]
                width: info.w
                height: info.h

                Rectangle {
                    anchors.fill: parent
                    radius: ghost.info.radius || 24
                    color: Qt.rgba(1, 1, 1, drag.pressed ? 0.12 : 0.06)
                }
                Shape {
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        fillColor: "transparent"
                        strokeColor: Qt.rgba(1, 1, 1, 0.7)
                        strokeWidth: 2
                        strokeStyle: ShapePath.DashLine
                        dashPattern: [4, 3]
                        PathRectangle { x: 1; y: 1; width: ghost.width - 2; height: ghost.height - 2; radius: ghost.info.radius || 24 }
                    }
                }
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.top
                    anchors.bottomMargin: 6
                    width: chip.implicitWidth + 16
                    height: 22
                    radius: 11
                    color: Qt.rgba(1, 1, 1, 0.85)
                    Label { id: chip; anchors.centerIn: parent; style: Theme.caption; color: "#000000"; text: ghost.info.label }
                }
                MouseArea {
                    id: drag
                    anchors.fill: parent
                    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    property point grab
                    onPressed: mouse => grab = Qt.point(mouse.x, mouse.y)
                    onPositionChanged: mouse => {
                        const p = mapToItem(root, mouse.x, mouse.y);
                        const gx = [], gy = [];
                        ghost.x = win.snapAxis(p.x - grab.x, ghost.width, root.width, gx);
                        ghost.y = win.snapAxis(p.y - grab.y, ghost.height, root.height, gy);
                        win.guidesX = gx;
                        win.guidesY = gy;
                    }
                    onReleased: { win.guidesX = []; win.guidesY = []; }
                }
            }
        }

        // toolbar
        Glass {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 24
            width: bar.implicitWidth + 24
            height: 44
            radius: 22
            Row {
                id: bar
                anchors.centerIn: parent
                spacing: 8
                Label { anchors.verticalCenter: parent.verticalCenter; style: Theme.small; color: Theme.secondary; text: Strings.dragToPlace; rightPadding: 8 }
                Repeater {
                    model: [[Strings.reset, false, () => win.reset(true)], [Strings.cancel, false, () => win.cancelled()],
                            [Strings.done, true, () => win.finish()]]
                    Rectangle {
                        required property var modelData
                        anchors.verticalCenter: parent.verticalCenter
                        width: lbl.implicitWidth + 24
                        height: 30
                        radius: 15
                        color: modelData[1] ? Theme.accent : Theme.fill
                        Label { id: lbl; anchors.centerIn: parent; style: [13, Font.DemiBold]; color: parent.modelData[1] ? "#FFFFFF" : Theme.label; text: parent.modelData[0] }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: parent.modelData[2]() }
                    }
                }
            }
        }
    }
}
