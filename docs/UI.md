# UI spec

Source of truth for the Quickshell UI. Sizes are logical pixels (Quickshell applies the monitor
scale, 1.0667 on HDMI-A-1 3440x1440). The mockup page shows every state; when the mockup and this
file disagree, this file wins.

## Tokens (`ui/Theme.qml`)

| Token | Dark (default) | Light |
|---|---|---|
| glass | `#1E1E20` at 72 % alpha | `#F6F6F8` at 78 % alpha |
| label | `#FFFFFF` | `#000000` |
| secondary | `#EBEBF5` at 60 % | `#3C3C43` at 60 % |
| fill (buttons, ring track) | `#767680` at 24 % | `#767680` at 12 % |
| hairline | `#FFFFFF` at 8 % | `#000000` at 6 % |
| accent | `#0A84FF` | `#007AFF` |
| battery ok / charging | `#30D158` | `#34C759` |
| battery low (<= 20 %) | `#FF453A` | `#FF3B30` |
| switch on | `#30D158` | `#34C759` |
| shadow | 0 20 60, black 35 % | 0 20 60, black 18 % |

Font: Inter. Sizes: title 19/600, body 15/400, button 17/600, label 13/400, caption 11/500.
Percentages always `font.features: {"tnum": 1}`.
Glass needs the Hyprland layer rules from PLAN.md 3.3 (blur happens in the compositor; QML only
draws the translucent color). `theme = "auto"` follows serpantinum's dark/light setting if it can be
read, else dark.

## Card (`ProximityCard.qml`)

- 360 wide, height from content (about 410), radius 38, padding 20, glass, 1 px hairline border.
- Top row: title centered ("AirPods Pro", or the device name), 19/600. Close button at top-right:
  30 px circle, fill token, 12 px "x" glyph in secondary. Esc also closes (`dismiss-card`).
- Render area: 230 tall, centered image 280 x 230. Plays `case-open.webp` once when the card
  appears, then `spin.webp` in a loop while not connected and `idle.webp` once connected; when the lid
  closes, `case-close.webp` plays once before the card slides away. Placeholder SVG until renders exist.
- Bottom area by state:
  - `disconnected`: button full width, 50 tall, radius 14, accent fill, "Connect" 17/600 white.
  - `connecting`: same button in fill token with a 18 px spinner and "Connecting...".
  - `connected`: battery rings row. If both pods are present and differ by <= 10 points, show two
    rings: "AirPods" (lower of the two) and "Case"; otherwise three: "Left", "Right", "Case".
  - `setup` (unknown AirPods in pairing mode): text "Not paired with this computer" 13 secondary,
    then the button "Set Up".
  - `error`: "Couldn't connect" 13 in battery-low color, button "Try Again".
- Battery ring: 52 px, stroke 5, round caps, track = fill token, arc color by level; a 22 px glyph of
  the part (pod or case) inside the ring; under the ring the percent 15/600 and a 10 px bolt when
  charging; under that the label 13 secondary. Unknown level: empty track and "-".
- Placement: default bottom center, 24 px from the bottom edge. Edit mode can move it.
- Motion: enter = from 60 px lower, scale 0.96, opacity 0 to final in 420 ms, `Easing.OutBack`
  (overshoot 1.1). Exit = 220 ms `Easing.InCubic` down 40 px and fade. Respect a
  `reduce_motion` config flag (fade only).
- Right-click on the card: small menu "Edit Position", "Settings...".

## Popover (`ListeningPopover.qml`)

- 320 wide, radius 26, padding 16, glass. Default: top right, 8 px under the bar, 12 px from the
  right screen edge.
- Header: `pods-pair` still 44 px, name 15/600, under it "Connected" 13 secondary. Right side:
  case percent small.
- Battery row: three 40 px rings (Left, Right, Case), same rules as the card.
- "Listening Mode" 13 secondary, then 4 equal columns: 52 px circle buttons with a 24 px icon and
  an 11/500 label under: Off, Transparency, Adaptive, Noise Cancellation ("Noise Cancel." if it
  does not fit). Selected: accent fill, white icon. Unselected: fill token, label-color icon.
- When Adaptive is selected: a slider row "Adaptive level" 0..100 (sends `adaptive-level` on
  release).
- Toggle row (44 tall): "Conversation Awareness" 15 + 51 x 31 switch.
- Footer separated by a hairline: "Disconnect" (accent text button) left, firmware 11 secondary right.
- Closes on outside click and Esc.

## Battery widget (`BatteryWidget.qml`, optional)

- 340 x 160, radius 24, glass, on the Bottom layer.
- Three 60 px rings (Left, Right, Case) spaced evenly, glyph inside, percent 15/600 under each.
- When disconnected and not seen for 10 min: rings show the last values in secondary color with
  "Last seen 14:32" caption.

## Edit mode (`EditMode.qml`)

- Full-screen overlay, black 45 % dim. All podglass windows shown as ghosts at their positions:
  same shape, 2 px dashed white 70 % border, a small name chip on top.
- Drag a ghost to move it; 8 px grid; snap guides (1 px accent lines) at screen center lines and at
  24 px from each edge, 12 px snap threshold.
- Toolbar pill top center, 44 tall: "Drag to place" caption, buttons Reset, Cancel, Done (accent).
- Done writes `layout.json` (per monitor) and exits; Cancel exits without saving; Esc = Cancel.

## Renders (`tools/render`)

| File | Size (2x) | Use |
|---|---|---|
| `case-open.webp` | 560 x 460, 48 frames, 33 ms | card enter |
| `idle.webp` | 560 x 460, 120 frames loop | card while open and connected (small sway) |
| `spin.webp` | 560 x 460, 150 frames loop (one turn, 5 s) | card while waiting to connect |
| `case-close.webp` | 560 x 460, 48 frames, played once | card exit when the lid closes (last frame held) |
| `case-closed.png` | 560 x 460 | card when lid closed during exit |
| `pods-pair.png` | 88 x 88 | popover header |
| `pod-left.png`, `pod-right.png`, `case-small.png` | 44 x 44 and 120 x 120 | ring glyphs, widget |

Transparent background, soft contact shadow baked in, camera 3/4 front, 15 degrees above, the same
for every shot so frames match.
