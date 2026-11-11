"""Render silhouette masks of our model from the reference cameras.
nix develop .#render -c blender -b -P tools/render/sf/sfrender.py -- --views front,right [--hide Case_Lid,Pod_] [--lid 121] [--pose Pod_L=x,y,z,rx,ry,rz;Pod_R=...] [--exploded] --out DIR
Workbench silhouettes (white on transparent, ~1-2 s each) from the cameras of the reference reference shots;
--scale (reference-scene units per cm) and --off (reference-scene position of our origin) are fitted on the case base
(front IoU 0.994, end 0.97)."""
import json, math, sys
import bpy
from mathutils import Matrix, Quaternion, Vector
a = sys.argv[sys.argv.index("--") + 1:]
opt = lambda k, d: a[a.index(k) + 1] if k in a else d
VIEWS = opt("--views", "front").split(",")
S = float(opt("--scale", "0.000996"))                     # reference-scene units per cm
O = Vector([float(v) for v in opt("--off", "0,-0.000315,0.000157").split(",")])   # reference-scene position of our origin
HIDE = [h for h in opt("--hide", "").split(",") if h]
OUT = opt("--out", "/tmp/claude-1000/m7/ours")
FOV = float(opt("--fov", "6"))
# pole views: the viewer rolls the camera about the view axis (fitted on the case silhouette: IoU 0.96)
UPS = {"top": (-1, 0, 0), "bottom": (-1, 0, 0)}
ROLLS = {"top": "197", "bottom": "-60"}
for u in opt("--up", "").split(";"):
    if u:
        k, v = u.split("="); UPS[k] = tuple(float(c) for c in v.split(","))
CASE_T, CASE_D = Vector((0, 0.0014, 0.0038)), 0.08
POD_T, POD_D = Vector((-0.0018, -0.0002, 0.0062)), 0.035
POD_DK = {"pod-back": 0.975}           # fitted camera distance factor of the pod-back shot (the others fit at 1.0)
DIRS = {"front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0), "left": (-1, 0, 0), "top": (0, -0.002, 1),
        "bottom": (0, -0.002, -1), "threequarter": (0.6, -1, 0.5), "frontlow": (0, -1, -0.25), "backhigh": (-0.5, 1, 0.6),
        "pod-outer": (-1, 0, 0), "pod-front": (0, -1, 0), "pod-back": (0, 1, 0), "pod-top": (0, -0.002, 1),
        "pod-3q": (-0.6, -1, 0.3), "pod-innerfront": (0.5, -1, 0)}
bpy.ops.wm.open_mainfile(filepath=opt("--model", "assets/models/airpods-pro2.blend"))
sc = bpy.context.scene
for o in bpy.data.objects:
    top = o
    while top.parent: top = top.parent
    o.hide_render = any(top.name.startswith(h) or o.name.startswith(h) for h in HIDE) or o.type == "LIGHT"
for spec in [q for q in opt("--pose", "").split(";") if q]:    # world pose of a pod root: cm and degrees (XYZ euler)
    nm, v6 = spec.split("=")
    v6 = [float(t) for t in v6.split(",")]
    bpy.data.objects[nm].location = v6[:3]
    bpy.data.objects[nm].rotation_euler = [math.radians(t) for t in v6[3:]]
if "--exploded" in a:    # reference pose: pods unrotated at the fitted roots (tools/render/profiles_pod.json), floating above the case
    rx, ry, rz = json.load(open("tools/render/profiles_pod.json"))["root"]
    for nm, sg in (("Pod_L", 1), ("Pod_R", -1)):
        bpy.data.objects[nm].location = (rx * sg, ry, rz)
        bpy.data.objects[nm].rotation_euler = (0, 0, 0)
lid_ang = opt("--lid", None)
if lid_ang is not None:
    bpy.data.objects["Case_Lid"].rotation_euler[0] = -math.radians(float(lid_ang))
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "SINGLE"
sc.display.shading.single_color = (1, 1, 1)
sc.render.film_transparent = True
MATCAP = opt("--matcap", None)      # e.g. zebra_h.png, check_reflection_vertical.exr: reflective shading to judge surface smoothness
if MATCAP:
    sc.display.shading.light = "MATCAP"
    sc.display.shading.studio_light = MATCAP
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("W")
    sc.world.color = (0.5, 0.5, 0.5)
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 2796, 1440, 100
sc.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("SFCam", bpy.data.cameras.new("SFCam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.sensor_fit = "VERTICAL"
cam.data.angle = math.radians(FOV)
cam.data.clip_start, cam.data.clip_end = 0.1, 1000
for vv in VIEWS:
    v, _, roll = vv.partition("@")     # "top@30": roll the camera about the view axis by 30 degrees (default: ROLLS)
    roll = roll or ROLLS.get(v, "")
    T, D = (POD_T, POD_D) if v.startswith("pod-") else (CASE_T, CASE_D)
    d = Vector(DIRS[v]).normalized()
    eye_sf = T + d * D * (POD_DK.get(v, 1.0) if v.startswith("pod-") else 1.0)
    eye, tgt = (eye_sf - O) / S, (T - O) / S
    cam.location = eye
    if v in UPS or roll:
        z_ax = (eye - tgt).normalized()
        up_v = Vector(UPS.get(v, (0, 0, 1)))
        if roll:
            up_v = Matrix.Rotation(math.radians(float(roll)), 3, z_ax) @ up_v
        x_ax = up_v.cross(z_ax).normalized()
        y_ax = z_ax.cross(x_ax)
        cam.rotation_euler = Matrix((x_ax, y_ax, z_ax)).transposed().to_euler()
    else:
        q = (tgt - eye).to_track_quat("-Z", "Y")
        if v == "pod-top":
            q = q @ Quaternion((0, 0, 1), math.pi)   # the reference top shots have -y up in the image
        cam.rotation_euler = q.to_euler()
    sc.render.filepath = f"{OUT}/{vv}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", vv)
