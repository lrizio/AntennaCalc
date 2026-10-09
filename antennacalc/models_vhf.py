"""VHF/UHF/satellite antennas: halo, turnstile, eggbeater, cross-Yagi, discone, helical."""
from __future__ import annotations

import math

import numpy as np

from .design import Design, Param, Spec, TuneTarget, register
from .mhelp import add_polygon, new_struct, regular_polygon, size_warn
from .models_beam import yagi_layout, yagi_size
from .models_wire import P, _sc
from .mom import C0, Load, Source


# =========================================================================== halo
def b_halo(req, ex, sc):
    lam = req.lam
    d = Design("halo", "Halo (horizontally polarised loop)")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = req.height
    gap_deg = float(P(ex, "gap", 25.0))
    Ltot = 0.46 * lam * _sc(sc, "len")
    ang = 2 * math.pi - math.radians(gap_deg)
    r = Ltot / ang
    nseg = 24
    # circle opened at angle 0 (+x); feed opposite at angle pi
    start = math.radians(gap_deg) / 2
    pts = []
    for i in range(nseg + 1):
        t = start + ang * i / nseg
        pts.append((r * math.cos(t), r * math.sin(t), H))
    ids = []
    for i in range(nseg):
        ids.append(st.add(pts[i], pts[i + 1], a, sigma=sg, min_seg=1))
    st.sources.append(Source(ids[nseg // 2 - 1], 1.0))
    d.pol = "H"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.7, hi=1.3, label="ring length")]
    d.dim("Total conductor length", 1, Ltot, "")
    d.dim("Ring diameter", 1, 2 * r, "")
    d.dim("Gap between the ends", 1, 2 * r * math.sin(math.radians(gap_deg) / 2), "")
    d.dim("Feed", 1, None, "opposite the gap; gamma or hairpin match to 50 ohm")
    d.notes += ["The halo is a dipole bent into a ring: omnidirectional in azimuth, horizontally polarised, compact for mobile VHF/UHF weak-signal.",
                "Feed impedance is low (10-30 ohm); the auto L-match or a gamma/hairpin match brings it to 50 ohm."]
    size_warn(d, req, 2 * r, "Diameter")
    return d


register(Spec("halo", "Halo (circular horizontal loop)", "VHF/UHF/satellite antennas", b_halo,
              params=[Param("gap", "Gap angle", "float", 25.0, 5, 90, 5, unit="deg")],
              desc="Dipole bent into a ring for omni horizontal polarisation.", height_default=4.0,
              size_label="Max diameter", band_default="2 m (144-148 MHz)", lmatch_default=True))


# =========================================================================== turnstile
def b_turnstile(req, ex, sc):
    lam = req.lam
    sense = P(ex, "sense", "R")
    hh = float(P(ex, "hgt", 0.25)) * lam
    d = Design("turnstile", "Turnstile over reflector (circular polarisation)")
    st = new_struct(req, d)
    st.ground.kind = "perfect"
    a, sg = req.radius, req.sigma
    half = 0.2375 * lam * _sc(sc, "len")
    w0 = st.add((-half, 0, hh), (0, 0, hh), a, sigma=sg, min_seg=5)
    st.add((0, 0, hh), (half, 0, hh), a, sigma=sg, min_seg=5)
    st.sources.append(Source(w0, 1.0))
    z2 = hh + 0.02 * lam
    w2 = st.add((0, -half, z2), (0, 0, z2), a, sigma=sg, min_seg=5)
    st.add((0, 0, z2), (0, half, z2), a, sigma=sg, min_seg=5)
    st.sources.append(Source(w2, 1.0))
    d.mode = "currents"
    d.i_des = [1.0, -1j if sense == "R" else 1j]
    d.cp = sense
    d.pol = "CP"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.7, hi=1.3, label="dipole length")]
    d.dim("Dipole elements", 2, 2 * half, "crossed at right angles, 90 deg phased")
    d.dim("Height above the reflector", 1, hh, "quarter wave gives a hemispherical pattern")
    d.dim("Reflector", 1, 1.0 * lam, "ground plane or screen at least 1 wavelength across")
    d.dim("Phasing", 1, None, "a quarter-wave extra cable length feeds one dipole (90 deg)")
    d.notes += ["Pattern is circularly polarised straight up, with some elliptical polarisation toward the horizon. Good for LEO satellites.",
                f"Sense chosen: {'right-hand' if sense == 'R' else 'left-hand'} circular (reverse the phasing line to change).",
                "The model uses an infinite perfect reflector; a finite screen gives lower gain and a back lobe."]
    return d


register(Spec("turnstile", "Turnstile (crossed dipoles)", "VHF/UHF/satellite antennas", b_turnstile,
              params=[Param("sense", "Polarisation sense", "choice", "R", choices=[("Right-hand circular", "R"), ("Left-hand circular", "L")]),
                      Param("hgt", "Height above the reflector", "float", 0.25, 0.1, 0.5, 0.01, unit="wavelengths")],
              desc="Two crossed dipoles fed 90 degrees out of phase over a reflector.", height_default=0.0, uses_height=False,
              uses_ground=False, ground_default="Perfect ground", band_default="70 cm (430-440 MHz)", size_label="Max size"))


# =========================================================================== eggbeater
def b_eggbeater(req, ex, sc):
    lam = req.lam
    sense = P(ex, "sense", "R")
    d = Design("eggbeater", "Eggbeater (crossed loops)")
    st = new_struct(req, d)
    st.ground.kind = "perfect"
    a, sg = req.radius, req.sigma
    per = 1.05 * lam * _sc(sc, "len")
    s = per / 4
    zb = 0.22 * lam
    pts = [(-s / 2, 0, zb), (s / 2, 0, zb), (s / 2, 0, zb + s), (-s / 2, 0, zb + s)]
    ids, j = add_polygon(st, pts, a, sg, feed_edge=0, min_seg=3)
    st.sources.append(Source(j["feed"], 1.0))
    off = 0.03 * lam
    pts2 = [(0, -s / 2, zb + off), (0, s / 2, zb + off), (0, s / 2, zb + s - off), (0, -s / 2, zb + s - off)]
    ids2, j2 = add_polygon(st, pts2, a, sg, feed_edge=0, min_seg=3)
    st.sources.append(Source(j2["feed"], 1.0))
    d.mode = "currents"
    d.i_des = [1.0, -1j if sense == "R" else 1j]
    d.cp = sense
    d.pol = "CP"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.2, label="loop size")]
    d.dim("Loop perimeter", 2, per, f"{s:.3f} m per side, loops crossed at 90 degrees")
    d.dim("Height of the loop bottoms above the reflector", 1, zb, "")
    d.dim("Phasing", 1, None, "quarter-wave extra cable to one loop gives 90 deg")
    d.notes += ["Omnidirectional circular polarisation with a hemispherical lobe over the horizon, popular for satellite work.",
                "This model is an approximation of the eggbeater (two crossed full-wave loops over a reflector); real designs fold the loops to a pair of rings."]
    return d


register(Spec("eggbeater", "Eggbeater (crossed loops)", "VHF/UHF/satellite antennas", b_eggbeater,
              params=[Param("sense", "Polarisation sense", "choice", "R", choices=[("Right-hand circular", "R"), ("Left-hand circular", "L")])],
              desc="Two crossed loops for omnidirectional circular polarisation.", height_default=0.0, uses_height=False,
              uses_ground=False, ground_default="Perfect ground", band_default="70 cm (430-440 MHz)", size_label="Max size"))


# =========================================================================== crossed Yagi
def b_crossyagi(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "n", 4))
    sense = P(ex, "sense", "R")
    d = Design("crossyagi", f"Crossed {n}-element Yagi (circular)")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = max(req.height, 3.0)
    lay = yagi_layout(lam, n, sc, req.radius)
    off = 0.02 * lam
    for idx, (nm, y, L) in enumerate(lay):
        half = L / 2
        w0 = st.add((-half, y, H), (0, y, H), a, sigma=sg, min_seg=5)
        st.add((0, y, H), (half, y, H), a, sigma=sg, min_seg=5)
        if nm == "Driven":
            st.sources.append(Source(w0, 1.0))
    for idx, (nm, y, L) in enumerate(lay):
        half = L / 2
        w0 = st.add((0, y + off, H - half), (0, y + off, H), a, sigma=sg, min_seg=5)
        st.add((0, y + off, H), (0, y + off, H + half), a, sigma=sg, min_seg=5)
        if nm == "Driven":
            st.sources.append(Source(w0, 1.0))
    d.mode = "currents"
    d.i_des = [1.0, 1j if sense == "R" else -1j]
    d.cp = sense
    d.pol = "CP"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.25, label="driven elements")]
    d.opt_keys = [("rl", 0.94, 1.06), ("rs", 0.6, 1.6)] + ([("dl", 0.9, 1.1), ("ds", 0.6, 1.5)] if n >= 3 else [])
    boom = lay[-1][1] - lay[0][1]
    d.dim("Boom length", 1, boom, "")
    for nm, y, L in lay:
        d.dim(f"{nm} (horizontal and vertical element)", 2, L, f"{y - lay[0][1]:+.3f} m from the reflector end")
    d.dim("Phasing", 1, None, "quarter-wave extra cable to one Yagi (90 deg) with a 2-way power divider")
    d.notes += ["Two Yagis on the same boom, one horizontal and one vertical, fed 90 degrees apart for circular polarisation; elevation rotor needed for LEO.",
                "Circular gain (dBic) is about the same as a single linear Yagi's gain."]
    size_warn(d, req, boom, "Boom")
    return d


register(Spec("crossyagi", "Cross-Yagi (circular polarisation)", "VHF/UHF/satellite antennas", b_crossyagi,
              params=[Param("n", "Elements per Yagi", "int", 4, 2, 12, 1),
                      Param("sense", "Polarisation sense", "choice", "R", choices=[("Right-hand circular", "R"), ("Left-hand circular", "L")])],
              desc="Two orthogonal Yagis fed in phase quadrature, for satellites and EME.", height_default=4.0,
              gain_scalable=True, auto_key="n", auto_lo=2, auto_hi=12, size_fn=yagi_size, size_label="Max boom length",
              band_default="70 cm (430-440 MHz)", ground_default="Free space (no ground)"))


# =========================================================================== discone
def b_discone(req, ex, sc):
    lam = req.lam
    flo = float(P(ex, "f_low", 0.0)) or (req.f_lo if req.f_lo > 0 else req.f_mhz * 0.7)
    lam_lo = C0 / (flo * 1e6)
    d = Design("discone", "Discone")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    slant = 0.25 * lam_lo * 0.95
    half_ang = math.radians(float(P(ex, "cone", 30.0)))
    disc_r = 0.7 * slant
    hc = slant * math.cos(half_ang)
    rc = slant * math.sin(half_ang)
    H = max(req.height, hc + 1.0)
    gapw = 0.012 * lam_lo
    nrad = int(P(ex, "nwires", 8))
    apex = (0, 0, H)
    g = st.add(apex, (0, 0, H + gapw), a, sigma=sg, nseg=2)
    st.sources.append(Source(g, 0.5))
    for k in range(nrad):
        t = 2 * math.pi * k / nrad
        st.add(apex, (rc * math.cos(t), rc * math.sin(t), H - hc), a, sigma=sg, min_seg=6)
        st.add((0, 0, H + gapw), (disc_r * math.cos(t), disc_r * math.sin(t), H + gapw), a, sigma=sg, min_seg=4)
    d.pol = "V"
    d.sweep_range = (flo * 0.95, max(req.f_hi, flo * 3.0))
    d.seg_len_hint = (C0 / (d.sweep_range[1] * 1e6)) / 8
    d.dim("Cone slant length", 1, slant, f"{math.degrees(half_ang):.0f} deg half-angle; quarter-wave at {flo:.1f} MHz")
    d.dim("Cone base diameter", 1, 2 * rc, "")
    d.dim("Disc diameter", 1, 2 * disc_r, "about 0.7x the cone slant length")
    d.dim("Cone height", 1, hc, "")
    d.dim("Feed gap (disc to cone apex)", 1, gapw, "coax centre to the disc, shield to the cone")
    d.notes += ["A discone is a very wideband omnidirectional antenna (about 10:1 frequency range) with vertical polarisation and a slightly upward-tilted pattern.",
                "Set the band to 'Custom range' and enter your lowest frequency in 'Lowest design frequency'; lower frequency = bigger cone.",
                "Model uses 8 wires each for the cone and disc; a solid surface would be a little better."]
    size_warn(d, req, 2 * rc, "Cone diameter")
    return d


register(Spec("discone", "Discone (wideband)", "VHF/UHF/satellite antennas", b_discone,
              params=[Param("f_low", "Lowest design frequency (0 = range start)", "float", 0.0, 0, 3000, 1, unit="MHz"),
                      Param("cone", "Cone half-angle", "float", 30.0, 20, 60, 1, unit="deg"),
                      Param("nwires", "Wires per surface", "int", 8, 6, 16, 2)],
              desc="Very wideband omni for scanners and general coverage.", height_default=3.0, custom_range=True,
              size_label="Max diameter", band_default="Custom range"))


# =========================================================================== helical whip / rubber duck
def b_duck(req, ex, sc):
    from .mhelp import coil_fn
    lam = req.lam
    d = Design("duck", "Rubber duck / helical whip (modelled as a distributed-coil whip)")
    st = new_struct(req, d)
    st.ground.kind = "free"
    a, sg = req.radius, req.sigma
    hl = float(P(ex, "length_mm", 0.0)) / 1000.0
    if hl <= 0:
        hl = 0.09 * lam if lam > 0.5 else 0.12 * lam
    q = float(P(ex, "coil_q", 80.0))
    body = float(P(ex, "body", 0.20)) * lam
    gap = st.add((0, 0, -0.003), (0, 0, 0.0), a, sigma=sg, nseg=1)
    w0 = st.add((0, 0, 0.0), (0, 0, hl * 0.5), a, sigma=sg, min_seg=3)
    w1 = st.add((0, 0, hl * 0.5), (0, 0, hl), a, sigma=sg, min_seg=3)
    st.add((0, 0, -0.003), (0, 0, -0.003 - body), a, sigma=sg, min_seg=6)
    st.sources.append(Source(gap, 1.0))
    # inductance needed for a short whip over a body: initial guess then tuned
    w = 2 * math.pi * req.f_mhz * 1e6
    l0 = 1.2e-6 * (lam / 2.07) * _sc(sc, "coil")
    st.loads.append(Load(w0, 1.0, coil_fn(l0, q, req.f_mhz), "helix inductance"))
    d.tune = [TuneTarget("coil", req.f_mhz, "x0", lo=0.02, hi=60.0, label="helix inductance")]
    d.pol = "V"
    dia = float(P(ex, "dia_mm", 9.0)) / 1000.0
    # winding estimate from the solenoid formula L = mu0 N^2 A / l_eff
    area = math.pi * (dia / 2) ** 2
    nt = math.sqrt(l0 * hl / (4e-7 * math.pi * area)) if hl > 0 else 0
    d.dim("Helix height", 1, hl, "")
    d.dim("Inductance needed", 1, None, f"{l0 * 1e6:.2f} uH (about {nt:.0f} turns of {dia * 1000:.0f} mm diameter wound over the {hl * 1000:.0f} mm height; first estimate)")
    d.dim("Body (counterpoise) length", 1, body, "the radio chassis and your hand act as the other half")
    d.notes += ["A normal-mode helix behaves like a short whip with distributed inductance; here the helix is represented by one lumped inductor at mid-height with the stated Q, so the number of turns is a first estimate - trim on an analyser.",
                "Efficiency is low (gain -3 to -6 dBi typical) because the radiator is far smaller than a quarter-wave."]
    return d


register(Spec("duck", "Rubber duck / helical whip", "VHF/UHF/satellite antennas", b_duck,
              params=[Param("length_mm", "Helix height (0 = default)", "float", 0.0, 0, 400, 5, unit="mm"),
                      Param("dia_mm", "Helix diameter", "float", 9.0, 4, 30, 0.5, unit="mm"),
                      Param("coil_q", "Helix Q", "float", 80.0, 20, 300, 5),
                      Param("body", "Body length", "float", 0.20, 0.05, 0.5, 0.01, unit="wavelengths")],
              desc="Short helically wound whip as fitted to handhelds.", height_default=0.0, uses_height=False,
              uses_ground=False, ground_default="Free space (no ground)", band_default="2 m (144-148 MHz)",
              size_label="Max length", lmatch_default=True))


# =========================================================================== axial-mode helix
def b_helix(req, ex, sc):
    lam = req.lam
    nt = int(P(ex, "n", 8))
    sense = P(ex, "sense", "R")
    d = Design("helix", f"{nt}-turn axial-mode helix")
    st = new_struct(req, d)
    st.ground.kind = "perfect"
    a, sg = req.radius, req.sigma
    C = 1.0 * lam * _sc(sc, "len")
    rad = C / (2 * math.pi)
    S = 0.23 * lam
    steps = 16
    N = nt * steps
    pts = []
    sgn = 1 if sense == "R" else -1
    for i in range(N + 1):
        t = sgn * 2 * math.pi * i / steps
        pts.append((rad * math.cos(t), rad * math.sin(t), S * i / steps))
    # ramp the first quarter turn down to the reflector
    pts[0] = (rad, 0, 0.0)
    w0 = None
    for i in range(N):
        w = st.add(pts[i], pts[i + 1], a, sigma=sg, min_seg=1)
        if i == 0:
            w0 = w
    st.sources.append(Source(w0, 0.0))
    d.cp = sense
    d.pol = "CP"
    d.tune = []
    length = nt * S
    gain_est = 10 * math.log10(15 * nt * (C / lam) ** 2 * (S / lam))
    d.dim("Helix diameter", 1, 2 * rad, f"circumference {C:.3f} m (1 wavelength)")
    d.dim("Turn spacing", 1, S, "0.23 wavelength (about 13 degree pitch)")
    d.dim("Axial length", 1, length, f"{nt} turns")
    d.dim("Wire length", 1, nt * math.sqrt(C ** 2 + S ** 2), "")
    d.dim("Ground plane diameter", 1, 0.9 * lam, "at least 0.75 wavelength; model assumes an infinite reflector")
    d.notes += [f"Kraus gain estimate for this helix: {gain_est:.1f} dBic. Beamwidth is about 52 deg / (C/lam x sqrt(N x S/lam)).",
                "Feed impedance of an axial-mode helix is 100-200 ohm; use a tapered first turn or a quarter-wave transformer to reach 50 ohm.",
                f"Winding sense: {'right' if sense == 'R' else 'left'}-hand."]
    size_warn(d, req, length, "Length")
    return d


def helix_size(req, ex, n):
    return n * 0.23 * req.lam


register(Spec("helix", "Helical antenna (axial mode)", "VHF/UHF/satellite antennas", b_helix,
              params=[Param("n", "Number of turns", "int", 8, 2, 20, 1),
                      Param("sense", "Winding sense", "choice", "R", choices=[("Right-hand", "R"), ("Left-hand", "L")])],
              desc="Circularly polarised end-fire antenna over a ground plane; gain set by the number of turns.",
              height_default=0.0, uses_height=False, uses_ground=False, ground_default="Perfect ground",
              gain_scalable=True, auto_key="n", auto_lo=2, auto_hi=20, size_fn=helix_size, size_label="Max length",
              band_default="70 cm (430-440 MHz)", lmatch_default=True))
