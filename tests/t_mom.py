import sys, time, math
sys.path.insert(0, ".")
import numpy as np
from antennacalc.mom import *
f = 14.2e6; lam = C0/f
def dip(Lfrac, a=1e-3, n=21, ground=Ground()):
    st = Structure(ground=ground)
    h = Lfrac*lam/2
    st.add((0,0,-h),(0,0,0),a,nseg=n//2+0, ) if False else None
    return st
for Lf in (0.45,0.47,0.5):
    st = Structure()
    h = Lf*lam/2
    st.add((-h,0,0),(0,0,0),1e-3,nseg=10); st.add((0,0,0),(h,0,0),1e-3,nseg=10)
    st.sources.append(Source(0,1.0))
    m = Model(st, lam/20)
    t=time.time(); s = solve(m, f); 
    th = np.linspace(0,math.pi,181); ph = np.full_like(th, math.pi/2)
    et,ep = far_field(s, th, ph)
    U = radiation_intensity(s, et, ep)
    # integrate over sphere using symmetric in phi (dipole along x → not axisymmetric) do full grid
    T,P = np.meshgrid(np.linspace(0,math.pi,91), np.linspace(0,2*math.pi,181), indexing='ij')
    et,ep = far_field(s,T,P); U = radiation_intensity(s,et,ep)
    prad = np.sum(U*np.sin(T))*(math.pi/90)*(2*math.pi/180)
    print(Lf, "Zin", np.round(s.zin[0],1), "Pin", s.pin, "Prad", prad, "gain dBi", 10*math.log10(4*math.pi*U.max()/s.pin), time.time()-t)
# monopole on perfect ground
st = Structure(ground=Ground("perfect"))
st.add((0,0,0),(0,0,0.235*lam),1e-3,nseg=12)
st.sources.append(Source(0,0.0))
m = Model(st, lam/20); s = solve(m,f); print("mono Z", s.zin[0])
T,P = np.meshgrid(np.linspace(0,math.pi/2,46), np.linspace(0,2*math.pi,37), indexing='ij')
et,ep = far_field(s,T,P); U = radiation_intensity(s,et,ep)
prad = np.sum(U*np.sin(T))*(math.pi/2/45)*(2*math.pi/36)
print("mono gain", 10*math.log10(4*math.pi*U.max()/s.pin), "eff", prad/s.pin)
# dipole 10 m high, real ground
st = Structure(ground=Ground("real",0.005,13)); h=0.5*lam/2*0.97
st.add((-h,0,10),(0,0,10),1e-3,nseg=10); st.add((0,0,10),(h,0,10),1e-3,nseg=10)
st.sources.append(Source(0,1.0)); m=Model(st,lam/20); s=solve(m,f); print("dip10m", s.zin[0])
