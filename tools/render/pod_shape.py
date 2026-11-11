"""Pod body and tip geometry from tools/render/profiles_pod.json (pure math, no bpy).

The table is traced from the reference pod silhouettes (tools/render/sf): sections of the head+stem
loft, in the pod-root frame of the LEFT pod (x grows towards the case centre). `sgn` mirrors it for the right pod.
  rows: [z, cx, cy, hx, hy]  elliptical section centred at (cx, cy) with half axes hx (x) and hy (y), top to bottom
  tip:  {"pos": [x, y, z], "dir": [x, y, z], "sr": radial scale, "sl": length scale} of TIP_PROF in the root frame
"""
import json
import math
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "tools/render",
                    "profiles_pod.json")


def load(path=PATH):
    return json.load(open(path))


def body_rings(rows, sgn=1, nlon=64):
    """List of rings (lists of (x, y, z)) and the two pole points (top, bottom)."""
    rings = []
    for z, cx, cy, hx, hy in rows:
        ring = []
        for k in range(nlon):
            t = 2 * math.pi * k / nlon
            ring.append((sgn * (cx + hx * math.cos(t)), cy + hy * math.sin(t), z))
        rings.append(ring)
    z0, cx0, cy0 = rows[0][0], rows[0][1], rows[0][2]
    z1, cx1, cy1 = rows[-1][0], rows[-1][1], rows[-1][2]
    return rings, (sgn * cx0, cy0, z0 + 0.012), (sgn * cx1, cy1, z1 - 0.04)


def smooth_rows(rows, passes=2):
    """Light 1-2-1 smoothing of the section parameters (keeps the first and last rows)."""
    r = [list(x) for x in rows]
    for _ in range(passes):
        n = [list(x) for x in r]
        for i in range(1, len(r) - 1):
            for j in range(1, 5):
                n[i][j] = (r[i - 1][j] + 2 * r[i][j] + r[i + 1][j]) / 4
        r = n
    return r


def catmull(pts, n=6):
    """Catmull-Rom samples through 2D points."""
    out = []
    P = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


def tip_matrix_args(tip, sgn=1):
    """Location and unit direction of the tip axis in the root frame (mirrored for the right pod)."""
    x, y, z = tip["pos"]
    dx, dy, dz = tip["dir"]
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    return (sgn * x, y, z), (sgn * dx / n, dy / n, dz / n)
