"""Copy every built-in MoM design into a Wire Editor drawing and check the copy analyses to the same result.

Run from the AntennaCalc folder:  python tests/copy_to_editor_test.py [key ...]
"""
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from antennacalc import custom, engine, models  # noqa: F401  (models registers the specs)
from antennacalc.custom import Drawing
from antennacalc.design import REGISTRY
from run_one import default_req
CUSTOM_DEFAULTS = {"lpda": (14.0, 30.0, 21.0), "discone": (100.0, 1000.0, 500.0)}   # as in ui/inputs.py


def check(key, tune=False):
    spec = REGISTRY[key]
    if spec.analytic or key == "custom":
        return None
    ex = {p.key: p.default for p in spec.params}
    band = spec.band_default or "20 m (14.0-14.35 MHz)"
    req = default_req(spec, band)
    if key in CUSTOM_DEFAULTS:                            # wide-range designs set their own frequency span
        req.f_lo, req.f_hi, req.f_mhz = CUSTOM_DEFAULTS[key]
    sc = engine.tune(spec, req, ex, {}) if tune else {}
    res = engine.evaluate(spec, req, ex, sc, do_bands=False)
    if res.design.structure is None:
        return None
    dr, notes, req.ground = custom.drawing_from_spec(spec, req, ex, sc)
    dr = Drawing.from_dict(dr.to_dict())                  # survives a save / open round trip
    probs = dr.problems(req.ground.kind != "free")
    cspec = REGISTRY["custom"]
    cres = engine.evaluate(cspec, req, {"drawing": dr.to_dict(), "tune": "none"}, {}, do_bands=False)
    za, zc = res.metrics["z_ant"], cres.metrics["z_ant"]
    ga, gc = res.metrics["gain_dbi"], cres.metrics["gain_dbi"]
    return dict(mode=res.design.mode, za=za, zc=zc, ga=ga, gc=gc, probs=probs, notes=notes,
                nw=len(dr.wires), ns=len(dr.sources), nl=len(dr.loads))


if __name__ == "__main__":
    keys = sys.argv[1:] or [k for k in REGISTRY]
    bad = 0
    for k in keys:
        t = time.time()
        try:
            r = check(k)
        except Exception as e:
            print(f"{k:14s} ERROR {type(e).__name__}: {e}")
            bad += 1
            continue
        if r is None:
            print(f"{k:14s} (closed-form, skipped)")
            continue
        dz = abs(r["zc"] - r["za"]) / max(abs(r["za"]), 1.0)
        dg = r["gc"] - r["ga"]
        flag = "OK " if dz < 0.05 and abs(dg) < 0.3 and not r["probs"] else "DIFF"
        if flag != "OK ":
            bad += 1
        print(f"{k:14s} {flag} {r['mode']:8s} w{r['nw']:3d} s{r['ns']:2d} l{r['nl']:2d}  "
              f"Z {r['za']:.1f} -> {r['zc']:.1f} ({dz * 100:.1f}%)  G {r['ga']:.2f} -> {r['gc']:.2f}  {time.time() - t:.1f}s")
        for p in r["probs"]:
            print("     PROBLEM", p)
        for n in r["notes"]:
            print("     note:", n[:110])
    print(f"\n{bad} design(s) differ or failed")
