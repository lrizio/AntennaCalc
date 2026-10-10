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
    lmatch: bool = False
    spw: int = 20                         # segments per wavelength
    auto_tune: bool = True
    optimize: bool = False
    wide_sweep: bool = False              # sweep the whole HF range (1.8-30 MHz) instead of just the band

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


@dataclass
class FeedChain:
    """antenna -> [feeder line] -> [L-match] -> [transformer] -> [coax] -> rig"""
    line: tuple | None = None          # (z0, vf, loss100, length_m)
    lmatch: tuple | None = None        # computed (kind, elements) or None
    ratio: float = 1.0
    coax: tuple = (50.0, 0.66, 8.6, 0.0)   # z0, vf, loss dB/100m @100MHz, length
    zref: float = 50.0
    lmatch_enabled: bool = False
    lmatch_f0: float = 0.0
    xfmr_g: float = 0.0                # shunt conductance (S) across the transformer's 50 ohm side (core loss)

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
        z = zant
        out = {"zant": zant}
        if self.line:
            z, _ = self.tline(z, self.line, f_mhz)
        out["zline_in"] = z
        z = self._lm(z, f_mhz)
        z = z / self.ratio
        xl = 0.0
        if self.xfmr_g > 0:
            y = 1 / z + self.xfmr_g
            xl = -10 * math.log10(max(1e-6, 1 - self.xfmr_g / y.real)) if y.real > 0 else 0.0
            z = 1 / y
        out["xfmr_loss_db"] = xl
        out["zfeed"] = z
        loss = 0.0
        if self.coax[3] > 0:
            z, loss = self.tline(z, self.coax, f_mhz)
        out["zrig"] = z
        out["coax_loss_db"] = loss
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


HF_SWEEP = (1.8, 30.0)
HF_SWEEP_STEP = 0.1


def apply_wide_sweep(design: "Design", req: "Requirements"):
    """Whole-HF SWR sweep: 1.8-30 MHz every 0.1 MHz with the amateur bands shaded."""
    if not getattr(req, "wide_sweep", False) or design.analytic is not None or design.structure is None:
        return design
    lo, hi = HF_SWEEP
    design.sweep_range = (lo, hi)
    design.sweep_points = int(round((hi - lo) / HF_SWEEP_STEP)) + 1
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
