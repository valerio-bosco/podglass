// Absolute paths: Quickshell blocks relative URLs that leave the ui/ directory.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: paths
    readonly property string root: Quickshell.env("PODGLASS_ROOT") || Quickshell.shellDir.toString().replace("file://", "").replace(/\/ui\/?$/, "")
    readonly property string assets: "file://" + root + "/assets/"
    readonly property string tools: root + "/tools/"
    // tools/render writes assets/renders/manifest.json last; until then the placeholders are used
    property bool hasRenders: false

    FileView {
        path: paths.root + "/assets/renders/manifest.json"
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoaded: paths.hasRenders = true
        onLoadFailed: paths.hasRenders = false
    }
}
