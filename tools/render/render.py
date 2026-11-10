"""Render the podglass shots from the .blend built by model.py.

Run:  nix develop .#render -c blender -b -P tools/render/render.py -- \
        [--model assets/models/airpods-pro2.blend] [--shots shots.toml] [--shot all|name,name]
        [--device cpu|gpu|auto] [--samples N] [--scale F] [--out assets/renders] [--keep-frames] [--no-manifest]

Frames go to <out>/<shot>/NNNN.png, animations are encoded with img2webp (libwebp) into
<out>/<name>.webp, then <out>/manifest.json is written last (the UI waits for it).
"""
import json
import math
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


MODEL = opt("--model", "assets/models/airpods-pro2.blend")
SHOTS = opt("--shots", str(HERE / "shots.toml"))
WANT = opt("--shot", "all")
SAMPLES = opt("--samples")
SCALE = float(opt("--scale", "1.0"))
OUT = Path(opt("--out", "assets/renders"))
KEEP = "--keep-frames" in argv
DEVICE = opt("--device", "auto")  # cpu | gpu | auto

cfg = tomllib.load(open(SHOTS, "rb"))
R, CAM, LIGHT = cfg["render"], cfg["camera"], cfg["light"]


def pick_device():
    """GPU (CUDA, then OPTIX: a GTX 1060 has no RT cores). `auto` and `gpu` fail with an error when there is no GPU;
    the CPU is used only with an explicit `--device cpu`."""
    if DEVICE == "cpu":
        print("render device: CPU (explicit)")
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("CUDA", "OPTIX"):
        try:
            prefs.compute_device_type = kind
            prefs.refresh_devices()
            gpus = [d for d in prefs.get_devices_for_type(kind) if d.type == kind]
        except Exception as e:  # type not compiled in
            print(f"device {kind}: unavailable ({e})")
            continue
        if gpus:
            for d in prefs.devices:
                d.use = d.type == kind
            print("render device: GPU", kind, [d.name for d in gpus])
            return "GPU"
    raise SystemExit("error: no GPU (OPTIX/CUDA) found; refusing to render on the CPU. "
                     "Use --device cpu to opt in.")


def setup_scene():
    bpy.ops.wm.open_mainfile(filepath=MODEL)
    sc = bpy.context.scene
    sc.render.engine = R["engine"]
    cy = sc.cycles
    cy.samples = int(SAMPLES or R["samples"])
    cy.use_denoising = R["denoise"]
    cy.denoiser = R.get("denoiser", "OPENIMAGEDENOISE")   # OPTIX runs on the GPU (works on Pascal)
    cy.denoising_input_passes = R.get("denoise_passes", "RGB_ALBEDO_NORMAL")
    cy.denoising_prefilter = R.get("denoise_prefilter", "ACCURATE")
    cy.use_adaptive_sampling = R.get("adaptive", False)
    cy.adaptive_threshold = R.get("adaptive_threshold", 0.02)
    cy.adaptive_min_samples = 0
    cy.max_bounces = 6
    cy.diffuse_bounces = 3
    cy.glossy_bounces = 4
    cy.transmission_bounces = 2
    cy.transparent_max_bounces = 4
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.sample_clamp_indirect = 10.0
    sc.render.use_persistent_data = True   # keep geometry/BVH between animation frames
    sc.cycles.device = pick_device()
    sc.render.threads_mode = "FIXED"
    sc.render.threads = 2  # keep the host light, the GPU does the work
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    sc.view_settings.view_transform = R["view_transform"]
    try:
        sc.view_settings.look = R["look"]
    except TypeError:
        print("look not available, keeping None")
    sc.view_settings.exposure = R["exposure"]
    sc.render.resolution_percentage = 100

    # world: soft neutral fill, visible only in reflections (film is transparent)
    w = bpy.data.worlds.new("studio")
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = LIGHT["world"]["strength"]
    # vertical gradient: dark floor, grey horizon, bright ceiling (what glossy surfaces reflect)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = -0.6
    rng.inputs["From Max"].default_value = 0.9
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    g = LIGHT["world"]["ramp"]
    ramp.color_ramp.elements[0].color = (g[0], g[0], g[0], 1)
    ramp.color_ramp.elements[1].color = (g[2], g[2], g[2], 1)
    mid = ramp.color_ramp.elements.new(0.5)
    mid.color = (g[1], g[1], g[1], 1)
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    sc.world = w

    dg = bpy.context.evaluated_depsgraph_get()
    tris = sum(len(o.evaluated_get(dg).to_mesh().polygons) for o in sc.objects if o.type == "MESH")
    print(f"polygons after modifiers: {tris}")
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36.0
    cam.data.lens = CAM["lens"]
    cam.data.clip_end = 1000.0

    lights = {}
    for name, c in LIGHT.items():
        if name == "world":
            continue
        ld = bpy.data.lights.new(name, "AREA")
        if isinstance(c["size"], list):  # strip softbox: [width, height]
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = c["size"]
        else:
            ld.shape = "SQUARE"
            ld.size = c["size"]
        ld.energy = c["energy"]
        ld.color = c["color"]
        ob = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(ob)
        lights[name] = ob

    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.is_shadow_catcher = True
    return sc, cam, lights, floor


def aim(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def place_rig(cam, lights, shot, yaw_rig=0.0):
    az = math.radians(shot.get("azimuth", CAM["azimuth"]))
    el = math.radians(shot.get("elevation", CAM["elevation"]))
    tgt = Vector(shot.get("target", CAM["target"]))
    fw = shot.get("frame_width", CAM["frame_width"])
    dist = fw * CAM["lens"] / 36.0
    cam.location = tgt + dist * Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    aim(cam, tgt)
    for name, ob in lights.items():
        p = Vector(LIGHT[name]["pos"])
        # the studio rotates with the camera azimuth so the key stays top-left of the view
        ob.location = Vector((0, 0, 2.7)) + Vector((p.x * math.cos(az) - p.y * math.sin(az),
                                                    p.x * math.sin(az) + p.y * math.cos(az), p.z))
        aim(ob, (0, 0, 2.2))


def set_pose(shot, lid_frac, yaw_deg):
    objs = bpy.data.objects
    angle = math.radians(R["open_angle"]) * lid_frac
    objs["Case_Lid"].rotation_euler = (-angle, 0, 0)
    objs["Rig"].rotation_euler = (0, 0, math.radians(yaw_deg))  # yaw about the case center


def build_rig():
    """Parent the whole model to one empty so yaw is a single rotation."""
    rig = bpy.data.objects.new("Rig", None)
    bpy.context.scene.collection.objects.link(rig)
    for o in list(bpy.data.objects):
        if o.parent is None and o.name.startswith(("Case_", "Pod_")):
            o.parent = rig
    return rig


def render_frame(sc, path, size, shadow):
    sc.render.resolution_x = max(8, int(size[0] * SCALE))
    sc.render.resolution_y = max(8, int(size[1] * SCALE))
    bpy.data.objects["Floor"].hide_render = not shadow
    sc.render.filepath = str(path)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"  render+denoise {time.time() - t:.2f}s", flush=True)


def smoothstep(t):
    return t * t * (3 - 2 * t)


def encode(frames, dst):
    exe = shutil.which("img2webp")
    if not exe:
        raise SystemExit("img2webp not found (use the nix develop .#render shell)")
    cmd = [exe, "-loop", "0", "-lossy", "-q", "90", "-d", "33"] + [str(f) for f in frames] + ["-o", str(dst)]
    subprocess.run(cmd, check=True)


def main():
    sc, cam, lights, floor = setup_scene()
    build_rig()
    home = {n: tuple(bpy.data.objects[n].location) for n in ("Pod_L", "Pod_R")}  # in-case pose from model.py
    names = [k for k, v in cfg["shots"].items() if not v.get("debug")] if WANT == "all" else WANT.split(",")
    OUT.mkdir(parents=True, exist_ok=True)
    produced = {}
    for name in names:
        shot = cfg["shots"][name]
        t0 = time.time()
        # reset pose of the two pods to the in-case pose (shot "place" overrides them)
        for n in ("Pod_L", "Pod_R"):
            o = bpy.data.objects[n]
            o.location = home[n]
            o.rotation_euler = (0, 0, 0)
            bpy.data.objects[n + "_TipRig"].rotation_euler = (0, (1 if n.endswith("_L") else -1) * math.radians(shot.get("tip_tilt", CAM.get("tip_tilt", 20.0))), 0)
        only = shot.get("only")
        for o in bpy.data.objects:
            top = o
            while top.parent is not None and top.parent.name != "Rig":
                top = top.parent
            if top.name.startswith(("Case_", "Pod_")):
                o.hide_render = bool(only) and top.name not in only
        for n, p in shot.get("place", {}).items():
            o = bpy.data.objects[n]
            o.location = p["loc"]
            o.rotation_euler = [math.radians(a) for a in p["rot"]]
        place_rig(cam, lights, shot)
        size = shot["size"]
        shadow = shot.get("shadow", True)
        fdir = OUT / name
        if fdir.exists():
            shutil.rmtree(fdir)
        fdir.mkdir(parents=True)
        outs = shot["out"] if isinstance(shot["out"], list) else [shot["out"]]
        if shot["kind"] == "anim":
            n = shot["frames"]
            frames = []
            for i in range(n):
                lid = shot["lid"]
                f = lid[0] + (lid[1] - lid[0]) * smoothstep(i / (n - 1))
                yaw = shot.get("yaw", 0.0) * math.sin(2 * math.pi * i / n)
                set_pose(shot, f, yaw)
                p = fdir / f"{i:04d}.png"
                render_frame(sc, p, size, shadow)
                frames.append(p)
                print(f"[{name}] frame {i + 1}/{n}  {time.time() - t0:.0f}s", flush=True)
            encode(frames, OUT / outs[0])
            produced[outs[0]] = {"frames": n, "size": size, "delay_ms": 33}
        else:
            set_pose(shot, shot["lid"] if "lid" in shot else 0.0, 0.0)
            p = fdir / "still.png"
            render_frame(sc, p, size, shadow)
            for o in outs:
                fname, _, px = o.partition(":")
                dst = OUT / fname
                if px:
                    sc2 = int(px)
                    # extra smaller size: re-render at that size for crisp edges
                    render_frame(sc, dst, (sc2, sc2), shadow)
                else:
                    shutil.copy(p, dst)
                produced[fname] = {"size": list(size) if not px else [int(px)] * 2}
        if not KEEP:
            shutil.rmtree(fdir)
        print(f"[{name}] done in {time.time() - t0:.0f}s", flush=True)

    if WANT == "all" and "--no-manifest" not in argv:
        manifest = {"version": 1, "model": Path(MODEL).name, "files": produced,
                    "generated": time.strftime("%Y-%m-%dT%H:%M:%S")}
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print("manifest written")


main()
