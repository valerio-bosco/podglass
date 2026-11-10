// Renders every view in every state to PNG files, without a compositor:
//   QT_QPA_PLATFORM=offscreen quickshell -p ui/preview.qml
// Output: docs/screens/<name>.png (or $PODGLASS_SCREENS). PODGLASS_THEME=light for the light set.
import QtQuick
import Quickshell

ShellRoot {
    id: root

    readonly property string outDir: Quickshell.env("PODGLASS_SCREENS")
        || Paths.root + "/docs/screens"
    readonly property string suffix: Theme.dark ? "" : "-light"

    function dev(patch) {
        const d = {
            present: true, connected: false, connecting: false, paired: true, known: true,
            name: "AirPods Pro", model: "pro2-usbc", firmware: "7A305",
            battery: { left: { level: 80, charging: false }, right: { level: 80, charging: false },
                       "case": { level: 60, charging: false }, precise: false },
            inEar: { left: false, right: false }, lid: "open", mode: "anc",
            conversationAwareness: true, adaptiveLevel: 50
        };
        return Object.assign(d, patch);
    }
    readonly property var connected: ({ connected: true, battery: {
        left: { level: 82, charging: false }, right: { level: 80, charging: false },
        "case": { level: 64, charging: true }, precise: true } })

    readonly property var shots: [
        { name: "card-disconnected", view: "card", device: dev({}) },
        { name: "card-connecting", view: "card", device: dev({ connecting: true }) },
        { name: "card-connected", view: "card", device: dev(connected) },
        { name: "card-one-pod", view: "card", device: dev(Object.assign({}, connected, { battery: {
            left: { level: 74, charging: false }, right: { level: null, charging: false },
            "case": { level: 64, charging: true }, precise: true } })) },
        { name: "card-low-battery", view: "card", device: dev(Object.assign({}, connected, { battery: {
            left: { level: 12, charging: false }, right: { level: 9, charging: false },
            "case": { level: 18, charging: false }, precise: true } })) },
        { name: "card-setup", view: "card", kind: "setup", device: dev({ paired: false, known: false }) },
        { name: "card-error", view: "card", error: true, device: dev({}) },
        { name: "popover-anc", view: "popover", device: dev(connected) },
        { name: "popover-adaptive", view: "popover", device: dev(Object.assign({}, connected, { mode: "adaptive", conversationAwareness: false })) },
        { name: "widget", view: "widget", device: dev(connected) },
        { name: "widget-last-seen", view: "widget", device: dev({ present: false }) }
    ]

    property int pending: shots.length

    FloatingWindow {
        implicitWidth: 1800
        implicitHeight: 1200
        visible: true
        color: "black"

        Flow {
            anchors.fill: parent
            Repeater {
                model: root.shots
                Rectangle {
                    id: stage
                    required property var modelData
                    readonly property Item view: loader.item
                    width: (view ? view.width : 300) + 64
                    height: (view ? view.height : 300) + 64
                    // a wallpaper-like background so the glass is visible
                    gradient: Gradient {
                        GradientStop { position: 0; color: Theme.dark ? "#2b3a55" : "#c9d6ea" }
                        GradientStop { position: 1; color: Theme.dark ? "#4a2f45" : "#ead2dc" }
                    }
                    Loader {
                        id: loader
                        x: 32; y: 32
                        sourceComponent: ({ card: cardC, popover: popoverC, widget: widgetC })[stage.modelData.view]
                    }
                    Component { id: cardC; CardView { device: stage.modelData.device; kind: stage.modelData.kind || "normal"; error: !!stage.modelData.error; playing: false } }
                    Component { id: popoverC; PopoverView { device: stage.modelData.device } }
                    Component { id: widgetC; WidgetView { device: stage.modelData.device; lastSeen: "14:32" } }

                    Timer {
                        running: true
                        interval: 1500  // let animations (ring sweep) finish
                        onTriggered: stage.grabToImage(r => {
                            const path = root.outDir + "/" + stage.modelData.name + root.suffix + ".png";
                            console.log((r.saveToFile(path) ? "saved " : "FAILED ") + path);
                            if (--root.pending === 0) Qt.quit();
                        })
                    }
                }
            }
        }
    }
}
