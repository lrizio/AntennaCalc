"""Evaluation engine: build -> tune -> sweep -> pattern -> metrics."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from . import mom
from .common import swr_from_z
from .design import Design, FeedChain, Requirements, Spec
from .mom import C0, Model, Structure


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------- model helpers
def seg_len_for(req: Requirements, design: Design, f_max_mhz: float | None = None) -> float:
    fm = f_max_mhz if f_max_mhz else (design.sweep_range[1] if design.sweep_range else req.f_hi)
    fm = max(fm, req.f_mhz)
    lam = C0 / (fm * 1e6)
    return design.seg_len_hint or (lam / req.spw)


def build_model(design: Design, req: Requirements) -> Model | None:
    if design.structure is None:
        return None
    return Model(design.structure, seg_len_for(req, design))


def terminal_z(design: Design, model: Model, f_mhz: float):
    """Impedance at the antenna terminals + the solution."""
    f = f_mhz * 1e6
    st = design.structure
    mode = design.mode
    if mode == "network":
        z, sol = mom.network_input_impedance(model, f)
        return z, sol
    if mode == "currents":
        sol = mom.solve_currents(model, f, np.array(design.i_des, complex))
        return sol.zin[0], sol
    sol = mom.solve(model, f)
    if mode == "equal" and len(sol.zin) > 1:
        itot = sum(sol.I[b] for b in sol.port_basis)
        v = st.sources[0].volts
        return v / itot, sol
    return sol.zin[0], sol


def make_feed(design: Design, req: Requirements, zant_f0: complex | None = None) -> FeedChain:
    ratio = design.force_ratio if design.force_ratio else req.ratio
    z0, vf, loss, _ = (50.0, 0.66, 8.6, 0.0)
    from .common import COAX
    c = COAX[req.coax_key]
    ln = req.coax_len if req.coax_key != "none" else 0.0
    fc = FeedChain(line=design.line, ratio=ratio, coax=(c[1], c[2], c[3], ln), zref=req.zref)
    if req.lmatch and zant_f0 is not None:
        zin = zant_f0
        if design.line:
            zin, _ = FeedChain.tline(zin, design.line, req.f_mhz)
        fc.lmatch_enabled = True
        fc.compute_lmatch(zin, req.f_mhz)
        if fc.lmatch is None:
            fc.lmatch_enabled = False
    return fc


# --------------------------------------------------------------------------- patterns
@dataclass
class Pattern:
    az_ang: np.ndarray = None       # degrees 0..359
    az_db: dict = None              # comp -> dBi
    el_ang: np.ndarray = None       # degrees along the vertical plane circle (0=front horizon)
    el_db: dict = None
    peak_db: float = 0.0
    peak_theta: float = 0.0         # deg from zenith
    peak_phi: float = 0.0
    takeoff: float = 0.0            # deg above horizon
    directivity: float = 0.0
    efficiency: float = 1.0
    fb: float | None = None
    fr: float | None = None
    hpbw_az: float | None = None
    hpbw_el: float | None = None
    pol: str = ""
    comp_peak: dict = None
    sphere: tuple | None = None     # (theta_deg, phi_deg, total_db) coarse grid for 3-D style views
    az_floor: float = -40.0
    peak_bearing: float = 0.0


COMPS = ("total", "vertical", "horizontal", "rhcp", "lhcp")


def _components(Et, Ep):
    return {
        "total": np.abs(Et) ** 2 + np.abs(Ep) ** 2,
        "vertical": np.abs(Et) ** 2,
        "horizontal": np.abs(Ep) ** 2,
        "rhcp": np.abs(Et + 1j * Ep) ** 2 / 2,
        "lhcp": np.abs(Et - 1j * Ep) ** 2 / 2,
    }


def _beamwidth(vals_db: np.ndarray, ipk: int, step_deg: float, circular: bool) -> float | None:
    n = len(vals_db)
    thr = vals_db[ipk] - 3.0
    if not np.isfinite(vals_db[ipk]):
        return None
    up = 0
    i = ipk
    while up < n:
        j = (i + 1) % n if circular else i + 1
        if (not circular and j >= n) or vals_db[j] < thr:
            break
        i = j
        up += 1
    dn = 0
    i = ipk
    while dn < n:
        j = (i - 1) % n if circular else i - 1
        if (not circular and j < 0) or vals_db[j] < thr:
            break
        i = j
        dn += 1
    if up + dn >= n - 1:
        return None                 # omnidirectional / no -3 dB points
    return (up + dn + 1) * step_deg


def _gain_fn_factory(design: Design, sol, pin: float, ground_on: bool):
    """Returns (g_of_theta_phi -> dict comp->linear gain, up_only)"""
    if design.analytic is not None:
        an = design.analytic

        def fn(theta, phi):
            g = 10 ** (an.gain_db(theta, phi) / 10)
            out = {c: np.zeros_like(g) for c in COMPS}
            # distribute the analytic gain into the declared polarisation
            if an.pol == "V":
                out["total"] = g; out["vertical"] = g
            elif an.pol == "H":
                out["total"] = g; out["horizontal"] = g
            elif an.pol == "CP":
                out["total"] = g; out["rhcp"] = g * 0.97; out["lhcp"] = g * 0.03
            else:
                out["total"] = g; out["vertical"] = g * 0.5; out["horizontal"] = g * 0.5
            return out
        return fn, an.upper_only

    def fn(theta, phi):
        Et, Ep = mom.far_field(sol, theta, phi)
        scale = 4 * math.pi * mom.k_const(sol) / pin
        comps = _components(Et, Ep)
        return {c: v * scale for c, v in comps.items()}
    return fn, ground_on


def compute_pattern(design: Design, sol, req: Requirements, fine: bool = True) -> Pattern:
    gnd = design.structure.ground.kind != "free" if design.structure else False
    pin = sol.pin if sol is not None else 1.0
    fn, upper = _gain_fn_factory(design, sol, pin, gnd)
    upper = bool(upper)
    dth, dph = (4.0, 5.0) if fine else (8.0, 12.0)
    th = np.arange(0, (90 if upper else 180) + 1e-9, dth)
    ph = np.arange(0, 360, dph)
    T, P = np.meshgrid(np.radians(th), np.radians(ph), indexing="ij")
    comps = fn(T, P)
    head = "total"
    if design.cp == "R":
        head = "rhcp"
    elif design.cp == "L":
        head = "lhcp"
    G = comps[head]
    w = np.sin(T)
    wt = np.ones(len(th)); wt[0] = 0.5; wt[-1] = 0.5
    prad = float(np.sum(comps["total"] / (4 * math.pi) * w * wt[:, None]) * math.radians(dth) * math.radians(dph) * 4 * math.pi)
    # 4*pi*U integrated: comps are gains = 4 pi U / Pin ; Prad/Pin = (1/4pi) * integral(G dOmega)
    eff = prad / (4 * math.pi)
    i = np.unravel_index(np.argmax(G), G.shape)
    pk_th, pk_ph = th[i[0]], ph[i[1]]
    if fine:                                    # local refinement
        tt = np.arange(max(0, pk_th - dth), min(180, pk_th + dth) + 1e-9, 0.5)
        pp = np.arange(pk_ph - dph, pk_ph + dph + 1e-9, 1.0)
        T2, P2 = np.meshgrid(np.radians(tt), np.radians(pp), indexing="ij")
        c2 = fn(T2, P2)[head]
        j = np.unravel_index(np.argmax(c2), c2.shape)
        pk_th, pk_ph = tt[j[0]], pp[j[1]] % 360
    pat = Pattern()
    pat.peak_theta, pat.peak_phi = float(pk_th), float(pk_ph)
    pat.takeoff = 90.0 - pk_th
    # azimuth cut at the peak take-off angle
    az = np.arange(0, 360, 1.0)
    Ta = np.full_like(az, math.radians(pk_th))
    caz = fn(Ta, np.radians(az))
    pat.az_ang = az
    pat.az_db = {c: 10 * np.log10(np.maximum(v, 1e-6)) for c, v in caz.items()}
    # vertical-plane cut: full circle through zenith in the plane containing the peak azimuth
    psi = np.arange(0, 360, 1.0)
    thv = np.zeros_like(psi); phv = np.zeros_like(psi)
    for k, a in enumerate(psi):
        if a <= 90:
            thv[k], phv[k] = 90 - a, pk_ph
        elif a <= 180:
            thv[k], phv[k] = a - 90, pk_ph + 180
        elif a <= 270:
            thv[k], phv[k] = a - 90, pk_ph + 180
        else:
            thv[k], phv[k] = 450 - a, pk_ph
    if upper:
        cel = {c: np.zeros_like(psi) for c in COMPS}
        okm = thv <= 90 + 1e-9
        cc = fn(np.radians(np.where(okm, thv, 90)), np.radians(phv))
        for c in COMPS:
            cel[c] = np.where(okm, cc[c], 0.0)
        # below the horizon we have no pattern: mark
        below = ((psi > 180) & (psi < 360)) | False
    else:
        cel = fn(np.radians(thv), np.radians(phv))
    pat.el_ang = psi
    pat.el_db = {c: 10 * np.log10(np.maximum(v, 1e-6)) for c, v in cel.items()}
    if upper:
        # the 270..360 / 180..270 branch below the horizon is empty in a ground-plane model
        for c in COMPS:
            m = (psi > 180) & (psi < 360)
            pat.el_db[c][m] = -60
            m2 = psi == 180
            pat.el_db[c][m2] = pat.el_db[c][m2]
    pat.peak_db = float(10 * math.log10(max(G.max(), 1e-9))) if not fine else float(10 * np.log10(max(np.max(c2), 1e-9)))
    pat.efficiency = float(min(eff, 1.0)) if design.analytic is None else float(getattr(design.analytic, "eta", 1.0))
    pat.directivity = pat.peak_db - 10 * math.log10(max(pat.efficiency, 1e-6))
    # beamwidths and F/B from the cuts
    azh = pat.az_db[head]
    ipk = int(round(pk_ph)) % 360
    mean_lin = float(np.mean(10 ** (azh / 10)))
    directional = 10 ** (azh[ipk] / 10) > 2.0 * mean_lin
    pat.hpbw_az = _beamwidth(azh, ipk, 1.0, True)
    if directional:
        back = azh[(ipk + 180) % 360]
        pat.fb = float(azh[ipk] - back)
        rear = np.array([azh[(ipk + d) % 360] for d in range(90, 271)])
        pat.fr = float(azh[ipk] - rear.max())
    elv = pat.el_db[head]
    ipe = int(np.argmax(elv))
    pat.hpbw_el = _beamwidth(elv, ipe, 1.0, False if upper else True)
    pk = {c: float(10 * math.log10(max(comps[c].max(), 1e-9))) for c in COMPS}
    pat.comp_peak = pk
    ptot = comps["total"].max()
    rv, rh = pk["vertical"], pk["horizontal"]
    rr, rl = pk["rhcp"], pk["lhcp"]
    if design.analytic is not None and design.analytic.pol == "CP":
        pat.pol = "Circular (RHCP)" if rr >= rl else "Circular (LHCP)"
    elif max(rr, rl) > max(rv, rh) - 1.5 and abs(rr - rl) > 6:
        pat.pol = "Circular (RHCP)" if rr > rl else "Circular (LHCP)"
    elif rv > rh + 6:
        pat.pol = "Vertical"
    elif rh > rv + 6:
        pat.pol = "Horizontal"
    else:
        pat.pol = "Mixed / slant"
    if design.pol in ("V", "H"):
        pass
    pat.sphere = (th, ph, 10 * np.log10(np.maximum(G, 1e-6)))
    # compass bearing for display: +y is north, +x is east
    bear = (90.0 - pat.az_ang) % 360.0
    order = np.argsort(bear)
    pat.az_ang = bear[order]
    pat.az_db = {c: v[order] for c, v in pat.az_db.items()}
    pat.peak_bearing = float((90.0 - pat.peak_phi) % 360.0)
    return pat


# --------------------------------------------------------------------------- tuning
def _target_error(tg, design, model, z):
    if tg.kind == "x0":
        return z.imag
    return (z.real - tg.target) / tg.target


def _scan_root(tg, z_of, guess, tol):
    """Fallback: scan the allowed range for sign changes of the target error, refine with Brent."""
    from scipy.optimize import brentq
    xs = np.linspace(tg.lo, tg.hi, 15)
    es = []
    for x in xs:
        try:
            es.append(_target_error(tg, None, None, z_of(x)))
        except Exception:
            es.append(float("nan"))
    es = np.array(es)
    cands = []
    for i in range(len(xs) - 1):
        if np.isfinite(es[i]) and np.isfinite(es[i + 1]) and es[i] * es[i + 1] <= 0:
            cands.append(i)
    if not cands:
        i = int(np.nanargmin(np.abs(es)))
        return xs[i]
    i = min(cands, key=lambda k: abs(0.5 * (xs[k] + xs[k + 1]) - guess))
    f = lambda x: _target_error(tg, None, None, z_of(x))
    return brentq(f, xs[i], xs[i + 1], xtol=1e-5, maxiter=30)


def tune(spec: Spec, req: Requirements, ex: dict, scales: dict, progress=None, cancel=None) -> dict:
    scales = dict(scales)
    d0 = spec.builder(req, ex, scales)
    if not d0.tune or d0.structure is None:
        return scales
    ntg = len(d0.tune)
    rounds = 3 if ntg > 1 else 1
    total = rounds * ntg
    done = 0
    for rd in range(rounds):
        for tg in d0.tune:
            if cancel and cancel():
                raise Cancelled()

            def z_of(s):
                sc = dict(scales); sc[tg.key] = s
                d = spec.builder(req, ex, sc)
                m = build_model(d, req)
                z, _ = terminal_z(d, m, tg.f_mhz)
                return z
            x0 = scales.get(tg.key, 1.0)
            x1 = x0 * 1.02
            tol = 0.3 if tg.kind == "x0" else 0.01
            best_x = x0
            try:
                e0 = _target_error(tg, d0, None, z_of(x0))
                e1 = _target_error(tg, d0, None, z_of(x1))
                for _ in range(9):
                    if abs(e1) < tol:
                        break
                    if abs(e1 - e0) < 1e-12:
                        break
                    xn = x1 - e1 * (x1 - x0) / (e1 - e0)
                    xn = min(max(xn, tg.lo), tg.hi)
                    x0, e0 = x1, e1
                    x1 = xn
                    e1 = _target_error(tg, d0, None, z_of(x1))
                    if abs(x1 - x0) < 1e-5:
                        break
                best_x = x1 if abs(e1) <= abs(e0) else x0
                if abs(min(e0, e1, key=abs)) >= tol * 3:
                    best_x = _scan_root(tg, z_of, best_x, tol)
            except Exception:
                try:
                    best_x = _scan_root(tg, z_of, best_x, tol)
                except Exception:
                    pass
            scales[tg.key] = float(best_x)
            done += 1
            if progress:
                progress(done / total, f"Tuning {tg.label or tg.key}  ({done}/{total})")
    return scales


# --------------------------------------------------------------------------- optimiser
def optimize(spec: Spec, req: Requirements, ex: dict, scales: dict, progress=None, cancel=None,
             maxiter: int = 60) -> dict:
    from scipy.optimize import minimize
    d0 = spec.builder(req, ex, scales)
    keys = d0.opt_keys
    if not keys or d0.structure is None:
        return scales
    fast_req = copy.copy(req)
    fast_req.spw = min(req.spw, 14)
    k_names = [k[0] for k in keys]
    x0 = np.array([scales.get(k, 1.0) for k in k_names])
    lo = np.array([k[1] for k in keys]); hi = np.array([k[2] for k in keys])
    count = [0]
    drv = d0.tune[0] if d0.tune else None

    def evaluate(x):
        if cancel and cancel():
            raise Cancelled()
        sc = dict(scales)
        for k, v in zip(k_names, np.clip(x, lo, hi)):
            sc[k] = float(v)
        pen = 0.0
        # keep the driven element resonant: two secant steps
        if drv is not None:
            def zf(s):
                s2 = dict(sc); s2[drv.key] = s
                d = spec.builder(fast_req, ex, s2)
                m = build_model(d, fast_req)
                z, _ = terminal_z(d, m, drv.f_mhz)
                return z
            a = sc.get(drv.key, 1.0)
            za = zf(a); b = a * 1.01; zb = zf(b)
            for _ in range(2):
                if abs(zb.imag - za.imag) < 1e-9:
                    break
                n = b - zb.imag * (b - a) / (zb.imag - za.imag)
                n = min(max(n, drv.lo), drv.hi)
                a, za = b, zb
                b = n
                zb = zf(b)
            sc[drv.key] = b
            z = zb
        d = spec.builder(fast_req, ex, sc)
        m = build_model(d, fast_req)
        z, sol = terminal_z(d, m, req.f_mhz)
        pat = compute_pattern(d, sol, fast_req, fine=False)
        g = pat.comp_peak["rhcp" if d.cp == "R" else "lhcp" if d.cp == "L" else "total"]
        fb = pat.fr if pat.fr is not None else 0.0
        r_pen = max(0.0, 12.0 - z.real) * 0.15 + abs(z.imag) / 80.0
        count[0] += 1
        if progress:
            progress(min(0.95, count[0] / maxiter), f"Optimising ({count[0]}): gain {g:.2f} dBi, F/R {fb:.1f} dB")
        return -g - 0.25 * min(fb, 28.0) + r_pen, sc

    best = {"v": 1e9, "sc": dict(scales)}

    def obj(x):
        v, sc = evaluate(x)
        if v < best["v"]:
            best["v"], best["sc"] = v, sc
        return v
    try:
        minimize(obj, x0, method="Nelder-Mead",
                 options={"maxfev": maxiter, "xatol": 2e-3, "fatol": 5e-3,
                          "initial_simplex": np.vstack([x0] + [x0 + np.eye(len(x0))[i] * 0.03 for i in range(len(x0))])})
    except Cancelled:
        raise
    return best["sc"]


# --------------------------------------------------------------------------- full evaluation
@dataclass
class Result:
    design: Design
    req: Requirements
    scales: dict
    f: np.ndarray = None
    zant: np.ndarray = None
    zfeed: np.ndarray = None
    zrig: np.ndarray = None
    swr_rig: np.ndarray = None
    swr_feed: np.ndarray = None
    swr_line: np.ndarray = None
    coax_loss: np.ndarray = None
    pattern: Pattern | None = None
    feed: FeedChain | None = None
    metrics: dict = field(default_factory=dict)
    bands: list = field(default_factory=list)
    sol0: object = None
    model: Model | None = None
    port_info: list = field(default_factory=list)
    ex: dict = field(default_factory=dict)
    basis: str = "ground"
    free_gain: float | None = None
    spec: object = None


def sweep_freqs(design: Design, req: Requirements, n: int = 25) -> np.ndarray:
    if design.sweep_range:
        lo, hi = design.sweep_range
        return np.linspace(lo, hi, 41 if design.imp_override is not None else max(n, 21))
    width = req.f_hi - req.f_lo
    span = max(width * 2.0, 0.06 * req.f_mhz)
    c = 0.5 * (req.f_lo + req.f_hi) if width > 0 else req.f_mhz
    return np.linspace(c - span / 2, c + span / 2, n)


def evaluate(spec: Spec, req: Requirements, ex: dict, scales: dict, progress=None, cancel=None,
             do_sweep: bool = True, do_bands: bool = True) -> Result:
    design = spec.builder(req, ex, scales)
    res = Result(design=design, req=req, scales=dict(scales), spec=spec)
    if design.analytic is not None:
        return _evaluate_analytic(spec, design, req, res, do_sweep)
    model = build_model(design, req)
    res.model = model
    if progress:
        progress(0.02, f"Solving at {req.f_mhz:.3f} MHz ({model.N} segments)")
    z0, sol0 = terminal_z(design, model, req.f_mhz)
    res.sol0 = sol0
    if design.imp_override is not None:
        z0 = design.imp_override(req.f_mhz)
    fc = make_feed(design, req, z0)
    res.feed = fc
    pattern_fine = True
    res.pattern = compute_pattern(design, sol0, req, fine=pattern_fine)
    # port table for arrays
    if len(sol0.zin) > 1:
        res.port_info = [(i, sol0.zin[i], abs(sol0.I[b]), math.degrees(cmath_phase(sol0.I[b])))
                         for i, b in enumerate(sol0.port_basis)]
    freqs = sweep_freqs(design, req)
    n = len(freqs)
    za = np.zeros(n, complex)
    if do_sweep:
        for i, f in enumerate(freqs):
            if cancel and cancel():
                raise Cancelled()
            if design.imp_override is not None:
                za[i] = design.imp_override(f)
            else:
                za[i], _ = terminal_z(design, model, f)
            if progress:
                progress(0.1 + 0.7 * (i + 1) / n, f"Sweep {i + 1}/{n}  ({f:.3f} MHz)")
    else:
        freqs = np.array([req.f_mhz]); za = np.array([z0])
    _fill_sweep(res, design, req, fc, freqs, za)
    res.metrics = summarize(res, z0)
    if do_bands and design.multiband:
        res.bands = band_table(spec, design, req, model, fc, progress, cancel)
    if progress:
        progress(1.0, "Done")
    return res


def cmath_phase(z):
    return math.atan2(z.imag, z.real)


def _fill_sweep(res, design, req, fc, freqs, za):
    n = len(freqs)
    res.f = freqs
    res.zant = za
    zf = np.zeros(n, complex); zr = np.zeros(n, complex); cl = np.zeros(n)
    sl = np.zeros(n)
    for i, (f, z) in enumerate(zip(freqs, za)):
        if design.imp_override is not None:
            zf[i] = zr[i] = z
        else:
            o = fc.apply(z, f)
            zf[i], zr[i], cl[i] = o["zfeed"], o["zrig"], o["coax_loss_db"]
        if design.line:
            sl[i] = swr_from_z(z, design.line[0])
        else:
            sl[i] = swr_from_z(z, req.zref * (design.force_ratio or req.ratio))
    res.zfeed, res.zrig, res.coax_loss = zf, zr, cl
    res.swr_feed = np.array([swr_from_z(z, req.zref) for z in zf])
    res.swr_rig = np.array([swr_from_z(z, req.zref) for z in zr])
    res.swr_line = sl


def _evaluate_analytic(spec, design, req, res, do_sweep):
    an = design.analytic
    res.pattern = compute_pattern(design, None, req, fine=True)
    fc = FeedChain(ratio=1.0, coax=(50.0, 0.66, 8.6, 0.0), zref=req.zref)
    res.feed = fc
    freqs = sweep_freqs(design, req, 41)
    za = np.array([an.zin(f) for f in freqs])
    _fill_sweep(res, design, req, fc, freqs, za)
    # analytic models give the system-side impedance directly
    res.zfeed = res.zrig = za
    res.swr_feed = res.swr_rig = np.array([swr_from_z(z, req.zref) for z in za])
    z0 = an.zin(req.f_mhz)
    res.metrics = summarize(res, z0)
    return res


def summarize(res: Result, z0: complex) -> dict:
    req, p, d = res.req, res.pattern, res.design
    m = {}
    m["z_ant"] = z0
    i0 = int(np.argmin(np.abs(res.f - req.f_mhz)))
    m["z_feed"] = res.zfeed[i0]
    m["z_rig"] = res.zrig[i0]
    m["swr_f0"] = float(res.swr_rig[i0])
    m["swr_feed_f0"] = float(res.swr_feed[i0])
    m["swr_line_f0"] = float(res.swr_line[i0])
    m["coax_loss_db"] = float(res.coax_loss[i0]) if res.coax_loss is not None else 0.0
    m["gain_dbi"] = p.peak_db
    m["gain_dbd"] = p.peak_db - 2.15
    m["directivity"] = p.directivity
    m["efficiency"] = p.efficiency
    m["fb"] = p.fb
    m["fr"] = p.fr
    m["hpbw_az"] = p.hpbw_az
    m["hpbw_el"] = p.hpbw_el
    m["takeoff"] = p.takeoff
    m["peak_az"] = p.peak_bearing
    m["pol"] = p.pol
    # SWR bandwidth around f0
    f, s = res.f, res.swr_rig
    for lim, key in ((2.0, "bw2"), (1.5, "bw15")):
        ok = s <= lim
        if ok[i0]:
            lo = i0
            while lo > 0 and ok[lo - 1]:
                lo -= 1
            hi = i0
            while hi < len(f) - 1 and ok[hi + 1]:
                hi += 1
            m[key] = (float(f[lo]), float(f[hi]), bool(lo == 0 or hi == len(f) - 1))
        else:
            m[key] = None
    # band coverage
    if req.f_hi > req.f_lo:
        sel = (f >= req.f_lo) & (f <= req.f_hi)
        m["band_ok"] = float(np.mean(s[sel] <= 2.0)) if sel.any() else None
        m["band_max_swr"] = float(np.max(s[sel])) if sel.any() else None
    else:
        m["band_ok"] = None
    # RF stress at the feedpoint
    pw = req.power_w
    zf = m["z_feed"]
    rr = max(zf.real, 1e-3)
    i_rms = math.sqrt(pw / rr)
    m["feed_i"] = i_rms
    m["feed_v"] = math.sqrt(pw * abs(zf) ** 2 / rr)
    return m


def band_table(spec, design, req, model, fc, progress=None, cancel=None):
    rows = []
    n = len(design.multiband)
    for k, (label, f) in enumerate(design.multiband):
        if cancel and cancel():
            raise Cancelled()
        try:
            z, sol = terminal_z(design, model, f)
            o = fc.apply(z, f)
            pat = compute_pattern(design, sol, req, fine=False)
            rows.append((label, f, z, swr_from_z(o["zrig"], req.zref), pat.comp_peak["total"], pat.takeoff))
        except Exception as e:      # an unsupported band must not kill the whole report
            rows.append((label, f, complex("nan"), float("nan"), float("nan"), float("nan")))
        if progress:
            progress(0.8 + 0.2 * (k + 1) / n, f"Band table {label}")
    return rows


# --------------------------------------------------------------------------- gain-target sizing
def headline_gain(pat: Pattern, design: Design) -> float:
    if design.cp == "R":
        return pat.comp_peak["rhcp"]
    if design.cp == "L":
        return pat.comp_peak["lhcp"]
    return pat.comp_peak["total"]


def auto_design(spec: Spec, req: Requirements, ex: dict, basis: str = "free", progress=None, cancel=None, margin: float = 0.0):
    """Choose spec.auto_key (e.g. number of elements) to reach req.target_gain within req.max_size.
    Returns (ex_new, notes)."""
    notes = []
    if not spec.auto_key or req.target_gain is None:
        return ex, notes
    lo, hi = spec.auto_lo, spec.auto_hi
    if spec.size_fn and req.max_size > 0:
        while hi > lo and spec.size_fn(req, ex, hi) > req.max_size:
            hi -= 1
        if spec.size_fn(req, ex, lo) > req.max_size:
            notes.append(f"Even the smallest version is {spec.size_fn(req, ex, lo):.2f} m, over the {req.max_size:.2f} m limit.")
    r2 = copy.copy(req)
    r2.spw = min(req.spw, 12)
    if basis == "free":
        r2.ground = mom.Ground("free")

    def gain_for(n):
        e = dict(ex); e[spec.auto_key] = n
        d = spec.builder(r2, e, {})
        m = build_model(d, r2)
        z, sol = terminal_z(d, m, r2.f_mhz)
        pat = compute_pattern(d, sol, r2, fine=False)
        return headline_gain(pat, d)
    cache = {}

    def g(n):
        if n not in cache:
            if cancel and cancel():
                raise Cancelled()
            cache[n] = gain_for(n)
            if progress:
                progress(0.05, f"Sizing: {n} {spec.auto_key} -> {cache[n]:.1f} dBi")
        return cache[n]
    tgt = req.target_gain - margin
    if g(hi) < tgt:
        notes.append(f"With {hi} elements the gain is {g(hi):.1f} dBi, short of the {tgt:.1f} dBi target"
                     + (" (size limit reached)." if hi < spec.auto_hi else " (largest design supported)."))
        pick = hi
    else:
        a, b = lo, hi
        while a < b:
            mid = (a + b) // 2
            if g(mid) >= tgt:
                b = mid
            else:
                a = mid + 1
        pick = a
        notes.append(f"{pick} elements give {g(pick):.1f} dBi ({'free space' if basis == 'free' else 'over ground'}), meeting the {tgt:.1f} dBi target.")
    e = dict(ex); e[spec.auto_key] = pick
    return e, notes


def free_space_gain(spec: Spec, req: Requirements, ex: dict, scales: dict) -> float | None:
    """Peak gain of the same antenna with the ground removed (for gain targets stated in free space)."""
    try:
        if req.ground.kind == "free" or spec.analytic:
            return None
        r2 = copy.copy(req)
        r2.spw = min(req.spw, 14)
        r2.ground = mom.Ground("free")
        d = spec.builder(r2, ex, scales)
        if d.structure is None:
            return None
        d.structure.ground = mom.Ground("free")
        m = build_model(d, r2)
        z, sol = terminal_z(d, m, r2.f_mhz)
        return headline_gain(compute_pattern(d, sol, r2, fine=False), d)
    except Exception:
        return None


def max_extent(design: Design) -> float:
    """Largest single dimension (m) of the structure."""
    if design.structure is not None and design.structure.wires:
        pts = np.array([w.p0 for w in design.structure.wires] + [w.p1 for w in design.structure.wires])
        return float(np.ptp(pts, axis=0).max())
    ls = [d.length_m for d in design.dims if d.length_m]
    return float(max(ls)) if ls else 0.0


def extents(design: Design):
    if design.structure is not None and design.structure.wires:
        pts = np.array([w.p0 for w in design.structure.wires] + [w.p1 for w in design.structure.wires])
        return np.ptp(pts, axis=0)
    return None
