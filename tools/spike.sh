#!/usr/bin/env bash
# Guided hardware capture for phase 0 (docs/SPIKE.md). Run inside `nix develop`.
# Each step: a desktop notification says what to do, 10 s to do it, then 20 s of recording.
# The AAP log runs in the background the whole time (needs the AirPods connected to this PC).
set -u
MAC=${1:-$(bluetoothctl devices Paired | awk '/AirPods/{print $2; exit}')}
cd "$(dirname "$0")/.."
say() { notify-send -u critical -t 9000 "podglass capture" "$1"; echo; echo "== $1"; }
python tools/capture_aap.py "$MAC" < <(sleep 900) > /tmp/podglass-aap.out 2>&1 &
AAP=$!
steps=(
  "case-closed|Pods in the case, lid CLOSED, case next to the PC"
  "lid-open|OPEN the lid and leave it open"
  "one-pod-out|Take the LEFT pod out of the case, hold it in your hand"
  "both-in-ears|Put BOTH pods in your ears"
  "one-out-of-ear|Take the RIGHT pod out of your ear (keep it in your hand)"
  "back-in-case|Put both pods back in the case, lid open"
  "lid-closed|CLOSE the lid"
  "case-charging|Plug the case into the charger, OPEN the lid"
  "iphone-playing|Pods in ears, connect them to the iPhone and PLAY music there"
  "iphone-call|Start a phone call (or FaceTime audio) on the iPhone with the pods in"
)
for s in "${steps[@]}"; do
  label=${s%%|*}; text=${s#*|}
  say "$text (recording starts in 10 s)"; sleep 10
  python tools/capture_ble.py --label "$label" --seconds 20 | tail -2
done
kill $AAP 2>/dev/null
say "Done. Tell Claude the capture is finished."
