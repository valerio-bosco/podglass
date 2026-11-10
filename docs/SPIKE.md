# Phase 0 spike

## P0.1 BlueZ experimental - done 2026-11-10
`hardware.bluetooth.settings.General.Experimental = true;` in /etc/nixos/configuration.nix, then
`sudo nixos-rebuild switch` **and** `sudo systemctl restart bluetooth`.

## Capture (P0.2 / P0.3 human checks)
AirPods connected to the PC, case nearby, then:

    nix develop -c tools/spike.sh

About 5 minutes. Follow the notifications. Output: `tests/fixtures/adv/<step>.jsonl` and the raw
AAP session in `tests/fixtures/aap/` (gitignored). Steps 9-10 need the iPhone.

## Findings (P0.4) - 2026-11-10, Pro 2 Lightning (A2698, adv id 0x1420), firmware 6807
- Each pod advertises with its own RPA; the AAP IRK resolves both.
- Lid: bit 3 of offset 8 clear = open. Valid while any pod is in the case (status `& 0x14`), not
  only when the broadcasting pod is (LibrePods' rule was too strict: lid read as unknown with the
  lid open). Fixed in `adv.py`.
- In-ear bits decode correctly (right pod removed -> right_in_ear False).
- **Lid closed = adverts stop**: 2 adverts right after closing, then none for 20 s. The daemon must
  treat "lid closed" as: last advert had lid closed, or no advert for 8 s while the card is shown (gaps up to 5.2 s seen with the lid open).
- Closing the lid with the pods inside disconnects them from the PC (AAP session ended at 11:18:10).
  Opening it again did not reconnect to the PC by itself: podglass has to call Connect().
- Connection byte: `04` idle (also during the iPhone call step), `05` while music played on the
  iPhone. Calls are not distinguishable yet.
- Encrypted payload decoded (PROTOCOL.md 1.3): exact battery + charging bits + **tail of the MAC of
  the owning host**. This is the "busy elsewhere" signal the policy needs: host != this PC and
  byte 0 == 05 -> do not steal.
- Adverts keep coming while pods are in ears (both-in-ears, iphone-playing), less often (~1/s).
- Not explained: step `case-charging` recorded 0 adverts with the lid open (case battery was 1 %,
  maybe the user was still plugging it in). Re-check once: open the lid with the case charged.
- `notify-send` missing in the dev shell: added libnotify.

## Policy changes for GATE 0
- "not busy elsewhere" = `precise.host_tail == adapter MAC tail` or `precise.busy is False`.
- "lid closed" also from advert silence (3 s).
- Autoconnect on in-ear only when the owning host is this PC, or the AirPods are idle.

## P0.5 audio stutter - done 2026-11-10
Music from the PC on the AirPods: 2 min passive scan (20 adverts), then 2 min active scan
(49 adverts). The user heard no dropouts in either. Decision for `scanner.py`: passive scan
(advertisement monitor, or-pattern `4c 00 07`) always on; active scan only as a fallback when
the monitor API is missing.

## GATE 0 - passed 2026-11-10 (Opus)
Protocol doc updated, policy changes moved to task P1.8. Open follow-up (not blocking): check
that adverts arrive with the lid open and the case charging (the `case-charging` step had 0).
