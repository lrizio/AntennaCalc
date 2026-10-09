"""Closed-form and hybrid models: dish, horn, patch, slot array, magnetic loop, receive antennas, dummy load."""
from __future__ import annotations

import math

import numpy as np
from scipy.special import j1

from .analytic import (AnalyticModel, angle_off, boresight, flat_match, resonator_z, unit_vec)
from .design import Design, Param, Spec, TuneTarget, register
from .mhelp import new_struct, size_warn
from .models_wire import P, _sc
from .mom import C0, Load, Source


def _db(x):
    return 10 * np.log10(np.maximum(x, 1e-12))


# =========================================================================== parabolic dish
def b_dish(req, ex, sc):
    lam = req.lam
    eta = float(P(ex, "eta", 0.55))
    fd = float(P(ex, "fd", 0.40))
    D = float(P(ex, "dia", 0.0))
    el = float(P(ex, "el", 0.0))
    d = Design("dish", "Parabolic dish")
    if D <= 0:
        if req.target_gain is not None:
            D = lam / math.pi * math.sqrt(10 ** (req.target_gain / 10) / eta)
        else:
            D = 1.0
    if req.max_size > 0 and D > req.max_size:
        d.warnings.append(f"Gain target needs a {D:.2f} m dish; limited to your {req.max_size:.2f} m size limit.")
        D = req.max_size
    gpk = _db(eta * (math.pi * D / lam) ** 2)
    b = boresight(0.0, el)
    hp = math.degrees(70 * lam / D) * math.pi / 180 * 180 / math.pi / 1.0
    hpbw = 70.0 * lam / D

    def gain_fn(th, ph):
        a = angle_off(th, ph, b)
        u = math.pi * D / lam * np.sin(a)
        u = np.where(np.abs(u) < 1e-6, 1e-6, u)
        af = (2 * j1(u) / u)
        gdb = gpk + 20 * np.log10(np.maximum(np.abs(af), 1e-3))
        gdb = np.where(a > math.pi / 2, gpk - 55.0, gdb)
        return np.maximum(gdb, gpk - 55.0)
    d.analytic = AnalyticModel(gain_fn, flat_match(1.15), pol="mixed", eta=1.0)
    F = fd * D
    depth = D * D / (16 * F)
    ang = 2 * math.degrees(math.atan(1 / (4 * fd)))
    d.pol = "mixed"
    d.dim("Dish diameter", 1, D, f"{D / lam:.1f} wavelengths")
    d.dim("Focal length (F)", 1, F, f"f/D = {fd:.2f}")
    d.dim("Dish depth", 1, depth, "")
    d.dim("Feed illumination angle (full)", 1, None, f"{ang:.0f} deg subtended by the dish edge - choose a feed with its -10 dB beamwidth near this")
    d.dim("Surface accuracy", 1, lam / 16, "RMS error under lambda/16 keeps surface loss under 1 dB")
    d.extra["hpbw"] = hpbw
    d.notes += [f"Gain {gpk:.1f} dBi at {eta * 100:.0f}% aperture efficiency (typical 50-65% with a well-matched feed). Half-power beamwidth about {hpbw:.1f} deg.",
                "Pattern is the Airy (uniformly illuminated) pattern; real dishes have lower sidelobes (-20 to -25 dB) because of the feed taper.",
                "Boresight is set by the elevation angle you enter; azimuth 0 deg."]
    size_warn(d, req, D, "Dish")
    return d


register(Spec("dish", "Parabolic dish", "Microwave antennas", b_dish,
              params=[Param("dia", "Diameter (0 = from gain target)", "float", 0.0, 0, 30, 0.05, unit="m"),
                      Param("fd", "f/D ratio", "float", 0.40, 0.25, 0.8, 0.01),
                      Param("eta", "Aperture efficiency", "float", 0.55, 0.3, 0.75, 0.01),
                      Param("el", "Boresight elevation", "float", 0.0, 0, 90, 1, unit="deg")],
              desc="Prime-focus reflector for microwaves, satellite and EME.", gain_scalable=True, uses_height=False,
              uses_ground=False, analytic=True, size_label="Max dish diameter", band_default="13 cm (2300-2450 MHz)", uses_material=False))


# =========================================================================== horn
WAVEGUIDES = [  # name, a mm, b mm, f_lo GHz, f_hi GHz
    ("WR-340", 86.36, 43.18, 2.2, 3.3), ("WR-284", 72.14, 34.04, 2.6, 3.95), ("WR-229", 58.17, 29.08, 3.3, 4.9),
    ("WR-187", 47.55, 22.15, 3.95, 5.85), ("WR-137", 34.85, 15.80, 5.85, 8.2), ("WR-112", 28.50, 12.62, 7.05, 10.0),
    ("WR-90", 22.86, 10.16, 8.2, 12.4), ("WR-62", 15.80, 7.90, 12.4, 18.0), ("WR-42", 10.67, 4.32, 18.0, 26.5),
]


def pick_wg(f_ghz: float):
    best = None
    for w in WAVEGUIDES:
        if w[3] <= f_ghz <= w[4]:
            return w
        if best is None or abs(f_ghz - 0.5 * (w[3] + w[4])) < abs(f_ghz - 0.5 * (best[3] + best[4])):
            best = w
    return best


def b_horn(req, ex, sc):
    lam = req.lam
    f_ghz = req.f_mhz / 1000
    wg = pick_wg(f_ghz)
    g = req.target_gain if req.target_gain is not None else float(P(ex, "gain", 15.0))
    eta = 0.51
    d = Design("horn", "Pyramidal horn")
    A = 10 ** (g / 10) * lam * lam / (4 * math.pi * eta)
    a1 = math.sqrt(A * math.sqrt(1.5))      # a1/b1 = sqrt(1.5) for the optimum horn
    b1 = a1 / math.sqrt(1.5)
    rho = a1 * a1 / (3 * lam)
    gpk = _db(eta * 4 * math.pi * a1 * b1 / lam ** 2)
    hpe = 56.0 * lam / b1
    hph = 67.0 * lam / a1
    # horn mouth at +x with E in the vertical plane
    b = boresight(0, float(P(ex, "el", 0.0)))

    def gain_fn(th, ph):
        x, y, z = unit_vec(th, ph)
        ae = np.degrees(np.arctan2(z, y))
        ah = np.degrees(np.arctan2(x, y))
        gdb = gpk - 12 * (ae / hpe) ** 2 - 12 * (ah / hph) ** 2
        gdb = np.maximum(gdb, gpk - 32.0)
        return np.where(y < 0, gpk - 40.0, gdb)
    d.analytic = AnalyticModel(gain_fn, flat_match(1.12), pol="V", eta=1.0)
    d.pol = "V"
    d.dim("Aperture width (H-plane) a1", 1, a1, f"HPBW {hph:.0f} deg")
    d.dim("Aperture height (E-plane) b1", 1, b1, f"HPBW {hpe:.0f} deg")
    d.dim("Slant length", 1, rho * 1.03, "optimum horn: a1^2 = 3 lambda L, b1^2 = 2 lambda L")
    d.dim(f"Feeding waveguide {wg[0]}", 1, wg[1] / 1000, f"{wg[1]:.1f} x {wg[2]:.2f} mm inside, {wg[3]}-{wg[4]} GHz")
    d.dim("Waveguide cutoff", 1, None, f"{C0 / (2 * wg[1] / 1000) / 1e9:.2f} GHz")
    d.notes += [f"Gain {gpk:.1f} dBi (51% aperture efficiency, optimum-gain proportions).",
                "Used as a standard-gain reference, a dish feed, or a direct antenna for microwave links.",
                "Pattern shown is a Gaussian approximation to the main lobe with a floor at -32 dB."]
    size_warn(d, req, a1, "Aperture")
    return d


register(Spec("horn", "Horn antenna / feed horn", "Microwave antennas", b_horn,
              params=[Param("gain", "Gain (if no target)", "float", 15.0, 8, 30, 0.5, unit="dBi"),
                      Param("el", "Boresight elevation", "float", 0.0, 0, 90, 1, unit="deg")],
              desc="Pyramidal horn designed for a given gain.", gain_scalable=True, uses_height=False, uses_ground=False,
              analytic=True, size_label="Max aperture", band_default="3 cm (10.0-10.5 GHz)", uses_material=False))


# =========================================================================== patch
SUBSTRATES = [("FR-4 (er 4.4, tan d 0.02)", (4.4, 0.02)), ("Rogers RO4003C (er 3.55, tan d 0.0027)", (3.55, 0.0027)),
              ("Rogers RT/duroid 5880 (er 2.2, tan d 0.0009)", (2.2, 0.0009)), ("Taconic TLY-5 (er 2.2)", (2.2, 0.0009)),
              ("Air-spaced (er 1.07)", (1.07, 0.0))]


def b_patch(req, ex, sc):
    lam = req.lam
    er, tand = P(ex, "sub", (4.4, 0.02))
    h = float(P(ex, "h_mm", 1.6)) / 1000.0
    f = req.f_mhz * 1e6
    d = Design("patch", "Rectangular microstrip patch")
    W = C0 / (2 * f) * math.sqrt(2 / (er + 1))
    eeff = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 * h / W)
    dl = 0.412 * h * (eeff + 0.3) * (W / h + 0.264) / ((eeff - 0.258) * (W / h + 0.8))
    Leff = C0 / (2 * f * math.sqrt(eeff))
    L = Leff - 2 * dl
    # edge resistance (cavity model approximation) and inset feed
    G1 = W / (120 * lam) * (1 - (2 * math.pi * h / lam) ** 2 / 24)
    Rin = 1.0 / (2 * G1) if G1 > 0 else 300.0
    rt = min(max(50.0 / Rin, 1e-3), 0.999)
    y0 = L / math.pi * math.acos(math.sqrt(rt))
    bw = 3.77 * (er - 1) / er ** 2 * (W / L) * (h / lam)
    q_loss = 1.0 / (bw / 1.0 if bw > 0 else 1.0) * 0.7071
    eta = max(0.25, min(0.95, 1 / (1 + tand * 25 + 0.0)))
    if h / lam > 0.05:
        eta *= 0.85
        d.warnings.append("Substrate is thick for this frequency; surface waves lower the efficiency.")
    dpk = 5.0 + 10 * math.log10(max(W / lam, 0.1) * 3.0) if False else 6.6 + 10 * math.log10(max(W / lam / 0.4, 0.5))
    gpk = dpk + 10 * math.log10(eta)
    p = max(0.5, 10 ** (dpk / 10) / 2 - 1)
    b = boresight(0.0, float(P(ex, "el", 0.0)))

    def gain_fn(th, ph):
        a = angle_off(th, ph, b)
        c = np.maximum(np.cos(a), 1e-6)
        g = gpk + 10 * p * np.log10(c)
        g = np.maximum(g, gpk - 25.0)
        return np.where(a > math.pi / 2, gpk - 25.0, g)
    f0 = req.f_mhz
    d.analytic = AnalyticModel(gain_fn, lambda ff: resonator_z(ff, f0, 50.0, 0.7071 / max(bw, 0.003)), pol="V", eta=eta)
    d.pol = "V"
    d.dim("Patch width (W)", 1, W, "")
    d.dim("Patch length (L)", 1, L, f"effective permittivity {eeff:.2f}")
    d.dim("Substrate thickness", 1, h, f"er = {er}")
    d.dim("Inset feed depth from the edge", 1, y0, f"edge resistance {Rin:.0f} ohm to 50 ohm")
    d.dim("Ground plane (minimum)", 1, max(W, L) + 6 * h, "")
    d.dim("Fractional bandwidth (SWR < 2)", 1, None, f"about {bw * 100:.1f}% ({bw * req.f_mhz:.1f} MHz)")
    d.notes += [f"Gain about {gpk:.1f} dBi (directivity {dpk:.1f} dBi x radiating efficiency {eta * 100:.0f}%).",
                "Patch size is from the transmission-line model with fringing correction; expect to trim the length 1-3% on the bench.",
                "Polarisation is linear along the length L (vertical when the patch is mounted with L vertical)."]
    return d


register(Spec("patch", "Patch / microstrip antenna", "Microwave antennas", b_patch,
              params=[Param("sub", "Substrate", "choice", (4.4, 0.02), choices=SUBSTRATES),
                      Param("h_mm", "Substrate thickness", "float", 1.6, 0.2, 6.0, 0.1, unit="mm"),
                      Param("el", "Boresight elevation", "float", 0.0, 0, 90, 1, unit="deg")],
              desc="Printed rectangular patch with an inset 50 ohm feed.", uses_height=False, uses_ground=False,
              analytic=True, size_label="Max size", band_default="13 cm (2300-2450 MHz)", uses_material=False))


# =========================================================================== waveguide slot array
def b_slot(req, ex, sc):
    lam = req.lam
    f_ghz = req.f_mhz / 1000
    wg = pick_wg(f_ghz)
    a_wg, b_wg = wg[1] / 1000, wg[2] / 1000
    lg = lam / math.sqrt(max(1 - (lam / (2 * a_wg)) ** 2, 0.05))
    if req.target_gain is not None:
        n = int(math.ceil(10 ** ((req.target_gain - 2.0) / 10)))
    else:
        n = int(P(ex, "n", 8))
    n = max(2, min(n, 64))
    d = Design("slot", f"{n}-slot waveguide array")
    dsp = lg / 2
    length = n * dsp + lg / 4
    if req.max_size > 0 and length > req.max_size:
        n2 = max(2, int((req.max_size - lg / 4) / dsp))
        d.warnings.append(f"Size limit reduces the array from {n} to {n2} slots.")
        n = n2
        length = n * dsp + lg / 4
    de = 3.0
    d_af = 2 * n * dsp / lam
    dpk = 10 * math.log10(de * d_af)
    gpk = dpk - 0.8
    hp_el = 50.8 * lam / (n * dsp)

    def gain_fn(th, ph):
        x, y, z = unit_vec(th, ph)
        beta = np.arcsin(np.clip(z, -1, 1))
        psi = 2 * math.pi * dsp / lam * np.sin(beta)
        s = np.sin(psi / 2)
        s = np.where(np.abs(s) < 1e-9, 1e-9, s)
        af = np.abs(np.sin(n * psi / 2) / (n * s))
        elem = np.clip(y, 0, 1)
        g = gpk + 20 * np.log10(np.maximum(af, 1e-3)) + 20 * np.log10(np.maximum(elem, 0.05))
        return np.where(y < 0, gpk - 30.0, np.maximum(g, gpk - 35.0))
    d.analytic = AnalyticModel(gain_fn, lambda ff, f0=req.f_mhz: resonator_z(ff, f0, 50.0, 20.0), pol="H", eta=1.0)
    d.pol = "H"
    d.dim(f"Waveguide {wg[0]}", 1, length, f"{wg[1]:.1f} x {wg[2]:.2f} mm inside")
    d.dim("Guide wavelength", 1, lg, f"free-space {lam * 1000:.1f} mm")
    d.dim(f"Slots ({n})", n, 0.48 * lam, "centre-offset alternately each side of the broad-wall centreline")
    d.dim("Slot spacing", 1, dsp, "half guide wavelength")
    d.dim("Offset from centreline", 1, None, "start at about 0.1 mm per % of required slot conductance; trim by network analyser")
    d.dim("End short", 1, lg / 4, "quarter guide wavelength beyond the last slot")
    d.notes += [f"Peak gain about {gpk:.1f} dBi, elevation half-power beamwidth about {hp_el:.1f} deg; the horizontal beamwidth is wide (about 80-100 deg).",
                "Resonant (standing-wave) arrays have narrow bandwidth, around 3-5%, and a good match only at the design frequency.",
                "Orientation: waveguide vertical gives horizontal polarisation and a narrow vertical beam."]
    size_warn(d, req, length, "Array length")
    return d


register(Spec("slot", "Waveguide slot array", "Microwave antennas", b_slot,
              params=[Param("n", "Slots (if no gain target)", "int", 8, 2, 64, 1)],
              desc="Resonant slotted waveguide array, e.g. for 3 cm and 10 GHz links.", gain_scalable=True, uses_height=False,
              uses_ground=False, analytic=True, size_label="Max length", band_default="3 cm (10.0-10.5 GHz)", uses_material=False))


# =========================================================================== small transmitting magnetic loop
def b_magloop(req, ex, sc):
    lam = req.lam
    D = float(P(ex, "dia", 1.0))
    if req.max_size > 0:
        D = min(D, req.max_size)
    orient = P(ex, "orient", "vertical")
    cmin = float(P(ex, "cap_min", 10.0)) * 1e-12
    cmax = float(P(ex, "cap_max", 250.0)) * 1e-12
    esr = float(P(ex, "esr", 0.01))
    nside = 24
    d = Design("magloop", "Small transmitting magnetic loop")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    Rl = D / 2
    H = req.height
    f = req.f_mhz * 1e6
    w = 2 * math.pi * f
    # analytic first estimates
    Lh = 4e-7 * math.pi * Rl * (math.log(8 * Rl / a) - 2.0)
    area = math.pi * Rl ** 2
    Rr = 320 * math.pi ** 4 * (area / lam ** 2) ** 2
    Rs = math.sqrt(math.pi * f * 4e-7 * math.pi / sg)
    Rloss = Rs * (2 * math.pi * Rl) / (2 * math.pi * a) * 1.1
    Rtot = Rr + Rloss + esr
    Xl = w * Lh
    C0f = 1 / (w * w * Lh)
    cap = C0f * _sc(sc, "cap")
    qu = Xl / Rtot
    eta_an = Rr / Rtot
    if orient == "vertical":
        pts = [(Rl * math.cos(2 * math.pi * k / nside + math.pi / 2), 0, H + Rl + Rl * math.sin(2 * math.pi * k / nside + math.pi / 2)) for k in range(nside)]
    else:
        pts = [(Rl * math.cos(2 * math.pi * k / nside + math.pi / 2), Rl * math.sin(2 * math.pi * k / nside + math.pi / 2), H) for k in range(nside)]
    # edges: edge 0 starts at the top (angle 90 deg) -> split edge so the capacitor sits at the top, feed at the bottom
    from .mhelp import add_polygon
    ids, j = add_polygon(st, pts, a, sg, gaps=[(0, 0.5, "cap"), (nside // 2, 0.5, "feed")], min_seg=1)
    capfn = lambda ff, c=cap, e=esr: complex(e, -1.0 / (2 * math.pi * ff * c))
    st.loads.append(Load(j["cap"], 1.0, capfn, "tuning capacitor"))
    st.sources.append(Source(j["feed"], 1.0))
    d.pol = "V" if orient == "vertical" else "H"
    d.tune = [TuneTarget("cap", req.f_mhz, "x0", lo=0.5, hi=2.0, label="tuning capacitor")]
    d.seg_len_hint = max(lam / 20, 2 * math.pi * Rl / nside)
    d.line = None
    f0 = req.f_mhz
    ql = max(qu / 2, 2.0)
    d.imp_override = lambda ff: complex(50.0, 50.0 * ql * (ff / f0 - f0 / ff))
    d.sweep_range = (f0 * (1 - 1.5 / ql if 1.5 / ql < 0.2 else 0.8), f0 * (1 + 1.5 / ql if 1.5 / ql < 0.2 else 1.2))
    bw3 = f0 / qu
    ipk = math.sqrt(2 * req.power_w / Rtot) if Rtot > 0 else 0
    vcap = ipk * Xl
    d.dim("Loop diameter", 1, D, f"circumference {math.pi * D:.2f} m = {math.pi * D / lam:.3f} wavelengths")
    d.dim("Conductor", 1, math.pi * D, f"{2 * a * 1000:.1f} mm diameter; use thick tube/coax shield for low loss")
    d.dim("Loop inductance", 1, None, f"{Lh * 1e6:.2f} uH")
    d.dim("Tuning capacitor for resonance", 1, None, f"{cap * 1e12:.1f} pF (need range {cmin * 1e12:.0f}-{cmax * 1e12:.0f} pF; {'OK' if cmin <= cap <= cmax else 'OUT OF RANGE'})")
    d.dim("Coupling loop (Faraday)", 1, math.pi * D / 5, f"about {D / 5:.2f} m diameter, one turn")
    d.dim("Radiation resistance", 1, None, f"{Rr * 1000:.2f} mOhm")
    d.dim("Loss resistance (conductor + capacitor)", 1, None, f"{(Rloss + esr) * 1000:.1f} mOhm")
    d.dim("Efficiency", 1, None, f"{eta_an * 100:.1f}% ({10 * math.log10(max(eta_an, 1e-6)):.1f} dB)")
    d.dim("Unloaded Q / 3 dB bandwidth", 1, None, f"Q = {qu:.0f}; BW = {bw3 * 1000:.1f} kHz")
    d.dim(f"Capacitor voltage at {req.power_w:.0f} W", 1, None, f"{vcap:.0f} V peak ({ipk:.1f} A peak in the loop) - use a vacuum or high-voltage variable")
    if cap > cmax or cap < cmin:
        d.warnings.append(f"Resonating needs {cap * 1e12:.0f} pF, outside your capacitor range {cmin * 1e12:.0f}-{cmax * 1e12:.0f} pF; change the loop diameter.")
    if math.pi * D > lam / 4:
        d.warnings.append("Loop is longer than lambda/4: no longer a small loop, expect a different pattern.")
    d.notes += ["A small loop is an efficient radiator only with very low-loss construction: thick copper tube, silver-plated joints, and a low-ESR vacuum or butterfly capacitor.",
                "Narrow bandwidth means retuning for every few kilohertz. SWR curve shown is for critical coupling to 50 ohm through a Faraday loop.",
                "Loop plane radiates along the loop plane (nulls broadside); high-Q loops can put thousands of volts across the capacitor - keep clear while transmitting."]
    size_warn(d, req, D, "Diameter")
    return d


register(Spec("magloop", "Magnetic loop (small transmitting loop)", "Compact antennas", b_magloop,
              params=[Param("dia", "Loop diameter", "float", 1.0, 0.3, 3.0, 0.05, unit="m"),
                      Param("orient", "Orientation", "choice", "vertical", choices=[("Vertical loop", "vertical"), ("Horizontal loop", "horizontal")]),
                      Param("cap_min", "Capacitor minimum", "float", 10.0, 1, 200, 1, unit="pF"),
                      Param("cap_max", "Capacitor maximum", "float", 250.0, 20, 2000, 10, unit="pF"),
                      Param("esr", "Capacitor ESR", "float", 0.01, 0.0, 0.5, 0.005, unit="ohm", decimals=3)],
              desc="Small resonant loop with a variable capacitor; narrow band but compact.", height_default=1.5,
              size_label="Max diameter", band_default="20 m (14.0-14.35 MHz)", feed_ratio=1.0))


# =========================================================================== receive-only small antennas
def b_activewhip(req, ex, sc):
    lam = req.lam
    h = float(P(ex, "height_m", 1.0))
    d = Design("activewhip", "Active whip (receive)")
    heff = h / 2
    ca = 8.0 + 12.0 * h   # pF, antenna capacitance
    gpk = 4.8

    def gain_fn(th, ph):
        s = np.maximum(np.sin(th), 1e-3)
        g = gpk + 20 * np.log10(s)
        return np.where(th > math.pi / 2, gpk - 40.0, g)
    d.analytic = AnalyticModel(gain_fn, flat_match(1.0), pol="V", eta=1.0, upper_only=True)
    d.rx_only = True
    d.pol = "V"
    af = 20 * math.log10(1 / heff)
    d.dim("Whip length", 1, h, "")
    d.dim("Effective height", 1, heff, f"open-circuit voltage = {heff:.2f} m x field strength")
    d.dim("Antenna capacitance (est.)", 1, None, f"{ca:.0f} pF")
    d.dim("Antenna factor (open circuit)", 1, None, f"{af:.1f} dB/m")
    d.dim("Amplifier input", 1, None, "very high impedance, low-noise JFET/MOSFET buffer, 1 Mohm || a few pF")
    d.notes += ["A short whip is far smaller than a wavelength, so its signal is weak but external noise dominates below 30 MHz anyway; a sensitive amplifier is not required for HF.",
                "Pattern is the monopole's omnidirectional sin(elevation) pattern; the gain shown is its directivity - mismatch to the amplifier is not included."]
    return d


register(Spec("activewhip", "Active whip (receive only)", "Receive-only antennas", b_activewhip,
              params=[Param("height_m", "Whip height", "float", 1.0, 0.2, 5.0, 0.1, unit="m")],
              desc="Short vertical whip with a high-impedance preamp.", uses_height=False, uses_ground=False, uses_material=False,
              analytic=True, rx_only=True, size_label="Max height", band_default="40 m (7.0-7.3 MHz)"))


def b_activeloop(req, ex, sc):
    lam = req.lam
    D = float(P(ex, "dia", 1.0))
    turns = int(P(ex, "turns", 1))
    d = Design("activeloop", "Active loop (receive)")
    area = math.pi * (D / 2) ** 2
    heff = 2 * math.pi * turns * area / lam
    Lh = 4e-7 * math.pi * (D / 2) * (math.log(8 * (D / 2) / max(req.radius, 1e-4)) - 2) * turns ** 2
    gpk = 1.76

    def gain_fn(th, ph):
        s = np.sqrt(np.maximum(1 - (np.sin(th) * np.cos(ph)) ** 2, 1e-4))     # loop axis along x
        return gpk + 20 * np.log10(s)
    d.analytic = AnalyticModel(gain_fn, flat_match(1.0), pol="V", eta=1.0)
    d.rx_only = True
    d.pol = "V"
    d.dim("Loop diameter", 1, D, "")
    d.dim("Turns", turns, math.pi * D * turns, "")
    d.dim("Effective height", 1, heff, f"{heff * 100:.2f} cm; antenna factor {20 * math.log10(1 / max(heff, 1e-6)):.0f} dB/m")
    d.dim("Loop inductance", 1, None, f"{Lh * 1e6:.2f} uH")
    d.dim("Preamp", 1, None, "low-noise transformer-coupled amplifier with high IP3; a loop is almost insensitive to the electric field of local noise")
    d.notes += ["Figure-eight pattern with nulls broadside to the loop plane; rotate the loop to null interference.",
                "Because the loop is broadband and electrically small, the preamplifier sets sensitivity - a Wellbrook-style loop uses 1.0 m diameter."]
    size_warn(d, req, D, "Diameter")
    return d


register(Spec("activeloop", "Active loop (Wellbrook-style, receive only)", "Receive-only antennas", b_activeloop,
              params=[Param("dia", "Loop diameter", "float", 1.0, 0.3, 3.0, 0.05, unit="m"),
                      Param("turns", "Turns", "int", 1, 1, 4, 1)],
              desc="Small broadband receive loop with a preamplifier.", uses_height=False, uses_ground=False,
              analytic=True, rx_only=True, size_label="Max diameter", band_default="40 m (7.0-7.3 MHz)"))


def b_ferrite(req, ex, sc):
    lam = req.lam
    ln = float(P(ex, "rod_len", 0.2))
    dia = float(P(ex, "rod_dia", 0.01))
    mu = float(P(ex, "mu_r", 125.0))
    turns = int(P(ex, "turns", 60))
    q = float(P(ex, "q", 150.0))
    d = Design("ferrite", "Ferrite loopstick (receive)")
    area = math.pi * (dia / 2) ** 2
    ld = ln / dia
    mu_app = mu / (1 + (mu - 1) * (1.0 / (ld ** 2)) * (math.log(2 * ld) - 1) * 0.85) if ld > 2 else 1
    mu_app = max(1.0, mu_app)
    heff = 2 * math.pi * turns * area * mu_app / lam
    Lh = 4e-7 * math.pi * mu_app * turns ** 2 * area / ln
    w = 2 * math.pi * req.f_mhz * 1e6
    cres = 1 / (w * w * Lh) if Lh > 0 else 0
    gpk = 1.76 - 10 * math.log10(max(1, 1.0))

    def gain_fn(th, ph):
        s = np.sqrt(np.maximum(1 - (np.sin(th) * np.sin(ph)) ** 2, 1e-4))     # rod axis along y
        return gpk + 20 * np.log10(s)
    d.analytic = AnalyticModel(gain_fn, flat_match(1.0), pol="V", eta=1.0)
    d.rx_only = True
    d.dim("Rod", 1, ln, f"{dia * 1000:.0f} mm diameter, mu_r {mu:.0f}, apparent permeability {mu_app:.0f}")
    d.dim("Winding", turns, None, "close-wound litz wire for best Q")
    d.dim("Inductance", 1, None, f"{Lh * 1e6:.1f} uH")
    d.dim("Tuning capacitor", 1, None, f"{cres * 1e12:.0f} pF to resonate at {req.f_mhz:.3f} MHz")
    d.dim("Effective height", 1, heff, f"{heff * 1000:.2f} mm; voltage gain from tuning = Q = {q:.0f}")
    d.dim("Bandwidth (3 dB)", 1, None, f"{req.f_mhz * 1000 / q:.1f} kHz")
    d.notes += ["Ferrite loopstick for LF/MF/HF receive: figure-eight pattern with nulls along the rod axis.",
                "Choose a ferrite material suited to the frequency: #77/#61 for MF-HF; large rod length/diameter ratio raises the apparent permeability."]
    d.pol = "V"
    return d


register(Spec("ferrite", "Ferrite loopstick (receive only)", "Receive-only antennas", b_ferrite,
              params=[Param("rod_len", "Rod length", "float", 0.2, 0.05, 0.5, 0.01, unit="m"),
                      Param("rod_dia", "Rod diameter", "float", 0.01, 0.005, 0.03, 0.001, unit="m", decimals=3),
                      Param("mu_r", "Ferrite mu_r", "float", 125.0, 20, 2000, 5),
                      Param("turns", "Turns", "int", 60, 5, 400, 1),
                      Param("q", "Unloaded Q", "float", 150.0, 30, 400, 5)],
              desc="Small rod antenna for LF, MF and low HF listening.", uses_height=False, uses_ground=False, uses_material=False,
              analytic=True, rx_only=True, size_label="Max rod length", band_default="160 m (1.8-2.0 MHz)"))


# =========================================================================== dummy load
def b_dummy(req, ex, sc):
    d = Design("dummy", "Dummy load")
    p = req.power_w
    ru = float(P(ex, "r_unit", 200.0))
    rw = float(P(ex, "r_watt", 25.0))
    n = max(1, int(round(ru / 50.0)))
    margin = float(P(ex, "margin", 2.0))
    per = p / n
    need_w = per * margin
    nparallel_w = max(n, int(math.ceil(need_w / rw)) * n)
    lpar = float(P(ex, "l_nh", 25.0)) * 1e-9
    cpar = float(P(ex, "c_pf", 4.0)) * 1e-12

    def zin(f):
        w = 2 * math.pi * f * 1e6
        zr = complex(50.0, w * lpar)
        yc = 1j * w * cpar
        return 1.0 / (1 / zr + yc)

    d.analytic = AnalyticModel(lambda th, ph: np.full(np.broadcast(th, ph).shape, -60.0), zin, pol="V", eta=1e-6)
    d.dim("Resistors", n, None, f"{ru:.0f} ohm {rw:.0f} W non-inductive, wired in parallel = 50 ohm")
    d.dim("Power per resistor at full power", 1, None, f"{per:.1f} W; with {margin:.1f}x margin need {need_w:.1f} W rating each")
    if need_w > rw:
        d.dim("Total resistors for rated power", nparallel_w, None, f"use {int(math.ceil(need_w / rw))} per leg ({nparallel_w} total, still 50 ohm)")
    d.dim("Heatsink", 1, None, f"dissipate {p:.0f} W continuous: roughly {p / 30:.1f} K/W thermal path to keep resistors cool")
    d.dim("Connector", 1, None, "SO-239 / N type to match the frequency")
    d.notes += ["A dummy load is not an antenna: it absorbs power without radiating. Pattern shown is a flat -60 dBi placeholder.",
                "SWR rises with frequency because of lead inductance and parasitic capacitance (modelled: 25 nH, 4 pF)."]
    d.rx_only = False
    return d


register(Spec("dummy", "Dummy load (non-radiating)", "Compact antennas", b_dummy,
              params=[Param("r_unit", "Resistor value", "choice", 200.0, choices=[("100 ohm (2 parallel)", 100.0), ("150 ohm (3 parallel)", 150.0), ("200 ohm (4 parallel)", 200.0), ("250 ohm (5 parallel)", 250.0), ("500 ohm (10 parallel)", 500.0), ("1 kohm (20 parallel)", 1000.0)]),
                      Param("r_watt", "Rating per resistor", "float", 25.0, 1, 500, 1, unit="W"),
                      Param("margin", "Safety margin", "float", 2.0, 1.0, 5.0, 0.5),
                      Param("l_nh", "Lead inductance", "float", 25.0, 0, 200, 1, unit="nH"),
                      Param("c_pf", "Shunt capacitance", "float", 4.0, 0, 50, 0.5, unit="pF")],
              desc="Resistive load made of paralleled non-inductive resistors.", uses_height=False, uses_ground=False,
              uses_material=False, analytic=True, size_label="Max size"))
