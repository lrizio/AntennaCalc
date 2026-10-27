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
    r.wide_sweep = spec.wide_default
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
    spec = REGISTRY["efhw"]; ex = {"fund": None, "end_h": 10.0, "tune_for": "fund"}
    req = _req(spec, wide_sweep=False)
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


# --------------------------------------------------------------------------- wire arrays (models_arrays)
def _tuned(key, band, ex):
    spec = REGISTRY[key]
    e = {p.key: p.default for p in spec.params}
    e.update(ex)
    req = _req(spec, band)
    sc = engine.tune(spec, req, e, {})
    return engine.evaluate(spec, req, e, sc)


def test_bobtail_beats_single_vertical_and_is_broadside():
    band = "40 m (7.0-7.3 MHz)"
    bob = _tuned("curtain", band, {"variant": "bobtail", "az": 0.0}).metrics
    hsq = _tuned("curtain", band, {"variant": "halfsq", "az": 0.0}).metrics
    gp = _tuned("gp", band, {"mount": "ground", "nburied": 16}).metrics
    assert bob["gain_dbi"] - gp["gain_dbi"] > 3.0                  # known 3-4 dB over a vertical
    assert bob["gain_dbi"] > hsq["gain_dbi"]
    assert abs(bob["z_ant"].imag) < 20 and bob["z_ant"].real > 500   # voltage-fed, high impedance
    assert min(bob["peak_az"] % 180, 180 - bob["peak_az"] % 180) < 8   # broadside to the top wire (north / south)


def test_curtain_direction_follows_azimuth_setting():
    m = _tuned("curtain", "40 m (7.0-7.3 MHz)", {"variant": "bobtail", "az": 90.0}).metrics
    assert abs(((m["peak_az"] - 90) + 90) % 180 - 90) < 8


def test_w8jk_is_end_fire_with_low_impedance():
    m = _tuned("w8jk", "20 m (14.0-14.35 MHz)", {}).metrics
    assert m["z_ant"].real < 25
    # lobes lie along the spacing direction (north / south for az = 0)
    assert min(m["peak_az"] % 180, 180 - m["peak_az"] % 180) < 10
    assert m["gain_dbi"] > _tuned("dipole", "20 m (14.0-14.35 MHz)", {"shape": "flat"}).metrics["gain_dbi"] + 2.0


def test_sterba_reflector_gives_front_to_back():
    b = "20 m (14.0-14.35 MHz)"
    free = _tuned("sterba", b, {"nsec": 3}).metrics
    refl = _tuned("sterba", b, {"nsec": 3, "reflector": True}).metrics
    assert refl["gain_dbi"] > free["gain_dbi"] + 1.0
    assert refl["fb"] is not None and refl["fb"] > 8.0


def test_bruce_gain_grows_with_sections():
    b = "40 m (7.0-7.3 MHz)"
    g3 = _tuned("bruce", b, {"n": 3}).metrics["gain_dbi"]
    g6 = _tuned("bruce", b, {"n": 6}).metrics["gain_dbi"]
    assert g6 > g3 + 2.0


# --------------------------------------------------------------------------- EFHW harmonic comb / transformer loss
def _efhw_sweep(ex):
    spec = REGISTRY["efhw"]
    e = {p.key: p.default for p in spec.params}
    e.update(ex)
    req = _req(spec, "80 m (3.5-4.0 MHz)")
    sc = engine.tune(spec, req, e, {})
    res = engine.evaluate(spec, req, e, sc, do_bands=False)
    return res


def _swr_at(res, f):
    return float(res.swr_rig[int(np.argmin(np.abs(res.f - f)))])


def test_efhw_compromise_length_puts_harmonic_bands_on_target():
    res = _efhw_sweep({})                       # all harmonic bands, hanging counterpoise, 0.5 dB unun
    for f in (7.1, 14.15, 21.2, 28.5):          # 40 / 20 / 15 / 10 m
        assert _swr_at(res, f) < 2.6, f
    fund = _efhw_sweep({"tune_for": "fund"})    # fundamental-only tuning leaves the harmonics high
    assert _swr_at(fund, 3.6) < 2.0
    assert _swr_at(fund, 14.15) > 4.0


def test_efhw_transformer_loss_caps_the_swr_peaks():
    lossless = _efhw_sweep({"xfmr_db": 0.0})
    lossy = _efhw_sweep({"xfmr_db": 1.0})
    assert lossy.swr_rig.max() < 0.8 * lossless.swr_rig.max()
    assert lossy.metrics["xfmr_loss_db"] > 0.3


# --------------------------------------------------------------------------- delta loop
def _delta(ex, height=8.0):
    spec = REGISTRY["delta"]
    e = {p.key: p.default for p in spec.params}
    e.update(ex)
    req = _req(spec, "20 m (14.0-14.35 MHz)", height=height)
    sc = engine.tune(spec, req, e, {})
    return engine.evaluate(spec, req, e, sc, do_sweep=False, do_bands=False)


def test_delta_loop_resonates_near_a_wavelength_and_feeds_about_100_ohm():
    res = _delta({})
    z = res.metrics["z_ant"]
    assert abs(z.imag) < 3.0 and 90 < z.real < 150
    per = res.design.total_wire_m()
    assert 1.02 < per / (299.792458 / 14.15) < 1.10


def test_delta_loop_orientation_and_feed_point_change_the_pattern():
    up = _delta({"orient": "up"}).pattern
    flat = _delta({"orient": "flat"}).pattern
    corner = _delta({"orient": "up", "feed": "corner"}).pattern
    assert flat.takeoff > up.takeoff + 8.0                              # flat loop is a high-angle radiator
    assert corner.comp_peak["vertical"] > up.comp_peak["vertical"] + 1.5   # corner feed adds vertical polarisation
    assert up.comp_peak["horizontal"] > corner.comp_peak["horizontal"] + 2.0


# --------------------------------------------------------------------------- whole-HF sweep option
def test_wide_sweep_option_covers_hf_and_leaves_the_design_unchanged():
    spec = REGISTRY["dipole"]
    assert spec.wide_ok and not spec.wide_default
    ex = {p.key: p.default for p in spec.params}
    band = "40 m (7.0-7.3 MHz)"
    req = _req(spec, band)
    sc = engine.tune(spec, req, ex, {})
    narrow = engine.evaluate(spec, req, ex, sc, do_bands=False)
    req2 = _req(spec, band, wide_sweep=True)
    wide = engine.evaluate(spec, req2, ex, sc, do_bands=False)
    assert abs(wide.f[0] - 1.8) < 1e-6 and abs(wide.f[-1] - 55.0) < 1e-6 and len(wide.f) > 250
    assert wide.design.shade_bands and len(wide.design.shade_bands) == 10
    assert abs(wide.metrics["swr_f0"] - narrow.metrics["swr_f0"]) < 0.3
    # a 40 m dipole is also resonant on its odd harmonics: a low SWR dip near 21 MHz
    third = wide.swr_rig[(wide.f > 20.5) & (wide.f < 22.5)]
    assert third.min() < 3.0 * 2
    assert not REGISTRY["yagi"].wide_ok
    # the scan range is user-selectable
    req3 = _req(spec, band, wide_sweep=True, wide_lo=13.0, wide_hi=15.0)
    part = engine.evaluate(spec, req3, ex, sc, do_bands=False)
    assert abs(part.f[0] - 13.0) < 1e-6 and abs(part.f[-1] - 15.0) < 1e-6


# --------------------------------------------------------------------------- NEC-2 deck export
def _parse_nec(deck):
    """Minimal NEC-2 reader (GW, GE, GN, LD 5, EX, FR) - enough to rebuild a plain wire design."""
    wires, ground, sig, ex, fr, cards = [], Ground("free"), 5.8e7, [], None, []
    for ln in deck.splitlines():
        t = ln.split()
        if not t:
            continue
        c = t[0]
        cards.append(c)
        if c == "GW":
            wires.append((int(t[1]), int(t[2]), [float(x) for x in t[3:10]]))
        elif c == "GN":
            k = int(t[1])
            ground = Ground("perfect") if k == 1 else Ground("real", float(t[6]), float(t[5])) if k == 0 else Ground("free")
        elif c == "LD" and t[1] == "5":
            sig = float(t[5])
        elif c == "EX":
            ex.append((int(t[2]), int(t[3]), complex(float(t[5]), float(t[6]))))
        elif c == "FR":
            fr = (int(t[2]), float(t[5]), float(t[6]))
    return wires, ground, sig, ex, fr, cards


@pytest.mark.parametrize("over", [{}, {"orient": "down", "feed": "corner"}, {"orient": "flat", "feed": "side"},
                                  {"tilt": 25.0, "az": 40.0}])
def test_delta_loop_nec_deck_round_trips(over):
    from antennacalc import export
    spec = REGISTRY["delta"]
    e = {p.key: p.default for p in spec.params}
    e.update(over)
    req = _req(spec, "20 m (14.0-14.35 MHz)", height=8.0)
    sc = engine.tune(spec, req, e, {})
    res = engine.evaluate(spec, req, e, sc, do_sweep=False, do_bands=False)
    deck = export.nec_deck(res)
    wires, ground, sig, ex, fr, cards = _parse_nec(deck)
    assert cards[:1] == ["CM"] and cards.index("CE") < cards.index("GW") < cards.index("GE") < cards.index("EX") < cards.index("FR")
    assert cards[-1] == "EN" and "RP" in cards and len(ex) == 1 and len(wires) >= 3
    assert fr[0] == 11 and fr[1] == pytest.approx(14.0)          # band sweep for the SWR plot
    # a closed loop: every end point is shared by exactly one other wire
    ends = {}
    for tag, n, v in wires:
        for p in (tuple(round(x, 3) for x in v[0:3]), tuple(round(x, 3) for x in v[3:6])):
            ends[p] = ends.get(p, 0) + 1
    assert all(c == 2 for c in ends.values())
    # neighbouring segment lengths stay within NEC's 5:1 guideline
    seglens = [math.dist(v[0:3], v[3:6]) / n for tag, n, v in wires]
    assert max(seglens) / min(seglens) <= 5.0
    # re-solve the deck with the solver: same feedpoint impedance as the design
    st = Structure(ground=ground)
    for tag, n, v in wires:
        st.add(tuple(v[0:3]), tuple(v[3:6]), v[6], sigma=sig, nseg=n)
    st.sources.append(Source(ex[0][0] - 1, (ex[0][1] - 0.5) / wires[ex[0][0] - 1][1]))
    z = solve(Model(st, 1.0), req.f_mhz * 1e6).zin[0]
    z0 = res.metrics["z_ant"]
    assert abs(z - z0) / abs(z0) < 0.03
