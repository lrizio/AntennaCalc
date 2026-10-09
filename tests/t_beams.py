import sys,time; sys.path.insert(0,'.'); sys.path.insert(0,'tests')
from run_one import *
t=time.time()
r=run('lpda', ex=None, tune=False, f_mhz=21.0, f_lo=14.0, f_hi=30.0)
print('LPDA sweep SWR', [round(float(x),2) for x in r.swr_rig[::4]], 'N', r.model.N, time.time()-t)
print([ (d.item, round(d.length_m,2) if d.length_m else None) for d in r.design.dims][:5])
for key in ('moxon','yagi'):
    spec=REGISTRY[key]; ex={p.key:p.default for p in spec.params}; req=default_req(spec)
    sc=engine.tune(spec,req,ex,{})
    r0=engine.evaluate(spec,req,ex,sc,do_sweep=False)
    t=time.time()
    sc2=engine.optimize(spec,req,ex,sc,maxiter=40)
    sc2=engine.tune(spec,req,ex,sc2)
    r1=engine.evaluate(spec,req,ex,sc2,do_sweep=False)
    for lab,r in (('before',r0),('after',r1)):
        m=r.metrics; print(key,lab,'G',round(m['gain_dbi'],2),'FB',m['fb'],'FR',m['fr'],'Z',m['z_ant'])
    print(key,'opt time',time.time()-t, {k:round(v,3) for k,v in sc2.items()})
