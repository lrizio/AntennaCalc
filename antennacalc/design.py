"""Framework types: requirements, design result, spec registry, feed chain."""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .common import BAND_BY_LABEL, COAX, HF_BAND_LABELS, swr_from_z
from .mom import C0, Ground, Structure


# --------------------------------------------------------------------------- requirements
@dataclass
class Requirements:
    f_mhz: float = 14.15
    f_lo: float = 14.0
    f_hi: float = 14.35
    band_label: str = ""
    target_gain: float | None = None      # dBi, None = no target
    max_size: float = 0.0                 # metres, 0 = unlimited (longest dimension / boom)
    radius: float = 1.0e-3                # conductor radius, m
    sigma: float = 5.65e7
    density: float = 8.96
    material: str = "Copper"
    diameter_mm: float = 2.0
    hollow_wall_mm: float = 0.0           # 0 = solid
    height: float = 10.0                  # m above ground
    ground: Ground = field(default_factory=lambda: Ground("real", 0.005, 13.0))
    power_w: float = 100.0
    zref: float = 50.0
    ratio: float = 1.0                    # transformer n:1 (antenna side impedance is n x system)
    coax_key: str = "rg213"
    coax_len: float = 15.0
    feeder_key: str = "model"             # antenna-side feed line: "model" (the antenna's own), "none", or a COAX key
    feeder_len: float = 15.0              # m
    balun_loss_db: float = 0.0            # balun / unun insertion loss when matched (0 = ideal)
    tuner: str = "none"                   # none | rig3 | rig10 | wide  (ATU at the transmitter)
    tuner_q: float = 0.0                  # tuner inductor Q; 0 = typical for the tuner type
    balun_type: str = "current"           # current | voltage | unun
    choke_ohm: float = 2000.0             # common-mode impedance of a current balun / choke
    cm_model: bool = False                # estimate the common-mode current on the coax
    cm_grounded: bool = True              # coax shield grounded at the radio
    choke2_ohm: float = 0.0               # extra common-mode choke on the coax; 0 = none
    choke2_dist: float = 0.0              # its distance down the coax from the balun, m
    coax_dir: float = -1.0                # bearing of the coax run, degrees from +X toward +Y; -1 = at right angles to the antenna
    coax_height: float = 1.0              # height of the coax's horizontal run, m
    feeder_bottom: float = 2.0            # height the feed line comes down to (the balun), m
    lmatch: bool = False
    spw: int = 20                         # segments per wavelength
    auto_tune: bool = True
    optimize: bool = False
    wide_lo: float = 1.8                  # scan start/stop (MHz) used when wide_sweep is on
    wide_hi: float = 55.0
    wide_sweep: bool = False              # sweep 1.8-55 MHz instead of just the band

    @property
    def lam(self) -> float:
        return C0 / (self.f_mhz * 1e6)


@dataclass
class Param:
    key: str
    label: str
    kind: str                  # int | float | choice | bool | band
    default: object
    lo: float = 0.0
    hi: float = 0.0
    step: float = 1.0
    choices: list = field(default_factory=list)   # [(label, value)]
    unit: str = ""
    tip: str = ""
    decimals: int = 2


@dataclass
class Dim:
    item: str
    qty: int = 1
    length_m: float | None = None
    note: str = ""


@dataclass
class TuneTarget:
    key: str
    f_mhz: float
    kind: str = "x0"           # x0 (zero reactance) | r (match resistance to target) | swr (best compromise over `freqs`)
    target: float = 50.0
    lo: float = 0.5
    hi: float = 1.8
    port: int = 0
    label: str = ""
    freqs: list | None = None  # MHz, for kind "swr"


TUNERS = [("No tuner", "none", 0.0), ("Rig's internal ATU (about 3:1)", "rig3", 3.0),
          ("External ATU (about 10:1)", "rig10", 10.0), ("Wide-range / balanced tuner", "wide", float("inf"))]
TUNER_RANGE = {k: r for _, k, r in TUNERS}
# typical unloaded Q of the tuner's inductor at HF: small toroids in a rig's ATU, a good roller / air coil outside
TUNER_Q = {"rig3": 60.0, "rig10": 120.0, "wide": 150.0}
TUNER_CAP_Q = 1000.0                      # air / vacuum variable capacitors: nearly lossless
# network inside each tuner: rig ATUs and balanced tuners are L networks, the usual external ATU is a high-pass T
TUNER_TOPOLOGY = {"rig3": "L", "rig10": "T", "wide": "L"}
T_CMAX_PF = 250.0                         # largest setting of each T-network capacitor


def _el_z(kind: str, x: float, q_l: float, q_c: float) -> complex:
    """Lossy reactance: inductor (x > 0) with Q q_l, capacitor (x < 0) with Q q_c."""
    return complex(abs(x) / (q_l if kind == "L" else q_c), x)


def t_tuner_loss(z: complex, zref: float, f_mhz: float, q_l: float, q_c: float = TUNER_CAP_Q,
                 cmax_pf: float = T_CMAX_PF) -> float:
    """Loss (dB) of a high-pass T tuner (series C2 at the load, shunt L, series C1 to the transmitter), at the
    lowest-loss setting it can reach: the operator's best tuning.  inf if it cannot match."""
    w = 2 * math.pi * f_mhz * 1e6
    best = float("inf")
    for c2 in np.geomspace(10e-12, cmax_pf * 1e-12, 60):
        x2 = -1 / (w * c2)
        zp = z + complex(0, x2)                      # load plus the output capacitor (ideal, for the design)
        R, X = zp.real, zp.imag
        den = R * R + X * X
        G, Bl = R / den, -X / den
        if G > 1 / zref:
            continue
        for sgn in (1, -1):
            B = sgn * math.sqrt(G / zref - G * G) - Bl  # shunt susceptance added
            if B >= 0:                                   # must be an inductor
                continue
            yp = complex(G, Bl + B)
            xs = -(1 / yp).imag                          # series reactance toward the transmitter
            if xs >= 0 or -1 / (w * xs) > cmax_pf * 1e-12:   # must be a capacitor within range
                continue
            zc2 = _el_z("C", x2, q_l, q_c)
            zl = _el_z("L", -1 / B, q_l, q_c)
            zc1 = _el_z("C", xs, q_l, q_c)
            i_load = 1.0
            v1 = z * i_load + zc2 * i_load               # node at the shunt inductor
            i1 = i_load + v1 / zl
            vin = v1 + zc1 * i1
            p_load = (z * i_load).real
            p_in = (vin * i1.conjugate()).real
            if p_load > 0 and p_in > 0:
                best = min(best, 10 * math.log10(p_in / p_load))
    return best


def tuner_loss(z: complex, zref: float, f_mhz: float, q_l: float, q_c: float = TUNER_CAP_Q) -> tuple[float, tuple | None]:
    """Loss (dB) of a tuner matching load z to zref, modelled as the lowest-loss L network with finite component Q.
    Real T-network tuners need more circulating current and lose at least this much, often more at low impedances.
    Returns (loss dB, (kind, series element, shunt element)) or (0, None) when no network is needed or possible."""
    if not (z.real > 0) or swr_from_z(z, zref) < 1.05:
        return 0.0, None
    sol = l_match(z, zref, f_mhz)
    if sol is None:
        return 0.0, None
    kind, se, sh = sol
    w = 2 * math.pi * f_mhz * 1e6

    def zel(e):
        t, v = e
        return _el_z(t, w * v if t == "L" else -1 / (w * v), q_l, q_c)
    zse, zsh = zel(se), zel(sh)
    vl, il = z, 1.0                      # unit current into the load
    if kind == "shunt_first":            # shunt across the load, series toward the transmitter
        i1 = il + vl / zsh
        vin, iin = vl + i1 * zse, i1
    else:                                # series at the load, shunt toward the transmitter
        v1 = vl + il * zse
        vin, iin = v1, il + v1 / zsh
    p_load = (vl * complex(il).conjugate()).real
    p_in = (vin * iin.conjugate()).real
    if p_load <= 0 or p_in <= 0:
        return 0.0, sol
    return 10 * math.log10(p_in / p_load), sol


def line_section(zl: complex, spec: tuple, f_mhz: float) -> tuple[complex, float]:
    """Lossy line terminated in zl -> (input impedance, actual loss in dB at this mismatch).
    The loss is the real power ratio in/out, so it includes the extra loss caused by standing waves."""
    z0, vf, loss100, length = spec
    if length <= 0:
        return zl, 0.0
    a_db = loss100 * math.sqrt(f_mhz / 100.0) * length / 100.0
    alpha = a_db / 8.686 / length
    beta = 2 * math.pi * f_mhz * 1e6 / (C0 * vf)
    g = complex(alpha, beta) * length
    ch, sh = cmath.cosh(g), cmath.sinh(g)
    if abs(zl) > 1e12 or not math.isfinite(abs(zl)):       # open end: no power reaches it
        return z0 * ch / sh, float("inf")
    v2, i2 = zl, 1.0
    v1 = ch * v2 + z0 * sh * i2
    i1 = sh / z0 * v2 + ch * i2
    p_out = (v2 * i2.conjugate()).real
    p_in = (v1 * i1.conjugate()).real
    zin = v1 / i1
    if p_out <= 1e-15 or p_in <= 0:
        return zin, float("inf")
    return zin, 10 * math.log10(p_in / p_out)


@dataclass
class FeedChain:
    """antenna -> [feeder line] -> [L-match] -> [balun / transformer] -> [coax] -> [tuner] -> rig"""
    line: tuple | None = None          # (z0, vf, loss100, length_m)
    lmatch: tuple | None = None        # computed (kind, elements) or None
    ratio: float = 1.0
    coax: tuple = (50.0, 0.66, 8.6, 0.0)   # z0, vf, loss dB/100m @100MHz, length
    zref: float = 50.0
    lmatch_enabled: bool = False
    lmatch_f0: float = 0.0
    xfmr_g: float = 0.0                # shunt conductance (S) across the transformer's 50 ohm side (core loss)
    line_name: str = "Feed line"
    coax_name: str = "Coax"
    tuner_range: float = 0.0           # max SWR the tuner at the transmitter can match; 0 = no tuner
    tuner_name: str = ""
    tuner_q: float = 100.0             # inductor Q used for the tuner loss estimate
    tuner_topology: str = "L"          # L | T
    balun_name: str = "Balun / unun"

    # transmission line transform with loss
    @staticmethod
    def tline(zl: complex, spec: tuple, f_mhz: float, z0_override=None) -> tuple[complex, float]:
        z0, vf, loss100, length = spec
        if length <= 0:
            return zl, 0.0
        a_db = loss100 * math.sqrt(f_mhz / 100.0) * length / 100.0
        alpha = a_db / 8.686 / length
        beta = 2 * math.pi * f_mhz * 1e6 / (C0 * vf)
        g = complex(alpha, beta) * length
        ch, sh = cmath.cosh(g), cmath.sinh(g)
        if abs(zl) > 1e12:
            zin = z0 * ch / sh
        else:
            zin = z0 * (zl * ch + z0 * sh) / (z0 * ch + zl * sh)
        return zin, a_db

    def compute_lmatch(self, z_at_match: complex, f_mhz: float):
        """Design an L network making z_at_match (antenna-side) look like (zref*ratio)."""
        rt = self.zref * self.ratio
        sol = l_match(z_at_match, rt, f_mhz)
        self.lmatch = sol
        self.lmatch_f0 = f_mhz

    def _lm(self, z: complex, f_mhz: float) -> complex:
        if not (self.lmatch_enabled and self.lmatch):
            return z
        kind, se, sh = self.lmatch     # elements are ('L'|'C', value) at antenna / transformer side
        w = 2 * math.pi * f_mhz * 1e6

        def zel(e):
            t, v = e
            return 1j * w * v if t == "L" else 1 / (1j * w * v)
        if kind == "shunt_first":      # shunt across antenna, series toward source
            y = 1 / z + 1 / zel(sh)
            return 1 / y + zel(se)
        z2 = z + zel(se)               # series at antenna, shunt toward source
        return 1 / (1 / z2 + 1 / zel(sh))

    def apply(self, zant: complex, f_mhz: float) -> dict:
        """Walk from the antenna to the transmitter.  Losses are actual (at the real mismatch of each section).
        out["stages"]: [(name, impedance looking toward the antenna at the transmitter-side end of the stage,
        SWR on the stage relative to its own impedance or None, loss dB)]"""
        z = zant
        out = {"zant": zant}
        stages = [("Antenna terminals", zant, None, 0.0)]
        ll = 0.0
        if self.line:
            swr_l = swr_from_z(zant, self.line[0])
            z, ll = line_section(z, self.line, f_mhz)
            stages.append((self.line_name, z, swr_l, ll))
        out["zline_in"] = z
        out["line_loss_db"] = ll
        if self.lmatch_enabled and self.lmatch:
            z = self._lm(z, f_mhz)
            stages.append(("L-match (ideal)", z, None, 0.0))
        z = z / self.ratio
        xl = 0.0
        if self.xfmr_g > 0:
            y = 1 / z + self.xfmr_g
            xl = -10 * math.log10(max(1e-6, 1 - self.xfmr_g / y.real)) if y.real > 0 else 0.0
            z = 1 / y
        if self.ratio != 1.0 or self.xfmr_g > 0 or not self.balun_name.lower().startswith("unun"):
            stages.append((f"{self.balun_name} {self.ratio:g}:1", z, None, xl))
        out["xfmr_loss_db"] = xl
        out["zfeed"] = z
        loss = 0.0
        if self.coax[3] > 0:
            swr_c = swr_from_z(z, self.coax[0])
            z, loss = line_section(z, self.coax, f_mhz)
            stages.append((self.coax_name, z, swr_c, loss))
        out["zrig"] = z
        out["coax_loss_db"] = loss
        swr_rig = swr_from_z(z, self.zref)
        out["tuner_ok"] = None
        out["tuner_loss_db"] = 0.0
        if self.tuner_range > 0:
            ok = swr_rig <= self.tuner_range * 1.0001
            out["tuner_ok"] = ok
            tl = 0.0
            if ok and swr_rig >= 1.05:
                tl = (t_tuner_loss(z, self.zref, f_mhz, self.tuner_q) if self.tuner_topology == "T"
                      else tuner_loss(z, self.zref, f_mhz, self.tuner_q)[0])
                if not math.isfinite(tl):        # outside what this T network can reach
                    ok = False
                    out["tuner_ok"] = False
                    tl = 0.0
            out["tuner_loss_db"] = tl
            stages.append((self.tuner_name or "Tuner", complex(self.zref, 0) if ok else z, swr_rig, tl))
        tot = sum(st[3] for st in stages)
        out["total_loss_db"] = tot
        out["stages"] = stages
        return out


def l_match(zl: complex, rs: float, f_mhz: float):
    """L-network between load zl (antenna side) and real source rs.  Returns (kind, series_elem, shunt_elem)."""
    w = 2 * math.pi * f_mhz * 1e6
    R, X = zl.real, zl.imag
    cands = []
    if R > 0:
        # shunt at the load, series toward the source (needs R_par >= rs)
        G = R / (R * R + X * X)
        Bl = -X / (R * R + X * X)
        if G <= 1 / rs:
            for sgn in (+1, -1):
                B = sgn * math.sqrt(G / rs - G * G) - Bl
                yl = complex(G, Bl + B)
                zp = 1 / yl
                xs = -zp.imag
                cands.append(("shunt_first", B, xs))
        # series at the load, shunt toward the source (needs R <= rs)
        if R <= rs:
            for sgn in (+1, -1):
                xt = sgn * math.sqrt(R * rs - R * R)
                xseries = xt - X
                zz = complex(R, xt)
                yy = 1 / zz
                bsh = -yy.imag
                cands.append(("series_first", bsh, xseries))
    best = None
    for kind, B, xs in cands:
        # element: B>0 -> capacitor, B<0 -> inductor ; xs>0 -> inductor, xs<0 -> capacitor
        shunt = ("C", B / w) if B > 0 else ("L", -1 / (w * B)) if B != 0 else ("C", 1e-15)
        series = ("L", xs / w) if xs > 0 else ("C", -1 / (w * xs)) if xs != 0 else ("L", 1e-12)
        lowpass = shunt[0] == "C" and series[0] == "L"
        score = (0 if lowpass else 1, abs(xs) + abs(1 / B if B else 0))
        if best is None or score < best[0]:
            best = (score, (kind, series, shunt))
    return best[1] if best else None


# --------------------------------------------------------------------------- design
@dataclass
class Design:
    key: str
    title: str
    structure: Structure | None = None
    dims: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    tune: list = field(default_factory=list)
    scales: dict = field(default_factory=dict)
    mode: str = "single"                   # single | equal | currents | network
    i_des: list | None = None              # for mode currents
    cp: str | None = None                  # 'R' | 'L' circular polarisation headline
    pol: str = "mixed"
    rx_only: bool = False
    line: tuple | None = None              # (z0, vf, loss100, length) feeder section
    force_ratio: float | None = None       # model-mandated transformer ratio
    multiband: list = field(default_factory=list)    # [(label, f_mhz)] extra evaluation points
    analytic: object = None                # AnalyticModel for non-MoM antennas
    imp_override: Callable | None = None   # f_mhz -> system-side impedance (mag loop etc.)
    extra: dict = field(default_factory=dict)        # extra result text lines [(label, value)]
    mass_extra_kg: float = 0.0
    sweep_range: tuple | None = None       # override (f_lo, f_hi) MHz
    seg_len_hint: float | None = None
    opt_keys: list = field(default_factory=list)     # [(scale_key, lo, hi)] for the optimiser
    ground_note: str = ""
    xfmr_loss_db: float = 0.0              # matching-transformer loss at a matched load (EFHW unun)
    sweep_points: int | None = None        # override the SWR sweep point count
    shade_bands: list | None = None        # [(f_lo, f_hi)] amateur bands to shade on the SWR plot

    def dim(self, item, qty=1, length_m=None, note=""):
        self.dims.append(Dim(item, qty, length_m, note))

    def total_wire_m(self) -> float:
        if not self.structure:
            return 0.0
        tot = 0.0
        for w in self.structure.wires:
            tot += float(np.linalg.norm(np.subtract(w.p1, w.p0)))
        return tot


@dataclass
class Spec:
    key: str
    name: str
    category: str
    builder: Callable
    params: list = field(default_factory=list)
    desc: str = ""
    height_default: float = 10.0
    height_label: str = "Height above ground"
    gain_scalable: bool = False
    size_label: str = "Max size limit"
    feed_ratio: float = 1.0
    feed_coax: str = "rg213"
    feed_len: float = 15.0
    ground_default: str | None = None
    band_default: str | None = None
    rx_only: bool = False
    analytic: bool = False
    min_freq: float = 0.0
    max_freq: float = 1e9
    uses_material: bool = True
    uses_height: bool = True
    uses_ground: bool = True
    optimizable: bool = False
    needs_ground: bool = False             # ground-mounted: free space is auto-switched
    lmatch_default: bool = False
    auto_key: str | None = None            # extra-parameter chosen automatically from the gain target
    auto_lo: int = 1
    auto_hi: int = 1
    size_fn: Callable | None = None        # (req, ex, n) -> size in metres for the size limit
    custom_range: bool = False             # wideband: uses the editable frequency range
    optimize_default: bool = False
    wide_ok: bool = False                  # offers the whole-HF-range SWR sweep
    wide_default: bool = False


HF_SWEEP = (1.8, 55.0)
HF_SWEEP_STEP = 0.1


def apply_wide_sweep(design: "Design", req: "Requirements"):
    """Whole-HF SWR sweep: 1.8-55 MHz every 0.1 MHz with the amateur bands shaded."""
    if not getattr(req, "wide_sweep", False) or design.analytic is not None or design.structure is None:
        return design
    lo, hi = req.wide_lo, req.wide_hi
    if hi <= lo:
        lo, hi = HF_SWEEP
    design.sweep_range = (lo, hi)
    design.sweep_points = max(int(round((hi - lo) / HF_SWEEP_STEP)) + 1, 51)
    design.shade_bands = [(BAND_BY_LABEL[b][1], BAND_BY_LABEL[b][2]) for b in HF_BAND_LABELS]
    return design


def enable_wide_sweep(spec: "Spec", default: bool = False):
    """Mark a spec as supporting the whole-HF sweep and wrap its builder so every code path (tune, design,
    band table, optimiser) sees the same sweep range and segment size."""
    if spec.wide_ok:
        return
    inner = spec.builder

    def builder(req, ex, sc, _inner=inner):
        return apply_wide_sweep(_inner(req, ex, sc), req)
    spec.builder = builder
    spec.wide_ok = True
    spec.wide_default = default


REGISTRY: dict[str, Spec] = {}
CATEGORIES: list[str] = []


def register(spec: Spec) -> Spec:
    REGISTRY[spec.key] = spec
    if spec.category not in CATEGORIES:
        CATEGORIES.append(spec.category)
    return spec


def specs_in(category: str) -> list:
    return [s for s in REGISTRY.values() if s.category == category]
