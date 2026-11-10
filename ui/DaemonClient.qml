// Connection to the daemon: reads `podglass watch` (JSON lines, docs/PLAN.md 3.1) and sends
// commands with `podglass set ...`. With PODGLASS_DEMO=<scenario> it runs tools/demo_state.py
// instead and writes commands to its stdin.
import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: client

    readonly property string demo: Quickshell.env("PODGLASS_DEMO") || ""
    readonly property string podglass: Quickshell.env("PODGLASS_BIN") || "podglass"
    property var device: ({})
    property var config: ({})
    property bool online: false

    signal event(string name, var data)

    function send(verb, arg) {
        const words = arg === undefined || arg === null ? [verb] : [verb, String(arg)];
        if (demo) {
            proc.write(JSON.stringify({ cmd: words.join(" ") }) + "\n");
        } else {
            Quickshell.execDetached([podglass, "set"].concat(words));
        }
    }

    function handle(line) {
        let msg;
        try { msg = JSON.parse(line); } catch (e) { return; }
        if (msg.type === "state") {
            device = msg.device || {};
            online = true;
        } else if (msg.type === "config") {
            config = msg;
        } else if (msg.type === "event") {
            client.event(msg.name || "", msg);
        }
    }

    Process {
        id: proc
        running: true
        stdinEnabled: client.demo !== ""
        command: client.demo
            ? [Quickshell.env("PODGLASS_PYTHON") || "python3", Paths.tools + "demo_state.py", client.demo]
            : [client.podglass, "watch"]
        stdout: SplitParser { onRead: data => client.handle(data) }
        onExited: { client.online = false; restart.start(); }
    }

    Timer {
        id: restart
        interval: 2000
        onTriggered: proc.running = true
    }
}
