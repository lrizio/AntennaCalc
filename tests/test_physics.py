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


# --------------------------------------------------------------------------- Wire Editor (custom.py)
def _custom(dr, ground="free", tune="none"):
    from antennacalc.mom import Ground
    spec = REGISTRY["custom"]
    req = Requirements(f_mhz=14.15, f_lo=14.0, f_hi=14.35,
                       ground=Ground(ground, 0.005, 13.0) if ground != "free" else Ground("free"))
    ex = {"drawing": dr.to_dict(), "tune": tune}
    sc = engine.tune(spec, req, ex, {})
    return engine.evaluate(spec, req, ex, sc, do_sweep=False), sc


def test_custom_drawn_dipole_matches_builtin():
    from antennacalc.custom import template
    res, sc = _custom(template("dipole", 299.792458 / 14.15), tune="scale")
    z = res.metrics["z_ant"]
    assert 65 < z.real < 80 and abs(z.imag) < 2
    assert abs(res.metrics["gain_dbi"] - 2.1) < 0.2


def test_custom_split_and_loads():
    from antennacalc.custom import CLoad, Drawing, CSource, template
    dr = template("dipole", 299.792458 / 14.15)
    w = dr.wires[0]
    a, b = dr.split_wire(w.id, 0.3)
    assert dr.sources[0].wire == b.id and abs(dr.sources[0].at - (0.2 / 0.7)) < 1e-9
    assert abs(a.length() + b.length() - 2 * 0.2375 * 299.792458 / 14.15) < 1e-6
    # a parallel L-C trap resonant at the design frequency acts as an insulator
    lh = 5.0
    c = 1 / ((2 * math.pi * 14.15e6) ** 2 * lh * 1e-6) * 1e12
    dr.loads.append(CLoad(dr.new_id(), a.id, 0.5, "parallel", r=0.0, l_uh=lh, c_pf=c))
    res, _ = _custom(dr)
    assert np.isfinite(res.metrics["gain_dbi"])
    assert res.design.structure.loads


def test_custom_elevated_ground_plane_feeds_whole_junction():
    from antennacalc.custom import template
    res, _ = _custom(template("gp", 299.792458 / 14.15), ground="real", tune="scale")
    assert 35 < res.metrics["z_ant"].real < 65


# --------------------------------------------------------------------------- feed system (feed line, balun, coax, tuner)
def test_line_loss_matched_equals_datasheet_and_rises_with_swr():
    from antennacalc.design import line_section
    spec = (450.0, 0.91, 0.5, 30.0)
    _, matched = line_section(450.0, spec, 7.1)
    assert abs(matched - 0.5 * math.sqrt(7.1 / 100) * 0.3) < 1e-6
    _, high = line_section(4500.0, spec, 7.1)
    assert high > 3 * matched
    _, coax = line_section(4500.0, (50.0, 0.66, 8.6, 30.0), 7.1)
    assert coax > 8.0                       # the classic "coax at high SWR" loss


def test_feed_system_ladder_balun_coax_tuner():
    from antennacalc.custom import Drawing, CSource
    from antennacalc.mom import Ground
    dr = Drawing()
    a = dr.add_wire((-20, 0, 10), (0, 0, 10)); dr.add_wire((0, 0, 10), (20, 0, 10))
    dr.sources.append(CSource(dr.new_id(), a.id, 1.0))
    spec = REGISTRY["custom"]
    base = dict(f_mhz=7.1, f_lo=7.0, f_hi=7.3, ground=Ground("real", 0.005, 13.0), coax_key="rg213")
    direct = engine.evaluate(spec, Requirements(**base, coax_len=30, tuner="wide"), {"drawing": dr.to_dict()}, {}, do_sweep=False)
    ladder = engine.evaluate(spec, Requirements(**base, feeder_key="ladder450", feeder_len=20, ratio=9.0, coax_len=10, tuner="rig10"),
                             {"drawing": dr.to_dict()}, {}, do_sweep=False)
    md, ml = direct.metrics, ladder.metrics
    assert md["sys_loss_db"] > 6 and ml["sys_loss_db"] < md["sys_loss_db"] / 2
    names = [st[0] for st in ml["stages"]]
    assert names[0] == "Antenna terminals" and "Ladder line" in names[1] and "9:1" in names[2] and "RG-213" in names[3]
    assert abs(sum(st[3] for st in ml["stages"]) - ml["sys_loss_db"]) < 1e-9
    assert ml["tuner_range"] == 10.0


def test_tuner_loss_l_network_matches_theory_and_t_network_is_worse_into_low_z():
    from antennacalc.design import t_tuner_loss, tuner_loss
    # L network: power lost ~ loaded Q / inductor Q, with loaded Q = sqrt(Rhigh/Rlow - 1)
    for r in (500.0, 5.0):
        ql = math.sqrt(10 - 1)
        expect = -10 * math.log10(1 - ql / 120)
        assert abs(tuner_loss(complex(r, 0), 50, 7.1, 120)[0] - expect) < 0.02
    assert tuner_loss(50 + 0j, 50, 7.1, 120)[0] == 0.0
    # higher SWR -> more loss; lower Q -> more loss
    assert tuner_loss(2500 + 0j, 50, 7.1, 120)[0] > tuner_loss(500 + 0j, 50, 7.1, 120)[0]
    assert tuner_loss(500 + 0j, 50, 7.1, 60)[0] > tuner_loss(500 + 0j, 50, 7.1, 120)[0]
    # T network at its best setting: never better than the L network, much worse into low impedance at low frequency
    for z in (500 + 0j, 5 + 0j, 20 + 80j):
        assert t_tuner_loss(z, 50, 7.1, 120) >= tuner_loss(z, 50, 7.1, 120)[0] - 1e-6
    assert t_tuner_loss(5 + 0j, 50, 3.6, 120) > 5 * tuner_loss(5 + 0j, 50, 3.6, 120)[0]


# --------------------------------------------------------------------------- coax common-mode current (cm.py)
def _cm(key, ex, **kw):
    from antennacalc.mom import Ground
    spec = REGISTRY[key]
    req = Requirements(ground=Ground("real", 0.005, 13.0), power_w=100, cm_model=True, **kw)
    return engine.evaluate(spec, req, ex, {}, do_sweep=False).metrics


def test_choke_reduces_dipole_common_mode_and_matches_hand_estimate():
    direct = _cm("dipole", {"shape": "flat"}, balun_type="unun", coax_len=15)
    choke = _cm("dipole", {"shape": "flat"}, balun_type="current", choke_ohm=5000, coax_len=15)
    assert direct["cm_mode"] == "feedpoint"
    assert -30 < direct["cm_ratio_db"] < -10
    assert choke["cm_ratio_db"] < direct["cm_ratio_db"] - 6
    # at the balun the choke carries about (V/2) / Zcm
    z = choke["z_ant"]
    i_feed = choke["cm_i_feed"]
    expect = 0.5 * i_feed * abs(z) / 5000
    assert 0.5 * expect < choke["cm_i_balun"] < 2.0 * expect
    assert abs(choke["z_ant"] - direct["z_ant"]) < 5                  # the coax barely changes a choked dipole


def test_common_mode_with_ladder_line_leaves_main_model_untouched():
    from antennacalc.custom import CLoad, CSource, Drawing
    dr = Drawing()
    a = dr.add_wire((-20, 0, 10), (0, 0, 10)); b = dr.add_wire((0, 0, 10), (20, 0, 10))
    dr.sources.append(CSource(dr.new_id(), a.id, 1.0))
    dr.loads.append(CLoad(dr.new_id(), b.id, 0.5, "series", r=1, l_uh=1))
    base = dict(f_mhz=7.1, f_lo=7.0, f_hi=7.3, feeder_key="ladder450", feeder_len=20, ratio=9.0, coax_len=10)
    on = _cm("custom", {"drawing": dr.to_dict()}, balun_type="current", **base)
    from antennacalc.mom import Ground
    off = engine.evaluate(REGISTRY["custom"], Requirements(ground=Ground("real", 0.005, 13.0), **base),
                          {"drawing": dr.to_dict()}, {}, do_sweep=False).metrics
    assert on["cm_mode"] == "feedline" and math.isfinite(on["cm_ratio_db"])
    assert abs(on["z_ant"] - off["z_ant"]) < 1e-6                       # the estimate is separate from the main solution


def test_default_balun_type():
    from antennacalc.cm import default_balun_type
    assert default_balun_type(REGISTRY["efhw"]) == "unun"
    assert default_balun_type(REGISTRY["dipole"]) == "current"


def test_extra_coax_choke_down_the_line():
    one = _cm("dipole", {"shape": "flat"}, balun_type="current", choke_ohm=2000, coax_len=15)
    two = _cm("dipole", {"shape": "flat"}, balun_type="current", choke_ohm=2000, coax_len=15, choke2_ohm=2000, choke2_dist=13)
    assert "cm_i_beyond" in two and two["cm_i_beyond"] < 0.5 * one["cm_i_max"]
    assert two["cm_i_radio"] < 0.5 * one["cm_i_radio"]
    far = _cm("dipole", {"shape": "flat"}, balun_type="current", choke_ohm=2000, coax_len=15, choke2_ohm=2000, choke2_dist=40)
    assert "cm_i_beyond" not in far and "beyond the end" in far.get("cm_note", "")


def test_coax_route_follows_user_direction_heights_and_lengths():
    from antennacalc import cm
    from antennacalc.custom import CSource, Drawing, build_structure
    from antennacalc.mom import Ground, Structure
    dr = Drawing()
    a = dr.add_wire((-20, 0, 10), (0, 0, 10)); dr.add_wire((0, 0, 10), (20, 0, 10))
    dr.sources.append(CSource(dr.new_id(), a.id, 1.0))
    st = Structure(ground=Ground("real", 0.005, 13.0))
    req = Requirements(f_mhz=7.1, coax_len=12, coax_dir=45, coax_height=0.5, feeder_bottom=3)
    build_structure(dr, st, req)
    pl = cm.plan(st, np.array([0, 0, 10.0]), req, (450, 0.91, 0.5, 20))
    seglen = lambda P: sum(np.linalg.norm(np.subtract(P[i + 1], P[i])) for i in range(len(P) - 1))
    assert abs(seglen(pl["feedline"]) - 20) < 1e-9 and abs(pl["feedline"][1][2] - 3) < 1e-9
    assert abs(seglen(pl["coax"][:-1]) - 12) < 1e-9 and abs(pl["coax"][2][2] - 0.5) < 1e-9
    d = pl["coax"][2] - pl["coax"][1]
    assert abs(math.degrees(math.atan2(d[1], d[0])) - 45) < 1e-6
    assert pl["coax"][-1][2] == 0.0                                    # grounded at the radio
    auto = cm.plan(st, np.array([0, 0, 10.0]), Requirements(f_mhz=7.1, coax_len=12), None)
    d = auto["coax"][2] - auto["coax"][1]
    assert abs(d[0]) < 1e-9                                            # auto: at right angles to an X-directed antenna


# --------------------------------------------------------------------------- built-in design -> Wire Editor copy
def test_load_fit_kinds():
    from antennacalc.custom import _fit_load
    from antennacalc.mhelp import coil_fn, trap_fn
    f0 = 7.1e6
    assert _fit_load(lambda f: 12 + 0j, f0, "R")[0] == "fixed"
    kind, r, x, l_uh, c_pf, e = _fit_load(coil_fn(20e-6, 200, 7.1), f0, "coil")
    assert kind == "series" and abs(l_uh - 20) < 0.01 and e < 0.01
    fn, lh = trap_fn(7.1, 100.0, 150)
    kind, r, x, l_uh, c_pf, e = _fit_load(fn, 14.2e6, "trap")
    assert kind == "parallel" and abs(c_pf - 100) < 1 and abs(l_uh - lh * 1e6) / (lh * 1e6) < 0.01 and e < 0.05


@pytest.mark.parametrize("key", ["dipole", "loaded_dipole", "yagi", "gp", "turnstile"])
def test_copy_to_wire_editor_matches(key):
    from antennacalc import custom
    spec = REGISTRY[key]
    req = _req(spec, spec.band_default or "20 m (14.0-14.35 MHz)")
    ex = {p.key: p.default for p in spec.params}
    res = engine.evaluate(spec, req, ex, {}, do_bands=False)
    dr, _, req.ground = custom.drawing_from_spec(spec, req, ex, {})
    dr = custom.Drawing.from_dict(dr.to_dict())
    cres = engine.evaluate(REGISTRY["custom"], req, {"drawing": dr.to_dict(), "tune": "none"}, {}, do_bands=False)
    za, zc = res.metrics["z_ant"], cres.metrics["z_ant"]
    assert abs(zc - za) / abs(za) < 0.02
    assert abs(cres.metrics["gain_dbi"] - res.metrics["gain_dbi"]) < 0.1


def test_copy_rejects_closed_form():
    from antennacalc import custom
    spec = REGISTRY["dish"]
    with pytest.raises(ValueError):
        custom.drawing_from_spec(spec, _req(spec, spec.band_default or "20 m (14.0-14.35 MHz)"), {}, {})
