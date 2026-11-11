"""Pod body and tip geometry from tools/render/profiles_pod.json (pure math, no bpy).

The body is a smooth implicit surface (see sdf); "rows" is only its fit target. The table is traced from the reference pod silhouettes (tools/render/sf): sections of the head+stem
loft, in the pod-root frame of the LEFT pod (x grows towards the case centre). `sgn` mirrors it for the right pod.
  rows: [z, cx, cy, hx, hy, psi, n]  section centred at (cx, cy), half axes hx (x) and hy (y), rotated by psi about z,
        superellipse exponent n (2 = ellipse), top to bottom
  tip:  {"pos": [x, y, z], "dir": [x, y, z], "ecc", "roll"} of the lathe tip_prof (radius, z along the axis) in the root frame
"""
import json
import math
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "tools/render",
                    "profiles_pod.json")


def load(path=PATH):
    return json.load(open(path))


# ---- smooth body: implicit surface (egg head smooth-unioned with a rounded elliptic stem) -------------------------------------
# Parameters (left pod, pod-root frame, cm), fitted by tools/render/fit_pod.py to the traced sections ("rows", fit target only):
#   head: centre hc, half axes ha, euler angles hr (rad, rz*ry*rx);  stem: axis through sa (at z = sa[2]) with slopes ss = (dx/dz, dy/dz),
#   half axes sr (x, y), top/bottom z, end rounding rr;  k: smooth-union blend radius (concave elbow fillet).
BODY_KEYS = [("hc", 3), ("ha", 3), ("hr", 3), ("sa", 3), ("ss", 2), ("sr", 2), ("sz", 2), ("rr", 1), ("k", 1), ("hp", 1), ("et", 1)]


def pack(body):
    return [v for k, n in BODY_KEYS for v in (body[k] if n > 1 else [body[k]])]


def unpack(vec):
    out, i = {}, 0
    for k, n in BODY_KEYS:
        out[k] = list(vec[i:i + n]) if n > 1 else vec[i]
        i += n
    return out


def _rot(a, b, c, xp=math):
    ca, sa_, cb, sb, cc, sc = xp.cos(a), xp.sin(a), xp.cos(b), xp.sin(b), xp.cos(c), xp.sin(c)
    # R = Rz(a) Ry(b) Rx(c)
    return [[ca * cb, ca * sb * sc - sa_ * cc, ca * sb * cc + sa_ * sc],
            [sa_ * cb, sa_ * sb * sc + ca * cc, sa_ * sb * cc - ca * sc],
            [-sb, cb * sc, cb * cc]]


def sdf(B, x, y, z, xp):
    """Approximate signed distance (negative inside) of the pod body at points x, y, z (arrays of module xp: numpy or cupy)."""
    hc, ha, hr = B["hc"], B["ha"], B["hr"]
    R = _rot(*hr, xp=xp)
    dx, dy, dz = x - hc[0], y - hc[1], z - hc[2]
    # local = R^T d
    lx = R[0][0] * dx + R[1][0] * dy + R[2][0] * dz
    ly = R[0][1] * dx + R[1][1] * dy + R[2][1] * dz
    lz = R[0][2] * dx + R[1][2] * dy + R[2][2] * dz
    uz = lz / ha[2]
    eg = 1.0 + B["et"] * uz                            # egg: the section grows towards +/- local z
    ux, uy = lx / (ha[0] * eg), ly / (ha[1] * eg)
    p = B["hp"]                                        # superellipsoid exponent (2 = ellipsoid)
    ax, ay, az = xp.abs(ux) + 1e-9, xp.abs(uy) + 1e-9, xp.abs(uz) + 1e-9
    Nn = ax ** p + ay ** p + az ** p
    k0 = Nn ** (1.0 / p)
    gk = Nn ** (1.0 / p - 1.0)
    k1 = gk * xp.sqrt((ax ** (p - 1) / ha[0]) ** 2 + (ay ** (p - 1) / ha[1]) ** 2 + (az ** (p - 1) / ha[2]) ** 2) + 1e-12
    d_head = k0 * (k0 - 1.0) / k1                      # distance bound
    # stem: elliptic cylinder along a slanted axis with rounded ends
    sa, ss, sr = B["sa"], B["ss"], B["sr"]
    ex = x - (sa[0] + ss[0] * (z - sa[2]))
    ey = y - (sa[1] + ss[1] * (z - sa[2]))
    vx, vy = ex / sr[0], ey / sr[1]
    f = xp.sqrt(vx * vx + vy * vy) + 1e-12
    g = xp.sqrt((vx / sr[0]) ** 2 + (vy / sr[1]) ** 2) + 1e-12
    dxy = f * (f - 1.0) / g
    rr = B["rr"]
    zt, zb = B["sz"]
    a = dxy + rr
    b = xp.maximum(zb + rr - z, z - (zt - rr))
    d_stem = xp.minimum(xp.maximum(a, b), 0.0) + xp.sqrt(xp.maximum(a, 0.0) ** 2 + xp.maximum(b, 0.0) ** 2) - rr
    k = B["k"]
    h = xp.clip(0.5 + 0.5 * (d_stem - d_head) / k, 0.0, 1.0)
    return d_stem * (1 - h) + d_head * h - k * h * (1 - h)


def body_mesh(B, sgn=1, nz=160, nlon=96):
    """Structured mesh of the body surface: rings at heights z (clustered at both poles), each ring cast from a centre
    inside the section onto the zero set of sdf by bisection.  Returns (verts (N,3), quads (M,4), top pole idx, bottom pole idx)."""
    import numpy as np
    sa, ss = B["sa"], B["ss"]
    # vertical extent: along the head axis column and the stem axis
    zz = np.linspace(-3, 3, 60001)
    col = lambda cx, cy: zz[sdf(B, np.full_like(zz, cx), np.full_like(zz, cy), zz, np) < 0]
    ins = col(B["hc"][0], B["hc"][1])
    z_top = ins.max()
    ins2 = col(sa[0] + ss[0] * (B["sz"][1] + 0.3 - sa[2]), sa[1] + ss[1] * (B["sz"][1] + 0.3 - sa[2]))
    z_bot = min(ins2.min(), ins.min())
    t = (1 - np.cos(np.pi * (np.arange(nz) + 0.5) / nz)) / 2
    zs = z_bot + (z_top - z_bot) * t
    th = 2 * np.pi * np.arange(nlon) / nlon
    Z = np.repeat(zs[:, None], nlon, 1)
    # section centre: stem axis below the head, head axis above (blended); any point inside both is star-shaped for these shapes
    w = np.clip((zs - (B["hc"][2] - B["ha"][2] * 0.6)) / (B["ha"][2] * 0.6), 0, 1)
    w = w * w * (3 - 2 * w)
    sxs = sa[0] + ss[0] * (zs - sa[2])
    sys_ = sa[1] + ss[1] * (zs - sa[2])
    cx = (sxs * (1 - w) + B["hc"][0] * w)[:, None]
    cy = (sys_ * (1 - w) + B["hc"][1] * w)[:, None]
    lo = np.zeros_like(Z)
    hi = np.full_like(Z, 2.5)
    C, S = np.cos(th)[None], np.sin(th)[None]
    for _ in range(48):
        mid = (lo + hi) / 2
        inside = sdf(B, cx + mid * C, cy + mid * S, Z, np) < 0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    r = (lo + hi) / 2
    G = np.stack([cx + r * C, cy + r * S, Z], -1)               # (nz, nlon, 3)
    top = np.array([B["hc"][0], B["hc"][1], z_top])
    bot = np.array([sa[0] + ss[0] * (z_bot - sa[2]), sa[1] + ss[1] * (z_bot - sa[2]), z_bot])

    def grad(Q):
        e = 1e-4
        g = np.stack([sdf(B, Q[..., 0] + e, Q[..., 1], Q[..., 2], np) - sdf(B, Q[..., 0] - e, Q[..., 1], Q[..., 2], np),
                      sdf(B, Q[..., 0], Q[..., 1] + e, Q[..., 2], np) - sdf(B, Q[..., 0], Q[..., 1] - e, Q[..., 2], np),
                      sdf(B, Q[..., 0], Q[..., 1], Q[..., 2] + e, np) - sdf(B, Q[..., 0], Q[..., 1], Q[..., 2] - e, np)], -1)
        return g / (2 * e)

    # the z-rings sample the underside of the head (surface nearly horizontal at the elbow) badly: relax the grid along the surface
    # (tangential Laplacian) and project back onto the zero set, so the vertices end up evenly spread on the exact surface
    for _ in range(60):
        up = np.concatenate([np.broadcast_to(bot, (1, nlon, 3)), G[:-1]], 0)       # ring 0 is the lowest
        dn = np.concatenate([G[1:], np.broadcast_to(top, (1, nlon, 3))], 0)
        lap = (up + dn + np.roll(G, 1, 1) + np.roll(G, -1, 1)) / 4 - G
        g = grad(G)
        nrm = g / (np.linalg.norm(g, axis=-1, keepdims=True) + 1e-12)
        lap -= nrm * (lap * nrm).sum(-1, keepdims=True)
        G = G + 0.6 * lap
        for _k in range(2):
            d = sdf(B, G[..., 0], G[..., 1], G[..., 2], np)
            g = grad(G)
            G = G - (d / ((g * g).sum(-1) + 1e-12))[..., None] * g
    P = G.reshape(-1, 3)
    V = np.vstack([P, bot, top])
    if sgn < 0:
        V[:, 0] *= -1
    q = []
    for i in range(nz - 1):
        for k in range(nlon):
            a0, a1 = i * nlon + k, i * nlon + (k + 1) % nlon
            q.append((a0, a1, a1 + nlon, a0 + nlon))
    bi, ti = nz * nlon, nz * nlon + 1
    tris = [(((k + 1) % nlon), k, bi) for k in range(nlon)] + [((nz - 1) * nlon + k, (nz - 1) * nlon + (k + 1) % nlon, ti) for k in range(nlon)]
    if sgn < 0:
        q = [(a, d, c, b) for a, b, c, d in q]
        tris = [(b, a, c) for a, b, c in tris]
    return V, q, tris


def smooth_rows(rows, passes=2):
    """1-2-1 smoothing of the traced section parameters (fit target of tools/render/fit_pod.py)."""
    r = [list(x) for x in rows]
    for _ in range(passes):
        n = [list(x) for x in r]
        for i in range(1, len(r) - 1):
            for j in range(1, len(r[i])):
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
