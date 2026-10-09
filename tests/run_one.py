import sys, time, math
sys.path.insert(0, ".")
from antennacalc import models
from antennacalc.design import *
from antennacalc import engine
from antennacalc.common import *
def default_req(spec, band_label="20 m (14.0-14.35 MHz)", **kw):
    b = BAND_BY_LABEL[band_label]
    r = Requirements(f_mhz=b[3], f_lo=b[1], f_hi=b[2], band_label=band_label, radius=1e-3, height=spec.height_default)
    r.ratio = spec.feed_ratio; r.coax_key=spec.feed_coax; r.coax_len=spec.feed_len; r.lmatch=spec.lmatch_default
    if spec.ground_default: r.ground = GROUND_BY_LABEL[spec.ground_default]
    for k,v in kw.items(): setattr(r,k,v)
    return r
def run(key, band="20 m (14.0-14.35 MHz)", ex=None, tune=True, **kw):
    spec = REGISTRY[key]; ex = ex or {}
    if band == '20 m (14.0-14.35 MHz)' and spec.band_default: band = spec.band_default
    for p in spec.params:
        ex.setdefault(p.key, p.default)
    req = default_req(spec, band, **kw)
    t=time.time()
    sc = {}
    if tune: sc = engine.tune(spec, req, ex, sc)
    res = engine.evaluate(spec, req, ex, sc)
    m = res.metrics
    print(f"{key:12s} {band[:6]} tune={ {k:round(v,3) for k,v in sc.items()} } Zant={m['z_ant']:.1f} SWR={m['swr_f0']:.2f} G={m['gain_dbi']:.2f}dBi eff={m['efficiency']:.2f} FB={m['fb']} el={m['takeoff']:.0f} pol={m['pol']} N={res.model.N if res.model else '-'} t={time.time()-t:.1f}s")
    for w in res.design.warnings: print("   WARN", w)
    return res
if __name__ == "__main__":
    run(sys.argv[1], *(sys.argv[2:3]))
