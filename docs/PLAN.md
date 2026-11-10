# podglass - implementation plan

podglass makes AirPods Pro 2 behave on this NixOS desktop (Hyprland + serpantinum bar on
Quickshell) the way they behave on an iPhone:

- open the case lid near the PC -> a card slides up with a 3D render of the case and pods, battery
  of left pod, right pod and case, and a Connect button (or it connects by itself, see policy);
- put the pods in your ears -> audio connects without touching Bluetooth settings;
- while connected, an icon sits in the bar tray; clicking it opens a popover with battery and the
  listening mode (Off / Transparency / Adaptive / Noise Cancellation) and Conversation Awareness;
- an optional battery widget on the desktop;
- an edit mode to drag the card and the widget anywhere on screen.

Mockups: see the published mockup page (link in README.md) and `docs/UI.md` (exact sizes, colors,
motion). Protocol: `docs/PROTOCOL.md`. Agent rules: `AGENTS.md`.

---

## 0. How to use this plan (for agents)

- Do **one task** per session. Read `AGENTS.md`, this section, the task, and only the files listed
  in its "Read" line.
- Every task has: **Model** (who should run it), **Depends**, **Read**, **Do**, **Done when**
  (commands that must pass), and sometimes **Human check** (stop and ask the user; never fake it).
- When done: tick the box in this file, commit (Conventional Commits, English), and write 3-5 lines
  in `docs/LOG.md` (what you did, what you could not verify, surprises).
- If a task turns out bigger than described, stop and write the problem in `docs/LOG.md` instead of
  improvising architecture.

Model legend:
- **Haiku**: pure code with tests and fixtures given; no I/O, no async, no UI.
- **Sonnet**: I/O, asyncio, D-Bus, QML, Nix, Blender scripting.
- **Opus / user**: gates (review a spike, approve renders, change system config).

---

## 1. Fixed decisions

| Topic | Decision | Why |
|---|---|---|
| Daemon language | Python 3 (asyncio) | same stack as oring; all libs in nixpkgs (`bleak`, `dbus-fast`, `cryptography`); cheap agents handle it well |
| UI | separate Quickshell config, run as its own process (like oring) | Quickshell already runs; layer-shell windows; QML is easy to iterate |
| Bar integration | StatusNotifierItem tray icon published by the daemon | serpantinum's bar has no plugin API but shows the tray (`tray` module is enabled); no fork needed |
| Daemon <-> UI | daemon serves JSON lines on `$XDG_RUNTIME_DIR/podglass.sock`; UI runs `podglass watch` (stdout stream) and `podglass set ...` | simplest thing QML can consume (`Process` + `SplitParser`) |
| UI -> UI | Quickshell `IpcHandler` target `podglass` (`toggle-popover`, `show-card`, `edit`) | tray click and keybinds reuse it |
| 3D | pre-rendered with Blender (Cycles) to animated WebP + PNG stills; no realtime 3D | photoreal quality, no GPU cost in the shell, trivial in QML |
| Font | Inter (closest free font to the iOS system font; SF Pro may not be used on Linux) | license |
| Settings | `~/.config/podglass/config.toml` (user), `~/.config/podglass/layout.json` (written by edit mode), keys in `$XDG_STATE_HOME/podglass/keys.json` (0600) | |
| Packaging | flake with `packages.default`, `homeManagerModules.default` (systemd user service + Quickshell autostart + Hyprland layer rules) | same pattern as `~/Projects/oring` |

## 2. Open decisions (the user decides; agents must not)

| Id | Question | Answer |
|---|---|---|
| D1 | 3D model source | **Answered 2026-11-09:** model it ourselves in Blender; if that does not reach the look, fall back to a model found online (free or bought). P3.0 changes from "get the model" to "build the model". |
| D2 | License | **Answered 2026-11-09:** GPL-3.0-or-later (LICENSE). LibrePods code may be ported, with credit in the file header. |
| D3 | Auto-connect default: `in-ear` / `lid-open` / `never` | **Answered 2026-11-09:** `in-ear` |
| D4 | UI language: English / Italian | **Answered 2026-11-09:** English (strings in one file, `ui/Strings.qml`) |

## 3. Architecture

```
          BLE adverts (lid, coarse battery, in-ear)          AAP over L2CAP 0x1001 (exact battery,
  AirPods ───────────────────────────────┐                  mode, ear, keys) - only when connected
          ───────────────────────────────┼──────────────────────────────┐
                                         v                              v
                               podglass/scanner.py            podglass/aap_session.py
                                         │                              │
                                         └──────────┬───────────────────┘
                                                    v
     BlueZ (D-Bus) <── podglass/bluez.py <── podglass/policy.py (pure state machine) ──> media.py
     Connect(), BatteryProvider                     │                                    (playerctl, wpctl)
                                                    v
                                         podglass/ipc.py  (unix socket, JSON lines)
                                          │                 │
                         podglass/tray.py │                 │ `podglass watch` / `podglass set`
                   (SNI icon in the bar)  │                 v
                                          └──> Quickshell UI (ui/): ProximityCard, Popover,
                                               BatteryWidget, EditMode
```

Repository layout (create exactly this):

```
podglass/
  flake.nix  pyproject.toml  README.md  AGENTS.md  CLAUDE.md  .gitignore
  podglass/
    __init__.py  __main__.py     # CLI entry (argparse)
    crypto.py                    # ah(), resolve_rpa(), decrypt_payload()        (pure)
    adv.py                       # parse_advert(bytes, rssi, addr) -> Advert     (pure)
    aap.py                       # packet builders + parse_packet() -> AapEvent  (pure)
    state.py                     # DeviceState dataclass, merge(), to_json()     (pure)
    policy.py                    # Policy.step(event, now) -> list[Action]       (pure)
    config.py                    # load config.toml with defaults               (pure-ish)
    keys.py                      # keys.json read/write, 0600
    scanner.py  aap_session.py  bluez.py  media.py  tray.py  ipc.py  daemon.py
  ui/
    shell.qml  Theme.qml  Strings.qml  DaemonClient.qml
    ProximityCard.qml  ListeningPopover.qml  BatteryWidget.qml  EditMode.qml
    components/ BatteryRing.qml  ModeButton.qml  Toggle.qml  Render.qml
  assets/
    placeholder/  case-open.svg  case-closed.svg  pod-left.svg  pod-right.svg  (committed)
    renders/      (generated, gitignored)        models/ (bought model, gitignored)
  tools/
    capture_ble.py  capture_aap.py  demo_state.py
    render/ render.py  shots.toml
  tests/
    fixtures/  adv/*.jsonl  aap/*.jsonl
    test_crypto.py  test_adv.py  test_aap.py  test_state.py  test_policy.py  test_ipc.py
  nix/ package.nix  hm-module.nix
  docs/ PLAN.md  PROTOCOL.md  UI.md  SPIKE.md  LOG.md
```

### 3.1 State contract (daemon -> UI)

Every line on the socket / `podglass watch` stdout is one JSON object. The UI must tolerate
missing keys.

```json
{"type": "state",
 "device": {
   "present": true,                 // seen by BLE in the last 10 s, or connected
   "connected": true,               // BlueZ Device1.Connected
   "connecting": false,
   "paired": true,                  // known to BlueZ
   "known": true,                   // keys.json has it (RPA resolvable)
   "name": "AirPods Pro", "model": "pro2-usbc", "firmware": "7A305",
   "battery": {
     "left":  {"level": 82, "charging": false},   // level null = unknown / not in reach
     "right": {"level": 80, "charging": false},
     "case":  {"level": 64, "charging": true},
     "precise": true                              // false = 10 % steps from BLE
   },
   "inEar": {"left": true, "right": true},
   "inCase": {"left": false, "right": false},
   "lid": "open",                   // open | closed | unknown
   "mode": "anc",                   // off | transparency | adaptive | anc | null
   "conversationAwareness": true,
   "adaptiveLevel": 50
 }}
{"type": "event", "name": "lid-opened"}      // also: lid-closed, connected, disconnected,
                                             // ear-in, ear-out, connect-failed, setup-available
```

Commands (`podglass set ...`, and the same verbs as `{"cmd": ...}` lines on the socket):
`connect`, `disconnect`, `mode <off|transparency|adaptive|anc>`, `ca <on|off>`,
`adaptive-level <0-100>`, `dismiss-card`.

### 3.2 Policy (what happens when) - implemented in `policy.py`, table-tested

| Input | Condition | Actions |
|---|---|---|
| advert from my AirPods, lid open (rising edge) | always | `show_card` |
| advert with lid closed, or no advert for 8 s (adverts stop when the lid closes; gaps up to 5 s happen with the lid open) | card visible | `hide_card` after 1.5 s |
| lid open, not connected | `autoconnect == "lid-open"` and AirPods not busy with another device (busy = decrypted host tail is not this PC and byte 0 is `05`, PROTOCOL.md 1.3) | `connect` |
| advert, any pod in ear, not connected | `autoconnect in ("in-ear","lid-open")`, not busy elsewhere, a local input event in the last 10 min (user is at this PC) | `connect` |
| advert from unknown AirPods in pairing mode, RSSI > -55 | not shown in the last 5 min | `show_card(setup)` |
| AAP ear: a pod removed while playing | `ear_pause` setting (default on) | `pause_media`; on reinsert within 60 s `resume_media` |
| AAP conversation awareness 01/02 | setting on | `duck_volume`; on 03/08/09 `restore_volume` |
| connect fails | | event `connect-failed`, card shows "Couldn't connect. Try again" |
| BlueZ Connected true | | `start_aap`, tray icon visible |
| BlueZ Connected false | | `stop_aap`, tray icon hidden |

Extra rules added in P1.6 (not in the table above, needed in practice): after `connect-failed`
no automatic connect for 30 s; after a user `disconnect` no automatic connect until both pods
leave the ears or the lid closes; `card_timeout_s > 0` hides the card after that time; the
"busy elsewhere" rule is defined by GATE 0 (2026-11-10): see task P1.8.

The policy is a pure class: `Policy(config).step(event: Event, now: float) -> list[Action]`. No
I/O inside. Every row above is one test in `tests/test_policy.py`.

### 3.3 Windows (Quickshell, all `PanelWindow` on layer-shell)

| Window | Layer | Default place | Namespace (for Hyprland layer rules) |
|---|---|---|---|
| ProximityCard | Overlay | bottom center, 24 px from the bottom | `podglass-card` |
| ListeningPopover | Overlay | top right, 8 px under the bar, right edge 12 px | `podglass-popover` |
| BatteryWidget (optional) | Bottom (desktop) | bottom left, 24 px margins | `podglass-widget` |
| EditMode | Overlay, full screen, keyboard exclusive | | `podglass-edit` |

Hyprland rules (added by the HM module): `layerrule = blur, podglass-.*` and
`layerrule = ignorealpha 0.3, podglass-.*` so the glass blur works.

Positions are stored as `{monitor: {window: {anchor: "bottom-center", dx, dy}}}` in `layout.json`
and applied as layer-shell anchors + margins, so they survive resolution changes.

---

## 4. Phases and tasks

### Phase 0 - spike on the real hardware (blocks everything that touches Bluetooth)

The AirPods are **not paired** with this PC yet (checked 2026-11-09: `bluetoothctl devices` lists
MX Keys Mini, WH-1000XM4, MOMENTUM 4, Hue). Adapter: Realtek (manufacturer 93), BlueZ 5.87,
`AdvertisementMonitorManager1` not exposed (experimental features off).

- [x] **P0.1 Prepare the BlueZ setting** - Model: Sonnet - Depends: - - Read: `/etc/nixos/configuration.nix`
  - Do: write the exact snippet `hardware.bluetooth.settings.General.Experimental = true;` (and where
    it goes) into `docs/SPIKE.md`. **Do not edit /etc/nixos.**
  - Human check: the user adds it and runs `sudo nixos-rebuild switch`; then
    `busctl introspect org.bluez /org/bluez/hci0 | grep AdvertisementMonitorManager1` prints a line.
- [x] **P0.2 BLE capture tool** - Model: Sonnet - Depends: P1.1 - Read: PROTOCOL.md section 1
  - Do: `tools/capture_ble.py --label <text> --seconds N --out tests/fixtures/adv/<label>.jsonl`:
    bleak scanner, keep only Apple `0x004C` payloads starting with `07`, write
    `{"t", "addr", "rssi", "hex", "label"}` per line. Try passive mode (BlueZ advertisement monitor
    with or-pattern `0x004C 07`) first, fall back to active with a printed warning.
  - Done when: `python tools/capture_ble.py --help` works; a 10 s run with no AirPods writes an empty file.
  - Human check: the user runs the capture script in `docs/SPIKE.md` (10 labeled steps: case closed,
    lid open, lid open with one pod out, both pods in ears, one pod out of ear, case charging, lid
    closed, AirPods playing on the iPhone, in a call on the iPhone, far away).
- [x] **P0.3 Pair + AAP capture** - Model: Sonnet - Depends: P0.2 - Read: PROTOCOL.md section 2
  - Do: `tools/capture_aap.py <MAC>`: L2CAP connect to PSM 0x1001, send the startup sequence, log
    every packet both ways to `tests/fixtures/aap/session-<date>.jsonl`, interactive keys
    `1 2 3 4` = set mode off/anc/transparency/adaptive, `k` = request keys, `q` = quit. Keys found
    go to `keys.json`.
  - Human check: pairing (hold the case button until the light flashes white, then
    `bluetoothctl scan on; pair <MAC>; trust <MAC>; connect <MAC>`), run the tool, press every key,
    take pods out/in, listen that ANC really changes.
- [x] **P0.4 Read the captures** - Model: Sonnet - Depends: P0.2, P0.3 - Read: fixtures, PROTOCOL.md
  - Do: in `docs/SPIKE.md` write, from the data: which lid bit value means open; the values of
    the connection-state byte (offset 10) for: idle, playing on iPhone, call on iPhone, connected to
    this PC; whether adverts continue while connected to the PC; pairs (decrypted payload, AAP exact
    battery). Fix PROTOCOL.md where it was wrong.
- [x] **P0.5 Audio stutter test** - Model: user - Depends: P0.1, P0.3
  - Play music on the AirPods from the PC for 2 min with `capture_ble.py` running in passive mode,
    then 2 min in active mode. Note any dropouts in SPIKE.md. Decides `scanner.py` strategy:
    passive always / active only while not streaming.
- [x] **GATE 0** - Model: Opus or user - review SPIKE.md, update PROTOCOL.md and section 3.2 if the
  data contradicts them. Nothing in phase 2 starts before this box is ticked.

### Phase 1 - pure core (can run in parallel with phase 0 after P1.1)

- [x] **P1.1 Scaffold** - Model: Sonnet - Depends: - - Read: section 3, `~/Projects/oring/flake.nix` (pattern only)
  - Do: create the layout of section 3 (empty modules with docstrings), `pyproject.toml`
    (console script `podglass = podglass.__main__:main`), `flake.nix` with devShell
    (`python3.withPackages [bleak dbus-fast cryptography pytest]`, `quickshell`, `playerctl`,
    `libwebp`, `blender` only in a separate `devShells.render`), `checks.tests` running pytest,
    `.gitignore` (`assets/renders/`, `assets/models/`, `__pycache__`, `result`).
  - Done when: `nix develop -c pytest -q` exits 0 (no tests yet is fine: use `-q || [ $? = 5 ]`),
    `nix flake check` passes.
- [x] **P1.2 crypto.py** - Model: Haiku - Depends: P1.1 - Read: PROTOCOL.md 1.1, 1.3
  - Do: `ah(irk: bytes, prand: bytes) -> bytes`, `resolve_rpa(addr: str, irk: bytes) -> bool`,
    `decrypt_payload(payload16: bytes, key: bytes) -> bytes` using `cryptography`.
  - Done when: `pytest tests/test_crypto.py` passes, including the Core Spec vector, a non-RPA
    address (top bits != 01) returning False, and wrong key sizes raising `ValueError`.
- [x] **P1.3 adv.py** - Model: Haiku - Depends: P1.1 (fixtures from P0.2 when available) - Read: PROTOCOL.md 1
  - Do: frozen dataclass `Advert(addr, rssi, model, paired, primary_left, left, right, case,
    left_charging, right_charging, case_charging, left_in_ear, right_in_ear, lid_open, lid_known,
    lid_counter, conn_state, encrypted)`; `parse_advert(data: bytes, rssi: int, addr: str) -> Advert | None`
    (None for non-07, short, or pairing-mode payloads; pairing-mode returns
    `Advert(paired=False, ...)` with only model filled).
  - Done when: tests cover both primary sides, 15 = unknown, every status bit, short input; once
    P0 fixtures exist, every fixture line parses without exception.
- [x] **P1.4 aap.py** - Model: Haiku - Depends: P1.1 - Read: PROTOCOL.md 2
  - Do: constants for the startup packets; `set_mode(mode: str) -> bytes`, `set_ca(on) -> bytes`,
    `set_adaptive_level(n) -> bytes`, `request_keys() -> bytes`;
    `parse_packet(b: bytes) -> AapEvent | None` with event classes `Battery`, `Ear`, `Mode`,
    `ConversationAwareness`, `CaVolume`, `Keys`, `DeviceInfo`, `Ack`, `Unknown(opcode, raw)`.
  - Done when: every example packet in PROTOCOL.md round-trips in tests; garbage input never raises.
- [x] **P1.5 state.py** - Model: Haiku - Depends: P1.3, P1.4 - Read: section 3.1
  - Do: `DeviceState` dataclass; `apply_advert(state, adv)`, `apply_aap(state, event)` (AAP values win
    over BLE values while connected; `precise` follows the source), `to_json(state) -> str` matching
    section 3.1 exactly.
  - Done when: tests for merge precedence and a golden JSON test.
- [x] **P1.6 policy.py** - Model: Sonnet - Depends: P1.5 - Read: section 3.2
  - Do: as described in 3.2, with an injectable clock.
  - Done when: one test per table row plus: no `connect` while `connecting`; no second `show_card`
    while the lid stays open; `hide_card` cancelled if the lid reopens within 1.5 s.
- [x] **P1.7 config.py + keys.py** - Model: Haiku - Depends: P1.1
  - Do: config keys and defaults: `autoconnect = "in-ear"`, `ear_pause = true`,
    `ca_duck = false` (user choice 2026-11-10), `ca_duck_volume = 0.3`, `battery_widget = false`, `card_timeout_s = 0`
    (0 = stay while lid open), `theme = "auto"`. keys.json written atomically with mode 0600.
  - Done when: tests with a temp dir; unknown config keys are ignored with a warning.

- [x] **P1.8 Policy update after GATE 0** - Model: Sonnet - Read: SPIKE.md "Policy changes",
  PROTOCOL.md 1.3, `podglass/policy.py`, `podglass/state.py`
  - Do: feed `adv.parse_precise` into state (exact battery without connection, `precise: true`);
    policy: busy elsewhere = `host_tail != adapter tail and busy`; lid closed also after 3 s of
    advert silence; `adapter_tail` as a Policy constructor argument.
  - Done when: tests for each new rule pass, `nix develop -c pytest -q` green.

### Phase 2 - daemon (after GATE 0)

- [x] **P2.1 bluez.py** - Model: Sonnet - Read: PROTOCOL.md 3
  - Do: `dbus-fast` client: find the AirPods `Device1`, watch `Connected`, `connect()` with 15 s
    timeout, `disconnect()`, `BatteryProvider1` export of the lowest pod level.
  - Done when: `podglass debug bluez` prints the device path and connected state.
  - Human check: `podglass debug bluez --connect` connects the AirPods and audio plays.
- [x] **P2.2 scanner.py** - Model: Sonnet - Read: SPIKE.md (strategy), adv.py, crypto.py
  - Do: async generator of `Advert` for **my** AirPods only (resolved with keys.json), plus
    pairing-mode adverts; dedupe identical payloads within 1 s; strategy from SPIKE.md.
- [x] **P2.3 aap_session.py** - Model: Sonnet - Read: PROTOCOL.md 2, aap.py
  - Do: asyncio wrapper over the L2CAP socket (`loop.sock_recv`), startup sequence with 3 s
    timeouts, reconnect with backoff while BlueZ says connected, `send(bytes)`, async iterator of
    `AapEvent`. Store keys on first `Keys` event.
- [x] **P2.4 ipc.py + CLI** - Model: Sonnet (ipc), Haiku (CLI verbs) - Read: section 3.1
  - Do: unix socket server broadcasting the latest state on connect and on every change; CLI verbs
    `daemon`, `watch`, `status`, `set ...`, `show-card`, `popover`, `edit`, `debug bluez|scan|aap`.
    `show-card`/`popover`/`edit` call `quickshell ipc -p <ui path> call podglass <fn>`.
  - Done when: `tests/test_ipc.py` runs a server with a fake state and a client in the same loop.
- [x] **P2.5 media.py** - Model: Haiku - Do: `pause()`, `resume()` via `playerctl` (remember which
  players were playing), `duck(v)`/`restore()` via `wpctl set-volume @DEFAULT_AUDIO_SINK@`.
  Done when: tests with a fake runner (subprocess calls injected).
- [x] **P2.6 tray.py** - Model: Sonnet
  - Do: StatusNotifierItem on the session bus (`org.kde.StatusNotifierItem-<pid>-1`, register with
    `org.kde.StatusNotifierWatcher`), `IconPixmap` = 22 px pods glyph with a small battery arc,
    `ToolTip` = "AirPods Pro - L 82% R 80% Case 64%", `Activate` -> `podglass popover`,
    `ContextMenu`/menu: the 4 modes, Disconnect, Edit layout. Registered only while connected.
  - Human check: the icon appears in the serpantinum tray when the AirPods connect and leaves when
    they disconnect; click opens the popover.
- [ ] **P2.7 daemon.py** - Model: Sonnet - wire scanner + aap + bluez + policy + ipc + tray + media.
  - Done when: `podglass daemon --fake tests/fixtures/adv/lid-open.jsonl` replays a capture and
    `podglass watch` shows the state changing; real run documented in LOG.md.

### Phase 3 - renders (needs D1)

- [ ] **P3.0 Build the model** - Model: user + Sonnet (Blender) - per D1, model the case and pods in
  Blender from reference photos and save `assets/models/airpods-pro2-usbc.blend`; fallback: a model
  found online (glb, fbx, blend or usdz) in the same folder.
  Requirements: AirPods Pro 2 **USB-C** case (speaker grille on the bottom, lanyard loop on the right
  side), lid as a separate object, pods as separate objects, PBR materials.
- [ ] **P3.1 render.py** - Model: Sonnet - Read: docs/UI.md "Renders", `tools/render/shots.toml`
  - Do: Blender headless script (`nix develop .#render -c blender -b -P tools/render/render.py --
    --model assets/models/<file> --shot all`): import, center and scale to 1 unit, white-studio
    lighting (key area light 45 deg left-top, fill right, rim back, soft shadow catcher), transparent
    film, Cycles 256 samples + denoise, AgX view. Shots from `shots.toml` (object names, hinge axis
    and angle, camera). Output PNG frames to `assets/renders/<shot>/`, then `img2webp -lossy -q 90
    -d 33` into `assets/renders/<shot>.webp`.
  - Shots: `case-open` (48 frames, lid 0 -> 100 deg, camera 3/4 front 15 deg above, 2x size 560 px),
    `idle` (120 frames, slow +-8 deg yaw loop on the open case), stills `case-closed`, `pod-left`,
    `pod-right`, `pods-pair`, `case-small` (128 px and 256 px for rings, tray and widget).
- [ ] **P3.2 Look approval** - Model: user (+ Sonnet tweaking `shots.toml` only) - compare the
  stills with photos of the real AirPods next to the screen. Iterate on lights, roughness of the
  white plastic, the grey of the mesh, the steel of the hinge. Until approved, the UI uses
  `assets/placeholder/*.svg`.

### Phase 4 - UI (can start after P1.1 using `tools/demo_state.py`)

- [x] **P4.0 demo_state.py** - Model: Haiku - prints state JSON lines for scripted scenarios
  (`lid-open-disconnected`, `connecting`, `connected`, `low-battery`, `one-pod`, `setup`) with
  delays, so the UI can be built without hardware: `podglass watch` is replaced by it when
  `PODGLASS_DEMO=<scenario>` is set.
- [x] **P4.1 shell skeleton** - Model: Sonnet - Read: docs/UI.md, section 3.3, `~/Projects/oring/ui/shell.qml` (pattern)
  - Do: `shell.qml`, `Theme.qml` (singleton, tokens from UI.md, light/dark), `Strings.qml`,
    `DaemonClient.qml` (Process + SplitParser, exposes `state` and `send(cmd)`), `IpcHandler`
    target `podglass` with `showCard()`, `togglePopover()`, `edit()`.
  - Done when: `quickshell -p ui/shell.qml` starts with no QML warnings in the log.
- [x] **P4.2 ProximityCard.qml** - Model: Sonnet - Read: docs/UI.md "Card"
  - States: `setup`, `disconnected` (Connect button), `connecting` (spinner), `connected` (rings),
    `error`. Render on top (`Render.qml` picks webp or placeholder svg). Enter/exit animation.
  - Done when (verification without hardware): for each demo scenario,
    `PODGLASS_DEMO=<s> quickshell -p ui/shell.qml & sleep 3; grim docs/screens/card-<s>.png`.
  - Human check: compare screenshots with the mockup page.
- [x] **P4.3 ListeningPopover.qml** - Model: Sonnet - Read: docs/UI.md "Popover"
  - Close on outside click (`HyprlandFocusGrab`) and on Esc. Mode buttons send `set mode`; the
    selected state follows the daemon echo, not the click (optimistic highlight for max 2 s).
- [x] **P4.4 BatteryWidget.qml** - Model: Sonnet - only when `battery_widget = true`.
- [ ] **P4.5 EditMode.qml** - Model: Sonnet - Read: docs/UI.md "Edit mode"
  - Full-screen dim, ghost of card/widget/popover, drag with 8 px grid and snap guides at edges and
    centers (12 px threshold), toolbar Reset / Cancel / Done, writes `layout.json` (via
    `podglass set layout <json>` so the daemon owns the file). Entered from the tray menu, the
    card's right-click menu, or `podglass edit`.

### Phase 5 - package and install

- [ ] **P5.1 nix/package.nix + hm-module.nix** - Model: Sonnet - Read: `~/Projects/oring/nix/*` (pattern)
  - Options: `programs.podglass.{enable, settings, batteryWidget}`; creates the systemd user service
    `podglass.service` (after `bluetooth.target`, `graphical-session.target`), starts the Quickshell
    UI via `exec-once` or a second user service, adds the Hyprland layer rules.
- [ ] **P5.2 System integration** - Model: user (Sonnet prepares the diff in LOG.md)
  - Add `podglass` as a flake input in `/etc/nixos/flake.nix` the same way as oring
    (`url = "path:/home/voodoo/Projects/podglass"`), enable the HM module, rebuild.
- [ ] **P5.3 End-to-end check** - Model: user, checklist in section 5.

### Phase 6 - later

Exact battery from the encrypted advert (after P0.4 finds the layout); low battery notifications
(20 % and 10 %, once per charge cycle); other models (AirPods 4, Max); stem long-press settings;
case charging sound toggle; head-tracking: out of scope.

---

## 5. End-to-end checklist (P5.3)

1. AirPods in the closed case, PC unlocked. Open the lid: the card appears in < 2 s at the saved
   position, with the lid-open animation and three battery values.
2. Autoconnect `in-ear`: put the pods in: audio is connected in < 6 s, card shows "Connected",
   then hides when the lid closes.
3. Tray icon is present; click: popover with battery; switch Off / Transparency / Adaptive / ANC
   and hear each one; long-press a stem: the popover follows within 1 s.
4. Take one pod out while music plays: music pauses; put it back: resumes.
5. Start talking with Conversation Awareness on: volume drops, then comes back.
6. Edit mode: move the card to the top right, Done, reopen the lid: the card appears there.
7. AirPods playing on the iPhone: opening the lid near the PC shows the card with "Connect" and
   does **not** steal the audio.
8. Disconnect: tray icon goes away; `systemctl --user status podglass` has no errors.

## 6. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Realtek adapter stutters when LE scanning during A2DP | audio dropouts | P0.5 decides passive vs active-only-when-idle scanning |
| Stealing audio from the iPhone | annoying | policy uses the connection-state byte (P0.4) and "user is at this PC" |
| Lid bit or connection byte meaning differs from LibrePods notes | wrong card behavior | P0.4 measures it; GATE 0 |
| Firmware update changes AAP | features stop working | parsers never raise; unknown packets are logged; fixtures make the fix quick |
| 3D model license | cannot be redistributed | models and renders are gitignored; repo ships only placeholders and the render script |
| Apple fonts | license | Inter |
