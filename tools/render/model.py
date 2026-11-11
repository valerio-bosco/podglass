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
# case width (X), depth (Y), height (Z) and lid height: traced 1:1 from the reference reference shots
# (assets/reference/shots, 175 px/cm): base 2.97 high, lid 1.54, closed 4.51 (the real case: 45.2 mm)
W, D, H = 6.0, 2.2, 4.51
LID_H = 1.54
SEAM = H - LID_H
N_FRONT, N_PLAN = 4.2, 3.2          # superellipse exponents: front view (x/z) and plan (x/y); 2 = ellipse, inf = box
DOME = 0.03                         # the flat top and bottom faces bulge by this much
WALL = 0.1                          # lid wall thickness
POD_SCALE = 1.0                    # pod size vs the model below: head ~1.55 wide vs 6.0 case (photos 242/243)
POD_X = 1.6                        # pod centers at +-POD_X
POD_RISE = -0.07                    # pod root (stem axis, head centre level) above the seam: same height as fitted with
                                    # the old 2.70 seam (the seam is now 2.97)
POD_TILT = 20.0                     # the pods lean forward in the case (the reference pose does not fit: head+tip are 2.0 deep, the case 2.0 inside)
POD_YAW = 30.0                      # the tips turn towards the case centre (rotation about z, deg, mirrored for the right pod)
POD_Y = -0.15                       # centres the 1.55 deep tilted pod between the walls
POD_DEPTH = 0.93                    # pod depth / width (photos 239/240 vs 242)
CAVITY_R = 0.95
STEM_OFF = 0.12                     # the stem axis sits this far outwards of the head axis (reference pods)
LED_DROP = 0.78                     # status light below the seam (reference front shot: 0.08 wide)
# lid hinge axis (x direction): solved from the open lid of the reference end view (121 deg open): the back rim
# corner of the closed lid (y = 1.09, z = SEAM + gap) lands on the observed corner
HINGE_Y = 1.08
HINGE_Z = SEAM + 0.158
N_LID_RIM = float(sys.argv[sys.argv.index("--nrim") + 1]) if "--nrim" in sys.argv else N_PLAN   # plan exponent at the rim, blended to N_PLAN_LID over 0.6 cm
N_PLAN_LID = float(sys.argv[sys.argv.index("--nlid") + 1]) if "--nlid" in sys.argv else N_PLAN                    # the lid plan section is boxier than the base's (front-view widths)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[args.index("--out") + 1] if "--out" in args else "assets/models/airpods-pro2.blend"
if "--pod-pose" in args:      # experiments: x,y,rise,tilt,yaw of the in-case pods
    POD_X, POD_Y, POD_RISE, POD_TILT, POD_YAW = [float(v) for v in args[args.index("--pod-pose") + 1].split(",")]


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


def _profiles():
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "tools/render"
    return json.load(open(os.path.join(here, "profiles.json")))


def _profile():
    return _profiles()["sf_front"]


def _case_table():
    """tools/render/profiles_case.json: rows [z, half-width, y front, y back] of the closed case (base + lid),
    smoothed (pixel steps would show as bands in the reflections)."""
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "tools/render"
    rows = json.load(open(os.path.join(here, "profiles_case.json")))["case_shell"]
    cols = [[r[i] for r in rows] for i in range(4)]
    for k in (1, 2, 3):
        c = cols[k]
        for _ in range(3):
            c = [c[0]] + [(c[i - 1] + 2 * c[i] + c[i + 1]) / 4 for i in range(1, len(c) - 1)] + [c[-1]]
        cols[k] = c
    return cols


def traced_shell(name, dome=DOME, nlat=120, nlon=160):
    """Case body from the traced reference silhouettes (profiles_case.json). At height z the plan section is a
    superellipse with half-width hw(z) (front view), spanning y in [yf(z), yb(z)] (end view; the lid is lopsided:
    round at the front, slanted at the back), exponent N_PLAN (base) or N_PLAN_LID (lid)."""
    zs, hws, yfs, ybs = _case_table()

    def at(col, z):
        z = min(max(z, 0.0), H)
        for i in range(len(zs) - 1):
            if z <= zs[i + 1]:
                t = (z - zs[i]) / (zs[i + 1] - zs[i])
                return col[i] + t * (col[i + 1] - col[i])
        return col[-1]
    bm = bmesh.new()
    rings = []
    zl = [H / 2 * (1 - math.cos(math.pi * i / nlat)) for i in range(nlat + 1)]
    zl = sorted(set(zl + [SEAM - 0.01, SEAM + 0.01, SEAM + 0.03]))
    for z in zl:
        a_ = at(hws, z)
        yc, b_ = (at(yfs, z) + at(ybs, z)) / 2, max((at(ybs, z) - at(yfs, z)) / 2, 0.02)
        n_ = N_PLAN if z < SEAM + 0.02 else N_LID_RIM + (N_PLAN_LID - N_LID_RIM) * min((z - SEAM - 0.02) / 0.6, 1.0)
        e = 2.0 / n_
        ring = []
        for k in range(nlon):
            t = 2 * math.pi * k / nlon
            ring.append(bm.verts.new((a_ * math.copysign(abs(math.cos(t)) ** e, math.cos(t)),
                                      yc + b_ * math.copysign(abs(math.sin(t)) ** e, math.sin(t)), z)))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(nlon):
            bm.faces.new((r0[k], r0[(k + 1) % nlon], r1[(k + 1) % nlon], r1[k]))
    for ring, up in ((rings[0], False), (rings[-1], True)):
        pole = bm.verts.new((0, (at(yfs, H) + at(ybs, H)) / 2 if up else 0, H if up else -dome))
        for k in range(nlon):
            f = (ring[k], ring[(k + 1) % nlon], pole) if up else (ring[(k + 1) % nlon], ring[k], pole)
            bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = link(name, bm)
    smooth(ob, 60)
    return ob


def inner_shell(name, wall=WALL):
    """The case shell moved inwards along its normals by `wall`: clips cutters so they leave a wall."""
    ob = traced_shell(name)
    m = ob.modifiers.new("inset", "DISPLACE")
    m.direction = "NORMAL"
    m.mid_level = 0.0
    m.strength = -wall
    apply_mod(ob, m)
    return ob


def clean(obj, dist=4e-4):
    """Dissolve the sliver faces the exact booleans leave: with weighted normals they shade black."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


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
        "gold": material("Gold", (0.85, 0.62, 0.25), rough=0.3, metal=1.0),
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
    """Thumb recess (reference front/threequarter shots, 175 px/cm): a long shallow step cut into the top
    front edge of the base, open at the seam: 2.6 wide, 0.15 tall, 0.07 deep, flat bottom, rounded corners."""
    w, h, depth, r = 2.6, 0.15, 0.07, 0.07
    top = SEAM + 0.2
    return rbox("thumb", w, 0.3, top - (SEAM - h), r, segs=4, center=(0, -D / 2 + depth - 0.15, (top + SEAM - h) / 2))


# ---- case ------------------------------------------------------------------------------------
def build_case(mats, clear=()):
    """Base and lid as two separate objects with a small seam gap. `clear`: pod-shaped cutters (see
    pod_clearance) so the pods always fit, whatever their traced shape."""
    gap = 0.02

    def shell(name):
        return traced_shell(name)

    # ---- base
    base = shell("Case_Base")
    boolean(base, rbox("keep", W * 2, D * 2, SEAM - gap + 5, 0.0, segs=1, center=(0, 0, (SEAM - gap - 5) / 2)), "INTERSECT")
    # lanyard recess in the right end (reference right shot): white stadium 0.47 (y) x 0.95 (z), 0.05 deep,
    # with two round dimples (0.37 wide, 0.08 deep) in it; no steel eyes
    lz = SEAM - 0.84
    boolean(base, rbox("pocket", 0.2, 0.47, 0.47, 0.0, segs=1, center=(W / 2 + 0.05, 0.0, lz)))
    for dz in (-0.235, 0.235):
        boolean(base, cyl("pocket_r", 0.235, 0.2, (W / 2 + 0.05, 0.0, lz + dz), rot=(0, math.pi / 2, 0), verts=40))
    for dz in (-0.27, 0.27):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.26, segments=40, ring_count=20, location=(W / 2 + 0.13, 0.0, lz + dz))
        boolean(base, bpy.context.active_object)
    # Lightning slot (photo 247): centered, 1.0 x 0.3, rounded ends; speaker holes 1 left + 3 right of it (reference bottom shot)
    boolean(base, rbox("port", 1.0, 0.3, 1.0, 0.14, segs=6, center=(0.0, 0.0, 0.0)))
    for hx in (-1.40, 1.44, 1.67, 1.90):   # see-through in the reference bottom shot: up into the pod cavity
        boolean(base, cyl("hole", 0.063, 4.4, (hx, 0.0, 0.0), verts=16))
    boolean(base, cyl("ledcut", 0.045, 0.1, (0, -D / 2, SEAM - LED_DROP), rot=(math.pi / 2, 0, 0), verts=24))
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
    for c in clear:
        boolean(base, c, keep=True)
    clean(base)
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
        activate(c)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        # the traced top falls towards the ends: keep the bowl one wall inside the shell or it cuts through
        boolean(c, inner_shell("inner"), "INTERSECT")
        boolean(lid, c)
    lrec = superell("lrec", W / 2 - 0.2, D / 2 - 0.2, 0.5, center=(0, 0, SEAM + gap - 0.5 + 0.07), dome=0.0, nlat=8, nlon=96)
    boolean(lid, lrec)
    for c in clear:
        boolean(lid, c)
    clean(lid)
    bevel(lid, 0.1, 2, angle=35)
    smooth(lid, 35, weighted=True)

    # materials
    def base_pick(p):
        c, n = p.center, p.normal
        if c.z < 0.9 and abs(c.y) < 0.3 and c.z > 0.02 and (abs(c.x) < 0.6 or 1.2 < abs(c.x) < 2.2):
            return 2  # port and speaker holes
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
    # no hinge plate: the reference back shot shows a plain wall
    led = cyl("Case_LED", 0.045, 0.03, (0, -D / 2 + 0.01, SEAM - LED_DROP), rot=(math.pi / 2, 0, 0), verts=24)
    led.data.materials.append(mats["led"])

    # pairing button: a thin engraved ring on the back, 0.57 wide, 1.18 below the seam (reference back shot)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.285, minor_radius=0.012, major_segments=48, minor_segments=8,
                                     location=(0, D / 2 - 0.004, SEAM - 1.18), rotation=(math.pi / 2, 0, 0))
    btn = bpy.context.active_object
    btn.name = "Case_Button"
    btn.data.materials.append(mats["dark"])
    bpy.ops.object.shade_smooth()

    # Lightning contacts: a row of gold pins on the roof of the port (reference bottom shot)
    pins = []
    for i in range(12):
        pins.append(rbox("pin", 0.04, 0.1, 0.03, 0.0, segs=1, center=(-0.4 + i * 0.0727, 0.06, 0.45)))
    pin = pins[0]
    bpy.ops.object.select_all(action="DESELECT")
    for q in pins:
        q.select_set(True)
    bpy.context.view_layer.objects.active = pin
    bpy.ops.object.join()
    pin.name = "Case_Pins"
    pin.data.materials.append(mats["gold"])

    # move lid origin to the hinge axis
    bpy.context.scene.cursor.location = (0, HINGE_Y, HINGE_Z)
    activate(lid)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    return led, pin


# ---- pods ------------------------------------------------------------------------------------
# Everything below comes from the reference pod silhouettes (tools/render/pod_shape.py, profiles_pod.json): head+stem
# sections and the silicone tip are fitted in the reference pose (pod roots unrotated, see REF_ROOT) to
# pod-front/back/outer (IoU 0.96-0.99); the details are placed from the reference PNGs.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_shape  # noqa: E402

PODS = pod_shape.load()
REF_ROOT = PODS["root"]                # root of the left pod in the reference (cm, case frame)
_pm = PODS["tip"]["pm"]
# silicone tip profile (radius, z along the tip axis): bulb widest at the head, large opening; the last
# three points are the recess around the mesh
TIP_PROF = [(r * PODS["tip"]["sr"] * (_pm[i - 1] if 1 <= i <= 6 else 1.0), z * PODS["tip"]["sl"])
            for i, (r, z) in enumerate(PODS["tip_prof"])]


def build_pod(name, mats):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    sgn = 1 if name.endswith("_L") else -1    # x towards the case centre for the left pod; mirrored for the right

    # head + stem: one lofted surface of elliptical sections (profiles_pod.json: [z, cx, cy, hx, hy]), no seams
    rows = pod_shape.smooth_rows(PODS["rows"], 14)
    rings, top, bot = pod_shape.body_rings(rows, sgn, 64)
    bm = bmesh.new()
    vr = [[bm.verts.new(p_) for p_ in ring] for ring in rings]
    nlon = len(vr[0])
    for r0, r1 in zip(vr, vr[1:]):
        for k in range(nlon):
            bm.faces.new((r0[k], r0[(k + 1) % nlon], r1[(k + 1) % nlon], r1[k]))
    for ring, pt, up in ((vr[0], top, True), (vr[-1], bot, False)):
        pole = bm.verts.new(pt)
        for k in range(nlon):
            bm.faces.new((ring[(k + 1) % nlon], ring[k], pole) if up else (ring[k], ring[(k + 1) % nlon], pole))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    head = link(name + "_Body", bm)
    for p_ in head.data.polygons:
        p_.use_smooth = True
    head.data.materials.clear()
    head.data.materials.append(mats["white"])
    head.parent = root
    zbot = rows[-1][0]
    sx0 = sgn * rows[-1][1]
    # dark mic opening on the very bottom of the stem
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12,
                                         location=(sx0, rows[-1][2], zbot + 0.02))
    o = bpy.context.active_object
    o.name = name + "_Mic"
    o.scale = (rows[-1][3] * 0.8, rows[-1][4] * 0.8, 0.05)
    o.data.materials.append(mats["dark"])
    bpy.ops.object.shade_smooth()
    o.parent = root

    # silicone tip: built along +z, the TipRig empty aims it (position and direction fitted to the reference)
    rig = bpy.data.objects.new(name + "_TipRig", None)
    bpy.context.scene.collection.objects.link(rig)
    rig.parent = root
    pos, dvec = pod_shape.tip_matrix_args(PODS["tip"], sgn)
    rig.location = pos
    rig.rotation_euler = Vector((0, 0, 1)).rotation_difference(Vector(dvec)).to_euler()
    tip = lathe(name + "_Tip", TIP_PROF, steps=56)
    tip.data.materials.append(mats["grey_tip"])
    tip.parent = rig
    mesh = cyl(name + "_Mesh", 0.3, 0.02, (0, 0, 0.36), verts=40)
    mesh.data.materials.append(mats["mesh"])
    mesh.parent = rig

    from mathutils import Matrix

    def hit_along(org, dirv):
        ok, h, nn, _i = head.ray_cast(Vector(org), Vector(dirv).normalized())
        return (h, nn.normalized()) if ok else (None, None)

    def pill(nm, org, dirv, along, scl, mat="dark"):
        """Flat ellipsoid sitting on the body where the ray from `org` along `dirv` hits it; long axis `along`."""
        h, n = hit_along(org, dirv)
        if h is None:
            return
        pos = h - n * scl[2] * 0.5          # half sunk: flush
        lng = Vector(along)
        lng = (lng - n * lng.dot(n)).normalized()
        side_v = lng.cross(n).normalized()
        rot = Matrix((side_v, lng, n)).transposed()
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12, location=pos)
        o = bpy.context.active_object
        o.name = name + nm
        o.rotation_euler = rot.to_euler()
        o.scale = scl
        o.data.materials.append(mats[mat])
        bpy.ops.object.shade_smooth()
        o.parent = root
    # oval grille on the front of the head, 0.5 x 0.24 (pod-front, pod-innerfront), long axis tilted ~33 deg
    pill("_Slot", (sgn * 0.02, -3.0, 0.49), (0, 1, 0), (sgn * 1.0, 0, -0.65), (0.12, 0.25, 0.025))
    # long vertical mesh slot on the back of the head, over the stem (pod-back), 0.34 x 0.8: a squircle patch
    # projected onto the body along -y and lifted 0.006 (so it follows the curved head/stem junction exactly)
    bmp = bmesh.new()
    nr, ns, hx, hz, xc, zc = 8, 40, 0.17, 0.4, sgn * -0.06, -0.02
    cen = bmp.verts.new((0, 0, 0))
    grid = []
    for i in range(1, nr + 1):
        ring = []
        for k in range(ns):
            t = 2 * math.pi * k / ns
            c_, s_ = math.cos(t), math.sin(t)
            u = math.copysign(abs(c_) ** 0.5, c_) * hx * i / nr      # exponent 0.5 on the unit circle -> squircle-ish pill
            w = math.copysign(abs(s_) ** 0.5, s_) * hz * i / nr
            okk, loc, nrm, _ix = head.ray_cast(Vector((xc + u, 3.0, zc + w)), Vector((0, -1, 0)))
            ring.append(bmp.verts.new(loc + nrm * 0.006 if okk else (0, 0, 0)))
        grid.append(ring)
    for k in range(ns):
        bmp.faces.new((cen, grid[0][k], grid[0][(k + 1) % ns]))
    for r0, r1 in zip(grid, grid[1:]):
        for k in range(ns):
            bmp.faces.new((r0[k], r1[k], r1[(k + 1) % ns], r0[(k + 1) % ns]))
    cen.co = (sum(v.co.x for v in grid[0]) / ns, sum(v.co.y for v in grid[0]) / ns, sum(v.co.z for v in grid[0]) / ns)
    bmesh.ops.recalc_face_normals(bmp, faces=bmp.faces)
    slot2 = link(name + "_Slot2", bmp)
    for p_ in slot2.data.polygons:
        p_.use_smooth = True
    slot2.data.materials.append(mats["mesh"])
    slot2.parent = root

    # force-sensor flat on the stem front (-y)
    ok, hit, _n, _i = head.ray_cast(Vector((sx0, -3.0, -1.2)), Vector((0, 1, 0)))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12,
                                         location=(hit + Vector((0, 0.02, 0))) if ok else (sx0, -0.3, -1.2))
    o = bpy.context.active_object
    o.name = name + "_Sensor"
    o.scale = (0.05, 0.03, 0.4)
    o.data.materials.append(mats["white_rough"])
    bpy.ops.object.shade_smooth()
    o.parent = root
    root.scale = (POD_SCALE,) * 3
    return root


def pod_clearance(gap=0.03):
    """World-space copies of the pod bodies and tips, grown by `gap` along the normals."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o.name.startswith("Pod_") and o.name.endswith(("_Body", "_Tip", "_Mic")):
            if o.name.endswith("_Tip"):
                # from the profile: displacing the real tip folds its recess rim inwards and the cut fails
                prof = [(0.0, -gap)] + [(r + gap, z) for r, z in TIP_PROF[1:7]] + [(0.0, TIP_PROF[6][1] + gap)]
                c = lathe(o.name + "_Clear", prof, steps=56)
                c.data.transform(o.matrix_world)
                out.append(c)
                continue
            me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
            me.transform(o.matrix_world)
            me.materials.clear()
            c = bpy.data.objects.new(o.name + "_Clear", me)
            bpy.context.scene.collection.objects.link(c)
            m = c.modifiers.new("grow", "DISPLACE")
            m.direction = "NORMAL"
            m.mid_level = 0.0
            m.strength = gap
            apply_mod(c, m)
            out.append(c)
    return out


def main():
    reset()
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 0.01
    mats = make_materials()
    for sx, nm in ((-1, "Pod_L"), (1, "Pod_R")):
        pod = build_pod(nm, mats)
        pod.location = (sx * (POD_X + STEM_OFF), POD_Y, SEAM + POD_RISE)   # the root is the stem axis
        pod.rotation_euler = (-math.radians(POD_TILT), 0, -sx * math.radians(POD_YAW))
    base, lid = build_case(mats, pod_clearance())
    led, pins = build_hardware(mats, lid)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
