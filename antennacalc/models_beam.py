"""Directional HF/VHF beams and arrays."""
from __future__ import annotations

import math

import numpy as np

from . import mom
from .design import Design, Param, Spec, TuneTarget, register
from .mhelp import add_polygon, ground_loss_r, new_struct, size_warn
from .models_wire import P, _sc
from .mom import C0, Load, Source


# =========================================================================== Yagi
SPACE_D = [0.14, 0.20, 0.25, 0.28, 0.30, 0.32, 0.33, 0.34]


def thin_adjust(lt: float, lam: float, radius: float) -> float:
    """Template length (in wavelengths, valid for radius = 0.003 wavelength) -> length for the real radius.

    Parasitic elements are detuned from their own resonance by an amount that scales with 1/Z0 of the element,
    so thinner elements need a smaller offset from resonance."""
    import math
    from .mhelp import dipole_res_factor
    ar = radius / lam
    kref = dipole_res_factor(0.003)
    kact = dipole_res_factor(ar)
    zref = math.log(kref / 0.003) - 1.0
    zact = math.log(kact / ar) - 1.0
    frac = (lt - kref) / kref
    return kact * (1.0 + frac * zref / zact)


def yagi_layout(lam, n, sc, radius=None):
    """Return list of (name, y_position m, length m) from the reflector forward."""
    rl, rs = _sc(sc, "rl"), _sc(sc, "rs")
    dl, ds = _sc(sc, "dl"), _sc(sc, "ds")
    drv = 0.470 * _sc(sc, "len")
    adj = (lambda x: thin_adjust(x, lam, radius)) if radius else (lambda x: x)
    out = []
    ry = -0.20 * rs
    out.append(("Reflector", ry * lam, adj(0.495 * rl) * lam))
    out.append(("Driven", 0.0, (drv * lam) if not radius else adj(0.470) * _sc(sc, "len") * lam))
    y = 0.0
    for k in range(n - 2):
        sp = SPACE_D[min(k, len(SPACE_D) - 1)] * ds
        y += sp
        ln = max(0.395, 0.447 - 0.0045 * k)
        ln = adj(ln) * dl
        if k == 0:
            ln *= _sc(sc, "d1")
        out.append((f"Director {k + 1}", y * lam, ln * lam))
    return out


def yagi_size(req, ex, n):
    lay = yagi_layout(req.lam, n, {})
    return lay[-1][1] - lay[0][1]


def b_yagi(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "n", 3))
    n = max(2, n)
    pol = P(ex, "pol", "H")
    droop = math.radians(float(P(ex, "droop", 0.0)))
    spider = droop > 0
    d = Design("yagi", f"{n}-element Yagi-Uda" if not spider else f"{n}-element spider-style beam")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = req.height
    lay = yagi_layout(lam, n, sc, req.radius)
    for idx, (nm, y, L) in enumerate(lay):
        half = L / 2
        if pol == "H":
            if spider:
                dx, dz = half * math.cos(droop), half * math.sin(droop)
                p0, pc, p1 = (-dx, y, H - dz), (0, y, H), (dx, y, H - dz)
            else:
                p0, pc, p1 = (-half, y, H), (0, y, H), (half, y, H)
        else:
            zc = max(H, half + 0.2)
            p0, pc, p1 = (0, y, zc - half), (0, y, zc), (0, y, zc + half)
        w0 = st.add(p0, pc, a, sigma=sg, min_seg=5, name=nm)
        w1 = st.add(pc, p1, a, sigma=sg, min_seg=5, name=nm)
        if nm == "Driven":
            st.sources.append(Source(w0, 1.0))
    d.pol = "H" if pol == "H" else "V"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.25, label="driven element")]
    keys = [("rl", 0.94, 1.06), ("rs", 0.6, 1.6)]
    if n >= 3:
        keys += [("dl", 0.9, 1.1), ("ds", 0.6, 1.5), ("d1", 0.92, 1.08)]
    d.opt_keys = keys
    boom = lay[-1][1] - lay[0][1]
    d.dim("Boom length", 1, boom, f"{boom / lam:.2f} wavelengths")
    for nm, y, L in lay:
        d.dim(f"{nm} element", 1, L, f"{y - lay[0][1]:+.3f} m from the reflector end")
    d.dim("Feed", 1, None, "gamma, hairpin or beta match to 50 ohm plus a 1:1 balun (see Matching tab)")
    d.notes += ["Element lengths come from a starting design refined by the optimiser; lengths are tip to tip and assume a continuous (no boom-correction) element - add boom-through-element corrections for metal booms.",
                "Driven element radiates a modest impedance (15-30 ohm) at high gain; match with a hairpin/gamma or a 1.5:1-2:1 balun.",
                "Press Optimise to trade gain, front-to-rear and match with a short numerical search."]
    if spider:
        d.notes.append("Spider-style: drooping the element ends lets them hang from fibreglass spreaders. Multi-band spiders stack one such pair per band on the same hub.")
    size_warn(d, req, boom, "Boom")
    size_warn(d, req, max(L for _, _, L in lay), "Longest element")
    return d


register(Spec("yagi", "Yagi-Uda (2-20 elements) / spider beam", "Directional beams", b_yagi,
              params=[Param("n", "Number of elements", "int", 3, 2, 20, 1),
                      Param("pol", "Polarisation", "choice", "H", choices=[("Horizontal", "H"), ("Vertical", "V")]),
                      Param("droop", "Element droop (spider style)", "float", 0.0, 0, 45, 5, unit="deg")],
              desc="Parasitic beam. Set a gain target and size limit to choose the element count automatically.",
              height_default=12.0, gain_scalable=True, auto_key="n", auto_lo=2, auto_hi=20, size_fn=yagi_size,
              size_label="Max boom length", optimizable=True, feed_ratio=1.0, feed_len=20.0, lmatch_default=True))


# =========================================================================== Quad / Delta loop beam
def b_quad(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "n", 2))
    shape = P(ex, "shape", "square")
    d = Design("quad", f"{n}-element {'cubical quad' if shape == 'square' else 'delta loop beam'}")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = req.height
    pers = [1.05 * _sc(sc, "rl")] + [1.02 * _sc(sc, "len")] + [max(0.94, 0.985 - 0.005 * k) * _sc(sc, "dl") for k in range(n - 2)]
    spc = [0.0] + [0.20 * _sc(sc, "rs")] + [0.15 * _sc(sc, "ds")] * (n - 2)
    ys = []
    y = 0.0
    # reflector at -sp ; driven at 0
    ys = [-0.20 * _sc(sc, "rs") * lam, 0.0]
    for k in range(n - 2):
        ys.append(ys[-1] + (0.15 + 0.03 * min(k, 4)) * _sc(sc, "ds") * lam)
    names = ["Reflector", "Driven"] + [f"Director {k + 1}" for k in range(n - 2)]
    for k in range(n):
        per = pers[k] * lam
        if shape == "square":
            s = per / 4
            pts = [(-s / 2, ys[k], H - s / 2), (s / 2, ys[k], H - s / 2), (s / 2, ys[k], H + s / 2), (-s / 2, ys[k], H + s / 2)]
        else:
            s = per / 3
            hh = s * math.sqrt(3) / 2
            pts = [(-s / 2, ys[k], H - hh / 3), (s / 2, ys[k], H - hh / 3), (0, ys[k], H + 2 * hh / 3)]
        ids, j = add_polygon(st, pts, a, sg, feed_edge=0 if k == 1 else None, min_seg=2, name=names[k])
        if k == 1:
            st.sources.append(Source(j["feed"], 1.0))
        d.dim(f"{names[k]} loop", 1, per, (f"{per / 4:.3f} m per side" if shape == "square" else f"{per / 3:.3f} m per side") + f", y = {ys[k] - ys[0]:+.2f} m")
    d.pol = "H"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.85, hi=1.2, label="driven loop")]
    d.opt_keys = [("rl", 0.96, 1.06), ("rs", 0.6, 1.6)] + ([("dl", 0.93, 1.07), ("ds", 0.6, 1.5)] if n >= 3 else [])
    boom = ys[-1] - ys[0]
    d.dim("Boom length", 1, boom, "")
    d.dim("Feed", 1, None, "bottom-centre of the driven loop; 75 ohm quarter-wave section or 4:1 balun gives 50 ohm")
    d.notes += ["A two-element quad matches a three-element Yagi in gain but is lower-noise and less sensitive to height; loop perimeter is about 1.02 wavelengths.",
                "Driven loop impedance is 100-125 ohm: use a quarter-wave 75 ohm transformer, or reduce spacing for 50 ohm.",
                "Feed at the bottom for horizontal polarisation, at a side for vertical."]
    size_warn(d, req, boom, "Boom")
    size_warn(d, req, pers[0] * lam / 4, "Loop size")
    return d


def quad_size(req, ex, n):
    return (0.20 + sum(0.15 + 0.03 * min(k, 4) for k in range(n - 2))) * req.lam


register(Spec("quad", "Cubical quad / delta loop beam", "Directional beams", b_quad,
              params=[Param("n", "Number of elements", "int", 2, 2, 8, 1),
                      Param("shape", "Loop shape", "choice", "square", choices=[("Square (cubical quad)", "square"), ("Triangle (delta loop)", "delta")])],
              desc="Loop-element beam, low noise and about 1 dB better than a Yagi per element.",
              height_default=12.0, gain_scalable=True, auto_key="n", auto_lo=2, auto_hi=8, size_fn=quad_size,
              size_label="Max boom length", optimizable=True, feed_ratio=2.0, lmatch_default=False))


# =========================================================================== Quagi
def b_quagi(req, ex, sc):
    lam = req.lam
    n = int(P(ex, "n", 6))
    d = Design("quagi", f"{n}-element quagi")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = req.height
    ys = [-0.20 * lam * _sc(sc, "rs"), 0.0]
    for k in range(n - 2):
        ys.append(ys[-1] + (0.16 + 0.02 * min(k, 6)) * lam * _sc(sc, "ds"))
    names = ["Reflector (loop)", "Driven (loop)"] + [f"Director {k + 1}" for k in range(n - 2)]
    pers = [1.05 * _sc(sc, "rl"), 1.02 * _sc(sc, "len")]
    for k in range(2):
        s = pers[k] * lam / 4
        pts = [(-s / 2, ys[k], H - s / 2), (s / 2, ys[k], H - s / 2), (s / 2, ys[k], H + s / 2), (-s / 2, ys[k], H + s / 2)]
        ids, j = add_polygon(st, pts, a, sg, feed_edge=0 if k == 1 else None, min_seg=2)
        if k == 1:
            st.sources.append(Source(j["feed"], 1.0))
        d.dim(names[k], 1, pers[k] * lam, f"{s:.3f} m per side, y = {ys[k] - ys[0]:+.2f} m")
    for k in range(n - 2):
        L = thin_adjust(max(0.38, 0.43 - 0.003 * k), lam, a) * lam * _sc(sc, "dl")
        st.add((-L / 2, ys[k + 2], H), (L / 2, ys[k + 2], H), a, sigma=sg, min_seg=7)
        d.dim(names[k + 2], 1, L, f"y = {ys[k + 2] - ys[0]:+.2f} m")
    d.pol = "H"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.85, hi=1.2, label="driven loop")]
    d.opt_keys = [("rl", 0.96, 1.06), ("dl", 0.92, 1.08), ("ds", 0.7, 1.4)]
    d.dim("Boom length", 1, ys[-1] - ys[0], "")
    d.notes += ["The quagi uses a quad reflector and driven element with Yagi directors, popular for VHF/UHF weak-signal work.",
                "Driven loop is around 100 ohm; match with a 75 ohm quarter-wave section."]
    size_warn(d, req, ys[-1] - ys[0], "Boom")
    return d


def quagi_size(req, ex, n):
    return (0.20 + sum(0.16 + 0.02 * min(k, 6) for k in range(n - 2))) * req.lam


register(Spec("quagi", "Quagi (quad driven + Yagi directors)", "Directional beams", b_quagi,
              params=[Param("n", "Total elements", "int", 6, 3, 20, 1)],
              desc="Hybrid of loops and straight directors for VHF/UHF.", height_default=4.0,
              gain_scalable=True, auto_key="n", auto_lo=3, auto_hi=20, size_fn=quagi_size, size_label="Max boom length",
              optimizable=True, band_default="70 cm (430-440 MHz)", lmatch_default=True))


# =========================================================================== LPDA
_LPDA_CACHE = {}


def _lpda_geometry(req, ex):
    tau = float(P(ex, "tau", 0.90))
    sigma = float(P(ex, "sigma", 0.0))
    if sigma <= 0:
        sigma = 0.243 * tau - 0.051
    flo, fhi = req.f_lo, req.f_hi
    if fhi < flo * 1.1:
        flo, fhi = req.f_mhz * 0.95, req.f_mhz * 1.05
    B = fhi / flo
    alpha = math.atan((1 - tau) / (4 * sigma))
    bar = 1.1 + 7.7 * (1 - tau) ** 2 / math.tan(alpha)
    Bs = B * bar
    n = int(P(ex, "n", 0))
    if n <= 0:
        n = int(math.ceil(1 + math.log(Bs) / math.log(1 / tau)))
    n = max(4, min(n, 24))
    lam_lo = C0 / (flo * 1e6)
    Lmax = 0.5 * lam_lo * 0.97
    Ls = [Lmax * tau ** (n - 1 - i) for i in range(n)]       # i = 0 is the shortest
    ys = [0.0]
    for i in range(n - 1):
        ys.append(ys[-1] - 2 * sigma * Ls[i + 1])
    return tau, sigma, n, flo, fhi, Ls, ys, Lmax


def b_lpda(req, ex, sc):
    tau, sigma, n, flo, fhi, Ls, ys, Lmax = _lpda_geometry(req, ex)
    d = Design("lpda", f"{n}-element log-periodic dipole array")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = req.height
    for i in range(n):
        w0 = st.add((-Ls[i] / 2, ys[i], H), (0, ys[i], H), a, sigma=sg, min_seg=3, name=f"E{i}")
        w1 = st.add((0, ys[i], H), (Ls[i] / 2, ys[i], H), a, sigma=sg, min_seg=3, name=f"E{i}")
        st.sources.append(Source(w0, 1.0))
    z0 = float(P(ex, "z0", 0.0))
    vf = 0.95
    st.lines = []
    # z0 chosen below
    if z0 <= 0:
        z0 = _lpda_auto_z0(req, st, ex, n, Ls, ys, Lmax, flo, fhi, vf)
    for i in range(n - 1):
        st.lines.append((i, i + 1, z0, abs(ys[i + 1] - ys[i]), vf, True))
    st.stub_port = n - 1
    st.stub = (z0, Lmax / 2 * 0.5, vf)
    st.feed_port = 0
    d.mode = "network"
    d.pol = "H"
    d.sweep_range = (flo * 0.9, fhi * 1.1)
    d.seg_len_hint = (C0 / (fhi * 1e6)) / 8
    d.dim("Elements", n, None, f"tau = {tau:.3f}, sigma = {sigma:.3f}, boom line Z0 = {z0:.0f} ohm")
    for i in range(n - 1, -1, -1):
        d.dim(f"Element {n - i} ({'longest' if i == n - 1 else 'shortest' if i == 0 else ''})".replace("()", "").strip(), 1, Ls[i], f"{abs(ys[i] - ys[0]):.3f} m behind the front")
    d.dim("Boom length", 1, abs(ys[-1]), "")
    d.dim("Boom transmission line (two bars)", n - 1, None, "each element joined alternately to the two bars (phase-reversal); shorted stub at the back")
    d.dim("Feed", 1, None, "coax through the boom to the front (shortest) element, with a balun at the feedpoint")
    d.notes += ["Active region moves along the array with frequency; gain is roughly constant (about 7-9 dBi) over the whole design bandwidth.",
                "Boom line impedance is auto-chosen to minimise SWR across the band; real two-bar booms need spacing/diameter that gives that impedance.",
                "Set the band to 'Custom range' to design for a wide frequency span."]
    size_warn(d, req, abs(ys[-1]), "Boom")
    size_warn(d, req, Ls[-1], "Longest element")
    return d


def _lpda_auto_z0(req, st, ex, n, Ls, ys, Lmax, flo, fhi, vf):
    key = (round(flo, 3), round(fhi, 3), n, round(Ls[0], 3), round(req.radius, 6), req.height, req.ground.kind, req.ground.sigma, req.spw)
    if key in _LPDA_CACHE:
        return _LPDA_CACHE[key]
    from .engine import seg_len_for
    model = mom.Model(st, (C0 / (fhi * 1e6)) / 8)
    fs = np.linspace(flo, fhi, 5) * 1e6
    yps = [mom.port_impedance_matrix(model, f)[1] for f in fs]
    best, bz = 1e9, 100.0
    for z0 in (50, 60, 75, 90, 110, 130, 160, 200, 250, 320):
        lines = [(i, i + 1, z0, abs(ys[i + 1] - ys[i]), vf, True) for i in range(n - 1)]
        tot = 0.0
        for f, Yp in zip(fs, yps):
            z, _ = mom.network_zin_from_yp(Yp, lines, n - 1, (z0, Lmax / 4, vf), 0, f)
            g = abs((z - req.zref) / (z + req.zref))
            tot += g
        if tot < best:
            best, bz = tot, z0
    _LPDA_CACHE[key] = float(bz)
    return float(bz)


register(Spec("lpda", "Log-periodic dipole array (LPDA)", "Directional beams", b_lpda,
              params=[Param("tau", "Scale factor tau", "float", 0.90, 0.8, 0.96, 0.01),
                      Param("sigma", "Spacing factor sigma (0 = optimum)", "float", 0.0, 0, 0.25, 0.005, decimals=3),
                      Param("n", "Elements (0 = from bandwidth)", "int", 0, 0, 24, 1),
                      Param("z0", "Boom line Z0 (0 = auto)", "float", 0.0, 0, 400, 10, unit="ohm")],
              desc="Wideband directional array: gain stays flat across the whole design range. Use 'Custom range' for the band edges.",
              height_default=12.0, custom_range=True, size_label="Max boom length", band_default="Custom range", feed_ratio=1.0))


# =========================================================================== Moxon / Hex beam
def b_moxon(req, ex, sc):
    lam = req.lam
    hexv = P(ex, "variant", "moxon") == "hex"
    beta = math.radians(40.0 if hexv else 0.0)
    d = Design("moxon", "Hex beam (Moxon-based)" if hexv else "Moxon rectangle")
    st = new_struct(req, d)
    a, sg = req.radius, req.sigma
    H = req.height
    A = (0.3745 if not hexv else 0.31) * lam * _sc(sc, "len")
    B = 0.0545 * lam * (1 if not hexv else 1.55) * _sc(sc, "len") * _sc(sc, "bt")
    D = 0.0566 * lam * (1 if not hexv else 1.50) * _sc(sc, "len") * _sc(sc, "rt")
    Cg = 0.0161 * lam * (1 if not hexv else 1.0) * _sc(sc, "gap")
    E = B * math.cos(beta) + Cg + D * math.cos(beta)
    sb, cb = math.sin(beta), math.cos(beta)
    # driven (y = 0) tails reach toward the reflector (-y); reflector at y = -E, tails toward +y
    tipL = (-(A / 2 - B * sb), -B * cb, H); cL = (-A / 2, 0, H); ctr = (0, 0, H); cR = (A / 2, 0, H); tipR = ((A / 2 - B * sb), -B * cb, H)
    st.add(tipL, cL, a, sigma=sg, min_seg=2)
    w0 = st.add(cL, ctr, a, sigma=sg, min_seg=5)
    st.add(ctr, cR, a, sigma=sg, min_seg=5)
    st.add(cR, tipR, a, sigma=sg, min_seg=2)
    st.sources.append(Source(w0, 1.0))
    rtl = (-(A / 2 - D * sb), -E + D * cb, H); rcl = (-A / 2, -E, H); rcr = (A / 2, -E, H); rtr = ((A / 2 - D * sb), -E + D * cb, H)
    st.add(rtl, rcl, a, sigma=sg, min_seg=2)
    st.add(rcl, rcr, a, sigma=sg, min_seg=8)
    st.add(rcr, rtr, a, sigma=sg, min_seg=2)
    d.pol = "H"
    d.tune = [TuneTarget("len", req.f_mhz, "x0", lo=0.8, hi=1.25, label="size")]
    d.opt_keys = [("gap", 0.4, 2.2), ("rt", 0.85, 1.2), ("bt", 0.85, 1.2)]
    tot_d = A + 2 * B
    tot_r = A + 2 * D
    d.dim("Width (A)", 1, A, "tip to tip of the straight portion")
    d.dim("Driven element total wire", 1, tot_d, f"tails {B:.3f} m each")
    d.dim("Reflector total wire", 1, tot_r, f"tails {D:.3f} m each")
    d.dim("Gap between the tail tips (C)", 1, Cg, "set with insulating spacers")
    d.dim("Depth (front to back)", 1, E, "")
    d.dim("Feed", 1, None, "centre of the driven element; 1:1 balun, directly 50 ohm")
    d.notes += ["The Moxon rectangle is compact (about 70% of a full-size Yagi's width) and has excellent front-to-back ratio (typically 25-35 dB) and a direct 50 ohm match.",
                "Best performance comes from the tuned gap: Press Optimise to refine it for your conductor size and height.",
                "Gain is about 5.5-6 dBi in free space, similar to a two-element Yagi."]
    if hexv:
        d.notes.append("Hex beam: the tails angle toward the centre to follow the hexagonal spreader frame; this geometry is an approximation of the commercial design.")
    size_warn(d, req, A, "Width")
    return d


register(Spec("moxon", "Moxon rectangle / Hex beam", "Directional beams", b_moxon,
              params=[Param("variant", "Type", "choice", "moxon", choices=[("Moxon rectangle", "moxon"), ("Hex beam (single band)", "hex")])],
              desc="Compact two-element wire beam with excellent front-to-back.", height_default=10.0,
              optimizable=True, optimize_default=True, size_label="Max width", feed_ratio=1.0, lmatch_default=False))


# =========================================================================== phased vertical arrays
PHASED = {
    "cardioid2": ("2-element cardioid (1/4 wl, 90 deg)", [(0, 0), (0.25, 0)], [0, -90], 0.0),
    "endfire2": ("2-element end-fire (1/2 wl, 180 deg)", [(0, 0), (0.5, 0)], [0, -180], 0.0),
    "broadside2": ("2-element broadside (1/2 wl, 0 deg)", [(0, 0), (0.5, 0)], [0, 0], 0.0),
    "line3": ("3-element end-fire (1/4 wl)", [(0, 0), (0.25, 0), (0.5, 0)], [0, -90, -180], 0.0),
    "square4": ("4-square (1/4 wl, 0/90/90/180 deg)", [(0, 0), (0.25, 0), (0, 0.25), (0.25, 0.25)], [0, -90, -90, -180], 45.0),
    "broadside4": ("4-element broadside (1/2 wl)", [(0, 0), (0.5, 0), (1.0, 0), (1.5, 0)], [0, 0, 0, 0], 0.0),
}


def b_phased(req, ex, sc):
    lam = req.lam
    var = P(ex, "variant", "square4")
    az = float(P(ex, "az", 0.0))
    nrad = int(P(ex, "nburied", 16))
    label, pos, ph, base = PHASED[var]
    d = Design("phased", label)
    st = new_struct(req, d, needs_ground=True)
    a, sg = req.radius, req.sigma
    L = 0.25 * lam * 0.97 * _sc(sc, "len")
    rg = ground_loss_r(nrad)
    rot = (90.0 - az) - base          # direction given as a compass bearing; +y is north
    ct, stt = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    cur = []
    for (px, py), p in zip(pos, ph):
        x, y = px * lam, py * lam
        xr, yr = x * ct - y * stt, x * stt + y * ct
        w = st.add((xr, yr, 0), (xr, yr, L), a, sigma=sg, min_seg=8)
        st.sources.append(Source(w, 0.0))
        st.loads.append(Load(w, 0.0, lambda f, r=rg: r + 0j, "radial loss"))
        cur.append(complex(math.cos(math.radians(p)), math.sin(math.radians(p))))
    d.mode = "currents"
    d.i_des = cur
    d.pol = "V"
    d.dim("Vertical elements", len(pos), L, "quarter-wave each")
    for k, ((px, py), p) in enumerate(zip(pos, ph)):
        x, y = px * lam, py * lam
        xr, yr = x * ct - y * stt, x * stt + y * ct
        d.dim(f"Element {k + 1} position (x, y)", 1, None, f"({xr:+.2f}, {yr:+.2f}) m, current phase {p:+d} deg")
    d.dim(f"Buried radials per element", nrad, 0.25 * lam, f"model assumes {rg:.1f} ohm ground loss per element")
    d.notes += ["The model feeds each element with the ideal current amplitude and phase shown; a real feed network (phasing lines, hybrid couplers) provides these.",
                "Element feedpoint impedances differ because of mutual coupling - see the port table.",
                "A full ground screen under every element is essential; without it ground loss eats the array gain."]
    return d


register(Spec("phased", "Phased vertical array (cardioid / 4-square / end-fire / broadside)", "Directional beams", b_phased,
              params=[Param("variant", "Array", "choice", "square4", choices=[(v[0], k) for k, v in PHASED.items()]),
                      Param("az", "Direction (azimuth)", "float", 0.0, 0, 359, 5, unit="deg"),
                      Param("nburied", "Radials per element", "int", 16, 2, 120, 2)],
              desc="Arrays of quarter-wave verticals phased for a steerable pattern.", height_default=0.0, uses_height=False,
              needs_ground=True, size_label="Max footprint", band_default="40 m (7.0-7.3 MHz)", lmatch_default=False))
