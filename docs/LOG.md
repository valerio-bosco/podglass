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
