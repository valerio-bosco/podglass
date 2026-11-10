"""Build the AirPods Pro 2 (Lightning) model procedurally and save a .blend.

Run:  nix develop .#render -c blender -b -P tools/render/model.py -- [--out assets/models/airpods-pro2.blend]

Units: 1 Blender unit = 1 cm. The case stands on z = 0, width along X, depth along Y, the hinge at
the back (+Y), the camera looks from the front (-Y). Objects (used by render.py / shots.toml):
  Case_Base, Case_Lid (origin = hinge axis, open by rotating about X by a negative angle),
  Case_Hinge, Case_LED, Case_Loop, Pod_L, Pod_R (empties, children: Body, Tip, Mesh, ...).
All dimensions below are in cm and come from the real Pro 2 Lightning case (60.6 x 45.2 x 21.7 mm).
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

# ---- dimensions (cm) --------------------------------------------------------------------------
W, D, H = 6.0, 2.2, 4.5            # case width (X), depth (Y), height (Z); measured from the photos: 60 x 45 x 22 mm
LID_H = H / 3                       # the seam is one third from the top: SEAM = H - LID_H
SEAM = H - LID_H
N_FRONT, N_PLAN = 4.2, 3.2          # superellipse exponents: front view (x/z) and plan (x/y); 2 = ellipse, inf = box
DOME = 0.07                         # the flat top and bottom faces bulge by this much
WALL = 0.1                          # lid wall thickness
POD_SCALE = 0.92                    # pod size vs the model below: head ~1.55 wide vs 6.0 case (photos 242/243)
POD_X = 1.6                        # pod centers at +-POD_X
POD_RISE = 0.12                     # head center sits this far above the seam (only the top of the heads shows, photo 243)
CAVITY_R = 0.95
STEM_OFF = 0.42                     # the stem axis sits this far outwards of the head axis (photo 241)
LED_DROP = 0.83                     # status light below the seam (photo 249: 18% of the case height)
HINGE_Y = D / 2 - 0.06              # hinge axis (y, z = SEAM): on the back surface, so the lid does not dig into the base

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


def superell(name, a, b, c, n1=N_FRONT, n2=N_PLAN, center=(0, 0, 0), dome=DOME, nlat=72, nlon=144):
    """Superellipsoid with half sizes a, b, c: (|x/a|^n2 + |y/b|^n2)^(n1/n2) + |z/c|^n1 = 1.
    Flat top and bottom (poles) are bulged by `dome`."""
    e1, e2 = 2.0 / n1, 2.0 / n2

    def sp(v, e):
        return math.copysign(abs(v) ** e, v)
    bm = bmesh.new()
    rings = []
    for i in range(1, nlat):
        phi = -math.pi / 2 + math.pi * i / nlat
        rho = sp(math.cos(phi), e1)
        z = c * sp(math.sin(phi), e1) + math.copysign(dome * (1 - rho * rho), phi)
        ring = [bm.verts.new((a * rho * sp(math.cos(t), e2), b * rho * sp(math.sin(t), e2), z + center[2]))
                for t in (2 * math.pi * k / nlon for k in range(nlon))]
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(nlon):
            bm.faces.new((r0[k], r0[(k + 1) % nlon], r1[(k + 1) % nlon], r1[k]))
    for ring, up in ((rings[0], False), (rings[-1], True)):
        zc = center[2] + (c + dome if up else -c - dome)
        pole = bm.verts.new((0, 0, zc))
        for k in range(nlon):
            f = (ring[k], ring[(k + 1) % nlon], pole) if up else (ring[(k + 1) % nlon], ring[k], pole)
            bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = link(name, bm)
    smooth(ob, 60)
    return ob


def _profile():
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "tools/render"
    return json.load(open(os.path.join(here, "profiles.json")))["front"]


def traced_shell(name, hd_end=0.42, m=2.7, n_plan=N_PLAN, dome=DOME, nlat=96, nlon=160):
    """Case body from two traced silhouettes. At height z the plan section is a superellipse with half-width
    hw(z) from the front photo (249, tools/render/trace.py) and half-depth hd(z) from the end photo (245):
    an ellipse-like pill of exponent `m` that keeps a flat end face `hd_end` deep."""
    prof = _profile()
    zs_t = [r[0] for r in prof]
    hs_t = [r[1] for r in prof]
    for _ in range(4):  # smooth the traced noise (pixel steps would show as bands in the reflections)
        hs_t = [hs_t[0]] + [(hs_t[i - 1] + 2 * hs_t[i] + hs_t[i + 1]) / 4 for i in range(1, len(hs_t) - 1)] + [hs_t[-1]]

    def hw(z):
        z = min(max(z, 0.0), H)
        for i in range(len(zs_t) - 1):
            if z <= zs_t[i + 1]:
                t = (z - zs_t[i]) / (zs_t[i + 1] - zs_t[i])
                return hs_t[i] + t * (hs_t[i + 1] - hs_t[i])
        return hs_t[-1]

    def hd(z):
        u = abs(2 * z / H - 1)
        return hd_end + (D / 2 - hd_end) * (1 - u ** m) ** (1 / m)
    e = 2.0 / n_plan
    bm = bmesh.new()
    rings = []
    for i in range(nlat + 1):
        z = H / 2 * (1 - math.cos(math.pi * i / nlat))
        a_, b_ = hw(z), hd(z)
        ring = []
        for k in range(nlon):
            t = 2 * math.pi * k / nlon
            ring.append(bm.verts.new((a_ * math.copysign(abs(math.cos(t)) ** e, math.cos(t)),
                                      b_ * math.copysign(abs(math.sin(t)) ** e, math.sin(t)), z)))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(nlon):
            bm.faces.new((r0[k], r0[(k + 1) % nlon], r1[(k + 1) % nlon], r1[k]))
    for ring, up in ((rings[0], False), (rings[-1], True)):
        pole = bm.verts.new((0, 0, H + dome if up else -dome))
        for k in range(nlon):
            f = (ring[k], ring[(k + 1) % nlon], pole) if up else (ring[(k + 1) % nlon], ring[k], pole)
            bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = link(name, bm)
    smooth(ob, 60)
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
def material(name, color, rough=0.3, metal=0.0, coat=0.0, coat_rough=0.05, emission=None, bump=None, spec=0.5, sss=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = coat_rough
    b.inputs["Specular IOR Level"].default_value = spec
    if sss:  # (weight, radius colour): soft translucent look of silicone
        b.inputs["Subsurface Weight"].default_value = sss[0]
        b.inputs["Subsurface Radius"].default_value = sss[1]
        b.inputs["Subsurface Scale"].default_value = 0.15
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
        "white": material("White gloss", (0.95, 0.94, 0.91), rough=0.13, coat=1.0, coat_rough=0.015, spec=0.6),
        "white_rough": material("White inside", (0.92, 0.91, 0.88), rough=0.35, coat=0.0),
        "grey_tip": material("Silicone tip", (0.82, 0.77, 0.6), rough=0.4, sss=(0.35, (0.8, 0.82, 0.85))),
        "mesh": material("Mesh", (0.03, 0.03, 0.034), rough=0.6, bump=(420.0, 0.9)),
        "steel": material("Steel", (0.82, 0.82, 0.83), rough=0.28, metal=1.0),
        "dark": material("Dark", (0.01, 0.01, 0.012), rough=0.5),
        "led": material("LED", (0.6, 1.0, 0.55), rough=0.4, emission=((0.6, 1.0, 0.55), 6.0)),
    }


def assign(obj, mats, names, picker):
    """picker(poly) -> index into names."""
    for n in names:
        obj.data.materials.append(mats[n])
    for p in obj.data.polygons:
        p.material_index = picker(p)


def thumb_scoop():
    """Wide shallow scoop in the base just under the seam (photos 249, 244): about half the case width
    (3.0 cm), 0.4 cm tall, 0.2 cm deep, smooth concave."""
    depth, b = 0.2, 0.5
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=64, ring_count=32,
                                         location=(0, -D / 2 - b + depth, SEAM - 0.17))
    o = bpy.context.active_object
    k = math.sqrt(1 - ((b - depth) / b) ** 2)      # chord fraction at the case surface
    o.scale = (1.5 / k, b, 0.23 / k)
    bpy.ops.object.transform_apply(scale=True)
    return o


# ---- case ------------------------------------------------------------------------------------
def build_case(mats):
    """Base and lid as two separate objects with a small seam gap."""
    gap = 0.02

    def shell(name):
        ob = traced_shell(name)
        # hinge notch at the back (the steel plate sits in it)
        boolean(ob, rbox("notch", 3.2, 0.3, 0.9, 0.0, segs=1, center=(0, HINGE_Y + 0.1, SEAM)))
        return ob

    # ---- base
    base = shell("Case_Base")
    boolean(base, rbox("keep", W * 2, D * 2, SEAM - gap + 5, 0.0, segs=1, center=(0, 0, (SEAM - gap - 5) / 2)), "INTERSECT")
    # lanyard slot in the right end (photo 246): stadium 1.0 (z) x 0.46 (y), dark inside
    boolean(base, rbox("pocket", 0.7, 0.46, 1.0, 0.22, segs=6, center=(W / 2, 0.0, SEAM - 0.91)))
    # Lightning slot (photo 247): centered, 1.0 x 0.3, rounded ends; speaker holes 3 left + 1 right of it
    boolean(base, rbox("port", 1.0, 0.3, 1.0, 0.14, segs=6, center=(0.0, 0.0, 0.0)))
    for hx in (-2.04, -1.79, -1.54, 1.57):
        boolean(base, cyl("hole", 0.07, 1.0, (hx, 0.0, 0.0), verts=12))
    boolean(base, cyl("ledcut", 0.06, 0.1, (0, -D / 2, SEAM - LED_DROP), rot=(math.pi / 2, 0, 0), verts=24))
    boolean(base, thumb_scoop())
    # recessed top face: a thin rim stands around the interior (photos 242/243)
    rec = superell("rec", W / 2 - 0.2, D / 2 - 0.2, 0.5, center=(0, 0, SEAM - gap + 0.5 - 0.07), dome=0.0, nlat=8, nlon=96)
    boolean(base, rec)
    for sx in (-1, 1):  # pod cavities: bowl for the head, offset slim cup for the stem
        prof = [(0, SEAM - 1.25), (0.55, SEAM - 1.2), (0.86, SEAM - 0.85), (CAVITY_R - 0.04, SEAM - 0.35),
                (CAVITY_R, SEAM - 0.2), (CAVITY_R + 0.16, SEAM - 0.07), (CAVITY_R + 0.2, SEAM + 0.3), (0, SEAM + 0.3)]
        c = lathe("cav", prof, steps=64)
        c.scale = (1.0, 0.82, 1.0)
        c.location = (sx * POD_X, 0, 0)
        boolean(base, c)
        sp = [(0, SEAM - 2.4), (0.3, SEAM - 2.38), (0.42, SEAM - 2.2), (0.42, SEAM - 0.8), (0, SEAM - 0.8)]
        c = lathe("cavs", sp, steps=40)
        c.scale = (1.0, 0.85, 1.0)
        c.location = (sx * (POD_X + STEM_OFF * POD_SCALE), 0, 0)
        boolean(base, c)
    boolean(base, rbox("trough", 3.0, 1.3, 1.4, 0.2, segs=5, center=(0, 0, SEAM - 0.5)))  # where the tips lie
    bevel(base, 0.1, 2, angle=35)
    smooth(base, 35, weighted=True)

    # ---- lid (origin later moved to the hinge axis): solid with two bowls for the pod heads
    lid = shell("Case_Lid")
    boolean(lid, rbox("keep", W * 2, D * 2, LID_H * 2, 0.0, segs=1, center=(0, 0, H - LID_H + gap + LID_H)), "INTERSECT")
    for sx in (-1, 1):
        prof = [(0, SEAM + 1.42), (0.5, SEAM + 1.37), (0.88, SEAM + 1.05), (1.08, SEAM + 0.4), (1.14, SEAM - 0.1), (0, SEAM - 0.1)]
        c = lathe("bowl", prof, steps=64)
        c.scale = (1.0, 0.78, 1.0)
        c.location = (sx * POD_X, 0, 0)
        boolean(lid, c)
    lrec = superell("lrec", W / 2 - 0.2, D / 2 - 0.2, 0.5, center=(0, 0, SEAM + gap - 0.5 + 0.07), dome=0.0, nlat=8, nlon=96)
    boolean(lid, lrec)
    bevel(lid, 0.1, 2, angle=35)
    smooth(lid, 35, weighted=True)

    # materials
    def base_pick(p):
        c, n = p.center, p.normal
        if c.z < 0.9 and abs(c.y) < 0.3 and c.z > 0.02 and (abs(c.x) < 0.6 or abs(abs(c.x) - 1.8) < 0.5):
            return 2  # port and speaker holes
        if W / 2 - 0.5 < c.x < W / 2 - 0.08 and abs(c.y) < 0.3 and SEAM - 1.5 < c.z < SEAM - 0.3:
            return 2  # lanyard slot
        d0 = math.hypot(abs(c.x) - POD_X, c.y)
        d1 = math.hypot(abs(c.x) - POD_X - STEM_OFF, c.y)
        inside = c.z > SEAM - 2.6 and (d0 < 1.3 or d1 < 0.62 or (abs(c.x) < 1.7 and abs(c.y) < 0.75 and c.z > SEAM - 1.3)
                                      or (n.z > 0.6 and c.z > SEAM - 0.2))
        return 1 if inside else 0
    assign(base, mats, ["white", "white_rough", "dark"], base_pick)

    def lid_pick(p):
        c, n = p.center, p.normal
        d0 = math.hypot(abs(c.x) - POD_X, c.y)
        return 1 if (c.z < SEAM + 1.4 and (n.z < -0.3 or d0 < 1.3) and c.z < H - 0.2) else 0
    assign(lid, mats, ["white", "white_rough"], lid_pick)
    return base, lid


def build_hardware(mats, lid):
    # steel hinge plate on the back (photo 248): about half the width, 0.7 high, straddling the seam, two small slits
    hinge = rbox("Case_Hinge", 3.0, 0.12, 0.7, 0.03, segs=2, center=(0, D / 2 - 0.045, SEAM + 0.15))
    smooth(hinge, 40)
    hinge.data.materials.append(mats["steel"])
    # photo 248: the plate is split by two L-shaped slits (vertical, then along the seam to the outside)
    yy = D / 2 + 0.018
    cuts = []
    for sx in (-1, 1):
        cuts.append(rbox("slit", 0.035, 0.03, 0.66 * 0.5 + 0.35 - 0.1, 0.0, segs=1, center=(sx * 0.82, yy, SEAM + 0.15 + 0.17)))
        cuts.append(rbox("slit", 0.7, 0.03, 0.035, 0.0, segs=1, center=(sx * (0.82 + 0.35), yy, SEAM - 0.02)))
    for c_ in cuts:
        c_.data.materials.append(mats["dark"])
        c_.parent = hinge

    led = cyl("Case_LED", 0.06, 0.03, (0, -D / 2 + 0.01, SEAM - LED_DROP), rot=(math.pi / 2, 0, 0), verts=24)
    led.data.materials.append(mats["led"])

    # pairing button: a thin engraved ring on the back, 0.8 wide, 1.5 below the seam (photo 248)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.39, minor_radius=0.012, major_segments=48, minor_segments=8,
                                     location=(0, D / 2 - 0.004, SEAM - 1.5), rotation=(math.pi / 2, 0, 0))
    btn = bpy.context.active_object
    btn.name = "Case_Button"
    btn.data.materials.append(mats["dark"])
    bpy.ops.object.shade_smooth()

    # lanyard loop (photo 246): two steel eyes in the dark slot of the right end
    eyes = []
    for dz in (-0.27, 0.27):
        e = cyl("eye", 0.19, 0.1, (W / 2 - 0.12, 0.0, SEAM - 0.91 + dz), rot=(0, math.pi / 2, 0), verts=24)
        eyes.append(e)
    loop = eyes[0]
    bpy.ops.object.select_all(action="DESELECT")
    for e in eyes:
        e.select_set(True)
    bpy.context.view_layer.objects.active = loop
    bpy.ops.object.join()
    loop.name = "Case_Loop"
    loop.data.materials.append(mats["steel"])
    smooth(loop, 40)

    # move lid origin to the hinge axis
    bpy.context.scene.cursor.location = (0, HINGE_Y, SEAM)
    activate(lid)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    return hinge, led, loop


# ---- pods ------------------------------------------------------------------------------------
TIP_TILT = 105.0  # degrees from the stem axis (up) towards the tip direction: ~20 below horizontal (photo 241)


def build_pod(name, mats):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    sgn = 1 if name.endswith("_L") else -1    # tip direction (+x for the left pod, towards the case center)

    # head: egg of revolution around the vertical axis, origin at its center
    hprof = [(0.0, -0.9), (0.4, -0.86), (0.68, -0.62), (0.8, -0.3), (0.84, 0.1), (0.8, 0.5),
             (0.62, 0.86), (0.34, 1.06), (0.0, 1.12)]
    head = lathe(name + "_Head", hprof, steps=64)
    head.scale = (1.0, 0.92, 1.0)
    # stem: slightly flat in y, offset outwards so its outer edge runs on into the head silhouette; rounded
    # white cap at the bottom
    sprof = [(0.0, -2.65), (0.2, -2.63), (0.29, -2.54), (0.3, -2.4), (0.33, -1.7), (0.37, -1.0),
             (0.4, -0.6), (0.42, -0.1), (0.0, -0.1)]
    stem = lathe(name + "_Stem", sprof, steps=48)
    stem.scale = (1.0, 0.95, 1.0)
    stem.location = (-sgn * STEM_OFF, 0, 0)
    for o in (head, stem):
        activate(o)
        bpy.ops.object.transform_apply(location=True, scale=True)
    boolean(head, stem, "UNION")           # one closed surface ...
    activate(head)
    head.data.remesh_voxel_size = 0.012      # ... re-meshed evenly, then smoothed so the joint is a fillet
    bpy.ops.object.voxel_remesh()
    sm = head.modifiers.new("fillet", "SMOOTH")
    sm.factor = 0.5
    sm.iterations = 40
    apply_mod(head, sm)
    head.name = name + "_Body"
    # dark mic opening on the very bottom tip of the stem (photos 239-241)
    for p_ in head.data.polygons:
        p_.use_smooth = True
    head.data.materials.clear()  # the boolean leaves an empty slot 0 (default grey material): drop it
    head.data.materials.append(mats["white"])
    head.parent = root
    sx0 = -sgn * STEM_OFF
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12, location=(sx0, 0, -2.635))
    o = bpy.context.active_object
    o.name = name + "_Mic"
    o.scale = (0.2, 0.15, 0.045)
    o.data.materials.append(mats["dark"])
    bpy.ops.object.shade_smooth()
    o.parent = root

    # silicone tip: built along +z, the TipRig empty tilts it about y (render.py sets the angle per shot)
    rig = bpy.data.objects.new(name + "_TipRig", None)
    bpy.context.scene.collection.objects.link(rig)
    rig.parent = root
    rig.location = (sgn * 0.5, 0, -0.3)
    rig.rotation_euler = (0, sgn * math.radians(TIP_TILT), 0)
    tprof = [(0.0, 0.0), (0.5, 0.0), (0.58, 0.2), (0.57, 0.45), (0.53, 0.65), (0.48, 0.8), (0.43, 0.88),
             (0.37, 0.88), (0.34, 0.82), (0.0, 0.82)]
    tip = lathe(name + "_Tip", tprof, steps=56)
    tip.data.materials.append(mats["grey_tip"])
    tip.parent = rig
    mesh = cyl(name + "_Mesh", 0.33, 0.02, (0, 0, 0.83), verts=40)
    mesh.data.materials.append(mats["mesh"])
    mesh.parent = rig

    # black pill slots on the head (photos 239-243): a long one facing front-up, a second on the top
    from mathutils import Matrix

    def pill(nm, nvec, along, scl):
        n = Vector(nvec).normalized()
        org = n * 3.0
        ok, hit, _nn, _i = head.ray_cast(org, -n)
        pos = hit - n * 0.01 if ok else n * 0.85
        lng = Vector(along)
        lng = (lng - n * lng.dot(n)).normalized()
        side_v = lng.cross(n).normalized()
        rot = Matrix((side_v, lng, n)).transposed()
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12, location=pos)
        o = bpy.context.active_object
        o.name = name + nm
        o.rotation_euler = rot.to_euler()
        o.scale = scl
        o.data.materials.append(mats["dark"])
        bpy.ops.object.shade_smooth()
        o.parent = root
    pill("_Slot", (-sgn * 0.25, -0.68, 0.68), (sgn * 0.5, 0, -1.0), (0.1, 0.26, 0.07))
    pill("_Slot2", (-sgn * 0.45, 0.2, 0.87), (sgn * 0.3, 1.0, 0.0), (0.075, 0.2, 0.06))

    # force-sensor flat on the stem front (-y)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12, location=(sx0, -0.33, -1.4))
    o = bpy.context.active_object
    o.name = name + "_Sensor"
    o.scale = (0.05, 0.03, 0.4)
    o.data.materials.append(mats["white_rough"])
    bpy.ops.object.shade_smooth()
    o.parent = root
    root.scale = (POD_SCALE,) * 3
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
        pod.location = (sx * POD_X, 0.0, SEAM + POD_RISE)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
