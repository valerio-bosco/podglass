"""Trace silhouettes of the reference photos into tools/render/profiles.json (numbers only, no photos).

Run (needs numpy + pillow, e.g. nix-shell -p "python3.withPackages (p: [p.numpy p.pillow])"):
  python3 tools/render/trace.py /path/to/assets/reference
Outputs half-width of the case against height (photo 249, front) and half-depth against height (photo 245,
end view, case lying on its back), both scaled to the real size 6.0 x 4.5 x 2.2 cm.
"""
import json
import sys

import numpy as np
from PIL import Image

REF = sys.argv[1] if len(sys.argv) > 1 else "/home/voodoo/Projects/podglass/assets/reference"
W, D, H = 6.0, 2.2, 4.5


def load(n, sub=2):
    im = Image.open(f"{REF}/photo_6023591478757626{n}_w.jpg").convert("L")
    return np.asarray(im.resize((im.width // sub, im.height // sub))).astype(float)


def run_extent(row, c, thr, gap=5):
    """Walk from column c outwards until `gap` consecutive pixels are below thr; return (left, right)."""
    out = []
    for step in (-1, 1):
        x, miss, last = c, 0, c
        while 0 <= x < len(row):
            if row[x] > thr:
                miss, last = 0, x
            else:
                miss += 1
                if miss >= gap:
                    break
            x += step
        out.append(last)
    return out


def front():
    a = load("249")
    m = a > 85
    m[:, :100] = False
    m[:400] = False
    m[1000:] = False
    ys = np.nonzero(m[:, 474])[0]
    top, bot = ys.min(), ys.max()
    # the contiguous column at x=474 starts at the top edge; the bottom edge is where the white ends
    runs = np.nonzero(a[:, 474] > 85)[0]
    top = runs[runs > 400].min()
    bot = runs[runs < 1000].max()
    prof = []
    ext = []
    for r in range(top, bot + 1):
        l, rr = run_extent(a[r], 474, 85)
        ext.append((l, rr))
    ext = np.array(ext)
    scale = W / np.median(ext[:, 1] - ext[:, 0] + 1)
    full = (ext[:, 1] - ext[:, 0] + 1).max()
    scale = W / full
    hh = (bot - top + 1) * scale
    for r in np.linspace(0, bot - top, 61):
        i = int(round(r))
        hw = (ext[i, 1] - ext[i, 0] + 1) * scale / 2
        prof.append([round(H - r / (bot - top) * H, 4), round(hw, 4)])
    return prof[::-1], hh


if __name__ == "__main__":
    fp, hh = front()
    print("front height at width 6.0:", round(hh, 3))
    # 3-point median to drop edge noise; the end ring (z = 0 and H) keeps the first/last traced width
    hw = [r[1] for r in fp]
    sm = [hw[0]] + [sorted(hw[i - 1:i + 2])[1] for i in range(1, len(hw) - 1)] + [hw[-1]]
    out = {"front": [[r[0], round(v, 4)] for r, v in zip(fp, sm)]}
    json.dump(out, open("tools/render/profiles.json", "w"))
    print("wrote tools/render/profiles.json", out["front"][:3], out["front"][-3:])


def pod(head_w=1.62):
    """Pod body (head + stem, no silicone tip) from the side photo 241: centre line and half-width per height.
    Scaled so the head is `head_w` wide (matches the open-case photos 242/243). Returns rows [z, cx, hw], z up,
    origin at the head's widest row centre (x) and 1.0 cm below the top of the head (z)."""
    im = Image.open(f"{REF}/photo_6023591478757626241_w.jpg").convert("RGB")
    a = np.asarray(im).astype(float)
    L = a.mean(axis=2)
    warm = a[:, :, 0] - a[:, :, 2]
    from scipy import ndimage as ndi
    Ls = ndi.gaussian_filter(L, 4)
    ws = ndi.gaussian_filter(warm, 4)
    body = (Ls > 205) & (ws < 30)               # white shell, not the cream tip, not the leather glitter
    lab, _n = ndi.label(body)
    body = lab == lab[1664, 784]                # the blob under the stem (full-res px)
    x0, x1, y0, y1 = 650, 1350, 1050, 1950      # crop around the pod
    m = body[y0:y1, x0:x1]
    rows = []
    for r in range(m.shape[0]):
        xs = np.nonzero(m[r])[0]
        if len(xs):
            rows.append((r, xs.min(), xs.max()))
    rows = np.array(rows, float)
    return rows, (x0, y0)


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * k / 4


def pod_profile(head_w=1.62):
    rows, _off = pod()
    r, lo, hi = rows[:, 0], rows[:, 1], rows[:, 2]
    # stem (rows 520..790): straight edges, their lean is the photo's, remove it by shearing
    sel = (r > 520) & (r < 780)
    kl, bl = np.polyfit(r[sel], lo[sel], 1)
    kr, br = np.polyfit(r[sel], hi[sel], 1)
    lean = (kl + kr) / 2
    # head ellipse from the clean boundary: top/upper rows both sides, left edge to the stem
    hsel = r < 190
    pts = [(lo[i], r[i]) for i in np.nonzero(hsel)[0]] + [(hi[i], r[i]) for i in np.nonzero(hsel)[0]]
    pts += [(lo[i], r[i]) for i in np.nonzero((r >= 190) & (r < 215))[0]]
    P = np.array(pts, float)
    # head = ellipse, centre and radii read off the mask by hand (the lower right of the head is hidden by the tip)
    cx, cy, ax, by = 292.0, 275.0, 200.0, 210.0
    s = head_w / (2 * ax)                      # cm per px
    zt, zb = cy - by, r.max() + 10
    out = []
    for rr in np.arange(zt + 1, zb, 4):
        t = (rr - cy) / by
        if abs(t) < 1:
            hl, hr = cx - ax * np.sqrt(1 - t * t), cx + ax * np.sqrt(1 - t * t)
        else:
            hl, hr = 1e9, -1e9
        sl, sr = kl * rr + bl, kr * rr + br
        sl, sr = sl - lean * (rr - cy), sr - lean * (rr - cy)    # derotate the stem
        up = max(0.0, cy + 0.3 * by - rr)                   # above the head centre the stem edges curve in and vanish
        sl, sr = sl + up * up / 110.0, sr - up * up / 110.0
        L = smin(np.array([hl]), np.array([sl]), 90.0)[0]
        R = -smin(np.array([-hr]), np.array([-sr]), 90.0)[0]
        if rr > r.max() - 30:                  # rounded stem bottom
            q = (rr - (r.max() - 30)) / 40.0
            sh = np.sqrt(max(0.0, 1 - q * q))
            m_ = (L + R) / 2
            L, R = m_ - (R - L) / 2 * sh, m_ + (R - L) / 2 * sh
        out.append([round(float(-(rr - cy) * s), 4), round(float(((L + R) / 2 - cx) * s), 4), round(float((R - L) / 2 * s), 4)])
    print("pod: ellipse a,b px", round(ax), round(by), "cm/px", round(s, 5), "height cm", round((zb - zt) * s, 2),
          "lean deg", round(float(np.degrees(np.arctan(lean))), 1))
    return out


if __name__ == "__main__" and "pod" in sys.argv:
    prof = json.load(open("tools/render/profiles.json"))
    prof["pod"] = pod_profile()
    json.dump(prof, open("tools/render/profiles.json", "w"))
