"""Workbench shape previews from the same cameras as the reference photos (orthographic where the photo is
straight on). Fast (about 1 s), no materials.

Run: nix develop .#render -c blender -b -P tools/render/preview.py -- --view front [--lid 0] [--out /tmp/p] [--model F]
Views: front (249), end (245), bottom (247), back (248), top (242), pod (241). The scale of each view is
fixed so that it can be overlaid on the photo crop made by tools/render/compare.py.
"""
import math
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return args[args.index(name) + 1] if name in args else default


VIEW = opt("--view", "front")
OUT = opt("--out", "/tmp/m6prev")
MODEL = opt("--model", "assets/models/airpods-pro2.blend")
LID = float(opt("--lid", "1" if VIEW.startswith("sk-") else "0"))
# name: (px w, px h, ortho_scale cm across the larger side, camera location, camera rotation deg, hide)
SEAM_Z = 3.0
VIEWS = {
    "front": (800, 660, 800 * 0.00824, (0, -60, 2.24), (90, 0, 0), ()),
    "pod": (700, 900, 900 * 0.00399, (-1.6 + 0.24, -60, SEAM_Z + 0.29 - 0.78), (90, 0, 0), ("Pod_R", "Case")),
    "end": (560, 1030, 1030 * 0.0049, (60, 0, 2.29), (90, 0, 90), ()),
    # reference reference views (assets/reference/shots): 2796x1440 at 175 px/cm, case bottom at z = 0, case centred
    "sk-front": (2796, 1440, 2796 / 175, (0, -60, 3.65), (90, 0, 0), ()),
    "sk-right": (2796, 1440, 2796 / 175, (60, 0, 3.65), (90, 0, 90), ()),
    "sk-left": (2796, 1440, 2796 / 175, (-60, 0, 3.65), (90, 0, -90), ()),
    "sk-back": (2796, 1440, 2796 / 175, (0, 60, 3.65), (90, 0, 180), ()),
    # left pod from the back / the front (compare pod-back, pod-front); 3 cm per 600 px would be too tight: 5 cm across
    "pod-back": (900, 900, 5.0, (-1.6, 60, 2.6), (90, 0, 180), ("Pod_R", "Case")),
    "pod-front": (900, 900, 5.0, (-1.6, -60, 2.6), (90, 0, 0), ("Pod_R", "Case")),
    "sk-top": (2796, 1440, 2796 / 175, (0, 0, 60), (0, 0, 0), ()),
    "sk-bottom": (2796, 1440, 2796 / 175, (0, 0, -60), (180, 0, 0), ()),
}
PODONLY = ("pod",)

bpy.ops.wm.open_mainfile(filepath=MODEL)
sc = bpy.context.scene
w, h, osc, loc, rot, hide = VIEWS[VIEW]
cam = bpy.data.objects.new("PCam", bpy.data.cameras.new("PCam"))
sc.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = osc
cam.data.clip_end = 500
cam.location = loc
cam.rotation_euler = [math.radians(a) for a in rot]
sc.camera = cam
for o in bpy.data.objects:
    top = o
    while top.parent is not None:
        top = top.parent
    if any(top.name.startswith(h) for h in hide):
        o.hide_render = True
lid = bpy.data.objects.get("Case_Lid")
if lid:
    lid.rotation_euler = (-math.radians(100.0) * LID, 0, 0)
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x, sc.render.resolution_y = w, h
sc.render.resolution_percentage = 100
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "SINGLE"
sh.single_color = (0.85, 0.85, 0.85)
sh.show_cavity = True
sh.show_object_outline = True
sh.object_outline_color = (0.0, 0.0, 0.0)
sc.render.filepath = f"{OUT}/{VIEW}.png"
bpy.ops.render.render(write_still=True)
print("PREVIEW", sc.render.filepath)
