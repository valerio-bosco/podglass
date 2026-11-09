# podglass - rules for agents

AirPods Pro 2 integration for the user's NixOS desktop (Hyprland + serpantinum bar on Quickshell).
Start with `docs/PLAN.md` section 0, then do exactly one task.

## Language and commits
- Everything in the repo is English: code, comments, docs, UI strings, commit messages.
  Talk to the user in Italian.
- Conventional Commits, imperative: `feat(daemon): add AAP session`, `test(adv): ...`,
  `fix(ui): ...`, `docs: ...`. Scopes: core, daemon, ui, render, nix, docs, tools.
- One task = one or more commits; tick the box in `docs/PLAN.md` and add a note to `docs/LOG.md`.

## Hard rules
- Never edit anything outside this repo (`/etc/nixos`, `~/.config/hypr`, serpantinum). Write the
  proposed change in `docs/LOG.md` and ask the user.
- Never fake a "Human check": stop and ask the user to do it, then record the result.
- Never commit `assets/models/` or `assets/renders/` (paid 3D model and its renders), keys,
  or real MAC addresses in docs (fixtures may keep addresses; they rotate).
- Pure modules (`crypto`, `adv`, `aap`, `state`, `policy`, `config`) do no I/O and never raise on
  bad input from the air: return `None` / `Unknown`.
- Protocol facts come from `docs/PROTOCOL.md` only. If the hardware disagrees, add the fixture and
  fix the doc in the same commit.

## License
GPL-3.0-or-later (decision D2, `LICENSE`). Protocol facts still come from PROTOCOL.md; if code is
ported from LibrePods (also GPL-3.0), say so in a comment at the top of the file with the source path.

## Commands
- Tests: `nix develop -c pytest -q`
- All checks: `nix flake check`
- UI without hardware: `PODGLASS_DEMO=connected nix develop -c quickshell -p ui/shell.qml`
- Screenshot for review: `grim docs/screens/<name>.png`
