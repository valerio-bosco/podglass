"""Build the AirPods Pro 2 (Lightning) model procedurally and save a .blend.

Run:  nix develop .#render -c blender -b -P tools/render/model.py -- [--out assets/models/airpods-pro2.blend]

Units: 1 Blender unit = 1 cm. The case stands on z = 0, width along X, depth along Y, the hinge at
the back (+Y), the camera looks from the front (-Y). Objects (used by render.py / shots.toml):
  Case_Base, Case_Lid (origin = hinge axis, open by rotating about X by a negative angle),
  Case_Hinge, Case_LED, Case_Loop, Pod_L, Pod_R (empties, children: Body, Tip, Mesh, ...).
All dimensions below are in cm and come from the real Pro 2 Lightning case (60.6 x 45.2 x 21.7 mm).
"""
import math
import sys

import bmesh
import bpy
from mathutils import Vector

# ---- dimensions (cm) --------------------------------------------------------------------------
W, D, H = 6.06, 2.17, 4.52          # case width (X), depth (Y), height (Z)
LID_H = 1.35                        # lid height, the seam is at SEAM = H - LID_H
SEAM = H - LID_H
EDGE = 0.75                         # outer rounding radius of the case
POD_X = 1.42                        # pod centers at +-POD_X
POD_DROP = 0.42                     # head center sits this far below the seam
CAVITY_R = 0.95
HINGE_Y = D / 2 - 0.2               # hinge axis (y, z = SEAM)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[args.index("--out") + 1] if "--out" in args else "assets/models/airpods-pro2.blend"


# ---- helpers ---------------------------------------------------------------------------------
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def link(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def apply_mod(obj, mod):
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def smooth(obj, angle=35, weighted=False):
    """Smooth shading with sharp edges above `angle` degrees. `weighted` adds area-weighted normals,
    which keeps big flat faces flat (no shading creases from the bevel rings)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    lim = math.radians(angle)
    for e in bm.edges:
        if len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0) < lim
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    if weighted:
        m = obj.modifiers.new("wn", "WEIGHTED_NORMAL")
        m.mode = "FACE_AREA"
        m.weight = 60
        m.keep_sharp = True
        apply_mod(obj, m)


def bevel(obj, width, segments=3, angle=None, profile=0.5):
    m = obj.modifiers.new("bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.profile = profile
    m.affect = "EDGES"
    m.limit_method = "ANGLE" if angle else "NONE"
    if angle:
        m.angle_limit = math.radians(angle)
    apply_mod(obj, m)


def rbox(name, sx, sy, sz, r, segs=10, profile=0.6, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * sx + center[0], v.co.y * sy + center[1], v.co.z * sz + center[2]))
    ob = link(name, bm)
    if r > 0:
        bevel(ob, r, segs, profile=profile)
    return ob


def boolean(obj, cutter, op="DIFFERENCE", keep=False):
    m = obj.modifiers.new("bool", "BOOLEAN")
    m.operation = op
    m.object = cutter
    m.solver = "EXACT"
    apply_mod(obj, m)
    if not keep:
        bpy.data.objects.remove(cutter, do_unlink=True)


def catmull(pts, n=6):
    """Sample a Catmull-Rom spline through 2D points (profile curves for lathes)."""
    out = []
    P = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t +
                                    (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 +
                                    (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


def lathe(name, profile, steps=48, spline=True):
    """Solid of revolution around Z from a (radius, z) profile that starts and ends on the axis."""
    pts = catmull(profile) if spline else profile
    bm = bmesh.new()
    vs = [bm.verts.new((max(r, 0.0), 0, z)) for r, z in pts]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=steps)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = link(name, bm)
    smooth(ob, 50)
    return ob


def cyl(name, r, depth, loc, rot=(0, 0, 0), verts=32):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=depth)
    ob = link(name, bm)
    ob.location = loc
    ob.rotation_euler = rot
    return ob


# ---- materials -------------------------------------------------------------------------------
def material(name, color, rough=0.3, metal=0.0, coat=0.0, coat_rough=0.05, emission=None, bump=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    if emission:
        b.inputs["Emission Color"].default_value = (*emission[0], 1)
        b.inputs["Emission Strength"].default_value = emission[1]
    if bump:  # procedural bump: (scale, strength)
        tex = nt.nodes.new("ShaderNodeTexChecker")
        tex.inputs["Scale"].default_value = bump[0]
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump[1]
        nt.links.new(tex.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], b.inputs["Normal"])
    return m


def make_materials():
    return {
        "white": material("White gloss", (0.93, 0.93, 0.92), rough=0.22, coat=0.7, coat_rough=0.04),
        "white_rough": material("White inside", (0.88, 0.88, 0.87), rough=0.5),
        "grey_tip": material("Silicone tip", (0.4, 0.41, 0.42), rough=0.5),
        "mesh": material("Mesh", (0.008, 0.008, 0.01), rough=0.85, bump=(160.0, 0.6)),
        "steel": material("Steel", (0.78, 0.78, 0.8), rough=0.14, metal=1.0),
        "dark": material("Dark", (0.01, 0.01, 0.012), rough=0.5),
        "led": material("LED", (0.6, 1.0, 0.55), rough=0.4, emission=((0.6, 1.0, 0.55), 6.0)),
    }


def assign(obj, mats, names, picker):
    """picker(poly) -> index into names."""
    for n in names:
        obj.data.materials.append(mats[n])
    for p in obj.data.polygons:
        p.material_index = picker(p)


# ---- case ------------------------------------------------------------------------------------
def build_case(mats):
    """Base and lid as two separate objects with a small seam gap."""
    gap = 0.02

    def shell(name):
        ob = rbox(name, W, D, H, EDGE, segs=12, profile=0.62, center=(0, 0, H / 2))
        # hinge notch at the back
        boolean(ob, rbox("notch", 2.4, 1.0, 0.76, 0.0, segs=1, center=(0, D / 2 - 0.2, SEAM)))
        return ob

    # ---- base
    base = shell("Case_Base")
    boolean(base, rbox("keep", W * 2, D * 2, SEAM - gap + 5, 0.0, segs=1, center=(0, 0, (SEAM - gap - 5) / 2)), "INTERSECT")
    boolean(base, rbox("pocket", 0.6, 0.62, 0.74, 0.12, segs=4, center=(W / 2, 0.0, 0.95)))
    boolean(base, rbox("port", 0.86, 0.2, 1.0, 0.09, segs=4, center=(-0.5, 0.0, 0.0)))
    for row in (-1, 1):
        for i in range(7):
            boolean(base, cyl("hole", 0.045, 1.0, (0.55 + i * 0.2, row * 0.11, 0.0), verts=12))
    boolean(base, cyl("ledcut", 0.085, 0.1, (0, -D / 2, SEAM - 0.55), rot=(math.pi / 2, 0, 0), verts=24))
    for sx in (-1, 1):  # pod cavities: flared lathe cutters
        prof = [(0, SEAM - 1.6), (CAVITY_R - 0.1, SEAM - 1.6), (CAVITY_R - 0.03, SEAM - 1.4),
                (CAVITY_R, SEAM - 0.4), (CAVITY_R + 0.0, SEAM - 0.1), (CAVITY_R + 0.12, SEAM + 0.02),
                (CAVITY_R + 0.12, SEAM + 0.3), (0, SEAM + 0.3)]
        c = lathe("cav", prof, steps=64)
        c.location = (sx * POD_X, 0, 0)
        boolean(base, c)
    bevel(base, 0.07, 2, angle=35)
    smooth(base, 35, weighted=True)

    # ---- lid (origin later moved to the hinge axis)
    lid = shell("Case_Lid")
    boolean(lid, rbox("keep", W * 2, D * 2, LID_H * 2, 0.0, segs=1, center=(0, 0, H - LID_H + gap + LID_H)), "INTERSECT")
    inset = 0.17
    boolean(lid, rbox("hollow", W - 2 * inset, D - 2 * inset, 2.0, EDGE - inset, segs=10, profile=0.62,
                      center=(0, 0, H - 0.14 - 1.0)))
    bevel(lid, 0.07, 2, angle=35)
    smooth(lid, 35, weighted=True)

    # materials
    def base_pick(p):
        c, n = p.center, p.normal
        inside = c.z > SEAM - 1.8 and (n.z > 0.6 or math.hypot(abs(c.x) - POD_X, c.y) < CAVITY_R + 0.15)
        if c.z < 0.9 and abs(c.y) < 0.3 and (-1.0 < c.x < 0.0 or 0.4 < c.x < 2.2) and c.z > 0.02:
            return 2  # port and speaker holes
        return 1 if inside else 0
    assign(base, mats, ["white", "white_rough", "dark"], base_pick)

    def lid_pick(p):
        c, n = p.center, p.normal
        inner = n.z < -0.3 or (abs(c.x) < W / 2 - inset - 0.05 and abs(c.y) < D / 2 - inset - 0.05
                               and c.z < H - 0.16 and c.z > SEAM + 0.3 and abs(n.z) < 0.99 and False)
        return 1 if inner else 0
    assign(lid, mats, ["white", "white_rough"], lid_pick)
    return base, lid


def build_hardware(mats, lid):
    hinge = cyl("Case_Hinge", 0.17, 2.25, (0, HINGE_Y, SEAM), rot=(0, math.pi / 2, 0), verts=40)
    bevel(hinge, 0.02, 2, angle=40)
    smooth(hinge, 40)
    hinge.data.materials.append(mats["steel"])

    led = cyl("Case_LED", 0.07, 0.03, (0, -D / 2 + 0.01, SEAM - 0.55), rot=(math.pi / 2, 0, 0), verts=24)
    led.data.materials.append(mats["led"])

    bpy.ops.mesh.primitive_torus_add(major_radius=0.2, minor_radius=0.04, major_segments=40, minor_segments=14,
                                     location=(W / 2 - 0.2, 0.0, 0.92), rotation=(math.pi / 2, 0, 0))
    loop = bpy.context.active_object
    loop.name = "Case_Loop"
    loop.data.materials.append(mats["steel"])
    bpy.ops.object.shade_smooth()

    # move lid origin to the hinge axis
    bpy.context.scene.cursor.location = (0, HINGE_Y, SEAM)
    activate(lid)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    return hinge, led, loop


# ---- pods ------------------------------------------------------------------------------------
IN_CASE_TILT = 8.0  # degrees, tip lean towards the front while the pod sits in the case
TIP_TILT = 0.0  # tips are built along +z; the 'TipRig' empty tilts them (render.py sets the angle per shot)


def build_pod(name, mats):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)

    # head + stem as one body of revolution around the stem axis (z)
    prof = [(0.0, -2.26), (0.13, -2.25), (0.22, -2.19), (0.26, -2.0), (0.285, -1.5), (0.34, -1.1),
            (0.48, -0.86), (0.68, -0.66), (0.82, -0.38), (0.88, 0.0), (0.82, 0.42), (0.63, 0.74),
            (0.34, 0.88), (0.0, 0.9)]
    body = lathe(name + "_Body", prof, steps=56)
    body.scale = (1.0, 0.94, 1.0)
    body.data.materials.append(mats["white"])
    body.parent = root

    # silicone tip: neck + dome, built along +z then tilted about x
    tprof = [(r, z * (0.88 if z > 0.4 else 1.0)) for r, z in [(0.0, 0.4), (0.46, 0.4), (0.47, 0.95), (0.58, 1.05), (0.66, 1.2), (0.65, 1.38),
             (0.56, 1.52), (0.42, 1.58), (0.31, 1.58), (0.3, 1.5), (0.0, 1.5)]]
    rig = bpy.data.objects.new(name + "_TipRig", None)   # tilt the tip by rotating this about x
    bpy.context.scene.collection.objects.link(rig)
    rig.parent = root
    rig.rotation_euler = (math.radians(IN_CASE_TILT), 0, 0)
    tip = lathe(name + "_Tip", tprof, steps=56)
    tip.data.materials.append(mats["grey_tip"])
    tip.parent = rig

    # black mesh disc in the tip opening
    mesh = cyl(name + "_Mesh", 0.29, 0.02, (0, 0, 1.505 * 0.88), verts=40)
    mesh.data.materials.append(mats["mesh"])
    mesh.parent = rig

    # small vent / mic dots on the head and the steel charging contacts at the stem end
    for i, (x, z) in enumerate(((0.0, -0.62), (0.28, -0.7))):
        d = cyl(f"{name}_Dot{i}", 0.06 if i else 0.11, 0.02, (0, 0, 0), verts=16)
        d.location = (x, 0.78 if not i else 0.7, z)
        d.rotation_euler = (math.pi / 2 - 0.35, 0, 0)
        d.data.materials.append(mats["mesh"])
        d.parent = root
    for sx in (-0.07, 0.07):
        c = cyl(f"{name}_Contact", 0.045, 0.02, (sx, 0, -2.255), verts=12)
        c.data.materials.append(mats["steel"])
        c.parent = root

    # pressure sensor flat on the stem (a slim inset capsule on the +y face)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12, location=(0, 0.27, -1.45))
    s = bpy.context.active_object
    s.name = name + "_Sensor"
    s.scale = (0.05, 0.03, 0.38)
    s.data.materials.append(mats["white_rough"])
    bpy.ops.object.shade_smooth()
    s.parent = root
    return root


def main():
    reset()
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 0.01
    mats = make_materials()
    base, lid = build_case(mats)
    hinge, led, loop = build_hardware(mats, lid)
    for sx, nm in ((-1, "Pod_L"), (1, "Pod_R")):
        pod = build_pod(nm, mats)
        pod.location = (sx * POD_X, 0.0, SEAM - POD_DROP)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
