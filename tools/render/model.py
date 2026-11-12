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
import subprocess
import sys
import tempfile

import numpy as np

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
POD_Y = -0.07                       # centres the 1.55 deep tilted pod between the walls
POD_DEPTH = 0.93                    # pod depth / width (photos 239/240 vs 242)
CAVITY_R = 0.95
PK_N = 3.6                         # pocket outline superellipse exponent (higher: straighter sides, a parallel bridge)
PK_X, PK_Y, PK_A, PK_B = 1.39, -0.06, 1.22, 0.86   # interior pocket: centre x/y, half axes (reference int-front: x 0.17..2.61, a constant 0.34 bridge)
PK_N_IN = 7.0                      # exponent of the inner (bridge side) half of the outline: a straight edge, constant-width bridge
REC_Z = SEAM - 0.02                       # base top face (rim, interior and bridge): ONE flat plane at the seam (user: no recess, no raised lip)
RIM_Z = 0.09                       # the interior rim / bridge face sits this far below the seam
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
HINGE_LUG = 0.09                    # how far the lid plate's centre lug reaches below the seam (it swings into the base)
HINGE_BAR_Y = (0.76, 0.92)          # one dark trapezoid on the base rim (hinge-inner): y range, half widths at front / back
HINGE_BAR_HW = (1.15, 1.30)
HINGE_BAR_Z = (-0.02, -0.016)       # top relative to the seam: flush with the base top face (REC_Z = SEAM - 0.02), a hair proud
HINGE_PARTS = {}
WELLS = []                          # world-space stem well axes (p0, p1), for the floor blend
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


PLAN_FLAT = float(sys.argv[sys.argv.index("--pf") + 1]) if "--pf" in sys.argv else 0.5    # flat side half length / half width a
PLAN_W = float(sys.argv[sys.argv.index("--pw") + 1]) if "--pw" in sys.argv else 0.6         # fraction of the end curve over which the curvature ramps up


def _end_curve(nc=96):
    """Unit end curve of the plan section: starts on the flat side (heading +x, curvature 0) and turns by 90 degrees to
    the end tip. Curvature k(u) = sin^2(pi/2 min(u/w, 1)): zero value and slope at the join (G3 with the straight side), a
    constant-curvature arc after w. Returns points (x, y) with the start at (0, 0), y running down to the tip (dx, -dy)."""
    w = PLAN_W
    n = 4000
    k = [math.sin(math.pi / 2 * min(i / n / w, 1.0)) ** 2 for i in range(n + 1)]
    cum = [0.0]
    for i in range(n):
        cum.append(cum[-1] + 0.5 * (k[i] + k[i + 1]) / n)
    sc = (math.pi / 2) / cum[-1]                  # total turning pi/2
    x = y = 0.0
    xs, ys = [0.0], [0.0]
    for i in range(n):
        th = sc * 0.5 * (cum[i] + cum[i + 1])
        x += math.cos(th) / n
        y -= math.sin(th) / n
        xs.append(x)
        ys.append(y)
    idx = [round(n * (i / nc)) for i in range(nc + 1)]
    return [(xs[i], ys[i]) for i in idx]


_END = None


def plan_quarter(a, b, nf=28, nc=56):
    """One quarter of the plan section with half sizes a (x) and b (y): straight side from (0, b) to (f a, b), then the
    end curve (affinely scaled, so it stays G3) to the tip (a, 0). Same vertex count for every (a, b)."""
    global _END
    if _END is None:
        _END = _end_curve(nc)
    x0 = PLAN_FLAT * a
    dx, dy = _END[-1][0], -_END[-1][1]
    pts = [(x0 * i / nf, b) for i in range(nf)]
    pts += [(x0 + (a - x0) * px / dx, b + b * py / dy) for px, py in _END]
    return pts


def plan_y(x, a, b):
    """y of the plan section at |x| (for _back_y), consistent with plan_quarter."""
    x = abs(x)
    q = plan_quarter(a, b)
    if x >= a:
        return 0.0
    for (x0, y0), (x1, y1) in zip(q, q[1:]):
        if x0 <= x <= x1 and x1 > x0:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return b


def plan_ring(a, b):
    """Full closed outline (CCW from the +x tip) with the same vertex count for every (a, b)."""
    q = plan_quarter(a, b)
    out = list(reversed(q))                                    # tip -> top centre
    out += [(-x, y) for x, y in q[1:]]                         # top centre -> -x tip
    out += [(-x, -y) for x, y in reversed(q[:-1])]             # -x tip -> bottom centre
    out += [(x, -y) for x, y in q[1:-1]]                       # bottom centre -> before the +x tip
    return out


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
    bm = bmesh.new()

    def ring(z, a_, b_):
        return [bm.verts.new((x, y, z)) for x, y in plan_ring(a_, b_)]
    nlon = len(plan_ring(1.0, 1.0))
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


def clean(obj, dist=4e-4, zmax=None):
    """Dissolve the sliver faces the exact booleans leave: with weighted normals they shade black. `zmax`: only below it."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=[v for v in bm.verts if zmax is None or v.co.z < zmax], dist=dist)
    bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def densify(obj, zmin, zmax, maxlen=0.12, rounds=6, sg=1):
    """Split the long edges of the flat faces between zmin and zmax: the exact boolean would otherwise leave long fan
    triangles on the rim face (they shade as streaks)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    def sel(f):                                  # flat faces inside the recess, away from the outer rim ring
        c = f.calc_center_median()
        return (zmin < c.z < zmax and sg * f.normal.z > 0.9
                and (abs(c.x) / (W / 2 - 0.35)) ** 3 + (abs(c.y) / (D / 2 - 0.35)) ** 3 < 1.0)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if sel(f)])
    for _ in range(rounds):
        faces = [f for f in bm.faces if sel(f)]
        edges = list({e for f in faces for e in f.edges if e.calc_length() > maxlen})
        if not edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(obj.data)
    bm.free()


def flat_prism(name, a, b, z0, h, n=N_PLAN, ns=192, flare=0.08, rise=0.035):
    """Superellipse prism with a perfectly flat bottom at z0 (the recess cutter: its floor must be exactly flat). The
    wall flares outwards by `flare` while rising `rise`: a shallow ramp (no sharp edge for the bevel to chew on)."""
    bm = bmesh.new()

    def ring(aa, bb, z):
        return [bm.verts.new((aa * math.copysign(abs(math.cos(t)) ** (2 / n), math.cos(t)),
                              bb * math.copysign(abs(math.sin(t)) ** (2 / n), math.sin(t)), z))
                for t in (2 * math.pi * k / ns for k in range(ns))]
    rs = [ring(a, b, z0), ring(a + flare, b + flare, z0 + rise), ring(a + flare, b + flare, z0 + h)]
    for r0, r1 in zip(rs, rs[1:]):
        for k in range(ns):
            bm.faces.new((r0[k], r0[(k + 1) % ns], r1[(k + 1) % ns], r1[k]))
    bm.faces.new(rs[0][::-1])
    bm.faces.new(rs[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm)


def patch_slivers(obj, maxlen=0.03, sides=8, weld=0.006):
    """Close the few micro holes the exact booleans leave: weld near-coincident boundary vertices (the holes are often
    open chains, not loops), fill boundary loops of up to `sides` short edges, drop what is left loose."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bv = list({v for e in bm.edges if e.is_boundary for v in e.verts})
    if bv:
        bmesh.ops.remove_doubles(bm, verts=bv, dist=weld)
        edges = [e for e in bm.edges if e.is_boundary and e.calc_length() < maxlen]
        if edges:
            bmesh.ops.holes_fill(bm, edges=edges, sides=sides)
        loose = [e for e in bm.edges if not e.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="EDGES")
        lv = [v for v in bm.verts if not v.link_edges]
        if lv:
            bmesh.ops.delete(bm, geom=lv, context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
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


def rrect(hu, hv, r, n=14):
    """Outline of a rounded rectangle (half sizes hu, hv, corner radius r <= min(hu, hv)), CCW, n points per corner."""
    pts = []
    for cx, cy, a0 in ((hu - r, hv - r, 0.0), (-hu + r, hv - r, 90.0), (-hu + r, -hv + r, 180.0), (hu - r, -hv + r, 270.0)):
        for i in range(n + 1):
            t = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def loft(name, stations, to3d):
    """Solid through several outlines [(l, [(u, v), ...]), ...] (same point count, in order along l); to3d(u, v, l) maps to
    world space. With one outline repeated it is a plain prism; growing outlines make a chamfered mouth."""
    bm = bmesh.new()
    rings = [[bm.verts.new(to3d(u, v, l)) for u, v in o] for l, o in stations]
    n = len(rings[0])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((r0[k], r0[(k + 1) % n], r1[(k + 1) % n], r1[k]))
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm)


# ---- materials -------------------------------------------------------------------------------
def material(name, color, rough=0.3, metal=0.0, coat=0.0, coat_rough=0.05, emission=None, bump=None, spec=0.5, sss=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = (*color, 1)      # viewport (workbench) colour
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
        "grey_tip": material("Silicone tip", (0.93, 0.93, 0.92), rough=0.55, sss=(0.35, (0.9, 0.9, 0.9))),   # white (user, like the reference reference)
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


GPU_PY = os.environ.get("PODGLASS_GPU_PY", "/home/voodoo/.local/share/podglass-gpu/py")
PK_RES, PK_EXTRA, PK_K, PK_SIGMA = 0.0125, 0.0, 200.0, 0.06     # field grid, wall start gap, wall parabola, smoothing (cm)


def pocket_cutters(clear):
    """Base pocket and lid bowl cutters as height fields derived from the pods (see pocket_field.py, run on the GPU):
    the smallest smooth cavity that lets each pod drop in vertically, with a small uniform clearance."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    vs, fs, off = [], [], 0
    for c in clear:
        me = c.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        v = np.array([c.matrix_world @ p.co for p in me.vertices], dtype=np.float32).reshape(-1, 3)
        f = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.int64).reshape(-1, 3)
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    tmp = tempfile.mkdtemp(prefix="pkfield")
    fin, fout = os.path.join(tmp, "in.npz"), os.path.join(tmp, "out.npz")
    np.savez(fin, v=np.concatenate(vs), f=np.concatenate(fs), seam=SEAM, res=PK_RES, extra=PK_EXTRA, k=PK_K,
             sigma=PK_SIGMA, dish_cx=1.385, dish_cy=PK_Y, dish_a=1.2, dish_b=0.8, dish_n=2.6, ztop=REC_Z + 0.045, zr=REC_Z, fr=0.09, zbot=SEAM + RIM_Z - 0.045)
    subprocess.run(["nice", "-n", "19", GPU_PY, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pocket_field.py"), fin, fout], check=True,
                   env={k: v for k, v in os.environ.items() if not k.startswith("PYTHON")})
    d = np.load(fout)
    return d


def field_cutter(name, d, key, sx, up):
    """Closed solid from a height field patch around the pocket on side sx: floor = field (cutter bottom, or its top
    when up), the other side a flat plate 0.3 beyond the rim face."""
    res, x0, y0 = float(d["res"]), float(d["x0"]), float(d["y0"])
    Z = d[key]
    i0, i1 = int((sx * PK_X - 1.5 - x0) / res), int((sx * PK_X + 1.5 - x0) / res)
    j0, j1 = int((-1.05 - y0) / res), int((1.05 - y0) / res)
    sub = Z[i0:i1, j0:j1]
    nx, ny = sub.shape
    xs = x0 + (np.arange(i0, i1) + 0.5) * res
    ys = y0 + (np.arange(j0, j1) + 0.5) * res
    plate = (SEAM - 0.5) if up else (SEAM + 0.5)
    bm = bmesh.new()
    grid = [[bm.verts.new((xs[i], ys[j], float(sub[i, j]))) for j in range(ny)] for i in range(nx)]
    for i in range(nx - 1):
        for j in range(ny - 1):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
    ring = [(i, 0) for i in range(nx)] + [(nx - 1, j) for j in range(1, ny)] + [(i, ny - 1) for i in range(nx - 2, -1, -1)] + [(0, j) for j in range(ny - 2, 0, -1)]
    top = [bm.verts.new((xs[i], ys[j], plate)) for i, j in ring]
    for a in range(len(ring)):
        b = (a + 1) % len(ring)
        bm.faces.new((grid[ring[a][0]][ring[a][1]], grid[ring[b][0]][ring[b][1]], top[b], top[a]))
    bm.faces.new(top[::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm)


def bathtub(name, cx, cy, a, b, z_top, z_bot, rb, n=2.8, up=False, nr=14, ns=96, rh=None, zf=None, rf=0.12, nf=8, n_in=None):
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
    r_end = rb if rh is None else rh
    prof += [(r_end + (0.8 * b - r_end) * k / 5, z_bot) for k in range(1, 6)]     # concentric rings across the floor (no long sliver triangles)
    rings = []
    for inset, z in prof:
        ring = []
        for k in range(ns):
            th = 2 * math.pi * k / ns
            c, sn = math.cos(th), math.sin(th)
            ne = n if (n_in is None or c * cx > 0) else n_in    # n_in: the half facing the case centre
            x = (a - inset) * math.copysign(abs(c) ** (2 / ne), c)
            y = (b - inset) * math.copysign(abs(sn) ** (2 / ne), sn)
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


def blend_wells(obj, reach=0.95, iters=5, fac=0.5, zmax=2.4):
    """Fillet the stem wells into the pocket floor: a few Laplacian passes on the vertices around each well axis
    (the boolean leaves slivers and a hard crater edge there)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    def near(v):
        for p0, p1 in WELLS:
            d = p1 - p0
            t = min(max((v.co - p0).dot(d) / d.length_squared, 0.0), 1.0)
            if (v.co - (p0 + d * t)).length < reach and v.co.z < zmax:
                return True
        return False
    sel = [v for v in bm.verts if near(v) and not v.is_boundary and v.normal.z > 0.2 and all(math.hypot(abs(v.co.x) - hx, v.co.y) > 0.16 for hx in (1.40, 1.44, 1.67, 1.90))]
    for _ in range(iters):
        bmesh.ops.smooth_vert(bm, verts=sel, factor=fac, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(obj.data)
    bm.free()


def stem_well(name, o, sgn, gap):
    """Analytic stem well: a smooth rounded capsule along the stem axis of pod body `o`, a little wider than the grown
    stem and flaring into the head, so the real body cut removes nothing visible from the pocket floor."""
    B = PODS["body"]
    zb, zt = B["sz"][1], -0.45
    ax = lambda z_: (sgn * (B["sa"][0] + B["ss"][0] * (z_ - B["sa"][2])), B["sa"][1] + B["ss"][1] * (z_ - B["sa"][2]))
    r_lo = max(B["sr"]) + gap + 0.04
    def rad(z_):                           # a plain cylinder, flaring (cosine) into a fillet where it meets the pocket floor
        t = min(max((z_ - (zb + 0.55)) / 0.7, 0.0), 1.0)
        return r_lo + 0.05 * (0.5 - 0.5 * math.cos(math.pi * t))
    zc = zb + 0.15                      # centre of the rounded end cap
    bm = bmesh.new()
    rings = []
    nz, ns = 40, 48
    prof = [(zc - r_lo * math.cos(math.pi / 2 * i / 8), r_lo * math.sin(math.pi / 2 * i / 8)) for i in range(0, 8)]
    prof += [(zc + (zt - zc) * i / nz, rad(zc + (zt - zc) * i / nz)) for i in range(0, nz + 1)]
    prof[-1] = (zt, rad(zt))
    for z_, r_ in prof:
        cx_, cy_ = ax(z_)
        rings.append([bm.verts.new((cx_ + r_ * math.cos(2 * math.pi * k / ns), cy_ + r_ * math.sin(2 * math.pi * k / ns), z_)) for k in range(ns)])
    bm.verts.ensure_lookup_table()
    pole = bm.verts.new((*ax(zc - r_lo), zc - r_lo))
    for i in range(len(rings) - 1):
        for k in range(ns):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % ns], rings[i + 1][(k + 1) % ns], rings[i + 1][k]))
    for k in range(ns):
        bm.faces.new((pole, rings[0][(k + 1) % ns], rings[0][k]))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    c = link(name, bm)
    for p_ in c.data.polygons:
        p_.use_smooth = True
    c.data.transform(o.matrix_world)
    WELLS.append((o.matrix_world @ Vector((*ax(zb), zb)), o.matrix_world @ Vector((*ax(zt), zt))))
    return c


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
    return plan_y(x, a_, max(b_, 0.02))


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


def _lug_sweep(name, x0, x1, z0, z1, din, dout, theta, nx=14, nr=40, cl=HINGE_CLEAR):
    """Analytic solid swept by the lid plate's centre lug (a plate on the back wall over [x0, x1] x [z0, z1], din
    below / dout above the wall) while the lid opens by `theta` rad: per x slice the yz region is bounded by two
    radial edges and two arcs about the hinge axis, lofted along x. One closed manifold, no boolean chain."""
    import numpy as np
    phis = np.linspace(-math.pi, math.pi, 7200)
    ring_n = None
    bm = bmesh.new()
    slices = []
    for i in range(nx + 1):
        x = x0 - cl + (x1 - x0 + 2 * cl) * i / nx
        yw = _back_y(min(abs(x), 1.4), 0.5 * (z0 + z1))
        ya, yb = yw - din - cl - HINGE_Y, yw + dout + cl - HINGE_Y        # dy range, relative to the axis
        za, zb_ = z0 - cl - HINGE_Z, z1 + cl - HINGE_Z
        cy, cz = min(max(0.0, ya), yb), min(max(0.0, za), zb_)
        rmin = max(math.hypot(cy, cz), 1e-3)
        rmax = max(math.hypot(yy, zz) for yy in (ya, yb) for zz in (za, zb_))
        rs = np.linspace(rmin + 0.002, rmax - 0.002, nr)
        lo, hi = [], []
        for r in rs:
            py, pz = r * np.cos(phis), r * np.sin(phis)
            ok = np.where((py >= ya) & (py <= yb) & (pz >= za) & (pz <= zb_))[0]
            if len(ok) == 0:          # circle just grazes the rectangle
                ok = [int(np.argmin(np.abs(phis - math.atan2(cz, cy))))]
            lo.append(phis[ok[0]])
            hi.append(phis[ok[-1]])
        # the lid turns by -theta (rotation about +x by -theta moves phi by -theta)
        pts = [(r, h) for r, h in zip(rs, hi)]
        k = 8
        pts += [(rmax, hi[-1] + (lo[-1] - theta - hi[-1]) * j / k) for j in range(1, k)]
        pts += [(r, l - theta) for r, l in zip(rs[::-1], lo[::-1])]
        pts += [(rmin, lo[0] - theta + (hi[0] - lo[0] + theta) * j / k) for j in range(1, k)]
        slices.append([bm.verts.new((x, HINGE_Y + r * math.cos(p), HINGE_Z + r * math.sin(p))) for r, p in pts])
    n = len(slices[0])
    for i in range(nx):
        for j in range(n):
            bm.faces.new((slices[i][j], slices[i][(j + 1) % n], slices[i + 1][(j + 1) % n], slices[i + 1][j]))
    bm.faces.new(slices[0][::-1])
    bm.faces.new(slices[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link(name, bm)


def _bar(zb):
    """One continuous dark trapezoid on the base rim (hinge-inner): plan trapezoid, low arched top, flat sunk bottom."""
    y0, y1 = HINGE_BAR_Y
    nu, nv = 48, 6
    bm = bmesh.new()
    def top(u, v):
        hw = HINGE_BAR_HW[0] + (HINGE_BAR_HW[1] - HINGE_BAR_HW[0]) * v
        z = SEAM + HINGE_BAR_Z[0] + (HINGE_BAR_Z[1] - HINGE_BAR_Z[0]) * (1 - u * u) * (1.0 - 0.6 * v)
        return (u * hw, y0 + (y1 - y0) * v, z)
    g = [[bm.verts.new(top(-1 + 2 * i / nu, j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
    for j in range(nv):
        for i in range(nu):
            bm.faces.new((g[j][i], g[j][i + 1], g[j + 1][i + 1], g[j + 1][i]))
    ring = [g[0][i] for i in range(nu)] + [g[j][nu] for j in range(nv)] + [g[nv][i] for i in range(nu, 0, -1)] + [g[j][0] for j in range(nv, 0, -1)]
    low = [bm.verts.new((v.co.x, v.co.y, zb)) for v in ring]
    for k in range(len(ring)):
        k2 = (k + 1) % len(ring)
        bm.faces.new((ring[k], ring[k2], low[k2], low[k]))
    bm.faces.new(low[::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return link("Case_HingeBar", bm)


def hinge_cuts(base, lid, gap):
    """Steel plate flush in the back wall across the seam (photo 248): the lid half reaches below the seam in the
    middle (a short lug), the base half only at the ends; plus ONE dark trapezoid on the base rim in front of the lug's
    swing. Slots are cut into base and lid; the lug's analytic sweep is cut out of the base. Solids go to
    HINGE_PARTS for build_hardware."""
    hw, mid, e, m = HINGE_HW, HINGE_MID, 0.01, 0.012
    zb0, zt, zs_ = SEAM - HINGE_PLATE_BELOW, SEAM + HINGE_PLATE_ABOVE, SEAM + gap + e
    zl = SEAM - HINGE_LUG
    sk = HINGE_SKIN
    top_r = ((1, 1), (-1, 1))
    upper = lambda din, dout, mg: _sheet("u", -hw - mg, hw + mg, zs_ - mg, zt + mg, din, dout, top_r, HINGE_R + mg)
    centre = lambda din, dout, mg: _sheet("c", -mid - mg, mid + mg, zl - mg, zs_ + 0.002, din, dout, ((1, -1), (-1, -1)) if mg == 0 else (), HINGE_R)
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
    sweep = _lug_sweep("lug_sweep", -mid, mid, zl, zs_ + 0.002, sk, 0.0, math.radians(125.0))   # the lug's swing, base frame
    boolean(base, sweep)
    bar = _bar(SEAM - 0.3)
    cut = bar.copy()
    cut.data = bar.data.copy()
    bpy.context.collection.objects.link(cut)
    boolean(base, cut)
    plate_b = bpy.data.objects[plate_b.name]
    plate_b.name, plate_l.name = "Case_Hinge", "Case_HingeLid"
    HINGE_PARTS.update(base=plate_b, lid=plate_l, bar=bar)
    for ob in (plate_b, plate_l):
        clean(ob)
        bevel(ob, 0.015, 2, angle=35)
    bevel(bar, 0.015, 2, angle=35)
    clean(base, 1.5e-3)


def refine(obj, boxes, maxlen=0.05, passes=8):
    """Split the long edges inside the given world boxes ((x0, x1), (y0, y1), (z0, z1)) down to `maxlen`, so an exact
    boolean there meets small, even triangles instead of the long slivers of the case's cap fans."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for _ in range(passes):
        es = []
        for e in bm.edges:
            if e.calc_length() <= maxlen:
                continue
            m = (e.verts[0].co + e.verts[1].co) / 2
            if any(bx[0][0] <= m.x <= bx[0][1] and bx[1][0] <= m.y <= bx[1][1] and bx[2][0] <= m.z <= bx[2][1] for bx in boxes):
                es.append(e)
        if not es:
            break
        bmesh.ops.subdivide_edges(bm, edges=es, cuts=1, use_grid_fill=False)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def outer_details(base):
    """Crisp outer details, cut after the big edge bevel (so it cannot chew them up) and with chamfered mouths:
    lanyard recess with two dimples (right end), Lightning slot, speaker holes, thumb step."""
    lz = SEAM - 0.84
    # lanyard recess in the right end (reference right shot): white stadium 0.47 (y) x 0.95 (z), 0.05 deep, following
    # the curved end (floor = the shell moved in by 0.05), with two round dimples (0.37 wide, 0.08 deep) in it
    lbox = ((W / 2 - 0.5, W / 2 + 0.1), (-0.55, 0.55), (lz - 0.62, lz + 0.62))
    refine(base, [lbox], 0.025, passes=10)
    refine(base, [((-0.7, 0.7), (-0.32, 0.32), (-0.1, 0.12)),
                  ((-1.55, -1.25), (-0.15, 0.15), (-0.1, 0.12)), ((1.3, 2.05), (-0.15, 0.15), (-0.1, 0.12)),
                  ((-1.5, 1.5), (-1.15, -0.9), (SEAM - 0.4, SEAM + 0.02))], 0.045)
    xf = W / 2 - 0.05                                    # floor level on the axis: the mouth flares at 45 degrees above it
    st = [(W / 2 - 0.6, 0.0), (xf, 0.0), (xf + 0.03, 0.03), (xf + 0.45, 0.45)]
    rec = loft("lany", [(l, rrect(0.235 + d, 0.475 + d, 0.235 + d, 24)) for l, d in st], lambda u, v, l: (l, u, lz + v))
    boolean(rec, inner_shell("lany_in", wall=0.05))
    refine(rec, [lbox], 0.025, passes=10)
    boolean(base, rec)
    for dz in (-0.235, 0.235):
        # spherical cap 0.37 wide, 0.08 deep below the floor: steep enough (49 deg) at the rim for a crisp edge
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2455, segments=64, ring_count=32, location=(xf - 0.08 + 0.2455, 0.0, lz + dz))
        boolean(base, bpy.context.active_object)
    # Lightning slot (photo 247): centred, 1.0 x 0.3, rounded ends; speaker holes 1 left + 3 right of it
    st = [(-0.3, 0.29), (-0.01, 0.0), (0.5, 0.0)]          # 0.02 chamfer at the mouth (bottom face at z = -0.03 .. 0)
    boolean(base, loft("port", [(l, rrect(0.5 + d, 0.15 + d, 0.14 + d, 12)) for l, d in st], lambda u, v, l: (u, v, l)))
    for hx in (-1.40, 1.44, 1.67, 1.90):   # see-through in the reference bottom shot: up into the pod cavity
        boolean(base, cyl("hole", 0.063, 4.4, (hx, 0.0, 0.0), verts=32))
    boolean(base, thumb_scoop())
    clean(base, 1.5e-3)
    patch_slivers(base)
    clean(base, 1e-3, zmax=2.5)             # a few micro slivers of the pocket booleans, away from the hinge slots


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
    fld = pocket_cutters(clear) if clear else None
    densify(base, SEAM - 0.2, SEAM)
    for sx in (-1, 1):  # two pockets hugging the pods: the smallest smooth cavity that lets the pod drop in
        if fld is not None:
            pk = field_cutter("pocket_b", fld, "base", sx, False)
            boolean(base, pk)
    for c in clear:
        boolean(base, c, keep=True)
    clean(base, 1.5e-3)
    bevel(base, 0.1, 2, angle=35)
    if "--nod" not in sys.argv:
        outer_details(base)
    smooth(base, 35, weighted="--nown" not in sys.argv)

    # ---- lid (origin later moved to the hinge axis): solid with two bowls for the pod heads
    lid = shell("Case_Lid")
    boolean(lid, rbox("keep", W * 2, D * 2, LID_H * 2, 0.0, segs=1, center=(0, 0, H - LID_H + gap + LID_H)), "INTERSECT")
    for sx in (-1, 1):
        if fld is None:
            continue
        c = field_cutter("bowl", fld, "lid", sx, True)
        # the traced top falls towards the ends: keep the bowl one wall inside the shell or it cuts through
        boolean(c, inner_shell("inner", 0.24), "INTERSECT")
        boolean(lid, c)
    lrec = superell("lrec", W / 2 - 0.2, D / 2 - 0.2, 0.5, center=(0, 0, SEAM + gap - 0.5 + 0.07), dome=0.0, nlat=8, nlon=96)
    boolean(lid, lrec)
    densify(lid, SEAM, SEAM + 0.2, sg=-1)
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
    # status light: a disc sunk in the front wall, its face 0.003 proud of the surface (no cut in the base: no slivers)
    yf = -_back_y(0.0, SEAM - LED_DROP) - 0.003
    led = cyl("Case_LED", 0.04, 0.06, (0, yf + 0.03, SEAM - LED_DROP), rot=(math.pi / 2, 0, 0), verts=32)
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
TIP_MESH_R, TIP_MESH_Z, TIP_MESH_DIP = 0.27, 0.235, 0.03   # speaker mesh: radius, rim height on the tip axis, concave dip at the centre
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
    mv, mf = pod_shape.mesh_dome(TIP_MESH_R, TIP_MESH_Z, TIP_MESH_DIP)
    bmm = bmesh.new()
    mvv = [bmm.verts.new(tuple(p_)) for p_ in mv]
    for f_ in mf:
        bmm.faces.new([mvv[i] for i in f_])
    bmesh.ops.recalc_face_normals(bmm, faces=bmm.faces)
    mesh = link(name + "_Mesh", bmm)
    for p_ in mesh.data.polygons:
        p_.use_smooth = True
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
            if o.name.endswith("_Body"):
                out.append(stem_well(o.name + "_Well", o, 1 if "_L_" in o.name else -1, gap))
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
            if o.name.endswith("_Body"):
                # keep only the head: below local z -0.85 the stem is covered by the analytic well (no stem faces in the pocket)
                bmh = bmesh.new()
                bmh.from_mesh(c.data)
                no = o.matrix_world.to_3x3() @ Vector((0, 0, 1))
                geom = bmh.verts[:] + bmh.edges[:] + bmh.faces[:]
                r_ = bmesh.ops.bisect_plane(bmh, geom=geom, dist=1e-6, plane_co=o.matrix_world @ Vector((0, 0, -0.85)), plane_no=no, clear_inner=True)
                edges = [e_ for e_ in bmh.edges if e_.is_boundary]
                bmesh.ops.holes_fill(bmh, edges=edges, sides=0)
                bmesh.ops.recalc_face_normals(bmh, faces=bmh.faces)
                bmh.to_mesh(c.data)
                bmh.free()
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
    for ob in (base, lid):   # last word: micro holes from any later cut (the exact booleans are not deterministic)
        patch_slivers(ob, maxlen=0.1, sides=12)
    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print("saved", OUT)


main()
