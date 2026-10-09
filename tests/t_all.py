import sys, time, traceback; sys.path.insert(0,'.'); sys.path.insert(0,'tests')
from run_one import *
only = sys.argv[1:]
for key, spec in REGISTRY.items():
    if only and key not in only: continue
    t=time.time()
    try:
        kw = {}
        if key=='lpda': kw=dict(f_mhz=21.0,f_lo=14.0,f_hi=30.0)
        if key=='discone': kw=dict(f_mhz=500,f_lo=100,f_hi=1000)
        run(key, tune=True, **kw)
    except Exception as e:
        print(f"{key:12s} FAILED {type(e).__name__}: {e}")
        traceback.print_exc(limit=4)
