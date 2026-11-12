"""Pocket height fields (GPU, CuPy): the base pockets and lid bowls as smooth drop-in cavities derived from the pods.

Run with the GPU python (not Blender):  py pocket_field.py in.npz out.npz
in.npz: v (N,3) world vertices, f (M,3) triangles of the pod clearance cutters, seam, params.
out.npz: x0, y0, res, base (floor height of the base pocket cutter), lid (ceiling height of the lid bowl cutter).

Model: the lower envelope of the pod parts below the seam is the pocket floor, over the footprint of those parts
(vertical drop-in). Outside the footprint the floor climbs in a steep parabola (a softly curved wall), then it is
smoothed. The lid is the mirror: the upper envelope of the parts above the seam.
"""
import sys

import cupy as cp
import numpy as np
from cupyx.scipy import ndimage as nd

inp, outp = sys.argv[1:3]
d = np.load(inp)
V, F = cp.asarray(d["v"], cp.float32), cp.asarray(d["f"])
seam, res = float(d["seam"]), float(d["res"])
extra, k, sigma, ztop, zbot = (float(d[n]) for n in ("extra", "k", "sigma", "ztop", "zbot"))
X0, X1, Y0, Y1 = -3.2, 3.2, -1.3, 1.3
nx, ny = int(round((X1 - X0) / res)), int(round((Y1 - Y0) / res))
lo = cp.full((nx, ny), cp.inf, cp.float32)
hi = cp.full((nx, ny), -cp.inf, cp.float32)
n = 14
ij = [(i, j) for i in range(n + 1) for j in range(n + 1 - i)]
for s in range(0, len(F), 20000):
    t = V[F[s:s + 20000]]                       # (m,3,3)
    for i, j in ij:
        p = (t[:, 0] * (n - i - j) + t[:, 1] * i + t[:, 2] * j) / n
        ix = cp.clip(((p[:, 0] - X0) / res).astype(cp.int32), 0, nx - 1)
        iy = cp.clip(((p[:, 1] - Y0) / res).astype(cp.int32), 0, ny - 1)
        below = p[:, 2] < seam + 0.02
        above = p[:, 2] > seam - 0.02
        import cupyx
        cupyx.scatter_min(lo, (ix[below], iy[below]), p[below, 2])
        cupyx.scatter_max(hi, (ix[above], iy[above]), p[above, 2])


def field(env, k):
    """height of a floor from the lower envelope (env = min z), or of a ceiling when the envelope is stored negated."""
    m = cp.isfinite(env)
    m = nd.binary_closing(m, iterations=3, brute_force=True)
    m = nd.binary_opening(m, iterations=1, brute_force=True) | m
    dist, idx = nd.distance_transform_edt(~m, return_distances=True, return_indices=True)
    e = cp.where(cp.isfinite(env), env, cp.inf)
    # fill the holes of the envelope from the nearest valid cell
    ok = cp.isfinite(e)
    dd, ii = nd.distance_transform_edt(~ok, return_distances=True, return_indices=True)
    e = e[ii[0], ii[1]]
    mf = m.astype(cp.float32)
    gs = 0.1 / res                              # normalised blur: the envelope extended smoothly past the footprint edge
    z = nd.gaussian_filter(e * mf, gs, mode="nearest") / cp.maximum(nd.gaussian_filter(mf, gs, mode="nearest"), 1e-3)
    dm = dist * res
    dm = nd.gaussian_filter(dm, 0.04 / res, mode="nearest")   # a smooth outline, not a pixel staircase
    out = cp.where(m, e + 0.0, z + k * cp.maximum(dm - extra, 0.0) ** 2)
    return out, m


# floor: height of the cutter bottom (higher = shallower). ceiling: negate z so the same code applies.
fl, mb = field(lo, k)
fl = cp.where(mb, fl - 0.02, fl)
fl = cp.minimum(fl, ztop)
fl = nd.gaussian_filter(fl, sigma / res, mode="nearest")
fl = cp.minimum(fl, ztop)
# lid: two separate smooth dishes (superellipse plan, one smooth depth curve), deep enough for the pods
xs = X0 + (cp.arange(nx) + 0.5) * res
ys = Y0 + (cp.arange(ny) + 0.5) * res
cx, cy, da, db, dn = (float(d[n_]) for n_ in ("dish_cx", "dish_cy", "dish_a", "dish_b", "dish_n"))
cl = cp.full((nx, ny), zbot, cp.float32)
ml = cp.zeros((nx, ny), bool)
for sx in (-1, 1):
    r = ((cp.abs(xs[:, None] - sx * cx) / da) ** dn + (cp.abs(ys[None, :] - cy) / db) ** dn) ** (1.0 / dn)
    g = cp.sqrt(cp.clip(1.0 - r ** 2.2, 0.0, 1.0))
    need = cp.where((r < 0.85) & cp.isfinite(hi), (hi + 0.06 - zbot) / cp.maximum(g, 0.3), 0.0)
    D = float(need.max())
    print("dish depth", D)
    cl = cp.maximum(cl, zbot + D * g)
    ml |= r < 1.0
cl = nd.gaussian_filter(cl, 0.03 / res, mode="nearest")
cl = -cl                                        # (kept negated below)
np.savez(outp, x0=X0, y0=Y0, res=res, base=cp.asnumpy(fl), lid=-cp.asnumpy(cl), mb=cp.asnumpy(mb), ml=cp.asnumpy(ml))
print("field ok", fl.shape, float(mb.sum()) * res * res, float(ml.sum()) * res * res)
