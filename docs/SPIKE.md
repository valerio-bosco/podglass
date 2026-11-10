# Phase 0 spike

## P0.1 BlueZ experimental - done 2026-11-10
`hardware.bluetooth.settings.General.Experimental = true;` in /etc/nixos/configuration.nix, then
`sudo nixos-rebuild switch` **and** `sudo systemctl restart bluetooth`.

## Capture (P0.2 / P0.3 human checks)
AirPods connected to the PC, case nearby, then:

    nix develop -c tools/spike.sh

About 5 minutes. Follow the notifications. Output: `tests/fixtures/adv/<step>.jsonl` and the raw
AAP session in `tests/fixtures/aap/` (gitignored). Steps 9-10 need the iPhone.

## Findings (P0.4)
To be written from the captures: lid bit meaning, connection-state byte values, adverts while
connected, encrypted payload layout.

## P0.5 audio stutter
To be done by the user: 2 min of music with `capture_ble.py --mode passive`, then 2 min with
`--mode active`.
