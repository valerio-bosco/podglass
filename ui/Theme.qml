// Design tokens from docs/UI.md. Dark by default; PODGLASS_THEME=light|dark, or the daemon config.
pragma Singleton
import QtQuick
import Quickshell

Singleton {
    id: t

    property string mode: Quickshell.env("PODGLASS_THEME") || "auto"
    readonly property bool dark: mode !== "light"
    property bool reduceMotion: Quickshell.env("PODGLASS_REDUCE_MOTION") === "1"

    readonly property color glass: dark ? Qt.rgba(0x1E / 255, 0x1E / 255, 0x20 / 255, 0.72) : Qt.rgba(0xF6 / 255, 0xF6 / 255, 0xF8 / 255, 0.78)
    readonly property color label: dark ? "#FFFFFF" : "#000000"
    readonly property color secondary: dark ? Qt.rgba(0xEB / 255, 0xEB / 255, 0xF5 / 255, 0.6) : Qt.rgba(0x3C / 255, 0x3C / 255, 0x43 / 255, 0.6)
    readonly property color fill: Qt.rgba(0x76 / 255, 0x76 / 255, 0x80 / 255, dark ? 0.24 : 0.12)
    readonly property color hairline: dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.06)
    readonly property color accent: dark ? "#0A84FF" : "#007AFF"
    readonly property color batteryOk: dark ? "#30D158" : "#34C759"
    readonly property color batteryLow: dark ? "#FF453A" : "#FF3B30"
    readonly property color switchOn: batteryOk
    readonly property color shadow: Qt.rgba(0, 0, 0, dark ? 0.35 : 0.18)

    readonly property string font: Quickshell.env("PODGLASS_FONT") || "Inter"

    // sizes: [pixel size, weight]
    readonly property var title: [19, Font.DemiBold]
    readonly property var body: [15, Font.Normal]
    readonly property var button: [17, Font.DemiBold]
    readonly property var small: [13, Font.Normal]
    readonly property var caption: [11, Font.Medium]

    function batteryColor(level) {
        return level !== null && level !== undefined && level <= 20 ? batteryLow : batteryOk;
    }
}
