// podglass UI: proximity card, listening popover, battery widget and edit mode.
// Run: quickshell -p ui/shell.qml   (PODGLASS_DEMO=<scenario> runs without the daemon)
// IPC: quickshell -p ui/shell.qml ipc call podglass showCard | togglePopover | edit
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    id: shell

    property string cardKind: ""  // "" = hidden, normal, setup
    property bool cardError: false
    property bool popoverOpen: false
    property bool editing: false
    readonly property bool widgetEnabled: daemon.config.batteryWidget === true
        || Quickshell.env("PODGLASS_WIDGET") === "1" || daemon.demo === "widget"

    DaemonClient {
        id: daemon
        onEvent: (name, data) => {
            if (name === "show-card") { shell.cardKind = data.card || "normal"; shell.cardError = false; }
            else if (name === "hide-card") shell.cardKind = "";
            else if (name === "connect-failed") { shell.cardError = true; if (shell.cardKind === "") shell.cardKind = "normal"; }
            else if (name === "connected") shell.cardError = false;
            else if (name === "popover") shell.popoverOpen = true;
            else if (name === "edit") shell.editing = true;
        }
        onDeviceChanged: if (device.connecting) shell.cardError = false
        onConfigChanged: {
            if (config.theme) Theme.mode = config.theme;
            if (config.reduceMotion !== undefined) Theme.reduceMotion = !!config.reduceMotion;
        }
    }

    Layout { id: layout }

    ProximityCard {
        id: card
        layout: layout
        shown: shell.cardKind !== "" && !shell.editing
        kind: shell.cardKind || "normal"
        device: daemon.device
        error: shell.cardError
        onConnectClicked: { shell.cardError = false; daemon.send("connect"); }
        onDismissed: { shell.cardKind = ""; daemon.send("dismiss-card"); }
        onEditRequested: shell.editing = true
        onSettingsRequested: Quickshell.execDetached(["xdg-open", (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/podglass/config.toml"])
    }

    ListeningPopover {
        layout: layout
        open: shell.popoverOpen && !shell.editing
        device: daemon.device
        onClosed: shell.popoverOpen = false
        onCommand: (verb, arg) => daemon.send(verb, arg)
    }

    LazyLoader {
        active: shell.widgetEnabled && !shell.editing
        BatteryWidget { layout: layout; device: daemon.device }
    }

    EditMode {
        layout: layout
        active: shell.editing
        sizes: {
            const s = {
                card: { w: 360, h: 410, radius: 38, label: Strings.card },
                popover: { w: 320, h: 360, radius: 26, label: Strings.popover }
            };
            if (shell.widgetEnabled) s.widget = { w: 340, h: 160, radius: 24, label: Strings.widget };
            return s;
        }
        onCancelled: shell.editing = false
        onDone: positions => {
            const all = JSON.parse(JSON.stringify(layout.saved || {}));
            const name = Quickshell.screens[0].name;
            all[name] = Object.assign(all[name] || {}, positions);
            layout.saved = all;  // apply now; the daemon writes layout.json
            daemon.send("layout", JSON.stringify(all));
            shell.editing = false;
        }
    }

    IpcHandler {
        target: "podglass"
        function showCard(): void { shell.cardKind = "normal"; }
        function hideCard(): void { shell.cardKind = ""; }
        function togglePopover(): void { shell.popoverOpen = !shell.popoverOpen; }
        function edit(): void { shell.editing = true; }
    }
}
