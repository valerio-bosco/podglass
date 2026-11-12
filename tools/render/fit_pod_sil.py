"""Second stage of the pod body fit: tune the sdf parameters (pod_shape.sdf, already near the optimum from fit_pod.py) directly
on the nine reference silhouettes, GPU only (CuPy, one fused ray-march kernel per view).
  /home/voodoo/.local/share/podglass-gpu/py tools/render/fit_pod_sil.py TIPDIR [--write]
TIPDIR holds sfrender silhouettes of the silicone tips alone (--hide everything else), which are unioned with the body.
Same camera model as tools/render/sf/sfrender.py (FOV 6 deg vertical, 2796x1440)."""
import json, math, os, sys
import cupy as cp
import numpy as np
from PIL import Image
from scipy.optimize import minimize
from cupyx.scipy.ndimage import binary_fill_holes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_shape as ps

TIPDIR = sys.argv[1]
D = json.load(open(ps.PATH))
S = 0.000996
O = np.array([0, -0.000315, 0.000157])
CASE_T, CASE_D = np.array([0, 0.0014, 0.0038]), 0.08
POD_T, POD_D = np.array([-0.0018, -0.0002, 0.0062]), 0.035
DIRS = {"front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0), "left": (-1, 0, 0), "pod-outer": (-1, 0, 0),
        "pod-front": (0, -1, 0), "pod-back": (0, 1, 0), "pod-3q": (-0.6, -1, 0.3), "pod-innerfront": (0.5, -1, 0)}
WIN = {"front": (0, 470, 0, 1398), "back": (0, 480, 1400, 2796), "left": (0, 670, 1540, 2796), "right": (0, 700, 0, 1295),
       "pod-outer": (0, 1400, 960, 2000), "pod-front": (0, 1100, 0, 2000), "pod-back": (0, 1150, 660, 1800),
       "pod-innerfront": (0, 1090, 0, 2040), "pod-3q": (0, 780, 0, 2150)}
DK = {"pod-back": 0.975}
ROOT = np.array(D["root"])
ST = 4
F = 720 / math.tan(math.radians(3))

SRC = r"""
extern "C" __device__ float body_sdf(const float* P, float x, float y, float z) {
    float hc0=P[0],hc1=P[1],hc2=P[2],a0=P[3],a1=P[4],a2=P[5],r0=P[6],r1=P[7],r2=P[8];
    float sa0=P[9],sa1=P[10],sa2=P[11],ss0=P[12],ss1=P[13],sr0=P[14],sr1=P[15],zt=P[16],zb=P[17],rr=P[18],k=P[19],p=P[20],et=P[21];
    float ca=cosf(r0),sa_=sinf(r0),cb=cosf(r1),sb=sinf(r1),cc=cosf(r2),sc=sinf(r2);
    float R00=ca*cb,R01=ca*sb*sc-sa_*cc,R02=ca*sb*cc+sa_*sc,R10=sa_*cb,R11=sa_*sb*sc+ca*cc,R12=sa_*sb*cc-ca*sc,R20=-sb,R21=cb*sc,R22=cb*cc;
    float dx=x-hc0,dy=y-hc1,dz=z-hc2;
    float lx=R00*dx+R10*dy+R20*dz, ly=R01*dx+R11*dy+R21*dz, lz=R02*dx+R12*dy+R22*dz;
    float uz=lz/a2, eg=1.0f+et*uz, ux=lx/(a0*eg), uy=ly/(a1*eg);
    float ax=fabsf(ux)+1e-9f, ay=fabsf(uy)+1e-9f, az=fabsf(uz)+1e-9f;
    float N=powf(ax,p)+powf(ay,p)+powf(az,p);
    float k0=powf(N,1.0f/p), gk=powf(N,1.0f/p-1.0f);
    float gx=powf(ax,p-1.0f)/a0, gy=powf(ay,p-1.0f)/a1, gz=powf(az,p-1.0f)/a2;
    float k1=gk*sqrtf(gx*gx+gy*gy+gz*gz)+1e-12f;
    float dh=k0*(k0-1.0f)/k1;
    float ex=x-(sa0+ss0*(z-sa2)), ey=y-(sa1+ss1*(z-sa2));
    float vx=ex/sr0, vy=ey/sr1, f=sqrtf(vx*vx+vy*vy)+1e-12f;
    float g=sqrtf((vx/sr0)*(vx/sr0)+(vy/sr1)*(vy/sr1))+1e-12f;
    float dxy=f*(f-1.0f)/g;
    float a=dxy+rr, b=fmaxf(zb+rr-z, z-(zt-rr));
    float ds=fminf(fmaxf(a,b),0.0f)+sqrtf(fmaxf(a,0.0f)*fmaxf(a,0.0f)+fmaxf(b,0.0f)*fmaxf(b,0.0f))-rr;
    float h=fminf(fmaxf(0.5f+0.5f*(ds-dh)/k,0.0f),1.0f);
    return ds*(1.0f-h)+dh*h-k*h*(1.0f-h);
}
extern "C" __global__ void sil(const float* P, const float* cam, float* out, int nr, int nc, int r0, int c0, int st, float f) {
    int j = blockIdx.x * blockDim.x + threadIdx.x, i = blockIdx.y * blockDim.y + threadIdx.y;
    if (i >= nr || j >= nc) return;
    float u = (c0 + j * st - 1398.0f) / f, v = (720.0f - (r0 + i * st)) / f;
    // cam: eye(3) xa(3) ya(3) za(3) t0 dt n
    float dx = cam[3]*u + cam[6]*v - cam[9], dy = cam[4]*u + cam[7]*v - cam[10], dz = cam[5]*u + cam[8]*v - cam[11];
    int n = (int)cam[14];
    float dm = 1e9f;
    for (int s = 0; s < n; ++s) {
        float t = cam[12] + s * cam[13];
        float wx = cam[0] + dx*t, wy = cam[1] + dy*t, wz = cam[2] + dz*t;      // L-pod frame; the R pod is its mirror
        float d = body_sdf(P, wx, wy, wz);
        if (cam[15] > 0.5f) d = fminf(d, body_sdf(P, -(wx + 2.0f * cam[16]), wy, wz));
        dm = fminf(dm, d);
    }
    out[i * nc + j] = dm;
}
"""
MOD = cp.RawModule(code=SRC)
SIL = MOD.get_function("sil")


def camera(view):
    pod = view.startswith("pod-")
    T, Dd = (POD_T, POD_D) if pod else (CASE_T, CASE_D)
    d = np.array(DIRS[view], float); d /= np.linalg.norm(d)
    eye = (T + d * Dd * DK.get(view, 1.0) - O) / S
    tgt = (T - O) / S
    za = eye - tgt; za /= np.linalg.norm(za)
    xa = np.cross([0, 0, 1], za); xa /= np.linalg.norm(xa)
    ya = np.cross(za, xa)
    eye_p = eye - ROOT
    pairs = 0 if pod else 1
    c = ROOT + np.array([0.1, 0.3, -0.5]) - eye
    dist = float(-(za @ c))
    n = 150 if pod else 220
    span = 6.0 if pod else 11.0
    return np.concatenate([eye_p, xa, ya, za, [dist - span / 2, span / n, n, pairs, ROOT[0]]]).astype(np.float32)


VIEWS = {}
for v, (r0, r1, c0, c1) in WIN.items():
    m = binary_fill_holes(cp.asarray(np.asarray(Image.open(f"/tmp/claude-1000/m7/mask-{v}.png")) > 127))[r0:r1:ST, c0:c1:ST]
    tp = cp.asarray(np.asarray(Image.open(f"{TIPDIR}/{v}.png").convert("RGBA"))[..., 3] > 127)[r0:r1:ST, c0:c1:ST]
    VIEWS[v] = (cp.asarray(camera(v)), m.astype(cp.float32), tp.astype(cp.float32), r0, c0)
EPS = 0.012


def ious(vec, soft=True):
    P = cp.asarray(np.asarray(vec, np.float32))
    res = {}
    for v, (cam, m, tp, r0, c0) in VIEWS.items():
        nr, nc = m.shape
        out = cp.empty((nr, nc), cp.float32)
        SIL(((nc + 15) // 16, (nr + 15) // 16), (16, 16), (P, cam, out, np.int32(nr), np.int32(nc), np.int32(r0), np.int32(c0), np.int32(ST), np.float32(F)))
        s = 1 / (1 + cp.exp(out / EPS)) if soft else (out < 0).astype(cp.float32)
        s = 1 - (1 - s) * (1 - tp)
        res[v] = float((s * m).sum() / (s + m - s * m).sum())
    return res


LO = np.array([-1, -1, -1, .3, .3, .3, -3.2, -3.2, -3.2, -1, -1, -3, -1, -1, .15, .15, -1.2, -2.3, .02, .02, 2.0, -.5])
HI = np.array([1, 1, 1.2, 1.5, 1.5, 1.5, 3.2, 3.2, 3.2, 1, 1.5, 0, 1, 1, .5, .5, 0.5, -1.7, .3, 1.5, 4.5, .5])


def loss(vec):
    v = np.asarray(vec)
    pen = float(np.sum(np.maximum(LO - v, 0) ** 2 + np.maximum(v - HI, 0) ** 2)) * 1e3
    r = ious(np.clip(v, LO, HI))
    vals = np.array(list(r.values()))
    return float((1 - vals).mean() + 2.0 * (1 - vals).max() + pen)       # mean and worst view


v0 = np.array(ps.pack(D["body"]))
print("start", {k: round(x, 3) for k, x in ious(v0, False).items()}, flush=True)
for rnd in range(int(os.environ.get("ROUNDS", 3))):
    r = minimize(loss, v0, method="Powell", options=dict(xtol=1e-4, ftol=1e-7, maxfev=int(os.environ.get("MAXFEV", 1500))))
    v0 = np.clip(r.x, LO, HI)
    print(rnd, r.fun, {k: round(x, 3) for k, x in ious(v0, False).items()}, flush=True)
if "--write" in sys.argv:
    D["body"] = ps.unpack([float(t) for t in v0])
    json.dump(D, open(ps.PATH, "w"), indent=1)
    print("written")
