"""Helpers shared by the antenna model builders."""
from __future__ import annotations

import math

import numpy as np

from .common import BANDS, HF_BAND_LABELS, BAND_BY_LABEL, band_short
from .design import Design, Param, Requirements
from .mom import C0, Ground, Source, Load, Structure


def new_struct(req: Requirements, design: Design, needs_ground: bool = False,
               default_kind: str = "real") -> Structure:
    g = req.ground
    if needs_ground and g.kind == "free":
        g = Ground("real", 0.005, 13.0)
        design.warnings.append("This antenna works against ground, so 'free space' was changed to average ground.")
    st = Structure(ground=Ground(g.kind, g.sigma, g.eps_r))
    design.structure = st
    return st


def ground_loss_r(n_radials: int, length_lambda: float = 0.25) -> float:
    """Empirical series ground loss resistance (ohm) of an N-radial buried field (estimate)."""
    n = max(1, n_radials)
    return 35.0 * n ** -0.75 * (0.25 / max(length_lambda, 0.05)) ** 0.3


def band_choices(optional_text: str | None = None, hf_only: bool = False):
    out = []
    if optional_text:
        out.append((optional_text, None))
    for b in BANDS:
        if b[3] <= 0:
            continue
        if hf_only and b[0] not in HF_BAND_LABELS:
            continue
        out.append((b[0], b[3]))
    return out


def hf_multiband(f_min: float = 3.0, f_max: float = 30.0):
    return [(band_short(b[0]), b[3]) for b in BANDS if b[3] > 0 and f_min <= b[3] <= f_max and b[0] in HF_BAND_LABELS]


def trap_fn(f0_mhz: float, c_pf: float, q: float):
    c = c_pf * 1e-12
    w0 = 2 * math.pi * f0_mhz * 1e6
    lh = 1 / (w0 * w0 * c)
    r = w0 * lh / q

    def fn(f_hz: float) -> complex:
        w = 2 * math.pi * f_hz
        zl = r + 1j * w * lh
        zc = 1 / (1j * w * c)
        return zl * zc / (zl + zc)
    return fn, lh


def coil_fn(l_h: float, q: float, f0_mhz: float):
    w0 = 2 * math.pi * f0_mhz * 1e6
    r = w0 * l_h / q

    def fn(f_hz: float) -> complex:
        return r + 1j * 2 * math.pi * f_hz * l_h
    return fn


def add_polygon(st: Structure, pts, a, sigma, feed_edge: int | None = None, name="loop",
                gaps: list | None = None, min_seg=1):
    """Closed polygon of straight wires.  feed_edge splits that edge at its midpoint.
    gaps: list of (edge, fraction) extra joints.  Returns (wire ids, {joint: (wire id before joint)})."""
    n = len(pts)
    ids = []
    joints = {}
    for e in range(n):
        p0 = np.array(pts[e], float); p1 = np.array(pts[(e + 1) % n], float)
        cuts = []
        if feed_edge is not None and e == feed_edge:
            cuts.append(("feed", 0.5))
        if gaps:
            for (ge, gf, gname) in gaps:
                if ge == e:
                    cuts.append((gname, gf))
        cuts.sort(key=lambda c: c[1])
        fr = [0.0] + [c[1] for c in cuts] + [1.0]
        for k in range(len(fr) - 1):
            q0 = p0 + (p1 - p0) * fr[k]
            q1 = p0 + (p1 - p0) * fr[k + 1]
            w = st.add(q0, q1, a, sigma=sigma, name=f"{name}{e}", min_seg=min_seg)
            ids.append(w)
            if k < len(cuts):
                joints[cuts[k][0]] = w
    return ids, joints


def regular_polygon(n, radius, center=(0, 0, 0), plane="xy", phase=0.0):
    pts = []
    for i in range(n):
        t = phase + 2 * math.pi * i / n
        c, s = math.cos(t) * radius, math.sin(t) * radius
        if plane == "xy":
            pts.append((center[0] + c, center[1] + s, center[2]))
        elif plane == "xz":
            pts.append((center[0] + c, center[1], center[2] + s))
        else:
            pts.append((center[0], center[1] + c, center[2] + s))
    return pts


def dipole_pair(st: Structure, c, direction, half, a, sigma, min_seg=5, name="dipole"):
    """Centre-fed dipole through point c along unit vector `direction`; adds a Source at the centre."""
    c = np.array(c, float); u = np.array(direction, float); u /= np.linalg.norm(u)
    w0 = st.add(c - u * half, c, a, sigma=sigma, name=name, min_seg=min_seg)
    w1 = st.add(c, c + u * half, a, sigma=sigma, name=name, min_seg=min_seg)
    st.sources.append(Source(w0, 1.0, 1.0))
    return w0, w1


def rotate_xy(p, az_deg):
    t = math.radians(az_deg)
    c, s = math.cos(t), math.sin(t)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def clamp_height(h: float, lo: float) -> float:
    return max(h, lo)


def hz(f_mhz: float) -> float:
    return f_mhz * 1e6


def size_warn(design: Design, req: Requirements, size_m: float, what: str):
    if req.max_size > 0 and size_m > req.max_size * 1.0001:
        design.warnings.append(f"{what} is {size_m:.2f} m, over your {req.max_size:.2f} m size limit.")


def eq_radius_note(req: Requirements, design: Design):
    if req.radius * 2 > 0.02 * req.lam:
        design.warnings.append("Conductor diameter is more than 2% of a wavelength - thin-wire results are approximate.")


_RES_CACHE: dict = {}


def dipole_res_factor(a_over_lam: float) -> float:
    """Free-space self-resonant length of a straight dipole, in wavelengths, for radius/lambda = a_over_lam."""
    key = round(a_over_lam, 7)
    if key in _RES_CACHE:
        return _RES_CACHE[key]
    from .mom import Model, Structure, solve, C0
    lam = 1.0
    f = C0 / lam

    def x_of(L):
        st = Structure()
        w0 = st.add((-L / 2, 0, 0), (0, 0, 0), a_over_lam * lam, nseg=11)
        st.add((0, 0, 0), (L / 2, 0, 0), a_over_lam * lam, nseg=11)
        st.sources.append(Source(w0, 1.0))
        m = Model(st, lam / 20)
        return solve(m, f).zin[0].imag
    a, b = 0.46, 0.485
    xa, xb = x_of(a), x_of(b)
    for _ in range(8):
        if abs(xb - xa) < 1e-9:
            break
        n = b - xb * (b - a) / (xb - xa)
        n = min(max(n, 0.40), 0.50)
        a, xa = b, xb
        b, xb = n, x_of(n)
        if abs(xb) < 0.2:
            break
    _RES_CACHE[key] = b
    return b


def yagi_length_scale(req) -> float:
    """Element-length correction for the actual conductor radius (templates are for radius = 0.003 wavelength)."""
    lam = req.lam
    return dipole_res_factor(req.radius / lam) / dipole_res_factor(0.003)
