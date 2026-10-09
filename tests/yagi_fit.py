import sys, math, time
sys.path.insert(0,'.')
import numpy as np
from scipy.optimize import minimize
from antennacalc import mom
from antennacalc.mom import *
lam=1.0; f=C0  # lambda=1 m -> f = c
a=0.003  # radius 3mm in 1 m wavelength (typical 0.006λ dia)
def layout(N,p):
    Lr,sr,a0,a1,ag,amax,L1,taper,Lmin,Ld=p
    els=[("R",-sr,Lr),("D",0.0,Ld)]
    y=0.0
    for k in range(N-2):
        sp = a0 if k==0 else min(amax, a1+ag*(k-1))
        y+=sp
        els.append(("P",y,max(Lmin,L1-taper*k)))
    return els
def evalN(N,p,detail=False):
    st=Structure()
    for nm,y,L in layout(N,p):
        w0=st.add((-L/2,y,0),(0,y,0),a,min_seg=5); st.add((0,y,0),(L/2,y,0),a,min_seg=5)
        if nm=="D": st.sources.append(Source(w0,1.0))
    m=Model(st,lam/14)
    s=solve(m,f)
    th=np.array([math.pi/2]); 
    # forward = +y: theta=90, phi=90 ; back phi=270
    def U(phi):
        et,ep=far_field(s,np.array([math.pi/2]),np.array([math.radians(phi)])); return float(radiation_intensity(s,et,ep)[0])
    gf=4*math.pi*U(90)/s.pin; fb=U(90)/max(U(270),1e-12)
    # worst-case rear
    rear=max(U(90+d) for d in (110,130,150,170,180,190,210,230,250))
    if detail: return 10*math.log10(gf), 10*math.log10(U(90)/rear), s.zin[0]
    return 10*math.log10(gf), 10*math.log10(U(90)/rear), s.zin[0]
def obj(x,N,base):
    p=np.array(base)*x
    g,fb,z=evalN(N,p)
    return -g-0.12*min(fb,22)+max(0,10-z.real)*0.1+abs(z.imag)/60
base=[0.49,0.20,0.14,0.20,0.04,0.34,0.445,0.004,0.39,0.465]
import sys as _s
NS=[int(x) for x in _s.argv[1:]] or [4,8,14]
for N in NS:
    t=time.time()
    r=minimize(obj,np.ones(len(base)),args=(N,base),method="Nelder-Mead",options=dict(maxfev=400,xatol=1e-3,fatol=1e-3,initial_simplex=np.vstack([np.ones(len(base))]+[np.ones(len(base))+np.eye(len(base))[i]*0.05 for i in range(len(base))])))
    p=np.array(base)*r.x
    g0=evalN(N,base); g1=evalN(N,p)
    print(N,"base",np.round(g0[:2],2),"opt",np.round(g1[:2],2),np.round(g1[2],1),"t",round(time.time()-t))
    print("  p=",np.round(p,4).tolist())
    lay=layout(N,p); print("  boom",round(lay[-1][1]-lay[0][1],2),[ (round(y-lay[0][1],2),round(L,3)) for n,y,L in lay])

if len(sys.argv)>1 and sys.argv[1]=="small":
    pass
