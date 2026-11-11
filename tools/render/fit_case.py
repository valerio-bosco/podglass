"""Fit the quintic Bezier shell curves in profiles_case.json ("shell_bezier") to the traced "case_shell" table.
Run on the GPU python: /home/voodoo/.local/share/podglass-gpu/py tools/render/fit_case.py  (prints the best controls)."""
import json, cupy as cp, numpy as np
d=json.load(open('/home/voodoo/Projects/podglass-wt/case-shell/tools/render/profiles_case.json'))
r=np.array(d['case_shell']); H=4.51
m=r[:,0]<=H/2
z=r[m,0];hw=r[m,1];yh=(r[m,3]-r[m,2])/2
# also include mirrored top half averaged
zt=H-r[~m,0][::-1];
Z=cp.asarray(np.r_[z,H-r[~m,0]]);HW=cp.asarray(np.r_[hw,r[~m,1]]);YH=cp.asarray(np.r_[yh,(r[~m,3]-r[~m,2])/2])
Z=Z[::2];HW=HW[::2];YH=YH[::2]
T=cp.linspace(0,1,160)
from math import comb
Bm=cp.stack([comb(5,k)*T**k*(1-T)**(5-k) for k in range(6)])  # (6,T)  k-th control weight (t^k (1-t)^(5-k)): control k=0 is at t=1 ... we use order p0 at t=0

HWMAX,YMAX=3.003,1.1
def curves(P):
    zc,z1,z2,z3,h3,h4,x0,y3,y4,y0=[P[:,i:i+1] for i in range(10)]
    n=P.shape[0]
    one=cp.ones((n,1))
    zc_=zc
    zc_=zc
    Zc=cp.concatenate([zc,z1,z2,z3,0*one,0*one],1)
    Hc=cp.concatenate([HWMAX*one]*3+[h3,h4,x0],1)
    Yc=cp.concatenate([YMAX*one]*3+[y3,y4,y0],1)
    return Zc@Bm,Hc@Bm,Yc@Bm
def cost(P):
    zt,ht,yt=curves(P)
    pen=0
    mono=lambda a:(cp.minimum(cp.diff(a,axis=1),0)**2).sum(1)*1e7
    pen=mono(-zt)+mono(-ht)+mono(-yt)
    dh=((ht[:,:,None]-HW[None,None])**2+(zt[:,:,None]-Z[None,None])**2).min(1).sum(1)
    dy=((yt[:,:,None]-YH[None,None])**2+(zt[:,:,None]-Z[None,None])**2).min(1).sum(1)
    return dh+dy+pen
lo=cp.array([2.255,0.0,0.0,0.0, 1.0,1.0,1.75, 0.3,0.32,0.25]);hi=cp.array([2.255,3.0,3.0,0.0, 3.003,3.003,1.85, 1.1,1.1,0.3])
N=1200
P=lo+(hi-lo)*cp.random.random((N,10))
for it in range(90):
    c=cost(P);i=cp.argsort(c)[:40];el=P[i];best=el[0];sd=el.std(0)+1e-4
    if it%5==0 or it==89:print(it,float(c[i[0]]),cp.asnumpy(best).round(3))
    P=cp.clip(el[cp.random.randint(0,40,N)]+cp.random.standard_normal((N,10))*sd*0.8,lo,hi);P[0]=best
np.save('/tmp/fit_case.npy',cp.asnumpy(best))
