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
| `case-open.webp` | 560x460, 48 frames, 33 ms: lid opens 0 to 105 degrees (smoothstep), case standing, 3/4 front view |
| `idle.webp` | 560x460, 120 frames, loop: open case, slow yaw of +-8 degrees (starts and ends at 0, so it continues the last frame of `case-open`) |
| `case-closed.png` | 560x460 still, lid closed, same camera |
| `pods-pair.png` | 176x176 (2x of 88), both pods, stems down, tips leaning inward |
| `pod-left.png`, `pod-right.png`, `case-small.png` | 240x240 stills (2x of 120) |
| `*-44.png` | the same stills rendered at 44x44 for crisp small glyphs (not used by the UI yet) |
| `manifest.json` | list of the files above with sizes; the UI treats the renders as available only when it exists |

All have a transparent background; the floor shadow of the case shots is baked into the alpha.

## The model (`model.py`)

Units: 1 unit = 1 cm. Case 6.06 x 2.17 x 4.52 (W x D x H, from 60.6 x 21.7 x 45.2 mm), standing on z = 0,
hinge at the back (+Y), camera in front (-Y). Objects: `Case_Base`, `Case_Lid` (origin on the hinge axis,
open it by rotating about X by a negative angle), `Case_Hinge` (steel barrel in a notch), `Case_LED`
(emissive), `Case_Loop` (lanyard ring in a pocket on the right side), `Pod_L`/`Pod_R` (empties; children
body+stem, `_TipRig` > silicone tip and black mesh, vents, steel contacts, stem sensor flat). The bottom
has a Lightning slot and a speaker grille (not visible in the shots, but modelled).
Materials: glossy white (clearcoat), rougher white inside, grey silicone tip, black mesh (bump pattern),
polished steel. Shapes are bevelled boxes / surfaces of revolution with weighted normals, no low-poly look.

Constants at the top of `model.py` (case size, rounding `EDGE`, lid height `LID_H`, pod position and
tilt `IN_CASE_TILT` (tips lean toward the center), cavity radius) are the first things to tweak.

## What to tweak (`shots.toml`)

- `[render]`: `samples`, `adaptive`, `denoiser`, `exposure` (white level), `look`, `open_angle`.
- `[camera]`: `azimuth` / `elevation` (3/4 view), `lens`, `frame_width` (zoom), `target`.
- `[light]`: area lights `key`, `fill` (vertical strip, gives the highlight on the front face), `rim`,
  `top` (position in cm relative to the case, size, energy) and the `world` gradient
  (`ramp` = grey of floor / horizon / ceiling, what the glossy plastic reflects). The floor shadow strength follows the lights.
- Per shot: `size`, `frames`, `lid`, `yaw`, `only` (objects shown), `place` (pod position/rotation for
  the single-pod stills), `tip_tilt`, `shadow`, `out` (`"name.png:44"` adds a second size).
- Material colours and roughness: `make_materials()` in `model.py` (white plastic roughness `0.22` and
  coat, tip grey `0.4`).
- Shots with `debug = true` (`debug-open`, `debug-bottom`, `debug-back`) are skipped by `--shot all`.

## Known differences from the real AirPods

See the P3.2 notes in `docs/LOG.md` (the coordinator records them after the user's look review).
