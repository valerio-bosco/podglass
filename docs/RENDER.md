# Renders and 3D model

The card, popover and widget show renders of the user's AirPods Pro 2 (Lightning case). Both the model
and the renders are generated locally and are **not committed** (`assets/models/`, `assets/renders/`
are gitignored); the repo keeps only the scripts in `tools/render/`.

## Regenerate

```sh
# 1. model (about 3 s): builds assets/models/airpods-pro2.blend
nix develop .#render -c blender -b -P tools/render/model.py -- --out assets/models/airpods-pro2.blend

# 2. renders: every shot in shots.toml, then manifest.json (written last, the UI waits for it)
nix develop .#render -c blender -b -P tools/render/render.py -- --shot all --samples 96

# one shot, fast, to look at something (no manifest is written unless --shot all)
nix develop .#render -c blender -b -P tools/render/render.py -- --shot debug-open --samples 24 --out /tmp/prev
```

`render.py` options: `--device auto|gpu|cpu`, `--model`, `--shots`, `--shot all|name,name`, `--samples N`,
`--scale F` (multiplies every size), `--out DIR`, `--keep-frames`, `--no-manifest`.

GPU only: `auto` and `gpu` pick CUDA (then OPTIX) and **fail with an error** when there is no GPU; the CPU
is used only with an explicit `--device cpu`. Blender uses 2 host threads. The shell
(`nix develop .#render`) has the CUDA build of Blender from cache.nixos-cuda.org (needs the cache
trusted, about 3 GB first download) plus nvcc and the CUDA headers: Pascal cards (GTX 1060) have no
prebuilt Cycles kernels, so the first render compiles them (~3 min, cached afterwards).

Speed (GTX 1060 3GB, 560x460 frame, 96 samples, same still): 8.7 s with default settings. Tuned
(current `shots.toml`: 64 samples, adaptive sampling, OPTIX denoiser with albedo only, fast prefilter,
fewer light bounces, persistent data): 4.5 s. Most of the saving was dropping the denoiser's normal
pass; denoising still costs about 3 s of the frame at the old settings. The model has about 25k
polygons, so geometry is not the cost. `case-open` (48 frames) takes ~4 min, `idle` (120 frames) ~9 min.
Use `--samples 16-24` and `--scale 0.5` while iterating.

## Files in `assets/renders/`

| File | What |
|---|---|
| `case-open.webp` | 560x460, 48 frames, 33 ms: lid opens 0 to 100 degrees (smoothstep), case standing, 3/4 front view |
| `idle.webp` | 560x460, 120 frames, loop: open case, slow yaw of +-8 degrees (starts and ends at 0, so it continues the last frame of `case-open`) |
| `case-closed.png` | 560x460 still, lid closed, same camera |
| `pods-pair.png` | 176x176 (2x of 88), both pods, stems down, tips leaning inward |
| `pod-left.png`, `pod-right.png`, `case-small.png` | 240x240 stills (2x of 120) |
| `*-44.png` | the same stills rendered at 44x44 for crisp small glyphs (not used by the UI yet) |
| `manifest.json` | list of the files above with sizes; the UI treats the renders as available only when it exists |

All have a transparent background; the floor shadow of the case shots is baked into the alpha.

## The model (`model.py`)

Units: 1 unit = 1 cm. Proportions come from the user's own photos of the case (straight-on front, ends, bottom):
case 6.0 x 2.2 x 4.5 (W x D x H; a superellipsoid, rounded rectangle in front view, pill-shaped end profile,
slightly domed flat faces), seam one third from the top, standing on z = 0, hinge on the back at the seam
(+Y, no overlap when open), camera in front (-Y). Objects: `Case_Base`, `Case_Lid` (solid with two bowls for the
pod heads; origin on the hinge axis, open it by rotating about X by a negative angle), `Case_Hinge` (steel plate on
the back, about half the width), `Case_LED` (emissive, 0.83 cm below the seam), `Case_Button` (pairing ring on the
back), `Case_Loop` (two steel eyes in a dark slot on the right end, 0.9 cm below the seam), `Pod_L`/`Pod_R` (empties,
origin = head center; children: head, stem (offset outwards), `_TipRig` > silicone tip and black mesh, slot, steel
band, mic dot, force-sensor flat). Pod proportions from the profile photo: head 1.76 wide, stem 0.8 wide and 2.5 below
the head center, tip 1.1 wide, pointing sideways and 15 degrees down (`tip_tilt = 105` degrees from the stem axis).
The case has a thumb notch on the front at the seam, a Lightning slot (the user's case is Lightning, not USB-C: thin
stadium slot with pins) centered on the bottom, three speaker holes on its left and one on its right, and two shared
cavities per pod (head bowl, offset stem cup) plus a trough for the tips.
Materials: glossy white (roughness 0.13, full clearcoat), matte white inside, warm cream silicone tip (subsurface),
dark grey fine mesh (bump pattern), polished steel. Shapes are bevelled boxes / surfaces of revolution with weighted
normals, no low-poly look.

Photo-matching debug shots (skipped by `all`): `debug-front` (photo 249), `debug-end` (246), `debug-photo243`
(open, three-quarter), `debug-photo247` (bottom), `debug-photo248` (back), `debug-pod` (profile like 241).

Constants at the top of `model.py` (case size, `LID_H`, `POD_X`, `POD_RISE`, `STEM_OFF`, `LED_DROP`)
are the first things to tweak.

## What to tweak (`shots.toml`)

- `[render]`: `samples`, `adaptive`, `denoiser`, `exposure` (white level), `look`, `open_angle`.
- `[camera]`: `azimuth` / `elevation` (3/4 view), `lens`, `frame_width` (zoom), `target`.
- `[light]`: large soft area lights `key`, `fill`, `strip` (vertical strip, gives the highlight on the front face), `rim`,
  `top` (position in cm relative to the case, size, energy) and the `world` gradient
  (`ramp` = grey of floor / horizon / ceiling, what the glossy plastic reflects). The floor shadow strength follows the lights.
- Per shot: `size`, `frames`, `lid`, `yaw`, `only` (objects shown), `place` (pod position/rotation for
  the single-pod stills), `tip_tilt`, `shadow`, `out` (`"name.png:44"` adds a second size).
- Material colours and roughness: `make_materials()` in `model.py` (white plastic roughness `0.13` and
  full clearcoat, tip grey `0.42`).
- Shots with `debug = true` (`debug-open`, `debug-bottom`, `debug-back`) are skipped by `--shot all`.

## Known differences from the real AirPods

See the P3.2 notes in `docs/LOG.md` (the coordinator records them after the user's look review).
