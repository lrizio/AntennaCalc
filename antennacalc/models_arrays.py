"""Broadside / end-fire wire arrays: half-square and Bobtail curtains, Bruce array, Sterba curtain, W8JK."""
from __future__ import annotations

import math

import numpy as np

from .design import Design, Param, Spec, TuneTarget, register
from .mhelp import ground_loss_r, new_struct, rotate_xy, size_warn
from .models_wire import P, _sc
from .mom import Load, Source


REFL_SPACING = 0.25
REFL_LONGER = 1.03


def _az_param(label="Direction (azimuth)"):
    return Param("az", label, "float", 0.0, 0, 359, 5, unit="deg")


# =========================================================================== half-square / Bobtail curtain
def b_curtain(req, ex, sc):
    lam = req.lam
    n = 2 if P(ex, "variant", "bobtail") == "halfsq" else 3
    az = float(P(ex, "az", 0.0))
    nrad = int(P(ex, "nburied", 16))
    name = "Half-square" if n == 2 else "Bobtail curtain"
    d = Design("curtain", name)
    st = new_struct(req, d, needs_ground=True)
    a, sg = req.radius, req.sigma
    s = _sc(sc, "len")
    L = 0.25 * lam * 0.97 * s
    sp = 0.5 * lam * s
    hb = max(req.height, 0.3)
    top = hb + L
    feed = n // 2 if n % 2 else 0                  # odd: centre element (Bobtail), even: an end element (half-square)
    xs = [(k - (n - 1) / 2.0) * sp for k in range(n)]

    def R(x, z):
        return rotate_xy((x, 0.0, z), -az)

    for k, x in enumerate(xs):
        z0 = 0.0 if k == feed else hb
        w = st.add(R(x, z0), R(x, top), a, sigma=sg, min_seg=8, name="vertical")
        if k == feed:
            st.sources.append(Source(w, 0.0))
            rg = ground_loss_r(nrad)
            st.loads.append(Load(w, 0.0, lambda f, r=rg: r + 0j, "ground loss"))
    for k in range(n - 1):
        st.add(R(xs[k], top), R(xs[k + 1], top), a, sigma=sg, min_seg=10, name="top wire")
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.85, hi=1.15, label="element / wire length")]
    d.pol = "V"
    d.dim("Vertical elements", n, L, f"quarter-wave each, hanging from the top wire (lower ends {hb:.1f} m above ground, open)")
    d.dim("Top wire sections", n - 1, sp, "half-wave each, between the tops of adjacent verticals")
    d.dim("Top wire (total)", 1, (n - 1) * sp, "")
    d.dim("Feed point", 1, None, f"base of {'the centre' if n % 2 else 'one end'} vertical, against a ground / radial system")
    d.dim("Radials", nrad, 0.25 * lam, f"model assumes {rg:.1f} ohm ground loss at the feed")
    d.dim("Support height", 1, top, "top wire height")
    d.notes += ["The verticals carry in-phase current (all radiate) while the half-wave top-wire sections carry opposing currents and cancel, giving a bidirectional broadside "
                "pattern with the strong current maximum at the top, away from lossy ground.",
                "The base of the fed vertical is a high-impedance (voltage-fed) point, typically several kilohms - use an L-network or parallel-tuned circuit; narrow bandwidth is normal.",
                "A half-square is the 2-vertical case; the Bobtail adds a third element so two half-squares share the centre vertical (about 1 dB more gain).",
                "Maximum radiation is broadside to the top wire, in both directions (direction shown is one of the two lobes)."]
    size_warn(d, req, (n - 1) * sp, "Top wire span")
    return d


register(Spec("curtain", "Half-square / Bobtail curtain (broadside vertical array)", "Directional beams", b_curtain,
              params=[Param("variant", "Array", "choice", "bobtail", choices=[("Bobtail curtain (3 verticals)", "bobtail"), ("Half-square (2 verticals)", "halfsq")]),
                      _az_param("Broadside direction (azimuth)"),
                      Param("nburied", "Radials", "int", 16, 2, 120, 2)],
              desc="Quarter-wave verticals joined at the top by half-wave wires, fed at one base: bidirectional broadside gain at a low angle.",
              height_default=2.0, height_label="Lower-end height above ground", needs_ground=True,
              size_label="Max span", lmatch_default=True, band_default="40 m (7.0-7.3 MHz)"))


# =========================================================================== Bruce array
def b_bruce(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "n", 6))
    az = float(P(ex, "az", 0.0))
    nrad = int(P(ex, "nburied", 16))
    d = Design("bruce", f"Bruce array ({n} vertical sections)")
    st = new_struct(req, d, needs_ground=True)
    a, sg = req.radius, req.sigma
    s = _sc(sc, "len")
    q = 0.25 * lam * 1.03 * s
    hb = max(req.height, 0.3)

    def R(x, z):
        return rotate_xy((x, 0.0, z), -az)

    x = 0.0
    up = True
    for k in range(n):
        z0, z1 = (hb, hb + q) if up else (hb + q, hb)
        if k == 0:
            w = st.add(R(0.0, 0.0), R(0.0, hb + q), a, sigma=sg, min_seg=8, name="vertical")     # includes the feed lead
            st.sources.append(Source(w, 0.0))
            rg = ground_loss_r(nrad)
            st.loads.append(Load(w, 0.0, lambda f, r=rg: r + 0j, "ground loss"))
        else:
            st.add(R(x, z0), R(x, z1), a, sigma=sg, min_seg=8, name="vertical")
        if k < n - 1:
            zt = hb + q if up else hb
            st.add(R(x, zt), R(x + q, zt), a, sigma=sg, min_seg=8, name="horizontal")
            x += q
            up = not up
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.9, hi=1.15, label="section length")]
    d.pol = "V"
    d.dim("Vertical sections", n, q, "quarter-wave, alternately joined at the top and the bottom")
    d.dim("Horizontal sections", n - 1, q, "quarter-wave, alternately along the top and the bottom")
    d.dim("Total wire", 1, n * q + (n - 1) * q, "one continuous wire")
    d.dim("Overall width", 1, (n - 1) * q, "")
    d.dim("Feed point", 1, None, "base of the first vertical, against a ground / radial system; far end open")
    d.dim("Radials", nrad, 0.25 * lam, f"model assumes {rg:.1f} ohm ground loss at the feed")
    d.notes += ["The wire is an odd number of quarter waves long and end-fed, so the feed point is a current maximum; the model gives a few hundred ohms "
                "(roughly 250-400 ohm), so the default 4:1 transformer or an L-network brings it near 50 ohm.",
                "Each vertical adds in phase; the horizontal sections partly cancel in pairs. Gain rises with the number of sections.",
                "Pattern is bidirectional, broadside to the line of the array; in a long end-fed Bruce the current falls toward the far end, "
                "so the two lobes become unequal (front-to-back shown is the difference)."]
    size_warn(d, req, (n - 1) * q, "Width")
    return d


def bruce_size(req, ex, n):
    return (n - 1) * 0.25 * req.lam


register(Spec("bruce", "Bruce array (meandered broadside vertical array)", "Directional beams", b_bruce,
              params=[Param("n", "Vertical sections", "int", 6, 2, 14, 1),
                      _az_param("Broadside direction (azimuth)"),
                      Param("nburied", "Radials", "int", 16, 2, 120, 2)],
              desc="One long wire folded into alternate quarter-wave vertical and horizontal runs for broadside gain.",
              height_default=2.0, height_label="Lower-rail height above ground", needs_ground=True,
              gain_scalable=True, auto_key="n", auto_lo=2, auto_hi=14, size_fn=bruce_size, size_label="Max width",
              feed_ratio=4.0, band_default="40 m (7.0-7.3 MHz)"))


# =========================================================================== Sterba curtain
def b_sterba(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "nsec", 4))
    refl = bool(P(ex, "reflector", False))
    az = float(P(ex, "az", 0.0))
    d = Design("sterba", f"Sterba curtain ({n} x 2 half-wave sections)" + (" with reflector" if refl else ""))
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    s = _sc(sc, "len")
    el = 0.49 * lam * s                      # each half-wave section
    gap = 0.02 * lam
    pitch = el + gap
    H = req.height
    rows = [H, H + 0.5 * lam]
    span = n * pitch - gap

    def R(x, y, z):
        return rotate_xy((x, y, z), -az)

    for z in rows:
        for k in range(n):
            xc = (k - (n - 1) / 2.0) * pitch
            w0 = st.add(R(xc - el / 2, 0.0, z), R(xc, 0.0, z), a, sigma=sg, min_seg=5, name="radiator")
            st.add(R(xc, 0.0, z), R(xc + el / 2, 0.0, z), a, sigma=sg, min_seg=5, name="radiator")
            st.sources.append(Source(w0, 1.0))
    if refl:
        el2 = el * REFL_LONGER
        pitch2 = pitch * REFL_LONGER
        for z in rows:
            for k in range(n):
                xc = (k - (n - 1) / 2.0) * pitch2
                st.add(R(xc - el2 / 2, -REFL_SPACING * lam, z), R(xc + el2 / 2, -REFL_SPACING * lam, z), a, sigma=sg, min_seg=10, name="reflector")
        d.dim("Reflector sections", 2 * n, el2, "3% longer, a quarter wavelength behind the driven curtain, not fed")
    d.mode = "equal"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.85, hi=1.15, label="section length")]
    d.pol = "H"
    d.dim("Driven half-wave sections", 2 * n, el, f"{n} collinear sections in each of two rows")
    d.dim("Row spacing", 1, 0.5 * lam, "half wavelength between the two rows")
    d.dim("Phasing lines", 2 * n, 0.5 * lam, "half-wave open-wire lines (transposed) so all sections are driven in phase")
    d.dim("Height of the lower row", 1, H, "about half a wavelength gives a good take-off angle")
    d.dim("Top of the array", 1, H + 0.5 * lam, "")
    d.notes += ["Classic layout: quarter-wave end sections, half-wave centre sections, transposed half-wave phasing lines; "
                "this model puts every half-wave section on an ideal in-phase source, so the feed impedance shown is the parallel combination.",
                "In practice the corner or bottom-centre feed on open-wire line is typically several hundred ohms (about 600-1000 ohm); use a matching section or tuner.",
                "Single-band: gain is about 2 dB per added half-wave section; bandwidth is a few percent.",
                "Without the reflector the pattern is bidirectional (broadside); with the reflector it is a single forward lobe."]
    size_warn(d, req, span, "Width")
    return d


def sterba_size(req, ex, n):
    return n * 0.49 * req.lam


register(Spec("sterba", "Sterba curtain (stacked collinear half-wave array)", "HF wire antennas", b_sterba,
              params=[Param("nsec", "Half-wave sections per row", "int", 4, 2, 10, 1),
                      Param("reflector", "Add reflector curtain", "bool", False),
                      _az_param("Broadside direction (azimuth)")],
              desc="Two rows of in-phase half-wave sections one half wavelength apart: broadside horizontal gain, optionally with a reflector.",
              height_default=10.0, gain_scalable=True, auto_key="nsec", auto_lo=2, auto_hi=10, size_fn=sterba_size,
              size_label="Max width", lmatch_default=True))


# =========================================================================== W8JK
def b_w8jk(req, ex, sc):
    lam = req.lam
    spc = float(P(ex, "spacing", 0.125))
    ln = float(P(ex, "elen", 0.5))
    az = float(P(ex, "az", 0.0))
    d = Design("w8jk", f"W8JK flat-top ({ln:g} wavelength elements, {spc:g} wavelength spacing)")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    s = _sc(sc, "len")
    half = ln * lam / 2 * 0.95 * s
    H = req.height
    sy = spc * lam

    def R(x, y, z):
        return rotate_xy((x, y, z), -az)

    # element 1 runs -x -> +x, element 2 is drawn +x -> -x so equal source voltages drive opposite-direction currents
    w0 = st.add(R(-half, 0.0, H), R(0.0, 0.0, H), a, sigma=sg, min_seg=8, name="element 1")
    st.add(R(0.0, 0.0, H), R(half, 0.0, H), a, sigma=sg, min_seg=8, name="element 1")
    v0 = st.add(R(half, sy, H), R(0.0, sy, H), a, sigma=sg, min_seg=8, name="element 2")
    st.add(R(0.0, sy, H), R(-half, sy, H), a, sigma=sg, min_seg=8, name="element 2")
    st.sources.append(Source(w0, 1.0))
    st.sources.append(Source(v0, 1.0))
    d.mode = "equal"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.25, label="element length")]
    d.pol = "H"
    d.dim("Elements", 2, 2 * half, f"{ln:g} wavelength dipoles, parallel and level")
    d.dim("Element spacing", 1, sy, f"{spc:g} wavelength between the two dipoles")
    d.dim("Feed", 1, None, "both centres fed from one point, 180 degrees out of phase (transposed / crossed section of line)")
    d.dim("Height", 1, H, "")
    d.notes += ["Two close-spaced, anti-phase dipoles give bidirectional end-fire gain along the line that joins them; "
                "the lobes point along the spacing direction, not along the wires.",
                "Gain is about 3 dB over a dipole at 1/8 wavelength spacing and rises slightly at 1/4; it is a low-impedance array "
                "(the feed point is a few tens of ohms with large reactance), so a matching network is needed.",
                "Longer (about 0.625 wavelength) elements add roughly 1 dB and let the antenna work on its second harmonic band as well."]
    size_warn(d, req, 2 * half, "Element length")
    return d


register(Spec("w8jk", "W8JK flat-top (bidirectional end-fire pair)", "Directional beams", b_w8jk,
              params=[Param("spacing", "Element spacing", "float", 0.125, 0.05, 0.25, 0.025, unit="wavelengths", decimals=3),
                      Param("elen", "Element length", "float", 0.5, 0.4, 0.7, 0.025, unit="wavelengths", decimals=3),
                      _az_param("Direction (azimuth)")],
              desc="Two parallel horizontal dipoles fed out of phase: bidirectional end-fire, about 3 dB gain.",
              height_default=12.0, size_label="Max element length", lmatch_default=True))
