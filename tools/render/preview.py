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
LID = float(opt("--lid", "0"))
# name: (px w, px h, ortho_scale cm across the larger side, camera location, camera rotation deg, hide)
SEAM_Z = 3.0
VIEWS = {
    "front": (800, 660, 800 * 0.00824, (0, -60, 2.24), (90, 0, 0), ()),
    "pod": (700, 900, 900 * 0.00399, (-1.6 + 0.24, -60, SEAM_Z + 0.29 - 0.78), (90, 0, 0), ("Pod_R", "Case")),
    "end": (560, 1030, 1030 * 0.0049, (60, 0, 2.29), (90, 0, 90), ()),
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
