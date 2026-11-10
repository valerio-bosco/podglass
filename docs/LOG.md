# Log

One entry per task: date, task id, model, what was done, what could not be verified.

## 2026-11-09 - planning (Opus)
- Wrote PLAN.md, PROTOCOL.md, UI.md, AGENTS.md and the mockup page.
- Checked the machine: Hyprland, serpantinum bar with tray, Quickshell 0.3.1, BlueZ 5.87,
  Realtek adapter, AdvertisementMonitor off, AirPods not paired yet.

## 2026-11-09 - phase 1, P1.1-P1.7 (Opus)
- Decisions recorded: D1 model built in Blender (fallback: online model), D3 `in-ear`, D4 English.
  D2 still open (GPL-3.0 default kept).
- Scaffold, crypto, adv, aap, state, config, keys, policy done; 149 tests.
- Not verified: `nix develop -c pytest -q` and `nix flake check`. The agent sandbox blocks the
  Nix daemon socket and the network, so tests ran with python 3.14 + pytest from the store and a
  local shim for `cryptography` (AES through the openssl CLI). The Core Spec `ah()` vector was
  also checked with openssl directly. The user must run both Nix commands once.
- `flake.lock` copied from oring (same nixpkgs pin, already in the store).
- Choices to check at GATE 0: `resolve_rpa` tries the IRK in both byte orders (order of the AAP
  IRK unknown); DeviceInfo takes printable NUL-separated strings (name, model, -, -, firmware),
  layout unverified; the advert `in_case` bits (0x10, 0x04) are not mapped to left/right, so
  `inCase` comes only from AAP.
- policy.py: extra rules (retry cooldown, user-disconnect lock, card timeout) are listed in
  PLAN.md 3.2; `pause_media` is emitted on any pod removal, media.py must pause only players that
  are playing and resume only those.

## 2026-11-10 - phase 4, P4.0-P4.4 (Opus, closing an interrupted session)
- Committed the UI written on 2026-11-09: demo_state.py, shell, Theme, Strings, DaemonClient,
  card, popover, battery widget, edit mode, components, placeholder SVGs, screenshots in docs/screens.
- Not re-run in this session (low-cost close): screenshots are from the previous session.
- Human check pending: compare docs/screens with the mockup page.
- P4.5 EditMode left open: code exists but there is no screenshot or recorded test of drag/snap/save.

## 2026-11-10 - Nix verification (Opus)
- `nix develop -c pytest -q`: 149 passed (after adding `pythonpath = ["."]` to pyproject.toml).
- `nix flake check`: all checks passed. Phase 1 is now verified with the real `cryptography`.

## 2026-11-10 - P0.3 pairing step (Opus + user)
- AirPods paired, bonded, trusted and connected with BlueZ. Modalias `v004Cp2014`: Pro 2
  **Lightning** (`pro2-lightning`), not USB-C. Matters for the 3D model (no lanyard loop).
- First attempts failed with `AuthenticationRejected`: the case was not in pairing mode, and
  `bluetoothctl pair` without a registered agent fails. Working recipe: agent NoInputNoOutput +
  default-agent, scan, pair while the case light flashes white.

## 2026-11-10 - P0.1 BlueZ experimental (user)
- `hardware.bluetooth.settings.General.Experimental = true;` added to /etc/nixos/configuration.nix
  next to `programs.serpantinum.enable`; needs `sudo systemctl restart bluetooth` after rebuild
  (nixos-rebuild did not restart bluetoothd).
- `AdvertisementMonitorManager1` now exposed, monitor type `or_patterns`, adapter feature
  `HardwareOffload`. P0.1 done.

## 2026-11-10 - P0.2, P0.3 tools (Opus)
- `tools/capture_ble.py`: passive scan via BlueZ advertisement monitor works (or-pattern
  `4c 00 07`). Smoke run: both pods advertise with different RPAs, model `pro2-lightning`
  (adv id 0x1420, modalias p2014), coarse L50 R40 case 0, lid open, conn byte 4.
- `tools/capture_aap.py`: L2CAP 0x1001 connect without root works; handshake, features and
  notifications accepted. Got exact battery (L54 R44 case 1), Mode anc, Ear in-case/in-case,
  AdaptiveLevel 50, Keys. Keys go to ~/.local/state/podglass/keys.json and are redacted in logs.
- IRK from AAP resolves both captured RPAs with `resolve_rpa` (P1 byte-order question answered
  in practice).
- Unparsed opcodes seen at startup: 0x08, 0x0c, 0x0e, 0x17 (HID-like descriptors, contain the
  serial number), 0x2e, 0x53, 0x55, control settings 0x1b/0x35/0x3e. Raw sessions are gitignored.
- Pending: the user runs the labeled capture script (docs/SPIKE.md) - P0.2/P0.3 human checks.

## 2026-11-10 - P1.8 policy update after GATE 0 (Opus)
- `state.apply_advert(state, adv, precise)`: exact battery from the decrypted advert, AAP still
  wins while connected.
- `Policy(config, adapter_tail)`: busy elsewhere = decrypted host tail != this PC and streaming;
  `AdvertSeen.precise`. Replaces the `busy_states` argument.
- Lid closed also after 3 s without adverts from my AirPods (hides the card at once; adverts
  from unknown AirPods do not keep it open). Two older tests assumed time passing without adverts
  and were updated. 156 tests pass.
- The daemon (P2.2/P2.7) must: decrypt with keys.json, call `adv.parse_precise`, pass the result
  to both `apply_advert` and `AdvertSeen`, and read the adapter MAC from BlueZ for `adapter_tail`.

## 2026-11-10 - P2.1 bluez.py (Opus)
- dbus-fast client: adapter + MAC tail, `find_airpods` (pure `pick_airpods`, 3 tests), connect with
  15 s timeout, disconnect, `watch_connected`, BatteryProvider1.
- `podglass debug bluez` prints adapter `E8:48:B8:C8:20:00` (tail `c82000`, equal to the host bytes
  in the decrypted advert) and the AirPods device. 159 tests pass.
- `--battery 42`: BlueZ exposes Battery1 Percentage 42, Source "podglass"; upower shows it.
- First `--connect` timed out (AirPods in the closed case). Second try returned
  `org.bluez.Error.InProgress` because the AirPods had connected themselves: `connect()` now treats
  already-connected as success and waits for Connected on InProgress/AlreadyConnected.
- Verified: `--disconnect` then `--connect` -> connected=True, PipeWire sink "AirPods Pro" back as
  default output. P2.1 done.

## 2026-11-10 - P2.2 scanner.py (Opus)
- Pure `Classifier` (RPA -> public MAC cache, 1 s dedupe, decrypt + `parse_precise`, pairing-mode
  passthrough, "probably mine" rule without keys) + `scan()` on bleak: passive monitor with
  or-pattern `4c 00 07`, active fallback. Yields `Seen(adv, known, precise, device)`.
- 6 tests (synthetic RPA from the Core Spec IRK, real advert header). 165 tests pass.
- Live: `podglass debug scan` with pods in ears -> "mine", exact L84 R82, host c82000 (this PC).

## 2026-11-10 - P2.3 aap_session.py (Opus)
- `AapSession`: non-blocking L2CAP socket, reader task -> queue, startup (handshake ack 3 s,
  features, notifications, key request only when keys.json lacks the device), keys stored on the
  first `Keys`. Fails fast if the AirPods hang up during the handshake.
- `run_sessions()`: one session at a time while BlueZ says connected, backoff 1-30 s.
- 4 tests with a socketpair as fake AirPods. 169 tests pass.
- Live: `podglass debug aap --mode transparency` then `--mode anc`: the AirPods echoed both
  modes (PROTOCOL.md 2.4 confirmed), battery L82 R82, both in ear, firmware 6807.

## 2026-11-10 - P2.4 ipc.py + CLI (Opus)
- `IpcServer` on `$XDG_RUNTIME_DIR/podglass.sock` (mode 0600): sends the latest config + state on
  connect, broadcasts state changes and events; `parse_command` validates every verb (pure, tested).
- CLI: `watch`, `status [--json]`, `set <verb> [arg]`, `show-card`, `popover`, `edit`, `debug ...`.
  Change from PLAN: `show-card`/`popover`/`edit` go to the daemon, which must broadcast them as
  events (`show-card`, `popover`, `edit`); the UI already handles those events, no quickshell ipc.
- Bugs found by the tests: `wait_closed()` hangs while clients are open (Python 3.12+), and a
  one-shot `podglass set` that closed with unread data reset the connection and lost the command
  (client now half-closes and drains). 173 tests pass.
- Not live-tested: there is no daemon yet (P2.7).

## 2026-11-10 - P2.5 media.py (Opus)
- `Media.pause()/resume()` via playerctl, only players that were playing; `duck()/restore()` via
  wpctl on the default sink, never raises the volume.
- User decision: no volume ducking while talking. `ca_duck` default is now false (config, PLAN);
  the code stays behind the option. 178 tests pass.
- Live (read-only): playerctl sees `spotify`, wpctl reads the sink volume.

## 2026-11-10 - P2.6 tray.py (Opus + user)
- StatusNotifierItem + com.canonical.dbusmenu with dbus-fast: 22 px pods glyph as IconPixmap
  (generated, no files), tooltip "AirPods Pro - L 82% R 80% Case 64%", radio items for the 4
  modes, Disconnect, Edit Position. `show()` owns the name and registers with the watcher
  (Quickshell/serpantinum), `hide()` releases it. Battery arc on the icon not done (tooltip only).
- Live with the user: icon appeared next to Spotify, left click -> Activate, menu choices arrived
  (transparency, anc, edit); after `hide()` the watcher dropped the item. 181 tests pass.
