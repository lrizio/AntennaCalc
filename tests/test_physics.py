"""Physics and smoke tests.  Run:  python -m pytest tests -q"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pytest
from antennacalc import models, engine
from antennacalc.common import BAND_BY_LABEL, GROUND_BY_LABEL
from antennacalc.design import REGISTRY, Requirements
from antennacalc.mom import *


def _req(spec, band="20 m (14.0-14.35 MHz)", **kw):
    b = BAND_BY_LABEL[band]
    r = Requirements(f_mhz=b[3], f_lo=b[1], f_hi=b[2], band_label=band, radius=1e-3, height=spec.height_default)
    r.ratio, r.coax_key, r.coax_len = spec.feed_ratio, spec.feed_coax, spec.feed_len
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_half_wave_dipole_free_space():
    f = 14.2e6; lam = C0 / f
    st = Structure()
    h = 0.5 * lam / 2
    st.add((-h, 0, 0), (0, 0, 0), 1e-3, nseg=10); st.add((0, 0, 0), (h, 0, 0), 1e-3, nseg=10)
    st.sources.append(Source(0, 1.0))
    m = Model(st, lam / 20)
    s = solve(m, f)
    z = s.zin[0]
    assert 70 < z.real < 90 and 35 < z.imag < 55          # NEC: ~ 80 + j45 for a/lambda = 5e-5
    T, P = np.meshgrid(np.linspace(0, math.pi, 91), np.linspace(0, 2 * math.pi, 181), indexing="ij")
    et, ep = far_field(s, T, P)
    u = radiation_intensity(s, et, ep)
    g = 10 * math.log10(4 * math.pi * u.max() / s.pin)
    assert abs(g - 2.15) < 0.15
    prad = np.sum(u * np.sin(T)) * (math.pi / 90) * (2 * math.pi / 180)
    assert abs(prad / s.pin - 1) < 0.03                    # lossless: radiated = input power


def test_monopole_over_perfect_ground_is_half_a_dipole():
    f = 14.2e6; lam = C0 / f
    st = Structure(ground=Ground("perfect"))
    st.add((0, 0, 0), (0, 0, 0.235 * lam), 1e-3, nseg=12)
    st.sources.append(Source(0, 0.0))
    s = solve(Model(st, lam / 20), f)
    st2 = Structure()
    st2.add((-0.235 * lam, 0, 0), (0, 0, 0), 1e-3, nseg=12); st2.add((0, 0, 0), (0.235 * lam, 0, 0), 1e-3, nseg=12)
    st2.sources.append(Source(0, 1.0))
    s2 = solve(Model(st2, lam / 20), f)
    assert abs(s.zin[0] - s2.zin[0] / 2) < 3.0


def test_tuned_dipole_resonant_and_swr():
    spec = REGISTRY["dipole"]; ex = {"shape": "flat"}
    req = _req(spec)
    sc = engine.tune(spec, req, ex, {})
    res = engine.evaluate(spec, req, ex, sc)
    assert abs(res.metrics["z_ant"].imag) < 1.0
    assert res.metrics["swr_f0"] < 1.6


def test_yagi_gain_grows_with_elements():
    spec = REGISTRY["yagi"]
    g = []
    for n in (3, 8, 14):
        req = _req(spec, ground=GROUND_BY_LABEL["Free space (no ground)"], spw=14)
        ex = {"n": n, "pol": "H", "droop": 0.0}
        sc = engine.tune(spec, req, ex, {})
        r = engine.evaluate(spec, req, ex, sc, do_sweep=False)
        g.append(r.metrics["gain_dbi"])
    assert 7.0 < g[0] < 9.0 and 12.0 < g[1] < 14.5 and 14.5 < g[2] < 17.5
    assert g[0] < g[1] < g[2]


def test_gain_target_picks_element_count():
    spec = REGISTRY["yagi"]
    req = _req(spec, target_gain=11.0)
    ex, notes = engine.auto_design(spec, req, {"n": 3, "pol": "H", "droop": 0.0}, "free")
    assert 5 <= ex["n"] <= 9
    req.max_size = 3.0
    ex, notes = engine.auto_design(spec, req, {"n": 3, "pol": "H", "droop": 0.0}, "free")
    assert ex["n"] == 2 and notes


def test_efhw_high_impedance_with_transformer():
    spec = REGISTRY["efhw"]; ex = {"fund": None, "end_h": 10.0, "cp": 0.05}
    req = _req(spec)
    sc = engine.tune(spec, req, ex, {})
    res = engine.evaluate(spec, req, ex, sc, do_sweep=False)
    assert res.metrics["z_ant"].real > 800
    assert res.metrics["swr_f0"] < 3.0


def test_helix_is_circularly_polarised():
    spec = REGISTRY["helix"]
    req = _req(spec, "70 cm (430-440 MHz)")
    ex = {"n": 5, "sense": "R"}
    res = engine.evaluate(spec, req, ex, {}, do_sweep=False)
    pk = res.pattern.comp_peak
    assert pk["rhcp"] > pk["lhcp"] + 10 and res.pattern.pol.startswith("Circular (RHCP")


def test_dish_gain_formula():
    spec = REGISTRY["dish"]
    req = _req(spec, "13 cm (2300-2450 MHz)")
    ex = {"dia": 1.0, "fd": 0.4, "eta": 0.55, "el": 0.0}
    res = engine.evaluate(spec, req, ex, {})
    lam = C0 / 2.4e9
    assert abs(res.metrics["gain_dbi"] - 10 * math.log10(0.55 * (math.pi / lam) ** 2)) < 0.3


@pytest.mark.parametrize("key", [k for k in REGISTRY if k not in ("rhombic", "vbeam", "helix", "discone", "lpda", "duck")])
def test_every_design_runs(key):
    spec = REGISTRY[key]
    ex = {p.key: p.default for p in spec.params}
    band = spec.band_default if spec.band_default and spec.band_default != "Custom range" else "20 m (14.0-14.35 MHz)"
    req = _req(spec, band)
    sc = engine.tune(spec, req, ex, {}) if not spec.analytic else {}
    res = engine.evaluate(spec, req, ex, sc)
    m = res.metrics
    assert np.isfinite(m["gain_dbi"]) and np.isfinite(m["swr_f0"])
    assert res.design.dims
