# Next steps - handoff

Read this first in a new session, together with `AGENTS.md`. It replaces re-reading the whole
history: everything decided so far is in `docs/PLAN.md`, `docs/SPIKE.md`, `docs/LOG.md`.

## State (2026-11-10)

- Phases 0, 1, 2 done and verified on the real AirPods (Pro 2 **Lightning**, A2698, adv id 0x1420,
  firmware 6807): card on lid open, auto-connect in ear, exact battery from adverts and AAP, pause on
  ear removal, resume when the pod is cased or reinserted, stem presses via `mpris-proxy`, mode
  changes from popover and tray. 183 tests (`nix develop -c pytest -q`).
- UI (phase 4) P4.0-P4.4 done in demo mode and used live. Known defects: popover clipped at the right
  screen edge, firmware shown as the long `90.3431000025000000.6807`.
- Not installed: daemon, UI and mpris-proxy run from a temporary wrapper
  (`/tmp/claude-1000/pg/podglass`) and are gone after a reboot. Phase 5 fixes that.
- User decisions: D1 build the 3D model ourselves in Blender (fallback: a model found online),
  D2 GPL-3.0-or-later, D3 autoconnect `in-ear`, D4 English UI, no volume ducking while talking.

## Update 2026-11-12

Model, renders and card animations are on master (see LOG 2026-11-10..12). Renders installed in
~/.local/share/podglass/renders and assets/renders. Left for the user: rebuild the system with the new
podglass (docs/INSTALL.md) so the installed UI gets the WebP plugin and the new card logic; then P3.2
look approval on the real card and P5.3 checklist. Worktrees under ~/Projects/podglass-wt can be removed.

## Update 2026-11-10 afternoon

W1, W2, W3 are merged into master (worktrees removed). Left: P5.2 install (user: flake input,
podglass.nix, import, Lua layer rule, then rebuild - see docs/INSTALL.md), P5.3 checklist, P4.5
mouse drag check, P3.2 look approval and model iterations (GPU only: `nix develop .#render`,
docs/RENDER.md; renders go to assets/renders and ~/.local/share/podglass/renders).
When spawning parallel agents, create worktrees with `git worktree add` from this repo first
(agent `isolation: worktree` uses the session's current directory, which may be another repo).

## Blender MCP (2026-11-10)

blender-mcp (github.com/ahujasid/blender-mcp, commit 2e4b0bc) is pinned in
`~/.local/share/blender-mcp` with its python env; server wrapper `~/.local/bin/blender-mcp-server`
(telemetry off). The user installs the addon in Blender (Install from Disk: addon.py, start server
from the N panel "BlenderMCP" tab) and registers the server with
`claude mcp add blender --scope user -- /home/voodoo/.local/bin/blender-mcp-server`, then restarts
Claude Code. Model work: shape first by tracing the reference photos (docs/LOG.md rounds 3-6),
quick viewport/workbench previews, Cycles only at the end, GPU only.

## Workstreams (done 2026-11-10; kept as reference)

Each workstream owns its files. Do not edit files owned by another workstream, and do not edit
`docs/PLAN.md` or `docs/LOG.md` (the coordinator merges and updates them). End with a commit on
your branch and a report: what was done, how it was verified, what only the user can check.

### W1 - packaging and autostart (P5.1, prepare P5.2) - Sonnet
Owns: `flake.nix`, `nix/`, `docs/INSTALL.md`, and in `podglass/__main__.py` only a new `ui` verb.
Read: `PLAN.md` phase 5, `~/Projects/oring/nix/{package,hm-module}.nix` (same pattern),
`~/Projects/oring/flake.nix`, `/etc/nixos/oring.nix` (how oring is enabled; read only).
- `nix/package.nix`: install `podglass/`, `ui/`, `assets/placeholder/`, `tools/demo_state.py` to
  `$out/share/podglass`; `$out/bin/podglass` wrapper with python (bleak, dbus-fast, cryptography),
  `PODGLASS_ROOT=$out/share/podglass`, and PATH suffix with playerctl, wireplumber (wpctl),
  hyprland (hyprctl), libnotify. `packages.default`.
- `podglass ui`: exec quickshell `-p $PODGLASS_ROOT/ui/shell.qml` with `PODGLASS_BIN` set to the
  same podglass binary (the UI's `DaemonClient.qml` reads it). Renders, when they exist, are read
  from `$XDG_DATA_HOME/podglass/renders` if `assets/renders` is not in the store: check
  `ui/Paths.qml` and add only an env var it can read (`PODGLASS_ASSETS`), do not edit QML (W2 owns
  ui/); write in your report what W2 must change if needed.
- `nix/hm-module.nix`: `programs.podglass.{enable, package, settings (toml -> config.toml),
  batteryWidget}`; user services `podglass.service` (`podglass daemon`, After/PartOf
  graphical-session.target, Restart=on-failure) and `podglass-ui.service` (`podglass ui`);
  `services.mpris-proxy.enable = lib.mkDefault true`. `homeManagerModules.default` in flake.nix.
- Hyprland layer rules for the glass blur: the user's Hyprland config is Lua
  (`~/.config/hypr/*.lua`, `/etc/nixos/hyprland-local.lua`, read only). Write the exact lines to
  add in `docs/INSTALL.md`; do not edit those files.
- `docs/INSTALL.md`: the snippet for `/etc/nixos/flake.nix` + a `podglass.nix` like `oring.nix`,
  the rebuild command, how to stop the temporary run (`pkill -f "podglass daemon"`, the old
  quickshell UI, `mpris-proxy`), how to check (`systemctl --user status podglass podglass-ui`).
- Done when: `nix build` succeeds, `result/bin/podglass --help` works, `nix flake check` passes,
  and `nix eval .#homeManagerModules.default` evaluates. Never edit /etc/nixos.

### W2 - UI fixes and edit mode (P4 fixes, P4.5) - Sonnet
Owns: `ui/`, `docs/screens/`.
Read: `docs/UI.md`, `ui/*.qml`, `tools/demo_state.py` (scenarios), `AGENTS.md` commands.
- Popover: it is clipped at the right edge on HDMI-A-1 (3440x1440, scale 1.0667): the switch of
  "Conversation Awareness" and the firmware text are cut. Fix placement/size so the whole panel is
  inside the screen with the 12 px margin from UI.md.
- Firmware: show only the last dot-separated part (`6807`) as "Firmware 6807".
- P4.5 edit mode: verify and fix `EditMode.qml` end to end: dim, ghosts at the saved positions,
  drag with 8 px grid, snap guides (12 px), Reset / Cancel / Done, Esc = Cancel, Done sends
  `layout` (the daemon writes `~/.config/podglass/layout.json`; in demo mode demo_state.py does).
  The card and widget must then appear at the new place.
- Verify only in demo mode, never against the live daemon: `PODGLASS_DEMO=<scenario> quickshell -p
  ui/shell.qml`, trigger with `quickshell -p ui/shell.qml ipc call podglass <fn>`, screenshot with
  `grim`, look at the PNG, iterate. Close your quickshell instance when done. Another UI instance
  of the user may be running: do not kill it (it is the one started with PODGLASS_BIN).
- Done when: new screenshots in `docs/screens/` (popover dark/light, edit mode before/after a
  move, card at the moved position) and no QML warnings in the quickshell log.

### W3 - 3D model and renders (P3.0 draft, P3.1) - Sonnet
Owns: `tools/render/`, `assets/models/` and `assets/renders/` (both gitignored), `docs/RENDER.md`.
Read: `docs/UI.md` "Renders", `PLAN.md` phase 3, `ui/components/Render.qml` and `ui/Paths.qml`
(what the UI expects: `assets/renders/manifest.json` written last, file names in UI.md).
- The user's AirPods are **Pro 2 Lightning** (case 45.2 x 60.6 x 21.7 mm, lanyard loop on the right
  side, speaker grille on the bottom, Lightning port; pod 30.9 x 21.8 x 24.0 mm with silicone tip,
  black mesh, stem with a pressure sensor flat). Same look as USB-C except the port.
- `tools/render/model.py`: Blender (bpy) script that builds the case (body, lid as a separate object
  with the hinge pivot at the back edge, inner cavities, steel hinge, status light, lanyard loop,
  speaker holes, Lightning port) and the two pods (head, tip, mesh, stem) from these dimensions, with
  PBR materials (glossy white plastic, slightly rougher inside, dark grey mesh, polished steel), and
  saves `assets/models/airpods-pro2.blend`. Geometry: subdivision surface + bevels, it must look
  smooth, not low-poly.
- `tools/render/render.py` + `shots.toml`: as in PLAN P3.1 (studio light, transparent film, Cycles,
  AgX, shots and sizes from UI.md, img2webp), then `manifest.json`.
  Run with `nix develop .#render -c blender -b -P ...`. Use fewer samples while iterating.
- Self-check: render the stills, open the PNGs and compare with what AirPods Pro 2 look like;
  iterate on shape before materials. The final look is approved by the user (P3.2), so stop after
  a solid first version and say what still differs.
- Done when: `assets/renders/` has every file in the UI.md table + manifest, and
  `docs/RENDER.md` says how to regenerate and what to tweak.

## After the workstreams (coordinator)

1. Merge W1, W2, W3 branches into master, run `nix develop -c pytest -q` and `nix flake check`,
   tick PLAN boxes, add LOG entries from the reports.
2. User: P5.2 (add the flake input + module, rebuild, stop the temporary run), then P5.3 checklist
   (PLAN section 5), then P3.2 look approval of the renders.
3. Open follow-ups: lid-open adverts with the case charging (SPIKE.md); battery arc on the tray
   icon; one unexplained audio-quality drop (check the bluez profile if it happens again:
   `wpctl status`, `pw-dump` api.bluez5.profile); phase 6 items in PLAN.
