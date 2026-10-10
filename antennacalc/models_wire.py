"""HF wire antennas (dipoles, loops, long wires, rhombics, beverage)."""
from __future__ import annotations

import math

import numpy as np

from .common import COAX, BAND_BY_LABEL, band_short, HF_BAND_LABELS, BANDS
from .design import Design, Param, Spec, TuneTarget, register
from .mhelp import (add_polygon, band_choices, dipole_pair, hf_multiband, new_struct,
                    regular_polygon, rotate_xy, size_warn, trap_fn, eq_radius_note)
from .mom import C0, Load, Source


def P(ex, key, default):
    v = ex.get(key, default)
    return default if v is None and default is not None and key not in ex else v


def _sc(sc, key):
    return sc.get(key, 1.0)


# =========================================================================== dipole family
def b_dipole(req, ex, sc):
    lam = req.lam
    shape = P(ex, "shape", "flat")
    d = Design("dipole", "Dipole")
    st = new_struct(req, d)
    half = 0.2375 * lam * _sc(sc, "len")
    H = req.height
    a, sg = req.radius, req.sigma
    if shape == "flat":
        c = np.array([0, 0, H]); u = np.array([1, 0, 0])
        title = "Half-wave dipole"
    elif shape == "invv":
        ang = math.radians(float(P(ex, "vangle", 120.0)))
        beta = (math.pi - ang) / 2
        dx, dz = half * math.cos(beta), half * math.sin(beta)
        w0 = st.add((-dx, 0, H - dz), (0, 0, H), a, sigma=sg, name="leg", min_seg=5)
        w1 = st.add((0, 0, H), (dx, 0, H - dz), a, sigma=sg, name="leg", min_seg=5)
        st.sources.append(Source(w0, 1.0))
        if H - dz < 1.0:
            d.warnings.append(f"Leg ends are only {H - dz:.1f} m above ground - raise the apex.")
        title = "Inverted-V dipole"
    else:
        sl = math.radians(float(P(ex, "slope", 45.0)))
        cz = H - half * math.sin(sl)
        cz = max(cz, 0.5)
        w0 = st.add((-half * math.cos(sl), 0, cz - half * math.sin(sl)), (0, 0, cz), a, sigma=sg, min_seg=5)
        w1 = st.add((0, 0, cz), (half * math.cos(sl), 0, cz + half * math.sin(sl)), a, sigma=sg, min_seg=5)
        st.sources.append(Source(w0, 1.0))
        title = "Sloper dipole"
    if shape == "flat":
        w0 = st.add(c - u * half, c, a, sigma=sg, min_seg=5)
        w1 = st.add(c, c + u * half, a, sigma=sg, min_seg=5)
        st.sources.append(Source(w0, 1.0))
    d.title = title
    d.pol = "H"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.7, hi=1.4, label="length")]
    leg = 2 * half / 2
    d.dim("Total length (tip to tip)", 1, 2 * half, "cut slightly long and trim to the SWR minimum")
    d.dim("Each leg", 2, half, "from the centre insulator")
    d.dim("Feed point", 1, None, "centre insulator with 1:1 current balun and coax")
    if shape == "invv":
        d.dim("Apex height", 1, H, f"included angle {P(ex, 'vangle', 120)} deg")
    d.notes += ["Resonant length is about 142.5/f (MHz) metres in free space; height above ground and conductor size shift it.",
                "A 1:1 choke balun at the feedpoint keeps feedline current off the coax shield.",
                "Higher is better for DX up to about 0.5 wavelength; lower heights give more high-angle (NVIS) radiation."]
    size_warn(d, req, 2 * half, "Antenna span")
    eq_radius_note(req, d)
    return d


register(Spec("dipole", "Dipole / Inverted-V / Sloper", "HF wire antennas", b_dipole,
              params=[Param("shape", "Shape", "choice", "flat", choices=[("Flat-top dipole", "flat"), ("Inverted-V", "invv"), ("Sloper (tilted)", "slope")]),
                      Param("vangle", "Inverted-V included angle", "float", 120.0, 90, 175, 5, unit="deg"),
                      Param("slope", "Sloper angle from horizontal", "float", 45.0, 15, 80, 5, unit="deg")],
              desc="Centre-fed half-wave dipole in flat-top, inverted-V or sloper form. The baseline antenna.",
              height_default=10.0, size_label="Max span"))


# =========================================================================== OCFD / Windom
def b_ocfd(req, ex, sc):
    lam_f0 = req.lam
    ffund = P(ex, "fund", None) or req.f_mhz
    lam = C0 / (ffund * 1e6)
    off = float(P(ex, "offset", 0.22))
    var = P(ex, "variant", "ocfd")
    d = Design("ocfd", "Off-centre-fed dipole")
    st = new_struct(req, d)
    L = 0.4750 * lam * _sc(sc, "len")
    H = req.height
    a, sg = req.radius, req.sigma
    wa = st.add((-L * off, 0, H), (0, 0, H), a, sigma=sg, min_seg=5)
    wb = st.add((0, 0, H), (L * (1 - off), 0, H), a, sigma=sg, min_seg=5)
    st.sources.append(Source(wa, 1.0))
    if var == "carolina":
        st.add((0, 0, H), (0, 0, max(H - 0.12 * lam, 0.5)), a, sigma=sg, min_seg=5)
        d.notes.append("Carolina Windom: the vertical radiating section stands in for the coax shield that radiates below the feed.")
    d.title = {"ocfd": "Off-centre-fed dipole (OCFD)", "windom": "Windom", "carolina": "Carolina Windom"}.get(var, "OCFD")
    d.pol = "H"
    d.force_ratio = None
    d.tune = [TuneTarget("len", ffund, "x0", lo=0.8, hi=1.25, label="length")]
    d.multiband = hf_multiband(ffund * 0.95)
    d.dim("Total length", 1, L, f"fundamental {ffund:.3f} MHz")
    d.dim("Short leg", 1, off * L, "")
    d.dim("Long leg", 1, (1 - off) * L, "")
    d.dim("Feed", 1, None, "4:1 current balun (200 ohm to 50 ohm) at the feedpoint")
    d.notes += ["The off-centre feed gives roughly 200-300 ohm on the fundamental and moderate impedances on the even harmonics, so a 4:1 balun and a single coax serve several bands (an antenna tuner helps on the harmonics).",
                "Odd harmonics show a poorer match; check the multi-band table.",
                "'Cobra' Windoms are modelled by this same geometry."]
    size_warn(d, req, L, "Antenna span")
    return d


register(Spec("ocfd", "Off-centre-fed dipole (OCFD / Windom / Carolina / Cobra)", "HF wire antennas", b_ocfd,
              params=[Param("variant", "Variant", "choice", "ocfd", choices=[("OCFD (feed off-centre)", "ocfd"), ("Windom", "windom"), ("Carolina Windom (vertical section)", "carolina")]),
                      Param("offset", "Feed offset (fraction of length)", "float", 0.22, 0.15, 0.5, 0.01),
                      Param("fund", "Cut for fundamental band", "choice", None, choices=band_choices("(same as design band)", hf_only=True))],
              desc="Multiband dipole fed off-centre (about 20-25% from one end) through a 4:1 balun. Cobra and Carolina Windoms use the same basic shape.",
              feed_ratio=4.0, size_label="Max span"))


# =========================================================================== G5RV / doublet
def b_g5rv(req, ex, sc):
    preset = P(ex, "preset", "g5rv")
    d = Design("g5rv", "Doublet / G5RV")
    st = new_struct(req, d)
    if preset == "g5rv":
        Ld, Ll = 31.1, 10.36
    elif preset == "g5rv_half":
        Ld, Ll = 15.55, 5.18
    elif preset == "g5rv_double":
        Ld, Ll = 62.2, 20.7
    else:
        Ld, Ll = float(P(ex, "dip_len", 40.0)), float(P(ex, "lad_len", 12.0))
    fk = P(ex, "feeder", "ladder450")
    c = COAX[fk]
    d.line = (c[1], c[2], c[3], Ll)
    H = req.height
    a, sg = req.radius, req.sigma
    w0 = st.add((-Ld / 2, 0, H), (0, 0, H), a, sigma=sg, min_seg=8)
    w1 = st.add((0, 0, H), (Ld / 2, 0, H), a, sigma=sg, min_seg=8)
    st.sources.append(Source(w0, 1.0))
    d.pol = "H"
    d.title = "G5RV" if preset.startswith("g5rv") else "Doublet"
    d.multiband = hf_multiband(3.0 if Ld > 25 else 6.5)
    d.dim("Dipole (total)", 1, Ld, "")
    d.dim("Each leg", 2, Ld / 2, "")
    d.dim(f"Matching section ({c[0]})", 1, Ll, "")
    d.dim("Choke balun + coax", 1, None, "1:1 current balun where the ladder line meets the coax")
    d.notes += ["An antenna tuner is required: the antenna is a multiband doublet and the match depends on the band.",
                "'SWR at feedpoint' in the multi-band table is what the coax would see without a tuner; the tuner cancels the reactance.",
                "The matching section length should not be cut - the preset sizes are the G5RV design values."]
    size_warn(d, req, Ld, "Antenna span")
    return d


register(Spec("g5rv", "Doublet / G5RV / ladder-line fed dipole", "HF wire antennas", b_g5rv,
              params=[Param("preset", "Size", "choice", "g5rv", choices=[("G5RV full (31.1 m + 10.36 m)", "g5rv"), ("G5RV half (15.55 m + 5.18 m)", "g5rv_half"), ("G5RV double (62.2 m + 20.7 m)", "g5rv_double"), ("Custom doublet", "custom")]),
                      Param("dip_len", "Custom dipole length", "float", 40.0, 4, 120, 0.5, unit="m"),
                      Param("lad_len", "Custom feeder length", "float", 12.0, 1, 60, 0.5, unit="m"),
                      Param("feeder", "Feeder type", "choice", "ladder450", choices=[("Ladder line 450 ohm", "ladder450"), ("Twin-lead 300 ohm", "twin300"), ("Open wire 600 ohm", "open600")])],
              desc="Multiband doublet fed with open-wire line. Use with an antenna tuner.",
              feed_ratio=1.0, feed_coax="rg213", size_label="Max span"))


# =========================================================================== fan dipole
def b_fan(req, ex, sc):
    d = Design("fan", "Fan dipole")
    st = new_struct(req, d)
    fl = [req.f_mhz]
    for k in ("b2", "b3", "b4"):
        v = P(ex, k, None)
        if v:
            fl.append(v)
    spacing = float(P(ex, "spacing", 0.3))
    H = req.height
    a, sg = req.radius, req.sigma
    gap = st.add((-0.01, 0, H), (0.01, 0, H), a, sigma=sg, nseg=2)
    st.sources.append(Source(gap, 0.5))
    n = len(fl)
    d.tune = []
    for i, f in enumerate(fl):
        lam = C0 / (f * 1e6)
        half = 0.2375 * lam * _sc(sc, f"b{i}")
        y = (i - (n - 1) / 2) * spacing
        st.add((-0.01, 0, H), (-half, y, H), a, sigma=sg, min_seg=5)
        st.add((0.01, 0, H), (half, y, H), a, sigma=sg, min_seg=5)
        d.tune.append(TuneTarget(f"b{i}", f, "x0", lo=0.7, hi=1.4, label=f"{f:.2f} MHz leg"))
        d.dim(f"{f:.3f} MHz dipole, each leg", 2, half, f"spread {y:+.2f} m sideways")
        d.multiband.append((f"{f:.3f} MHz", f))
    d.pol = "H"
    d.title = f"Fan dipole ({n} bands)"
    d.dim("Feed", 1, None, "single centre insulator, 1:1 balun, one coax")
    d.notes += ["Each band gets its own dipole sharing the same feedpoint; the legs interact, so every leg is tuned in turn (automatic with Auto-tune).",
                "Keep the spacing between legs at 0.2-0.5 m with spreaders; closer coupling needs longer retrimming.",
                "Choose bands that are not close to harmonics of one another or the shorter dipoles will detune the longer ones."]
    if n < 2:
        d.warnings.append("Pick additional bands in the extra-band boxes to make this a fan.")
    size_warn(d, req, 2 * 0.2375 * (C0 / (min(fl) * 1e6)), "Antenna span")
    return d


register(Spec("fan", "Fan dipole (multiband)", "HF wire antennas", b_fan,
              params=[Param("b2", "Second band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("b3", "Third band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("b4", "Fourth band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("spacing", "Leg spacing at the tips", "float", 0.3, 0.05, 2.0, 0.05, unit="m")],
              desc="Several dipoles on one feedpoint, one per band. The design band is the first band.",
              size_label="Max span"))


# =========================================================================== trap dipole / trap vertical
def _trap_legs(st, d, req, ex, sc, bands, start, direction, ground_mounted: bool):
    """Build one trap leg per side.  bands: descending frequencies.  Returns list of wire ids per leg."""
    cpf = float(P(ex, "trap_c", 60.0))
    q = float(P(ex, "trap_q", 150.0))
    a, sg = req.radius, req.sigma
    n = len(bands)
    lens = []
    # section lengths: first section resonates the highest band, later ones extend to lower bands
    cum = 0.0
    for i, f in enumerate(bands):
        lam = C0 / (f * 1e6)
        target = 0.2375 * lam * (1.0 if not ground_mounted else 1.0)
        # trap adds a little inductance-like end loading; start slightly short
        sec = max(target - cum, 0.05 * lam) * _sc(sc, f"s{i}")
        if i > 0:
            sec *= 0.93
        lens.append(sec)
        cum += sec
    wires = []
    p = np.array(start, float)
    u = np.array(direction, float)
    for i, sec in enumerate(lens):
        q_ = p + u * sec
        w = st.add(p, q_, a, sigma=sg, min_seg=4)
        wires.append(w)
        if i < n - 1:
            fn, lh = trap_fn(bands[i], cpf, q)
            st.loads.append(Load(w, 1.0, fn, f"trap {bands[i]:.2f} MHz"))
        p = q_
    return wires, lens


def _trap_dipole_gap(req, ex, sc, fl):
    d = Design("trap_dipole", f"Trap dipole ({len(fl)} bands)")
    st = new_struct(req, d)
    H = req.height
    a, sg = req.radius, req.sigma
    gap = st.add((-0.01, 0, H), (0.01, 0, H), a, sigma=sg, nseg=2)
    st.sources.append(Source(gap, 0.5))
    wl, ll = _trap_legs(st, d, req, ex, sc, fl, (-0.01, 0, H), (-1, 0, 0), False)
    wr, lr = _trap_legs(st, d, req, ex, sc, fl, (0.01, 0, H), (1, 0, 0), False)
    cpf = float(P(ex, "trap_c", 60.0)); q = float(P(ex, "trap_q", 150.0))
    d.tune = [TuneTarget(f"s{i}", f, "x0", lo=0.6, hi=1.6, label=f"{f:.2f} MHz section") for i, f in enumerate(fl)]
    # the tuner scales both legs at once because the scale key is shared
    d.pol = "H"
    d.multiband = [(f"{f:.3f} MHz", f) for f in fl]
    tot = sum(ll)
    d.dim("Section lengths (each side, from centre)", len(ll), None, ", ".join(f"{x:.3f} m" for x in ll))
    d.dim("Overall span", 1, 2 * tot, "")
    for i, f in enumerate(fl[:-1]):
        fn, lh = trap_fn(f, cpf, q)
        x = 2 * math.pi * f * 1e6 * lh
        d.dim(f"Trap {i + 1} ({f:.3f} MHz), two required", 2, None,
              f"L = {lh * 1e6:.2f} uH, C = {cpf:.0f} pF (HV), X = {x:.0f} ohm, Q = {q:.0f}")
    d.notes += ["Each trap is a parallel LC resonant on the higher band of its pair; it isolates the outer wire on that band and acts as a loading coil on the lower bands.",
                "Build the trap coil a little large and tune it with a grid-dip meter or antenna analyser before installing.",
                "Real traps have loss: Q of 100-200 costs 0.3-1 dB on the lower bands (included in the model)."]
    return d


register(Spec("trap_dipole", "Trap dipole (2-3 bands)", "HF wire antennas", lambda r, e, s: _trap_dipole_gap(r, e, s, _fl(r, e)),
              params=[Param("b2", "Second (lower) band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("b3", "Third (lower) band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("trap_c", "Trap capacitor", "float", 60.0, 10, 500, 5, unit="pF"),
                      Param("trap_q", "Trap Q", "float", 150.0, 30, 400, 10)],
              desc="Dipole with parallel LC traps so it resonates on two or three bands. The design band is the highest band.",
              size_label="Max span"))


def _fl(req, ex):
    fl = [req.f_mhz]
    for k in ("b2", "b3"):
        v = P(ex, k, None)
        if v and v < fl[-1]:
            fl.append(v)
    return fl


# =========================================================================== long wire / random wire
def _best_long_length(fl, max_len):
    best, bs = 20.0, -1
    L = 8.0
    while L <= (max_len or 80.0) + 1e-9:
        score = 1.0
        for f in fl:
            half = 0.5 * C0 / (f * 1e6)
            r = L / half
            score = min(score, abs(r - round(r)))
        if score > bs:
            bs, best = score, L
        L += 0.1
    return best


def b_longwire(req, ex, sc):
    d = Design("longwire", "Long / random wire")
    st = new_struct(req, d, needs_ground=True)
    fl = [b[3] for b in BANDS if b[0] in HF_BAND_LABELS and b[3] >= 3.5]
    Lreq = float(P(ex, "length", 0.0))
    L = Lreq if Lreq > 0 else _best_long_length(fl, req.max_size or 0)
    hf = float(P(ex, "feed_h", 2.5))
    H = req.height
    end_h = float(P(ex, "end_h", H))
    a, sg = req.radius, req.sigma
    lead = st.add((0, 0, 0), (0, 0, H), a, sigma=sg, min_seg=4)
    st.sources.append(Source(lead, 0.0))
    st.add((0, 0, H), (L, 0, end_h), a, sigma=sg, min_seg=10)
    rg = float(P(ex, "rg", 8.0))
    st.loads.append(Load(lead, 0.0, lambda f, r=rg: r + 0j, "ground system loss"))
    d.pol = "mixed"
    d.multiband = hf_multiband(3.0)
    d.dim("Radiating wire", 1, L, "length chosen to avoid half-wave multiples on the HF bands" if Lreq <= 0 else "")
    d.dim("Vertical lead from the unun", 1, H, "")
    d.dim("Counterpoise / ground", 1, None, f"series ground-loss resistance assumed {rg:.0f} ohm")
    d.notes += ["A 9:1 unun brings the end-fed impedance down; use an antenna tuner for all bands.",
                "A good ground or counterpoise (e.g. several quarter-wave radials) is essential - the results assume the ground-loss figure you entered.",
                "The wire length is picked so no HF band sees a half-wave multiple (very high impedance)."]
    size_warn(d, req, L, "Wire")
    return d


register(Spec("longwire", "Long wire / random wire", "HF wire antennas", b_longwire,
              params=[Param("length", "Wire length (0 = auto)", "float", 0.0, 0, 200, 0.5, unit="m"),
                      Param("end_h", "Far end height", "float", 8.0, 1, 40, 0.5, unit="m"),
                      Param("rg", "Ground loss resistance", "float", 8.0, 0, 100, 1, unit="ohm")],
              desc="End-fed random wire with a 9:1 unun and a tuner. Length chosen to avoid resonant lengths.",
              feed_ratio=9.0, height_default=8.0, needs_ground=True, size_label="Max wire length"))


# =========================================================================== EFHW / Zepp
def _harmonic_bands(ffund, tol=0.03):
    """HF amateur bands whose centre lies within `tol` of an integer multiple of the fundamental."""
    out = []
    for lab in HF_BAND_LABELS:
        f = BAND_BY_LABEL[lab][3]
        n = round(f / ffund)
        if n >= 1 and abs(f / (n * ffund) - 1.0) <= tol:
            out.append(f)
    return out


def b_efhw(req, ex, sc):
    ffund = P(ex, "fund", None) or req.f_mhz
    lam = C0 / (ffund * 1e6)
    d = Design("efhw", "End-fed half-wave")
    st = new_struct(req, d)
    L = 0.4880 * lam * _sc(sc, "len")
    H = req.height
    end_h = float(P(ex, "end_h", H))
    a, sg = req.radius, req.sigma
    style = P(ex, "cp_style", "down")
    cp = float(P(ex, "cp_m", 3.0))
    if style == "inline":                   # collinear stub: really an off-centre-fed dipole on the harmonics
        u = np.array([-1.0, 0.0, 0.0])
    elif style == "angled":
        u = np.array([-math.sqrt(0.5), 0.0, -math.sqrt(0.5)])
    else:
        u = np.array([0.0, 0.0, -1.0])
    if u[2] < 0:
        cp = min(cp, (H - 0.5) / -u[2])     # keep the lower end off the ground
    cp = max(cp, 0.3)
    far = np.array([0.0, 0.0, H]) + u * cp
    g = st.add(tuple(far), (0, 0, H), a, sigma=sg, min_seg=3)
    st.add((0, 0, H), (L, 0, end_h), a, sigma=sg, min_seg=10)
    st.sources.append(Source(g, 1.0))
    d.pol = "H"
    d.dim("Counterpoise", 1, cp, {"down": "hangs straight down from the feed end (stands in for the coax shield / a short wire)",
                                  "angled": "slopes down and away from the radiator at 45 degrees",
                                  "inline": "continues the radiator in a straight line"}.get(style, ""))
    harm = _harmonic_bands(ffund)
    comp = P(ex, "tune_for", "all") == "all" and len(harm) > 1
    if comp:
        d.tune = [TuneTarget("len", ffund, "swr", lo=0.9, hi=1.2, label="length (all harmonic bands)", freqs=harm)]
    else:
        d.tune = [TuneTarget("len", ffund, "x0", lo=0.9, hi=1.1, label="length")]
    d.multiband = hf_multiband(ffund * 0.95)
    d.xfmr_loss_db = float(P(ex, "xfmr_db", 0.5))
    d.dim("Radiator", 1, L, f"{'compromise length for the harmonic bands' if comp else 'half-wave on %.3f MHz' % ffund}")
    d.dim("Matching transformer", 1, None, "49:1 (or 64:1) unun at the feed end; counterpoise stub or coax choke")
    d.notes += ["An EFHW has a very high feed impedance (2-5 kohm), hence the 49:1 or 64:1 transformer.",
                "A bare wire cut for the fundamental has its harmonics a few percent high (about (n/2 - 0.025) wavelengths); the "
                "'all harmonic bands' tuning lengthens the wire a little so the 40/20/15/10 m dips line up, at the cost of "
                "the fundamental sitting slightly low. Trim on the air.",
                "Real ununs have core loss and leakage, which cap the SWR peaks between the dips at roughly 5-8:1; the loss "
                "setting models this as a shunt resistance (it also costs transmit power at resonance).",
                "The counterpoise is the coax shield or a short wire; hanging it away from the radiator keeps the harmonics "
                "evenly spaced. A collinear stub makes the antenna an off-centre-fed dipole on the higher bands.",
                "Use a common-mode choke on the coax; the coax shield carries part of the antenna current."]
    size_warn(d, req, L, "Wire")
    return d


register(Spec("efhw", "End-fed half-wave (EFHW)", "HF wire antennas", b_efhw,
              params=[Param("fund", "Cut for fundamental band", "choice", None, choices=band_choices("(same as design band)", hf_only=True)),
                      Param("end_h", "Far end height", "float", 10.0, 1, 40, 0.5, unit="m"),
                      Param("tune_for", "Tune the length for", "choice", "all",
                            choices=[("All harmonic bands (compromise)", "all"), ("Fundamental band only", "fund")]),
                      Param("cp_m", "Counterpoise length", "float", 3.0, 0.3, 20, 0.5, unit="m"),
                      Param("cp_style", "Counterpoise runs", "choice", "down",
                            choices=[("Hanging down", "down"), ("Angled down and away", "angled"), ("In line with the wire", "inline")]),
                      Param("xfmr_db", "Transformer loss (matched)", "float", 0.5, 0.0, 3.0, 0.1, unit="dB")],
              desc="Half-wave wire fed at the end through a 49:1 transformer; works on harmonically related bands.",
              feed_ratio=49.0, size_label="Max wire length"))


def b_zepp(req, ex, sc):
    var = P(ex, "variant", "zepp")
    H = req.height
    a, sg = req.radius, req.sigma
    lam = req.lam
    llad = float(P(ex, "lad_len", 0.0))
    if var == "zepp":
        d = Design("zepp", "Zepp (end-fed half-wave with 1/4-wave feeders)")
        st = new_struct(req, d)
        L = 0.4880 * lam * _sc(sc, "len")
        g = st.add((-0.05 * lam, 0, H), (0, 0, H), a, sigma=sg, min_seg=3)
        st.add((0, 0, H), (L, 0, H), a, sigma=sg, min_seg=10)
        st.sources.append(Source(g, 1.0))
        ll = llad if llad > 0 else 0.25 * lam * 0.91
        d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.9, hi=1.1, label="length")]
        d.dim("Radiator", 1, L, "half-wave")
        d.dim("Quarter-wave feeder (450 ohm ladder)", 1, ll, "transforms the high end impedance to a low value")
    else:
        d = Design("zepp", "Extended Zepp (1.28 wavelength)")
        st = new_struct(req, d)
        half = 0.64 * lam * 0.985 * _sc(sc, "len")
        w0 = st.add((-half, 0, H), (0, 0, H), a, sigma=sg, min_seg=8)
        w1 = st.add((0, 0, H), (half, 0, H), a, sigma=sg, min_seg=8)
        st.sources.append(Source(w0, 1.0))
        ll = llad if llad > 0 else 0.5 * lam * 0.91
        d.dim("Radiator (centre fed)", 1, 2 * half, "1.28 wavelengths overall")
        d.dim("Feeder (450 ohm ladder)", 1, ll, "any length that keeps the line tunable; use a tuner")
    c = COAX["ladder450"]
    d.line = (c[1], c[2], c[3], ll)
    d.pol = "H"
    d.notes += ["Feeders radiate little only when balanced; keep the ladder line away from metal and run it away at right angles.",
                "The extended Zepp gives about 3 dB more gain than a half-wave dipole in the broadside direction."]
    return d


register(Spec("zepp", "Zepp / Extended Zepp", "HF wire antennas", b_zepp,
              params=[Param("variant", "Type", "choice", "zepp", choices=[("Zepp (end-fed half-wave + 1/4-wave feeder)", "zepp"), ("Extended Zepp (1.28 wavelength centre-fed)", "ext")]),
                      Param("lad_len", "Feeder length (0 = default)", "float", 0.0, 0, 60, 0.5, unit="m")],
              desc="Classic open-wire fed wires for use with a tuner."))


# =========================================================================== horizontal loop
def b_hloop(req, ex, sc):
    lam = req.lam
    shape = P(ex, "shape", "square")
    d = Design("hloop", "Horizontal full-wave loop (skywire)")
    st = new_struct(req, d)
    per = 1.03 * lam * _sc(sc, "len")
    H = req.height
    a, sg = req.radius, req.sigma
    if shape == "square":
        s = per / 4
        pts = [(-s / 2, -s / 2, H), (s / 2, -s / 2, H), (s / 2, s / 2, H), (-s / 2, s / 2, H)]
        side = f"{s:.2f} m square"
    elif shape == "delta":
        s = per / 3
        h = s * math.sqrt(3) / 2
        pts = [(-s / 2, -h / 3, H), (s / 2, -h / 3, H), (0, 2 * h / 3, H)]
        side = f"{s:.2f} m equilateral"
    else:
        n = 16
        r = per / (2 * math.pi)
        pts = regular_polygon(n, r, (0, 0, H))
        side = f"{2 * r:.2f} m diameter (16-sided)"
    ids, joints = add_polygon(st, pts, a, sg, feed_edge=0, min_seg=3)
    st.sources.append(Source(joints["feed"], 1.0))
    d.pol = "H"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.3, label="perimeter")]
    d.dim("Total wire (perimeter)", 1, per, side)
    d.dim("Feed point", 1, None, "middle of one side; 2:1 or 4:1 transformer, or 75 ohm quarter-wave section")
    d.notes += ["A full-wave loop is low noise and efficient; feedpoint resistance is about 100-130 ohm, so a 2:1 transformer or a 75 ohm quarter-wave transformer gives a good 50 ohm match.",
                "At low height the radiation is mostly high angle (NVIS). On higher harmonics it develops gain along the plane normal to the loop."]
    size_warn(d, req, per / 4 if shape == "square" else per / math.pi, "Loop span")
    return d


register(Spec("hloop", "Horizontal loop / skywire (full-wave)", "HF wire antennas", b_hloop,
              params=[Param("shape", "Shape", "choice", "square", choices=[("Square", "square"), ("Triangle (delta)", "delta"), ("Circle (16-sided)", "circle")])],
              desc="Full-wavelength closed loop in a horizontal plane.", feed_ratio=2.0, size_label="Max span"))


# =========================================================================== delta loop
def b_delta(req, ex, sc):
    lam = req.lam
    orient = P(ex, "orient", "up")
    feed = P(ex, "feed", "base")
    tilt = math.radians(float(P(ex, "tilt", 0.0)))
    az = float(P(ex, "az", 0.0))
    names = {"up": "apex up", "down": "apex down", "flat": "horizontal"}
    d = Design("delta", f"Delta loop ({names.get(orient, orient)})")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    per = 1.02 * lam * _sc(sc, "len")
    s = per / 3.0
    h = s * math.sqrt(3.0) / 2.0
    H = req.height

    def R(x, y, z):
        return rotate_xy((x, y, z), -az)

    if orient == "flat":
        pts = [R(-s / 2, -h / 3, H), R(s / 2, -h / 3, H), R(0.0, 2 * h / 3, H)]
        base_note = f"{s:.2f} m equilateral triangle in a horizontal plane"
    else:
        c, sn = math.cos(tilt), math.sin(tilt)
        if orient == "up":                  # base at the bottom, apex above (tilted loops lean toward +y)
            pts = [R(-s / 2, 0.0, H), R(s / 2, 0.0, H), R(0.0, h * sn, H + h * c)]
        else:                               # apex down: the base is the top edge, the apex is the lowest point
            pts = [R(-s / 2, h * sn, H + h * c), R(s / 2, h * sn, H + h * c), R(0.0, 0.0, H)]
        base_note = f"{s:.2f} m equilateral triangle, {h:.2f} m high" + (f", tilted {math.degrees(tilt):.0f} deg" if tilt > 0 else "")
    # segments stay close to the same length everywhere (NEC-2 wants neighbouring segments within about 5:1)
    if feed == "corner":
        # a one-segment feed wire right at the first corner (about a quarter of a normal segment long)
        p0, p1, p2 = (np.array(q, float) for q in pts)
        pf = p0 + (p1 - p0) * 0.06
        w_feed = st.add(p0, pf, a, sigma=sg, nseg=1, name="feed")
        st.add(pf, p1, a, sigma=sg, min_seg=2)
        st.add(p1, p2, a, sigma=sg, min_seg=2)
        st.add(p2, p0, a, sigma=sg, min_seg=2)
        joints = {"feed": w_feed}
    elif feed == "side":
        ids, joints = add_polygon(st, pts, a, sg, feed_edge=1, min_seg=2)
    else:
        ids, joints = add_polygon(st, pts, a, sg, feed_edge=0, min_seg=2)
    st.sources.append(Source(joints["feed"], 1.0))
    d.pol = "mixed"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.3, label="perimeter")]
    d.dim("Total wire (perimeter)", 1, per, base_note)
    d.dim("Sides", 3, s, "equal; a full wavelength of wire in all")
    d.dim("Loop height" if orient != "flat" else "Loop depth", 1, h, "")
    d.dim("Feed point", 1, None, {"base": "middle of the base wire", "corner": "close to a lower/base corner",
                                  "side": "middle of a slanted side"}[feed] +
          "; 1:1 balun, or a 75 ohm quarter-wave transformer / 2:1 unun for a 50 ohm match")
    d.notes += ["A full-wave loop has a feedpoint impedance of roughly 100-130 ohm; a 75 ohm quarter-wave section or a 2:1 transformer gives a good 50 ohm match.",
                "Apex-up with the feed in the middle of the base gives mainly horizontal polarisation; feeding at a corner or in a side shifts "
                "it toward vertical (check the Patterns tab, polarisation overlay).",
                "A vertical-plane loop radiates broadside, in both directions through the loop; the 'direction' setting is the compass bearing of one lobe.",
                "Apex down puts the high-current base on top and the low-current apex near the ground, which narrows the pattern slightly and helps "
                "low-angle radiation over poor ground.",
                "A flat (horizontal) loop at low height is a high-angle (NVIS) radiator."]
    size_warn(d, req, s, "Loop width")
    return d


register(Spec("delta", "Delta loop (full-wave triangle, selectable orientation)", "HF wire antennas", b_delta,
              params=[Param("orient", "Orientation", "choice", "up",
                            choices=[("Apex up (base at the bottom)", "up"), ("Apex down (base at the top)", "down"),
                                     ("Horizontal (flat triangle)", "flat")]),
                      Param("feed", "Feed point", "choice", "base",
                            choices=[("Middle of the base", "base"), ("Corner (near the base end)", "corner"), ("Middle of a slanted side", "side")]),
                      Param("tilt", "Tilt of the loop plane from vertical", "float", 0.0, 0, 80, 5, unit="deg"),
                      Param("az", "Direction (azimuth, broadside)", "float", 0.0, 0, 359, 5, unit="deg")],
              desc="Full-wavelength triangular loop in a vertical or horizontal plane, apex up or down, with a choice of feed point.",
              height_default=6.0, height_label="Height of the lowest point", size_label="Max side length", feed_ratio=2.0))


# =========================================================================== Lazy-H
def b_lazyh(req, ex, sc):
    lam = req.lam
    d = Design("lazyh", "Lazy-H array")
    st = new_struct(req, d)
    H = req.height
    a, sg = req.radius, req.sigma
    el = 0.625 * lam * 0.975
    sep = 0.5 * lam
    for k, z in enumerate((H, H + sep)):
        w0 = st.add((-el, 0, z), (0, 0, z), a, sigma=sg, min_seg=10)
        w1 = st.add((0, 0, z), (el, 0, z), a, sigma=sg, min_seg=10)
        st.sources.append(Source(w0, 1.0))
    d.mode = "equal"
    d.pol = "H"
    d.dim("Element wires", 4, el, "5/8 wavelength each; two collinear pairs")
    d.dim("Vertical spacing", 1, sep, "half wavelength between the pairs")
    d.dim("Phasing", 1, None, "feed both centres in phase (equal-length phasing lines to a common point)")
    d.notes += ["The Lazy-H gives about 3 dB gain over a single collinear pair, broadside to the wires.",
                "The model feeds both centres in phase with ideal sources; real phasing lines add a little loss.",
                "Needs a support structure about 0.5 wavelength tall above the lower wires."]
    size_warn(d, req, 2 * el, "Span")
    return d


register(Spec("lazyh", "Lazy-H array", "HF wire antennas", b_lazyh, desc="Two stacked pairs of collinear 5/8-wave wires fed in phase.",
              height_default=10.0, size_label="Max span", lmatch_default=True))


# =========================================================================== rhombic / V-beam
def b_rhombic(req, ex, sc):
    lam = req.lam
    Ll = float(P(ex, "leg", 4.0))
    dlt = math.radians(float(P(ex, "delta", 15.0)))
    rterm = float(P(ex, "rterm", 800.0))
    L = Ll * lam
    d = Design("rhombic", "Terminated rhombic")
    st = new_struct(req, d, needs_ground=True)
    cosa = (1 - 0.371 / Ll) / math.cos(dlt)
    cosa = min(cosa, 0.995)
    al = math.acos(cosa)
    H = req.height
    a, sg = req.radius, req.sigma
    gl = 0.2
    A1 = np.array([0, -gl / 2, H]); A2 = np.array([0, gl / 2, H])
    B = np.array([L * cosa, -L * math.sin(al) * 1.0, H]) + np.array([0, -gl / 2, 0]) * 0
    # axis is +x; A at the origin
    B = np.array([L * cosa, L * math.sin(al), H])
    Dp = np.array([L * cosa, -L * math.sin(al), H])
    C1 = np.array([2 * L * cosa, 0.1, H]); C2 = np.array([2 * L * cosa, -0.1, H])
    st.add(A2, B, a, sigma=sg, min_seg=int(Ll * 10))
    st.add(B, C1, a, sigma=sg, min_seg=int(Ll * 10))
    tg = st.add(C1, C2, a, sigma=sg, nseg=2)
    st.add(C2, Dp, a, sigma=sg, min_seg=int(Ll * 10))
    st.add(Dp, A1, a, sigma=sg, min_seg=int(Ll * 10))
    fg = st.add(A1, A2, a, sigma=sg, nseg=2)
    st.sources.append(Source(fg, 0.5))
    st.loads.append(Load(tg, 0.5, lambda f, r=rterm: r + 0j, "terminating resistor"))
    d.pol = "H"
    d.dim("Leg length", 4, L, f"{Ll:.1f} wavelengths each")
    d.dim("Leg angle from the main axis", 1, None, f"{math.degrees(al):.1f} deg (half the apex angle)")
    d.dim("Overall length", 1, 2 * L * cosa, "")
    d.dim("Overall width", 1, 2 * L * math.sin(al), "")
    d.dim("Terminating resistor", 1, None, f"{rterm:.0f} ohm non-inductive, rated at least half the transmit power")
    d.dim("Recommended height", 1, lam / (4 * math.sin(dlt)), f"for {math.degrees(dlt):.0f} deg take-off angle")
    d.notes += ["A rhombic is a broadband travelling-wave antenna; the terminating resistor absorbs the power that would otherwise reflect (about half the power is lost in it).",
                "Pattern points away from the feed toward the termination.",
                "Leg angle follows the standard relation cos(angle) = (1 - 0.371/L) / cos(take-off)."]
    d.sweep_range = (req.f_mhz * 0.7, req.f_mhz * 1.4)
    d.seg_len_hint = lam / 16
    size_warn(d, req, 2 * L * cosa, "Length")
    return d


register(Spec("rhombic", "Rhombic (terminated)", "HF wire antennas", b_rhombic,
              params=[Param("leg", "Leg length", "float", 4.0, 1.5, 8.0, 0.5, unit="wavelengths"),
                      Param("delta", "Design take-off angle", "float", 15.0, 5, 40, 1, unit="deg"),
                      Param("rterm", "Terminating resistor", "float", 800.0, 400, 1000, 25, unit="ohm")],
              desc="Large broadband directional wire array with a terminating resistor.",
              height_default=20.0, needs_ground=True, size_label="Max length", feed_ratio=16.0))


def b_vbeam(req, ex, sc):
    lam = req.lam
    Ll = float(P(ex, "leg", 3.0))
    dlt = math.radians(float(P(ex, "delta", 15.0)))
    L = Ll * lam
    d = Design("vbeam", "V-beam")
    st = new_struct(req, d, needs_ground=True)
    cosa = min((1 - 0.371 / Ll) / math.cos(dlt), 0.995)
    al = math.acos(cosa)
    H = req.height
    a, sg = req.radius, req.sigma
    gl = 0.2
    A1 = np.array([0, -gl / 2, H]); A2 = np.array([0, gl / 2, H])
    fg = st.add(A1, A2, a, sigma=sg, nseg=2)
    st.add(A2, A2 + np.array([L * cosa, L * math.sin(al), 0]), a, sigma=sg, min_seg=int(Ll * 10))
    st.add(A1, A1 + np.array([L * cosa, -L * math.sin(al), 0]), a, sigma=sg, min_seg=int(Ll * 10))
    st.sources.append(Source(fg, 0.5))
    d.pol = "H"
    d.dim("Leg length", 2, L, f"{Ll:.1f} wavelengths")
    d.dim("Included (apex) angle", 1, None, f"{2 * math.degrees(al):.1f} deg")
    d.dim("Recommended height", 1, lam / (4 * math.sin(dlt)), "")
    d.notes += ["Unterminated V-beam: bidirectional along its bisector, about 3 dB below a terminated rhombic of the same leg length.",
                "Adding a terminating resistor on each leg end to ground makes it unidirectional at the cost of gain."]
    d.sweep_range = (req.f_mhz * 0.7, req.f_mhz * 1.4)
    size_warn(d, req, L, "Leg")
    return d


register(Spec("vbeam", "V-beam", "HF wire antennas", b_vbeam,
              params=[Param("leg", "Leg length", "float", 3.0, 1.5, 8.0, 0.5, unit="wavelengths"),
                      Param("delta", "Design take-off angle", "float", 15.0, 5, 40, 1, unit="deg")],
              desc="Two long wires in a V fed at the apex; bidirectional.", height_default=20.0, needs_ground=True,
              feed_ratio=4.0, size_label="Max leg length"))


# =========================================================================== beverage
def b_beverage(req, ex, sc):
    lam = req.lam
    Ln = float(P(ex, "length", 0.0))
    L = Ln if Ln > 0 else 1.0 * lam
    rt = float(P(ex, "rterm", 500.0))
    d = Design("beverage", "Beverage")
    st = new_struct(req, d, needs_ground=True)
    h = req.height
    a, sg = req.radius, req.sigma
    lead1 = st.add((0, 0, 0), (0, 0, h), a, sigma=sg, min_seg=3)
    st.add((0, 0, h), (L, 0, h), a, sigma=sg, min_seg=12)
    lead2 = st.add((L, 0, h), (L, 0, 0), a, sigma=sg, min_seg=3)
    st.sources.append(Source(lead1, 0.0))
    st.loads.append(Load(lead2, 1.0, lambda f, r=rt: r + 0j, "termination"))
    d.rx_only = True
    d.pol = "mixed"
    d.dim("Wire", 1, L, f"{L / lam:.2f} wavelengths, {h:.1f} m above ground")
    d.dim("Termination resistor to ground", 1, None, f"{rt:.0f} ohm (use a 9:1 or 12:1 transformer at the receiver)")
    d.dim("Ground rod at the termination", 1, None, "two or more rods")
    d.notes += ["Receive-only antenna: it is lossy by design. Judge it by directivity and front-to-back ratio, not by gain.",
                "Directivity points toward the terminated end (signals arrive from there).",
                "Best on 160 m and 80 m. The model uses an approximate ground treatment for a wire this close to the ground."]
    d.sweep_range = (req.f_mhz * 0.8, req.f_mhz * 1.2)
    d.seg_len_hint = lam / 12
    size_warn(d, req, L, "Wire")
    return d


register(Spec("beverage", "Beverage (receive)", "Receive-only antennas", b_beverage,
              params=[Param("length", "Length (0 = 1 wavelength)", "float", 0.0, 0, 600, 5, unit="m"),
                      Param("rterm", "Termination", "float", 500.0, 200, 900, 25, unit="ohm")],
              desc="Long, low, terminated wire for receiving on the low bands.", height_default=2.5, rx_only=True,
              needs_ground=True, feed_ratio=9.0, size_label="Max length"))
