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
