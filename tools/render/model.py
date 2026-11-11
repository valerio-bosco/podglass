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
PK_N = 3.6                         # pocket outline superellipse exponent (higher: straighter sides, a parallel bridge)
PK_X, PK_Y, PK_A, PK_B = 1.41, 0.0, 1.21, 0.93   # interior pocket: centre x/y, half axes (reference int-front: x 0.17..2.6)
STEM_OFF = 0.12                     # the stem axis sits this far outwards of the head axis (reference pods)
LED_DROP = 0.78                     # status light below the seam (reference front shot: 0.08 wide)
# lid hinge axis (x direction): solved from the open lid of the reference end view (121 deg open): the back rim
# corner of the closed lid (y = 1.09, z = SEAM + gap) lands on the observed corner
HINGE_Y = 1.08
HINGE_Z = SEAM + 0.158
# hinge hardware (photo of the back + reference hinge-inner): a steel plate flush in the back wall over the seam, a
# dark bar on the rim behind the pods; the plate halves sit in matching skin slots of base and lid
HINGE_HW = 1.47                     # plate half width
HINGE_PLATE_BELOW = 0.2            # plate extent below / above the seam
HINGE_PLATE_ABOVE = 0.45
HINGE_SKIN = 0.06                   # plate thickness (it follows the shell)
HINGE_MID = 0.82                    # half width of the lid plate's centre piece that reaches below the seam
HINGE_CLEAR = 0.02                  # clearance of the swept slots
HINGE_R = 0.09                      # plate corner radius
HINGE_BAR_TOP2 = 0.08               # the bar is higher at the back
HINGE_BAR_Y = (0.66, 0.84)          # dark bar on the base rim: y range, half widths at front / back, top above the seam
HINGE_BAR_HW = (1.5, 1.7)
HINGE_BAR_TOP = 0.22
HINGE_PARTS = {}
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


def _bez(ctrl, t):
    """Bernstein evaluation of a Bezier curve with len(ctrl) control values."""
    n = len(ctrl) - 1
    return sum(math.comb(n, k) * t ** k * (1 - t) ** (n - k) * c for k, c in enumerate(ctrl))


def _shell_curves():
    """tools/render/profiles_case.json "shell_bezier": quintic Beziers z(t), hw(t), yh(t) from the equator (t=0) to the
    cap rim (t=1). The three share t, and both ends have zero curvature (end controls repeated), so the case is
    G2 from the equator into the cap: no kink, no curvature jump."""
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "tools/render"
    c = json.load(open(os.path.join(here, "profiles_case.json")))["shell_bezier"]
    return c["z"], c["hw"], c["yh"]


def traced_shell(name, dome=DOME, nlat=48, nlon=192):
    """Case body (closed, base + lid, mirror symmetric about z = H/2). The plan section at parameter t is a
    superellipse (exponent N_PLAN) with half sizes hw(t), yh(t), at height z(t): all three are quintic Beziers fitted
    to the traced reference silhouettes. Rings are spaced by arc length; the flat top and bottom are closed by
    concentric scaled rings (a fourth-order dome, so the curvature stays continuous) and a centre vertex."""
    cz, ch, cy = _shell_curves()
    dense = [i / 2000 for i in range(2001)]
    pts = [(_bez(cz, t), _bez(ch, t), _bez(cy, t)) for t in dense]
    acc = [0.0]
    for p, q in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.hypot(q[1] - p[1], q[0] - p[0]) + math.hypot(q[2] - p[2], q[0] - p[0]))
    ts = []
    j = 0
    for i in range(nlat + 1):
        target = acc[-1] * i / nlat
        while j < 2000 and acc[j + 1] < target:
            j += 1
        j = min(j, 1999)
        f = (target - acc[j]) / max(acc[j + 1] - acc[j], 1e-12)
        ts.append(dense[j] + f / 2000)
    half = [(_bez(cz, t), _bez(ch, t), _bez(cy, t)) for t in ts]          # equator -> rim, z falling
    e = 2.0 / N_PLAN
    bm = bmesh.new()

    def ring(z, a_, b_):
        out = []
        for k in range(nlon):
            th = 2 * math.pi * k / nlon
            out.append(bm.verts.new((a_ * math.copysign(abs(math.cos(th)) ** e, math.cos(th)),
                                     b_ * math.copysign(abs(math.sin(th)) ** e, math.sin(th)), z)))
        return out
    ncap = 12
    a_r, b_r = half[-1][1], half[-1][2]
    bottom = []
    for i in range(ncap):                                              # cap rings, centre outwards
        s = (i + 1) / (ncap + 1)
        s = math.sin(s * math.pi / 2)                                   # denser near the rim
        bottom.append((-dome * (1 - s * s) ** 2, a_r * s, b_r * s))
    seq = bottom + list(half[::-1])          # rim ... equator (z rising from 0)
    rings = [ring(z, a, b) for z, a, b in seq]
    # lid half: mirror of the above without the equator
    up = [(H - z, a, b) for z, a, b in seq[::-1][1:]]
    rings += [ring(z, a, b) for z, a, b in up]
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(nlon):
            bm.faces.new((r0[k], r0[(k + 1) % nlon], r1[(k + 1) % nlon], r1[k]))
    for rg, top in ((rings[0], False), (rings[-1], True)):
        pole = bm.verts.new((0, 0, H + dome if top else -dome))
        for k in range(nlon):
            f = (rg[k], rg[(k + 1) % nlon], pole) if top else (rg[(k + 1) % nlon], rg[k], pole)
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
        "grey_tip": material("Silicone tip", (0.82, 0.77, 0.6), rough=0.55, sss=(0.35, (0.8, 0.82, 0.85))),
        "mesh": material("Mesh", (0.03, 0.03, 0.034), rough=0.6, bump=(420.0, 0.9)),
        "gold": material("Gold", (0.85, 0.62, 0.25), rough=0.3, metal=1.0),
        "steel": material("Steel", (0.82, 0.82, 0.83), rough=0.28, metal=1.0),
        "hinge_dark": material("Hinge bar", (0.2, 0.19, 0.2), rough=0.4, metal=0.6),
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


def bathtub(name, cx, cy, a, b, z_top, z_bot, rb, n=2.8, up=False, nr=14, ns=96, rh=None, zf=None, rf=0.12, nf=8):
    """Pocket cutter: a superellipse prism (half axes a, b, exponent n) with a rounded bottom corner of radius rb
    (the reference pockets are rounded rectangles hugging the pods). up=True mirrors it (lid bowls: bottom = top)."""
    bm = bmesh.new()
    # (inset, z) from the wall down round the corner: inset 0 -> rb
    # zf: height of the surface the pocket is cut into; the rim is flared into it with a fillet of radius rf (a smooth edge)
    if zf is None:
        top = [(0.0, z_top + 0.3)]
    else:
        top = [(-rf, z_top + 0.3), (-rf, zf)] + [(-rf * (1 - math.cos(t)), zf - rf + rf * math.sin(t))
                                                  for t in [math.pi / 2 - i / nf * math.pi / 2 for i in range(1, nf + 1)]]
    prof = top + [(0.0, z_bot + rb)] + [((rb if rh is None else rh) * (1 - math.cos(t)), z_bot + rb - rb * math.sin(t))
                                                      for t in [i / nr * math.pi / 2 for i in range(1, nr + 1)]]
    rings = []
    for inset, z in prof:
        ring = []
        for k in range(ns):
            th = 2 * math.pi * k / ns
            c, sn = math.cos(th), math.sin(th)
            x = (a - inset) * math.copysign(abs(c) ** (2 / n), c)
            y = (b - inset) * math.copysign(abs(sn) ** (2 / n), sn)
            ring.append(bm.verts.new((cx + x, cy + y, z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(ns):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % ns], rings[i + 1][(k + 1) % ns], rings[i + 1][k]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    if up:
        for v in bm.verts:
            v.co.z = 2 * (SEAM) - v.co.z
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm)


def _rot_about_axis(ob, ang):
    from mathutils import Matrix
    m = Matrix.Translation((0, HINGE_Y, HINGE_Z)) @ Matrix.Rotation(ang, 4, "X") @ Matrix.Translation((0, -HINGE_Y, -HINGE_Z))
    ob.data.transform(m)


def _sweep_cut(target, src, sign, step=6.0, top=125.0):
    """Cut from `target` the volume `src` sweeps about the hinge axis through the whole opening (one boolean per
    step: robust, where a self-overlapping union cutter is not). sign -1: lid part cut from the base, +1: base
    part cut from the lid (in the lid frame)."""
    fat = src.copy()                      # a hair of clearance, or the closed pose touches face to face
    fat.data = src.data.copy()
    bpy.context.collection.objects.link(fat)
    m = fat.modifiers.new("fat", "DISPLACE")
    m.direction, m.mid_level, m.strength = "NORMAL", 0.0, HINGE_CLEAR
    apply_mod(fat, m)
    for i in range(int(top / step) + 1):
        c = fat.copy()
        c.data = fat.data.copy()
        bpy.context.collection.objects.link(c)
        _rot_about_axis(c, sign * math.radians(i * step))
        boolean(target, c)
    bpy.data.objects.remove(fat, do_unlink=True)


def _back_y(x, z):
    """y of the shell's back surface at (x, z), from the same Bezier curves as traced_shell (lid half mirrored)."""
    cz, ch, cy = _shell_curves()
    zz = z if z <= H / 2 else H - z
    ts = [i / 400 for i in range(401)]
    rows = [(_bez(cz, t), _bez(ch, t), _bez(cy, t)) for t in ts]        # z falls from the equator to the cap rim
    a_, b_ = rows[-1][1], rows[-1][2]
    for (z0, h0, y0), (z1, h1, y1) in zip(rows, rows[1:]):
        if z1 <= zz <= z0:
            f = (zz - z0) / (z1 - z0) if z1 != z0 else 0.0
            a_, b_ = h0 + f * (h1 - h0), y0 + f * (y1 - y0)
            break
    else:
        if zz > rows[0][0]:
            a_, b_ = rows[0][1], rows[0][2]
    n_ = N_PLAN
    return max(b_, 0.02) * (1 - min(abs(x) / a_, 1.0) ** n_) ** (1.0 / n_)


def _sheet(name, x0, x1, z0, z1, d_in, d_out, round_corners=(), r=HINGE_R, dx=0.05, dz=0.025):
    """Plate-shaped solid that follows the back wall: from d_in below to d_out above the shell surface, over the
    rectangle [x0, x1] x [z0, z1] (rounded at the listed corners: (+-1, +-1) = (x side, z side))."""
    nx, nz = max(int((x1 - x0) / dx), 2), max(int((z1 - z0) / dz), 2)
    pts = []
    for j in range(nz + 1):
        for i in range(nx + 1):
            x, z = x0 + (x1 - x0) * i / nx, z0 + (z1 - z0) * j / nz
            for sx, sz in round_corners:
                cx, cz = (x1 - r) if sx > 0 else (x0 + r), (z1 - r) if sz > 0 else (z0 + r)
                if (x - cx) * sx > 0 and (z - cz) * sz > 0:
                    d = math.hypot(x - cx, z - cz)
                    if d > r:
                        x, z = cx + (x - cx) * r / d, cz + (z - cz) * r / d
            pts.append((x, z))
    bm = bmesh.new()
    top = [bm.verts.new((x, _back_y(x, z) + d_out, z)) for x, z in pts]
    bot = [bm.verts.new((x, _back_y(x, z) - d_in, z)) for x, z in pts]
    ix = lambda i, j: j * (nx + 1) + i
    for j in range(nz):
        for i in range(nx):
            q = (ix(i, j), ix(i + 1, j), ix(i + 1, j + 1), ix(i, j + 1))
            bm.faces.new([top[k] for k in q][::-1])
            bm.faces.new([bot[k] for k in q])
    ring = [ix(i, 0) for i in range(nx)] + [ix(nx, j) for j in range(nz)] + [ix(i, nz) for i in range(nx, 0, -1)] + [ix(0, j) for j in range(nz, 0, -1)]
    for k in range(len(ring)):
        a_, b_ = ring[k], ring[(k + 1) % len(ring)]
        bm.faces.new((bot[a_], bot[b_], top[b_], top[a_]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm)


def hinge_cuts(base, lid, gap):
    """Steel plate flush in the back wall across the seam (photo 248): the lid half reaches below the seam in the
    middle, the base half only at the ends; plus a dark block on the base rim. Slots are cut into base and lid, the
    moving part's sweep is cut out of the other half. Solids go to HINGE_PARTS for build_hardware."""
    hw, mid, e, m = HINGE_HW, HINGE_MID, 0.01, 0.012
    zb0, zt, zs_ = SEAM - HINGE_PLATE_BELOW, SEAM + HINGE_PLATE_ABOVE, SEAM + gap + e
    sk = HINGE_SKIN
    top_r = ((1, 1), (-1, 1))
    upper = lambda din, dout, mg: _sheet("u", -hw - mg, hw + mg, zs_ - mg, zt + mg, din, dout, top_r, HINGE_R + mg)
    centre = lambda din, dout, mg: _sheet("c", -mid - mg, mid + mg, zb0 - mg, zs_ + 0.002, din, dout, ((1, -1), (-1, -1)) if mg == 0 else (), HINGE_R)
    bend = lambda sgn, din, dout, mg: _sheet("b", min(sgn * (mid + 0.03) - mg, sgn * hw - mg) if sgn > 0 else -hw - mg,
                                             (hw + mg) if sgn > 0 else -(mid + 0.03) + mg, zb0 - mg, SEAM - gap - e + mg, din, dout,
                                             ((1, -1),) if sgn > 0 else ((-1, -1),), HINGE_R)
    plate_l = upper(sk - 0.004, 0.0, 0.0)
    ctr_plate = centre(sk - 0.004, 0.0, 0.0)
    plate_b = bend(1, sk - 0.004, 0.0, 0.0)
    pb2 = bend(-1, sk - 0.004, 0.0, 0.0)
    def join(dst, src):
        bpy.ops.object.select_all(action="DESELECT")
        src.select_set(True)
        dst.select_set(True)
        bpy.context.view_layer.objects.active = dst
        bpy.ops.object.join()
        return dst
    join(plate_l, ctr_plate)
    join(plate_b, pb2)
    boolean(lid, upper(sk, 0.3, m))
    boolean(base, bend(1, sk, 0.3, m))
    boolean(base, bend(-1, sk, 0.3, m))
    ctr = centre(sk, 0.0, 0)
    _sweep_cut(base, ctr, -1)     # the lid plate's centre piece over the opening, in the base frame
    bpy.data.objects.remove(ctr, do_unlink=True)
    # dark block on the base rim (hinge-inner): trapezoid in plan, sunk into the rim, raised HINGE_BAR_TOP
    y0, y1 = HINGE_BAR_Y
    zb, zt2 = SEAM - 0.3, SEAM + HINGE_BAR_TOP
    bm = bmesh.new()
    pts = [(-HINGE_BAR_HW[0], y0), (HINGE_BAR_HW[0], y0), (HINGE_BAR_HW[1], y1), (-HINGE_BAR_HW[1], y1)]
    lo = [bm.verts.new((x, y, zb)) for x, y in pts]
    hi = [bm.verts.new((x, y, zt2 + (HINGE_BAR_TOP2 if i >= 2 else 0.0))) for i, (x, y) in enumerate(pts)]
    bm.faces.new(lo[::-1])
    bm.faces.new(hi)
    for i in range(4):
        bm.faces.new((lo[i], lo[(i + 1) % 4], hi[(i + 1) % 4], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bar = link("Case_HingeBar", bm)
    boolean(bar, rbox("notch", 2 * (HINGE_MID + 0.03), 1.0, 1.0, 0.0, segs=1, center=(0, 1.0, SEAM - 0.2 + 0.5)))  # the plate's centre piece swings through here
    cut = bar.copy()
    cut.data = bar.data.copy()
    bpy.context.collection.objects.link(cut)
    boolean(base, cut)
    _sweep_cut(lid, bar, +1, top=102.0)   # the lid frame sees the bar swing down and away: only the start overlaps lid material
    plate_b = bpy.data.objects[plate_b.name]
    plate_b.name, plate_l.name = "Case_Hinge", "Case_HingeLid"
    HINGE_PARTS.update(base=plate_b, lid=plate_l, bar=bar)
    for ob in (plate_b, plate_l):
        clean(ob)
        bevel(ob, 0.015, 2, angle=35)
    clean(base)


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
    for sx in (-1, 1):  # two pockets hugging the pods (reference: rounded rectangles, a bridge between them)
        boolean(base, bathtub("pocket_b", sx * PK_X, PK_Y, PK_A, PK_B, SEAM + 0.3, SEAM - 1.6, 1.3, n=PK_N, rh=0.8, zf=SEAM - 0.09))
    for c in clear:
        boolean(base, c, keep=True)
    clean(base)
    bevel(base, 0.1, 2, angle=35)
    smooth(base, 35, weighted=True)

    # ---- lid (origin later moved to the hinge axis): solid with two bowls for the pod heads
    lid = shell("Case_Lid")
    boolean(lid, rbox("keep", W * 2, D * 2, LID_H * 2, 0.0, segs=1, center=(0, 0, H - LID_H + gap + LID_H)), "INTERSECT")
    for sx in (-1, 1):
        c = bathtub("bowl", sx * PK_X, PK_Y, PK_A, PK_B, SEAM + 0.3, SEAM - 1.05, 1.35, n=PK_N, up=True, rh=0.8, zf=SEAM - 0.09)
        # the traced top falls towards the ends: keep the bowl one wall inside the shell or it cuts through
        boolean(c, inner_shell("inner"), "INTERSECT")
        boolean(lid, c)
    lrec = superell("lrec", W / 2 - 0.2, D / 2 - 0.2, 0.5, center=(0, 0, SEAM + gap - 0.5 + 0.07), dome=0.0, nlat=8, nlon=96)
    boolean(lid, lrec)
    for c in clear:
        boolean(lid, c)
    hinge_cuts(base, lid, gap)
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
    hp = HINGE_PARTS
    for o, m in ((hp["base"], "steel"), (hp["lid"], "steel"), (hp["bar"], "hinge_dark")):
        o.data.materials.clear()          # the boolean results carry an empty slot
        o.data.materials.append(mats[m])
    for o in hp.values():
        smooth(o, 35)
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
    pl = hp["lid"]
    pl.parent = lid
    pl.matrix_parent_inverse = lid.matrix_world.inverted()
    return led, pin


# ---- pods ------------------------------------------------------------------------------------
# Everything below comes from the reference pod silhouettes (tools/render/pod_shape.py, profiles_pod.json): head+stem
# sections and the silicone tip are fitted in the reference pose (pod roots unrotated, see REF_ROOT) to
# pod-front/back/outer (IoU 0.96-0.99); the details are placed from the reference PNGs.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_shape  # noqa: E402

PODS = pod_shape.load()
REF_ROOT = PODS["root"]                # root of the left pod in the reference (cm, case frame)
# silicone tip profile (radius, z along the tip axis), traced from the reference (tools/render/profiles_pod.json): bulb widest
# near the head, the last three points are the opening and the recess around the mesh
TIP_PROF = [tuple(p) for p in PODS["tip_prof"]]
TIP_CTRL = PODS["tip_ctrl"]            # smooth B-spline meridian of the tip (pod_shape.tip_mesh), fitted to TIP_PROF


def build_pod(name, mats):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    sgn = 1 if name.endswith("_L") else -1    # x towards the case centre for the left pod; mirrored for the right

    # head + stem: one smooth implicit surface (pod_shape.sdf: egg head smooth-unioned with the rounded stem), meshed in rings
    B = PODS["body"]
    verts, quads, tris = pod_shape.body_mesh(B, sgn, 200, 128)
    bm = bmesh.new()
    vv = [bm.verts.new(tuple(p_)) for p_ in verts]
    for f_ in quads + tris:
        bm.faces.new([vv[i] for i in f_])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    head = link(name + "_Body", bm)
    for p_ in head.data.polygons:
        p_.use_smooth = True
    head.data.materials.clear()
    head.data.materials.append(mats["white"])
    head.parent = root
    # dark mic opening on the flat bottom of the stem
    zb = B["sz"][1]
    axx = lambda z_: (B["sa"][0] + B["ss"][0] * (z_ - B["sa"][2]), B["sa"][1] + B["ss"][1] * (z_ - B["sa"][2]))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12, location=(sgn * axx(zb)[0], axx(zb)[1], zb + 0.01))
    o = bpy.context.active_object
    o.name = name + "_Mic"
    o.scale = (B["sr"][0] * 0.45, B["sr"][1] * 0.45, 0.03)
    o.data.materials.append(mats["dark"])
    bpy.ops.object.shade_smooth()
    o.parent = root
    sx0 = sgn * axx(-1.2)[0]

    # silicone tip: built along +z, the TipRig empty aims it (position and direction fitted to the reference)
    rig = bpy.data.objects.new(name + "_TipRig", None)
    bpy.context.scene.collection.objects.link(rig)
    rig.parent = root
    pos, dvec = pod_shape.tip_matrix_args(PODS["tip"], sgn)
    rig.location = pos
    rig.rotation_euler = Vector((0, 0, 1)).rotation_difference(Vector(dvec)).to_euler()
    # the tip is slightly oval: scaled by ecc along an axis rolled by -roll about its own axis (mirrored for the right pod)
    oval = (0, 0, -sgn * PODS["tip"].get("roll", 0.0)), (1, PODS["tip"].get("ecc", 1.0), 1)
    tv, tf = pod_shape.tip_mesh(TIP_CTRL)
    bmt = bmesh.new()
    tvv = [bmt.verts.new(tuple(p_)) for p_ in tv]
    for f_ in tf:
        bmt.faces.new([tvv[i] for i in f_])
    bmesh.ops.recalc_face_normals(bmt, faces=bmt.faces)
    tip = link(name + "_Tip", bmt)
    for p_ in tip.data.polygons:
        p_.use_smooth = True
    tip.data.materials.append(mats["grey_tip"])
    tip.parent = rig
    tip.rotation_euler, tip.scale = oval
    mesh = cyl(name + "_Mesh", 0.245, 0.02, (0, 0, TIP_PROF[-1][1] + 0.01), verts=40)
    mesh.data.materials.append(mats["mesh"])
    mesh.parent = rig
    mesh.rotation_euler, mesh.scale = oval

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
    def stadium(f, hu, hv):
        """Point at the fraction f of the perimeter of a stadium (capsule) of half sizes hu >= hv."""
        a, r = hu - hv, hv
        per = 4 * a + 2 * math.pi * r
        d = f * per
        if d < 2 * a:                       # straight side, v = +r
            return a - d, r
        d -= 2 * a
        if d < math.pi * r:                 # cap at -u
            t = math.pi / 2 + d / r
            return -a + r * math.cos(t), r * math.sin(t)
        d -= math.pi * r
        if d < 2 * a:
            return -a + d, -r
        d -= 2 * a
        t = -math.pi / 2 + d / r
        return a + r * math.cos(t), r * math.sin(t)

    def patch(nm, centre, ax_u, ax_v, hu, hv, ray_y, mat, lift=0.006, nr=8, ns=64):
        """Stadium patch (half sizes hu, hv along the unit x-z vectors ax_u, ax_v) centred at the x-z `centre`, projected onto the
        body along the y direction pointing from `ray_y` (start plane) at the surface and lifted by `lift`."""
        bmp = bmesh.new()
        cen = bmp.verts.new((0, 0, 0))
        grid = []
        for i in range(1, nr + 1):
            ring = []
            for k in range(ns):
                u, w = stadium(k / ns, hu, hv)
                u, w = u * i / nr, w * i / nr
                x_ = centre[0] + u * ax_u[0] + w * ax_v[0]
                z_ = centre[1] + u * ax_u[1] + w * ax_v[1]
                okk, loc, nrm, _ix = head.ray_cast(Vector((x_, ray_y, z_)), Vector((0, -math.copysign(1, ray_y), 0)))
                ring.append(bmp.verts.new(loc + nrm * lift if okk else (0, 0, 0)))
            grid.append(ring)
        for k in range(ns):
            bmp.faces.new((cen, grid[0][k], grid[0][(k + 1) % ns]))
        for r0, r1 in zip(grid, grid[1:]):
            for k in range(ns):
                bmp.faces.new((r0[k], r1[k], r1[(k + 1) % ns], r0[(k + 1) % ns]))
        cen.co = (sum(v.co.x for v in grid[0]) / ns, sum(v.co.y for v in grid[0]) / ns, sum(v.co.z for v in grid[0]) / ns)
        bmesh.ops.recalc_face_normals(bmp, faces=bmp.faces)
        ob = link(name + nm, bmp)
        for p_ in ob.data.polygons:
            p_.use_smooth = True
        ob.data.materials.append(mats[mat])
        ob.parent = root
    GR = PODS["details"]
    # dark capsule grille on the front of the head (pod-front, pod-innerfront, pod-3q: 0.5 x 0.28, long axis 33 deg below the x axis)
    ga = math.radians(GR["grille"]["angle"])
    patch("_Slot", (sgn * GR["grille"]["xz"][0], GR["grille"]["xz"][1]), (sgn * math.cos(ga), -math.sin(ga)), (sgn * math.sin(ga), math.cos(ga)),
          GR["grille"]["half"][0], GR["grille"]["half"][1], -3.0, "dark", lift=0.004)
    # long vertical mesh slot on the back of the head, over the stem (pod-back), 0.34 x 0.8
    sl = GR["slot"]
    tl = math.radians(sl.get("tilt", 0.0))
    patch("_Slot2", (sgn * sl["xz"][0], sl["xz"][1]), (sgn * math.sin(tl), math.cos(tl)), (sgn * math.cos(tl), -math.sin(tl)),
          sl["half"][1], sl["half"][0], 3.0, "mesh")

    # force-sensor flat on the stem front (-y)
    ok, hit, _n, _i = head.ray_cast(Vector((sx0, -3.0, -1.2)), Vector((0, 1, 0)))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12,
                                         location=(hit + Vector((0, 0.005, 0))) if ok else (sx0, -0.3, -1.2))
    o = bpy.context.active_object
    o.name = name + "_Sensor"
    o.scale = (0.05, 0.02, 0.4)
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
                # analytic: the tip meridian offset by `gap` with the bore plugged (displacing the real tip folds the rim)
                tv, tf = pod_shape.revolve(pod_shape.tip_cutter_profile(TIP_CTRL, 0.4 * gap), 96)
                bmc = bmesh.new()
                tvv = [bmc.verts.new(tuple(p_)) for p_ in tv]
                for f_ in tf:
                    bmc.faces.new([tvv[i] for i in f_])
                bmesh.ops.recalc_face_normals(bmc, faces=bmc.faces)
                c = link(o.name + "_Clear", bmc)
                for p_ in c.data.polygons:
                    p_.use_smooth = True
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
