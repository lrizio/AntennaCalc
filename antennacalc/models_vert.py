"""Vertical antennas, loaded antennas and receive loops."""
from __future__ import annotations

import math

import numpy as np

from .common import BANDS, COAX, HF_BAND_LABELS
from .design import Design, Param, Spec, TuneTarget, register
from .mhelp import (add_polygon, band_choices, coil_fn, ground_loss_r, hf_multiband, new_struct,
                    regular_polygon, size_warn, trap_fn)
from .models_wire import P, _sc, b_dipole, b_hloop, b_longwire
from .mom import C0, Load, Source


# =========================================================================== ground plane
def b_gp(req, ex, sc):
    lam = req.lam
    nrad = int(P(ex, "nrad", 4))
    mount = P(ex, "mount", "elevated")
    droop = math.radians(float(P(ex, "droop", 45.0)))
    d = Design("gp", "Quarter-wave ground plane")
    L = 0.25 * lam * 0.96 * _sc(sc, "len")
    a, sg = req.radius, req.sigma
    if mount == "ground":
        st = new_struct(req, d, needs_ground=True)
        w = st.add((0, 0, 0), (0, 0, L), a, sigma=sg, min_seg=10)
        st.sources.append(Source(w, 0.0))
        nb = int(P(ex, "nburied", 16))
        rg = ground_loss_r(nb)
        st.loads.append(Load(w, 0.0, lambda f, r=rg: r + 0j, "buried radial system loss"))
        d.dim("Vertical radiator", 1, L, "")
        d.dim(f"Buried radials ({nb})", nb, 0.25 * lam, "quarter-wave, laid on or just under the soil")
        d.notes.append(f"Ground-mounted: the model adds an estimated {rg:.1f} ohm of ground loss for {nb} radials. More radials = less loss.")
    else:
        st = new_struct(req, d)
        h = max(req.height, 0.3)
        g = st.add((0, 0, h), (0, 0, h + 0.03), a, sigma=sg, nseg=2)
        st.sources.append(Source(g, 0.5))
        st.add((0, 0, h + 0.03), (0, 0, h + 0.03 + L), a, sigma=sg, min_seg=10)
        R = 0.25 * lam * 0.97
        for k in range(nrad):
            ang = 2 * math.pi * k / nrad
            dz = R * math.sin(droop)
            if h - dz < 0.1:
                dz = max(h - 0.1, 0)
            dx = math.sqrt(max(R * R - dz * dz, 0))
            st.add((0, 0, h), (dx * math.cos(ang), dx * math.sin(ang), h - dz), a, sigma=sg, min_seg=4)
        d.dim("Vertical radiator", 1, L, "")
        d.dim(f"Radials ({nrad})", nrad, R, f"drooping {math.degrees(droop):.0f} deg; 45 deg gives about 50 ohm")
        d.notes.append("Horizontal radials give ~36 ohm, 45 degree drooping radials ~50 ohm; with many radials the impedance falls again.")
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.2, label="radiator")]
    d.pol = "V"
    d.notes += ["Radiator length is about 71.3/f (MHz) metres; tuning shifts it for your conductor size.",
                "Low take-off angle makes this a good DX antenna; more/better radials raise efficiency."]
    size_warn(d, req, L, "Height")
    return d


register(Spec("gp", "Quarter-wave ground plane vertical", "Vertical antennas", b_gp,
              params=[Param("mount", "Mounting", "choice", "elevated", choices=[("Elevated with resonant radials", "elevated"), ("Ground-mounted with buried radials", "ground")]),
                      Param("nrad", "Number of elevated radials", "int", 4, 1, 16, 1),
                      Param("droop", "Radial droop angle", "float", 45.0, 0, 70, 5, unit="deg"),
                      Param("nburied", "Number of buried radials", "int", 16, 2, 120, 2)],
              desc="Quarter-wave vertical with radials, elevated or ground-mounted.", height_default=2.0,
              size_label="Max height"))


# =========================================================================== half-wave end-fed vertical
def b_vhw(req, ex, sc):
    lam = req.lam
    d = Design("vhw", "End-fed half-wave vertical")
    st = new_struct(req, d, needs_ground=True)
    L = 0.4850 * lam * _sc(sc, "len")
    a, sg = req.radius, req.sigma
    w = st.add((0, 0, 0.0), (0, 0, L), a, sigma=sg, min_seg=14)
    st.sources.append(Source(w, 0.0))
    nb = int(P(ex, "nburied", 16))
    rg = ground_loss_r(nb)
    st.loads.append(Load(w, 0.0, lambda f, r=rg: r + 0j, "ground loss"))
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.9, hi=1.1, label="radiator")]
    d.pol = "V"
    d.dim("Vertical radiator", 1, L, "half-wave, fed at the bottom")
    d.dim("Matching", 1, None, "49:1 or 64:1 unun, or a parallel-tuned L network at the base")
    d.notes += ["A half-wave vertical needs little ground system because the feed point is at a voltage maximum (high impedance), but the base must be insulated.",
                "Lower take-off angle than a quarter-wave vertical for the same height class."]
    size_warn(d, req, L, "Height")
    return d


register(Spec("vhw", "Half-wave end-fed vertical", "Vertical antennas", b_vhw,
              params=[Param("nburied", "Number of buried radials", "int", 4, 1, 120, 1)],
              desc="Vertical half-wave radiator fed at its base through a high-ratio transformer.",
              height_default=0.0, uses_height=False, needs_ground=True, feed_ratio=49.0, size_label="Max height"))


# =========================================================================== trap vertical
def b_trap_vertical(req, ex, sc):
    from .models_wire import _trap_legs
    fl = [req.f_mhz]
    for k in ("b2", "b3"):
        v = P(ex, k, None)
        if v and v < fl[-1]:
            fl.append(v)
    d = Design("trap_vert", f"Trap vertical ({len(fl)} bands)")
    st = new_struct(req, d, needs_ground=True)
    ws, ls = _trap_legs(st, d, req, ex, sc, fl, (0, 0, 0), (0, 0, 1), True)
    # the first section starts on the ground: feed it there
    st.sources.append(Source(ws[0], 0.0))
    nb = int(P(ex, "nburied", 16))
    rg = ground_loss_r(nb)
    st.loads.append(Load(ws[0], 0.0, lambda f, r=rg: r + 0j, "ground loss"))
    cpf = float(P(ex, "trap_c", 60.0)); q = float(P(ex, "trap_q", 150.0))
    d.tune = [TuneTarget(f"s{i}", f, "x0", lo=0.6, hi=1.6, label=f"{f:.2f} MHz section") for i, f in enumerate(fl)]
    d.pol = "V"
    d.multiband = [(f"{f:.3f} MHz", f) for f in fl]
    d.dim("Section lengths (from the base)", len(ls), None, ", ".join(f"{x:.3f} m" for x in ls))
    d.dim("Overall height", 1, sum(ls), "")
    for i, f in enumerate(fl[:-1]):
        fn, lh = trap_fn(f, cpf, q)
        d.dim(f"Trap {i + 1} ({f:.3f} MHz)", 1, None, f"L = {lh * 1e6:.2f} uH, C = {cpf:.0f} pF, X = {2 * math.pi * f * 1e6 * lh:.0f} ohm")
    d.notes += ["Traps isolate the upper sections on the higher bands and act as loading coils on the lower bands; efficiency falls on the lowest band.",
                "Radials: use a good ground system (at least 16 buried radials) for best efficiency."]
    return d


register(Spec("trap_vert", "Trap / multiband vertical", "Vertical antennas", b_trap_vertical,
              params=[Param("b2", "Second (lower) band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("b3", "Third (lower) band", "choice", None, choices=band_choices("(none)", hf_only=True)),
                      Param("trap_c", "Trap capacitor", "float", 60.0, 10, 500, 5, unit="pF"),
                      Param("trap_q", "Trap Q", "float", 150.0, 30, 400, 10),
                      Param("nburied", "Number of buried radials", "int", 16, 2, 120, 2)],
              desc="Ground-mounted vertical with parallel LC traps for two or three bands (Hustler / Cushcraft / Butternut style).",
              height_default=0.0, uses_height=False, needs_ground=True, size_label="Max height"))


# =========================================================================== Marconi / inverted-L / T
def b_marconi(req, ex, sc):
    lam = req.lam
    shape = P(ex, "shape", "invl")
    vfrac = float(P(ex, "vfrac", 0.5))
    d = Design("marconi", {"invl": "Inverted-L", "t": "T antenna", "straight": "Marconi vertical"}.get(shape, "Marconi"))
    st = new_struct(req, d, needs_ground=True)
    a, sg = req.radius, req.sigma
    Ltot = 0.25 * lam * 0.97
    if shape == "straight":
        Lv, Lh = Ltot * _sc(sc, "len"), 0.0
    else:
        Lv, Lh = Ltot * vfrac, Ltot * (1 - vfrac) * _sc(sc, "len")
    if req.max_size > 0 and shape != "straight":
        Lv_cap = req.max_size
        if Lv > Lv_cap:
            Lv, Lh = Lv_cap, Ltot - Lv_cap
    vw = st.add((0, 0, 0), (0, 0, Lv), a, sigma=sg, min_seg=8)
    st.sources.append(Source(vw, 0.0))
    nb = int(P(ex, "nburied", 32))
    rg = ground_loss_r(nb)
    st.loads.append(Load(vw, 0.0, lambda f, r=rg: r + 0j, "ground loss"))
    if shape == "invl":
        st.add((0, 0, Lv), (Lh, 0, Lv), a, sigma=sg, min_seg=6)
        d.dim("Vertical wire", 1, Lv, "")
        d.dim("Horizontal top wire", 1, Lh, "")
    elif shape == "t":
        st.add((0, 0, Lv), (Lh / 2, 0, Lv), a, sigma=sg, min_seg=4)
        st.add((0, 0, Lv), (-Lh / 2, 0, Lv), a, sigma=sg, min_seg=4)
        d.dim("Vertical wire", 1, Lv, "")
        d.dim("Top arms (each)", 2, Lh / 2, "")
    else:
        d.dim("Vertical wire", 1, Lv, "")
    if shape != "straight":
        d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.5, hi=1.5, label="top wire")]
    else:
        d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.2, label="length")]
    d.pol = "V"
    d.dim("Radial system", nb, 0.25 * lam, f"buried radials (model uses {rg:.1f} ohm ground loss)")
    d.notes += ["The top wire (or T arms) adds capacitive loading, letting you use a shorter vertical on 160 m and 80 m.",
                "The vertical part radiates the useful low-angle signal; make it as tall as you can."]
    size_warn(d, req, Lv + Lh, "Total wire")
    return d


register(Spec("marconi", "Marconi / Inverted-L / T antenna", "Vertical antennas", b_marconi,
              params=[Param("shape", "Shape", "choice", "invl", choices=[("Inverted-L", "invl"), ("T antenna", "t"), ("Straight Marconi vertical", "straight")]),
                      Param("vfrac", "Vertical share of total length", "float", 0.5, 0.15, 0.9, 0.05),
                      Param("nburied", "Number of buried radials", "int", 32, 2, 120, 2)],
              desc="Quarter-wave-class top-loaded vertical for 160 and 80 m.", height_default=0.0, uses_height=False,
              needs_ground=True, size_label="Max vertical height", band_default="160 m (1.8-2.0 MHz)"))


# =========================================================================== 5/8 vertical
def b_v58(req, ex, sc):
    lam = req.lam
    nrad = int(P(ex, "nrad", 4))
    droop = math.radians(float(P(ex, "droop", 45.0)))
    d = Design("v58", "5/8-wave vertical")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    h = max(req.height, 0.3)
    L = 0.625 * lam * 0.985 * _sc(sc, "len")
    g = st.add((0, 0, h), (0, 0, h + 0.03), a, sigma=sg, nseg=2)
    st.sources.append(Source(g, 0.5))
    st.add((0, 0, h + 0.03), (0, 0, h + 0.03 + L), a, sigma=sg, min_seg=14)
    R = 0.25 * lam * 0.97
    for k in range(nrad):
        ang = 2 * math.pi * k / nrad
        dz = min(R * math.sin(droop), max(h - 0.1, 0))
        dx = math.sqrt(max(R * R - dz * dz, 0))
        st.add((0, 0, h), (dx * math.cos(ang), dx * math.sin(ang), h - dz), a, sigma=sg, min_seg=4)
    d.pol = "V"
    d.dim("Vertical radiator", 1, L, "5/8 wavelength")
    d.dim(f"Radials ({nrad})", nrad, R, "")
    d.dim("Matching", 1, None, "series loading coil / L network at the base (see Matching panel)")
    d.notes += ["A 5/8-wave vertical concentrates energy at a lower angle than a quarter-wave (about 3 dB better on the horizon) but its feed impedance is capacitive, so it needs a base matching coil.",
                "Use the matching network shown on the Matching tab; component values are for the centre frequency."]
    size_warn(d, req, L, "Height")
    return d


register(Spec("v58", "5/8-wave vertical", "Vertical antennas", b_v58,
              params=[Param("nrad", "Number of radials", "int", 4, 2, 16, 1),
                      Param("droop", "Radial droop angle", "float", 45.0, 0, 70, 5, unit="deg")],
              desc="Tall, low-angle VHF/UHF (and HF) vertical with a matching coil.", height_default=2.0,
              lmatch_default=True, size_label="Max height", band_default="2 m (144-148 MHz)"))


# =========================================================================== J-pole / Slim Jim
def b_jpole(req, ex, sc):
    lam = req.lam
    variant = P(ex, "variant", "jpole")
    tape = variant == "tape"
    d = Design("jpole", {"jpole": "J-pole", "slim": "Slim Jim", "tape": "Tape-measure J-pole"}.get(variant, "J-pole"))
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    if tape:
        a = 0.025 / 4          # equivalent radius of a 25 mm wide flat tape
        sg = 5.0e6
    s = float(P(ex, "spacing_mm", 0.0)) / 1000.0
    if s <= 0:
        s = max(0.012 * lam, 6 * a)
    z0 = max(req.height, 0.2)
    lscale = _sc(sc, "len")
    Llong = 0.75 * lam * 0.96 * lscale
    Lstub = 0.25 * lam * 0.96 * lscale
    ht = 0.035 * lam * _sc(sc, "tap")
    ht = max(ht, 3 * a + 0.002)
    seg = lam / 20
    if variant == "slim":
        Llong = Lstub = 0.75 * lam * 0.96 * lscale
    A1 = st.add((0, 0, z0), (0, 0, z0 + ht), a, sigma=sg, min_seg=3)
    A2 = st.add((0, 0, z0 + ht), (0, 0, z0 + Llong), a, sigma=sg, min_seg=10)
    B1 = st.add((s, 0, z0), (s, 0, z0 + ht), a, sigma=sg, min_seg=3)
    B2 = st.add((s, 0, z0 + ht), (s, 0, z0 + Lstub), a, sigma=sg, min_seg=6 if variant != "slim" else 10)
    st.add((0, 0, z0), (s, 0, z0), a, sigma=sg, nseg=2)
    D = st.add((0, 0, z0 + ht), (s, 0, z0 + ht), a, sigma=sg, nseg=2)
    st.sources.append(Source(D, 0.5))
    if variant == "slim":
        st.add((0, 0, z0 + Llong), (s, 0, z0 + Llong), a, sigma=sg, nseg=2)
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.2, label="element lengths"),
              TuneTarget("tap", req.f_mhz, "r", target=req.zref, lo=0.3, hi=3.0, label="feed tap height")]
    d.pol = "V"
    d.dim("Long element", 1, Llong, "" if variant != "slim" else "both legs the same length")
    d.dim("Matching stub", 1, Lstub if variant != "slim" else None, "" if variant != "slim" else "(same legs)")
    d.dim("Spacing between the two conductors", 1, s, "centre to centre")
    d.dim("Feed tap above the bottom shorting bar", 1, ht, "adjust for lowest SWR")
    d.dim("Bottom shorting bar", 1, s, "")
    if variant == "slim":
        d.dim("Top shorting bar", 1, s, "")
    if tape:
        d.notes.append("Flat 25 mm steel tape (a tape measure) is modelled as an equivalent round conductor of 12.5 mm diameter and steel conductivity - so it is lossy.")
    d.notes += ["Feed with coax: centre conductor to the long element, shield to the stub at the tap point. A choke at the feed keeps the coax from radiating.",
                "The J-pole is a half-wave radiator end-fed through a quarter-wave shorted stub that acts as a matching transformer.",
                "Gain is about 2-3 dBi (Slim Jim slightly more); the stub and spacing set the match."]
    size_warn(d, req, Llong, "Height")
    return d


register(Spec("jpole", "J-pole / Slim Jim / tape-measure J-pole", "Vertical antennas", b_jpole,
              params=[Param("variant", "Type", "choice", "jpole", choices=[("J-pole", "jpole"), ("Slim Jim (folded)", "slim"), ("Tape-measure J-pole (25 mm steel tape)", "tape")]),
                      Param("spacing_mm", "Conductor spacing (0 = auto)", "float", 0.0, 0, 200, 1, unit="mm")],
              desc="End-fed half-wave with a quarter-wave matching stub, for VHF/UHF.", height_default=3.0,
              size_label="Max height", band_default="2 m (144-148 MHz)", feed_coax="rg58", feed_len=5.0))


# =========================================================================== collinear
def b_collinear(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "n", 3))
    d = Design("collinear", f"{n}-element collinear")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    el = 0.5 * lam * 0.96
    gap = 0.05 * lam
    z = max(req.height, 0.3)
    for k in range(n):
        w = st.add((0, 0, z), (0, 0, z + el), a, sigma=sg, min_seg=10)
        st.sources.append(Source(w, 0.5))
        z += el + gap
    d.mode = "equal"
    d.pol = "V"
    tot = n * el + (n - 1) * gap
    d.dim("Radiating elements", n, el, "half-wave each")
    d.dim("Phasing sections between elements", n - 1, gap, "coils / stubs so all elements are in phase")
    d.dim("Total height", 1, tot, "")
    d.notes += ["Elements are driven in phase (ideal phasing). Each doubling of elements adds up to 3 dB; expect about 2 dB per doubling after losses.",
                "Real Franklin or sleeve-dipole designs use phasing stubs or coils; the loss in them lowers the gain slightly."]
    size_warn(d, req, tot, "Height")
    return d


def collinear_size(req, ex, n):
    lam = req.lam
    return n * 0.5 * lam * 0.96 + (n - 1) * 0.05 * lam


register(Spec("collinear", "Collinear array (VHF/UHF)", "Vertical antennas", b_collinear,
              params=[Param("n", "Number of elements", "int", 3, 2, 8, 1)],
              desc="Stack of in-phase half-wave elements for omnidirectional gain.", height_default=4.0,
              gain_scalable=True, auto_key="n", auto_lo=2, auto_hi=8, size_fn=collinear_size, size_label="Max height",
              lmatch_default=True, band_default="2 m (144-148 MHz)"))


# =========================================================================== loaded monopole (screwdriver / hamstick / mag-mount)
def _coil_guess(lam, h, zc, a, f_mhz):
    beta = 2 * math.pi / lam
    z0 = 60.0 * (math.log(2 * h / a) - 1.0)
    z0 = max(z0, 150)
    # short monopole reactance, seen at the base
    xa = -z0 / math.tan(beta * h) if beta * h < math.pi / 2 - 0.05 else 0.0
    w = 2 * math.pi * f_mhz * 1e6
    return max(-xa, 10.0) / (w) * 1.0


def b_loaded(req, ex, sc):
    lam = req.lam
    kind = P(ex, "kind", "screw")
    h = float(P(ex, "height_m", 2.4))
    zc_frac = float(P(ex, "coil_pos", 0.35))
    q = float(P(ex, "coil_q", 200.0))
    d = Design("loaded", {"screw": "Screwdriver antenna", "ham": "Hamstick-style loaded whip", "mag": "Whip / mag-mount",
                          "res": "Mobile resonator"}.get(kind, "Loaded monopole"))
    st = new_struct(req, d, needs_ground=True)
    if req.ground.kind == "real":
        pass
    a, sg = req.radius, req.sigma
    h = min(h, req.max_size) if req.max_size > 0 else h
    if h >= 0.24 * lam:
        h = 0.25 * lam * 0.96 * _sc(sc, "len")
        w = st.add((0, 0, 0), (0, 0, h), a, sigma=sg, min_seg=8)
        st.sources.append(Source(w, 0.0))
        d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.2, label="whip length")]
        d.dim("Whip", 1, h, "full-size quarter-wave, no coil needed")
    else:
        zc = max(0.02, min(zc_frac, 0.98)) * h
        w0 = st.add((0, 0, 0), (0, 0, zc), a, sigma=sg, min_seg=4)
        w1 = st.add((0, 0, zc), (0, 0, h), a, sigma=sg, min_seg=4)
        st.sources.append(Source(w0, 0.0))
        l0 = _coil_guess(lam, h, zc, a, req.f_mhz) * _sc(sc, "coil")
        fn = coil_fn(l0, q, req.f_mhz)
        st.loads.append(Load(w0, 1.0, fn, "loading coil"))
        d.tune = [TuneTarget("coil", req.f_mhz, "x0", lo=0.03, hi=30.0, label="coil inductance")]
        d.dim("Whip height (above the mount)", 1, h, "")
        d.dim("Lower section to the coil", 1, zc, f"coil {zc_frac * 100:.0f}% of the way up")
        d.dim("Upper section above the coil", 1, h - zc, "")
        d.dim("Loading coil", 1, None, f"L = {l0 * 1e6:.1f} uH at Q = {q:.0f} (loss {2 * math.pi * req.f_mhz * 1e6 * l0 / q:.1f} ohm)")
        d.notes.append("Coil Q is the biggest efficiency factor: a Q of 200 loses about as much power as the radiation resistance of a very short whip.")
    rg = float(P(ex, "rg", 2.0))
    st.loads.append(Load(0, 0.0, lambda f, r=rg: r + 0j, "mount / ground loss"))
    d.pol = "V"
    d.dim("Ground", 1, None, f"modelled as a conducting plane (vehicle roof, radial field); {rg:.0f} ohm series loss")
    d.notes += ["Efficiency of a loaded whip rises with height and with coil Q; the base-loaded form is easier to build, centre-loaded gives better efficiency.",
                "The model assumes a large flat ground plane under the whip - on a real vehicle the roof is small, so expect a higher take-off angle and some loss.",
                "Screwdriver antennas adjust the coil by motor so one whip covers many bands - the design shows the coil for your chosen band."]
    return d


register(Spec("loaded", "Screwdriver / Hamstick / mag-mount whip / mobile resonator", "Compact antennas", b_loaded,
              params=[Param("kind", "Type", "choice", "screw", choices=[("Screwdriver (motor-tuned coil)", "screw"), ("Hamstick-style loaded whip", "ham"), ("Mag-mount / bumper whip", "mag"), ("Mobile resonator (coil near base)", "res")]),
                      Param("height_m", "Whip height", "float", 2.4, 0.2, 8.0, 0.1, unit="m"),
                      Param("coil_pos", "Coil position (fraction of height)", "float", 0.35, 0.05, 0.95, 0.05),
                      Param("coil_q", "Coil Q", "float", 200.0, 50, 500, 10),
                      Param("rg", "Mount / ground loss", "float", 2.0, 0, 30, 1, unit="ohm")],
              desc="Short mobile whip with a loading coil. The coil value needed for the chosen band is designed for you.",
              height_default=0.0, uses_height=False, needs_ground=True, ground_default="Perfect ground",
              size_label="Max whip height", band_default="20 m (14.0-14.35 MHz)", feed_ratio=1.0, feed_len=5.0))


# =========================================================================== loaded / shortened dipole
def b_loaded_dipole(req, ex, sc):
    lam = req.lam
    frac = float(P(ex, "frac", 0.6))
    cpos = float(P(ex, "coil_pos", 0.6))
    q = float(P(ex, "coil_q", 150.0))
    d = Design("loaded_dipole", "Shortened (loaded) dipole")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    half = 0.2375 * lam * frac * 1.0
    if req.max_size > 0:
        half = min(half, req.max_size / 2)
    H = req.height
    lc = half * cpos
    w = []
    for sgn in (-1, 1):
        w1 = st.add((0, 0, H) if sgn > 0 else (0, 0, H), (sgn * lc, 0, H), a, sigma=sg, min_seg=4)
        w2 = st.add((sgn * lc, 0, H), (sgn * half, 0, H), a, sigma=sg, min_seg=3)
        w.append((w1, w2))
    st.sources.append(Source(w[0][0], 0.0))
    # coil guess from the missing length
    z0 = 600.0
    beta = 2 * math.pi / lam
    xa = -z0 / math.tan(beta * half) if beta * half < math.pi / 2 - 0.05 else 0.0
    wang = 2 * math.pi * req.f_mhz * 1e6
    l0 = max(-xa, 20.0) / wang / 2.0 * _sc(sc, "coil")
    fn = coil_fn(l0, q, req.f_mhz)
    for (w1, w2) in w:
        st.loads.append(Load(w1, 1.0, fn, "loading coil"))
    d.tune = [TuneTarget("coil", req.f_mhz, "x0", lo=0.03, hi=30.0, label="coil inductance")]
    d.pol = "H"
    d.dim("Total span", 1, 2 * half, f"{frac * 100:.0f}% of a full-size dipole")
    d.dim("Each leg to the coil", 2, lc, "")
    d.dim("Each outer section", 2, half - lc, "")
    d.dim("Loading coils", 2, None, f"L = {l0 * 1e6:.1f} uH each, Q = {q:.0f}")
    d.notes += ["Shortening a dipole narrows its bandwidth and costs gain (about 1 dB at 70% size, 3 dB at 50%).",
                "Coils further from the feedpoint work better but add more mechanical stress; end-loading with a capacity hat is another option."]
    size_warn(d, req, 2 * half, "Span")
    return d


register(Spec("loaded_dipole", "Loaded / shortened dipole (and rotatable dipole)", "Compact antennas", b_loaded_dipole,
              params=[Param("frac", "Size compared with a full dipole", "float", 0.6, 0.25, 0.95, 0.05),
                      Param("coil_pos", "Coil position along each arm", "float", 0.6, 0.2, 0.95, 0.05),
                      Param("coil_q", "Coil Q", "float", 150.0, 50, 400, 10)],
              desc="Dipole with a loading coil in each arm; use a modest size for a rotatable dipole.",
              height_default=12.0, size_label="Max span", band_default="40 m (7.0-7.3 MHz)"))


# =========================================================================== stealth antennas
def b_stealth(req, ex, sc):
    var = P(ex, "variant", "flagpole")
    if var == "flagpole":
        e2 = {"kind": "mag", "height_m": float(P(ex, "pole_h", 8.0)), "coil_pos": 0.0, "coil_q": 150.0, "rg": 4.0}
        d = b_loaded(req, e2, sc)
        d.title = "Stealth flagpole vertical"
        d.dims.insert(0, __import__("antennacalc.design", fromlist=["Dim"]).Dim("Conductor inside the pole", 1, None, "a wire or tube inside a fibreglass flagpole"))
        d.notes.insert(0, "Hidden inside a non-conductive flagpole; matched at the base with an L network or loading coil.")
        return d
    if var == "attic":
        e2 = {"shape": "invv", "vangle": 150.0}
        d = b_dipole(req, e2, sc)
        d.title = "Attic dipole"
        d.warnings.append("Roof tiles, wiring and rafters detune and absorb: expect 3-6 dB loss and a lower resonant frequency than shown.")
        return d
    if var == "gutter":
        e2 = {"shape": "square"}
        d = b_hloop(req, e2, sc)
        d.title = "Gutter / eaves loop"
        d.warnings.append("A metal gutter is a lossy conductor with joints; treat the result as an upper bound.")
        return d
    d = b_longwire(req, {"length": float(P(ex, "wire_len", 0.0)), "end_h": 3.0, "rg": 10.0}, sc)
    d.title = "Hidden wire"
    return d


register(Spec("stealth", "Stealth antennas (flagpole / attic / gutter loop / hidden wire)", "Compact antennas", b_stealth,
              params=[Param("variant", "Type", "choice", "flagpole", choices=[("Flagpole vertical", "flagpole"), ("Attic dipole (inverted-V)", "attic"), ("Gutter / eaves loop", "gutter"), ("Hidden random wire", "hidden")]),
                      Param("pole_h", "Flagpole height", "float", 8.0, 3, 20, 0.5, unit="m"),
                      Param("wire_len", "Hidden wire length (0 = auto)", "float", 0.0, 0, 100, 0.5, unit="m")],
              desc="Low-profile antennas for restricted locations (HOA-friendly).", height_default=5.0,
              size_label="Max size", lmatch_default=True, needs_ground=True))


# =========================================================================== terminated receive loops
def b_rxloop(req, ex, sc):
    lam = req.lam
    kind = P(ex, "kind", "k9ay")
    w_m = float(P(ex, "width", 0.0))
    h_m = float(P(ex, "height_m", 0.0))
    rt = float(P(ex, "rterm", 390.0))
    d = Design("rxloop", {"k9ay": "K9AY loop", "flag": "Flag antenna", "pennant": "Pennant antenna", "ewe": "EWE antenna"}.get(kind, "RX loop"))
    st = new_struct(req, d, needs_ground=True)
    a, sg = req.radius, req.sigma
    z0 = 0.5
    if kind == "k9ay":
        h_m = h_m or 7.6; w_m = w_m or 15.2
        pts = [(-w_m / 2, 0, z0), (w_m / 2, 0, z0), (0, 0, z0 + h_m)]
        ids, j = add_polygon(st, pts, a, sg, gaps=[(0, 0.25, "feed"), (0, 0.75, "term")], min_seg=4)
        st.sources.append(Source(j["feed"], 1.0)); st.loads.append(Load(j["term"], 1.0, lambda f, r=rt: r + 0j, "termination"))
    elif kind == "flag":
        h_m = h_m or 3.7; w_m = w_m or 6.0
        pts = [(-w_m / 2, 0, z0), (w_m / 2, 0, z0), (w_m / 2, 0, z0 + h_m), (-w_m / 2, 0, z0 + h_m)]
        ids, j = add_polygon(st, pts, a, sg, gaps=[(0, 0.25, "feed"), (0, 0.75, "term")], min_seg=4)
        st.sources.append(Source(j["feed"], 1.0)); st.loads.append(Load(j["term"], 1.0, lambda f, r=rt: r + 0j, "termination"))
    elif kind == "pennant":
        h_m = h_m or 3.7; w_m = w_m or 6.0
        pts = [(-w_m / 2, 0, z0), (w_m / 2, 0, z0), (w_m / 2, 0, z0 + h_m)]
        ids, j = add_polygon(st, pts, a, sg, gaps=[(0, 0.25, "feed"), (0, 0.75, "term")], min_seg=4)
        st.sources.append(Source(j["feed"], 1.0)); st.loads.append(Load(j["term"], 1.0, lambda f, r=rt: r + 0j, "termination"))
    else:
        h_m = h_m or 1.8; w_m = w_m or 4.6
        v1 = st.add((0, 0, 0), (0, 0, h_m), a, sigma=sg, min_seg=3)
        st.add((0, 0, h_m), (w_m, 0, h_m), a, sigma=sg, min_seg=6)
        v2 = st.add((w_m, 0, h_m), (w_m, 0, 0), a, sigma=sg, min_seg=3)
        st.sources.append(Source(v1, 0.0))
        st.loads.append(Load(v2, 1.0, lambda f, r=rt: r + 0j, "termination"))
    d.rx_only = True
    d.pol = "V"
    d.dim("Loop width", 1, w_m, "")
    d.dim("Loop height", 1, h_m, "")
    d.dim("Termination resistor", 1, None, f"{rt:.0f} ohm, non-inductive")
    d.dim("Feed", 1, None, "small transformer (e.g. 4:1 or 9:1) into the receive coax")
    d.seg_len_hint = min(lam / 20, max(min(w_m, h_m) / 4, 0.1))
    d.notes += ["Receive-only: small terminated loops are very inefficient as transmit antennas but have good directivity and low noise pickup.",
                "Pattern is unidirectional (cardioid-like) and points away from the termination side; the model reports the computed peak direction.",
                "The gain shown is far below 0 dBi by design; compare front-to-rear ratio and directivity."]
    return d


register(Spec("rxloop", "K9AY / Flag / Pennant / EWE (terminated loops)", "Receive-only antennas", b_rxloop,
              params=[Param("kind", "Type", "choice", "k9ay", choices=[("K9AY loop", "k9ay"), ("Flag", "flag"), ("Pennant", "pennant"), ("EWE", "ewe")]),
                      Param("width", "Width (0 = default)", "float", 0.0, 0, 40, 0.1, unit="m"),
                      Param("height_m", "Height (0 = default)", "float", 0.0, 0, 30, 0.1, unit="m"),
                      Param("rterm", "Termination", "float", 390.0, 100, 1000, 10, unit="ohm")],
              desc="Small unidirectional receive antennas for the low bands.", height_default=0.0, uses_height=False,
              rx_only=True, needs_ground=True, size_label="Max size", band_default="160 m (1.8-2.0 MHz)"))
