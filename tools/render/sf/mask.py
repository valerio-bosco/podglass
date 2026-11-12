"""Masks of the reference shots: model = bright or unsaturated pixels, background = dark blue vignette."""
import sys
import numpy as np
from PIL import Image
R = "/home/voodoo/Projects/podglass/assets/reference/shots"
OUTDIR = "/tmp/claude-1000/m7"   # masks of every view are already there

def mask(name):
    a = np.asarray(Image.open(f"{R}/{name}.png").convert("RGB")).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    bg = (b - r > 12) & (b - g > 12) & (a.mean(axis=2) < 110)    # blue-ish dark background
    dark = a.max(axis=2) < 35                                    # vignette corners
    return ~(bg | dark)

if __name__ == "__main__":
    for n in sys.argv[1:]:
        m = mask(n)
        ys, xs = np.nonzero(m)
        print(n, m.shape, "bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())
        Image.fromarray((m * 255).astype(np.uint8)).save(f"{OUTDIR}/mask-{n}.png")
