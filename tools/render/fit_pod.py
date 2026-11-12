"""Fit the few parameters of the implicit pod body (pod_shape.sdf) to the traced sections of profiles_pod.json ("rows").
GPU only (CuPy):  /home/voodoo/.local/share/podglass-gpu/py tools/render/fit_pod.py [--write]
The loss is the soft-occupancy mismatch on a voxel grid: smooth by construction, the fit cannot add ripples."""
import json, math, os, sys
import cupy as cp
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_shape as ps

PATH = ps.PATH
D = json.load(open(PATH))
rows = cp.asarray(np.array(ps.smooth_rows(D["rows"], 10)))          # z cx cy hx hy psi n, top to bottom
H = float(os.environ.get('H', 0.025))
gx = cp.arange(-1.15, 1.25, H); gy = cp.arange(-0.95, 1.1, H); gz = cp.arange(-2.1, 1.0, H)
X, Y, Z = cp.meshgrid(gx, gy, gz, indexing="ij")
zr = rows[::-1, 0]


def interp(col):
    return cp.interp(Z, zr, rows[::-1, col])


cx, cy, hx, hy, psi, n = (interp(c) for c in range(1, 7))
dx, dy = X - cx, Y - cy
c_, s_ = cp.cos(psi), cp.sin(psi)
u = dx * c_ + dy * s_
v = -dx * s_ + dy * c_
f = (cp.abs(u) / hx) ** n + (cp.abs(v) / hy) ** n
OCC = ((f <= 1) & (Z <= rows[0, 0]) & (Z >= rows[-1, 0])).astype(cp.float32)
print("grid", OCC.shape, "occ vox", int(OCC.sum()))
EPS = 0.02


# one fused CUDA kernel = pod_shape.sdf (keep in sync) + soft occupancy error: a single launch per evaluation
KER = cp.ElementwiseKernel(
    "float32 x, float32 y, float32 z, float32 occ, raw float32 P, float32 eps", "float32 err, float32 inside",
    r"""
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
    float d=ds*(1.0f-h)+dh*h-k*h*(1.0f-h);
    float o=1.0f/(1.0f+expf(d/eps));
    err=(o-occ)*(o-occ); inside=d<0.0f?1.0f:0.0f;
    """, "pod_sdf")
Xf, Yf, Zf = (a.astype(cp.float32).ravel() for a in (X, Y, Z))
Of = OCC.ravel()


def loss(vec, hard=False):
    P = cp.asarray(np.asarray(ps.pack(ps.unpack(list(vec))), np.float32))
    e, ins = KER(Xf, Yf, Zf, Of, P, np.float32(EPS))
    if hard:
        m = ins > 0
        return float((m & (Of > 0)).sum() / (m | (Of > 0)).sum())
    return float(e.mean() * 1e3)


init = dict(hc=[0.12, 0.04, 0.2], ha=[0.85, 0.85, 0.7], hr=[0.0, 0.0, 0.0], sa=[0.0, 0.6, -1.0], ss=[0.0, -0.14],
            sr=[0.27, 0.285], sz=[-0.3, -1.99], rr=0.14, k=0.3, hp=2.0, et=0.0)
if D.get('body') and 'hp' in D['body']:
    init = D['body']
v0 = np.array(ps.pack(init))
LO = np.array([-1, -1, -1, .3, .3, .3, -3.2, -3.2, -3.2, -1, -1, -3, -1, -1, .15, .15, -1.2, -2.3, .02, .02, 2.0, -.5])
HI = np.array([1, 1, 1.2, 1.5, 1.5, 1.5, 3.2, 3.2, 3.2, 1, 1.5, 0, 1, 1, .5, .5, 0.5, -1.7, .3, 1.5, 4.5, .5])
_loss = loss


def loss(vec, hard=False):
    v = np.asarray(vec)
    pen = float(np.sum(np.maximum(LO - v, 0) ** 2 + np.maximum(v - HI, 0) ** 2)) * 1e3
    return _loss(np.clip(v, LO, HI), hard) + (0 if hard else pen)


rng = np.random.default_rng(int(os.environ.get("SEED", 1)))
best = (loss(v0), v0)
for st in range(int(os.environ.get("STARTS", 24))):
    s0 = best[1].copy() if st % 3 == 0 else v0.copy()
    sc = np.array([.15, .15, .2, .15, .15, .15, .6, .6, .6, .1, .1, .2, .05, .05, .03, .03, .1, .05, .03, .15, .5, .1])
    s0 = s0 + rng.normal(size=s0.shape) * sc * (0.5 if st % 3 == 0 else 1)
    r = minimize(loss, s0, method="Powell", options=dict(xtol=1e-3, ftol=1e-6, maxfev=2500))
    if r.fun < best[0]:
        best = (r.fun, r.x)
    print("start", st, round(r.fun, 3), "best", round(best[0], 3), flush=True)
v0 = best[1]
for rnd in range(2):
    r = minimize(loss, v0, method="Powell", options=dict(xtol=1e-4, ftol=1e-8, maxfev=4000))
    v0 = r.x
    print(rnd, r.fun, "IoU3D", loss(v0, True))
v0 = np.clip(v0, LO, HI)
B = ps.unpack([float(t) for t in v0])
print(json.dumps(B, indent=1))
if "--write" in sys.argv:
    D["body"] = B
    json.dump(D, open(PATH, "w"), indent=1)
    print("written")
if "--diag" in sys.argv:
    P = cp.asarray(np.asarray(ps.pack(B), np.float32))
    e, ins = KER(Xf, Yf, Zf, Of, P, np.float32(EPS))
    ins = (ins > 0).reshape(X.shape); o = OCC > 0
    for k_ in range(0, X.shape[2], 4):
        sl = slice(k_, k_ + 4)
        print(round(float(gz[k_]), 2), "occ", int(o[..., sl].sum()), "fp", int((ins & ~o)[..., sl].sum()), "fn", int((~ins & o)[..., sl].sum()))
