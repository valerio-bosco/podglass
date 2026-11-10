"""IoU of our render vs the reference mask; optional row/col window. Saves an overlay (red = only ours, green = only reference)."""
import sys
import numpy as np
from PIL import Image
def run(view, ours_dir="/tmp/claude-1000/m7/ours", rows=None, cols=None, tag=""):
    sf = np.asarray(Image.open(f"/tmp/claude-1000/m7/mask-{view}.png")) > 127
    ou = np.asarray(Image.open(f"{ours_dir}/{view}.png").convert("RGBA"))[..., 3] > 127
    win = np.zeros_like(sf)
    r0, r1 = rows or (0, sf.shape[0]); c0, c1 = cols or (0, sf.shape[1])
    win[r0:r1, c0:c1] = True
    a, b = sf & win, ou & win
    iou = (a & b).sum() / max((a | b).sum(), 1)
    ys, xs = np.nonzero(a); yo, xo = np.nonzero(b)
    ov = np.zeros(sf.shape + (3,), np.uint8)
    ov[a & b] = (200, 200, 200); ov[b & ~a] = (255, 0, 0); ov[a & ~b] = (0, 255, 0)
    Image.fromarray(ov).resize((sf.shape[1] // 2, sf.shape[0] // 2)).save(f"/tmp/claude-1000/m7/ov-{view}{tag}.png")
    print(f"{view}{tag}: IoU {iou:.3f}  ref bbox x {xs.min()}-{xs.max()} y {ys.min()}-{ys.max()}  ours x {xo.min()}-{xo.max()} y {yo.min()}-{yo.max()}")
if __name__ == "__main__":
    v = sys.argv[1]
    rows = tuple(map(int, sys.argv[2].split(":"))) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    cols = tuple(map(int, sys.argv[3].split(":"))) if len(sys.argv) > 3 and sys.argv[3] != "-" else None
    run(v, ours_dir=sys.argv[5] if len(sys.argv) > 5 else "/tmp/claude-1000/m7/ours", rows=rows, cols=cols, tag=sys.argv[4] if len(sys.argv) > 4 else "")
