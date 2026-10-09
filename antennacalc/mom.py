"""Thin-wire method-of-moments solver (NEC-style, written for AntennaCalc).

Formulation: mixed-potential EFIE, Galerkin testing with piecewise-linear
("rooftop") basis functions, reduced thin-wire kernel, arbitrary junctions,
perfect / finite ground by the image method (finite ground uses a Fresnel
reflection-coefficient weighting - the same approximation as the NEC
"reflection coefficient" ground option), skin-effect wire loss, lumped
series loads and delta-gap voltage sources.  Time convention exp(+j w t).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

C0 = 299792458.0
MU0 = 4e-7 * math.pi
EPS0 = 1.0 / (MU0 * C0 ** 2)
ETA0 = MU0 * C0

_G3x, _G3w = np.polynomial.legendre.leggauss(3)
GT = 0.5 * (_G3x + 1.0)      # Gauss nodes on [0,1]
GW = 0.5 * _G3w


# --------------------------------------------------------------------------- data
@dataclass
class Ground:
    kind: str = "free"          # free | perfect | real
    sigma: float = 0.005        # S/m
    eps_r: float = 13.0

    def eps_c(self, f_hz: float) -> complex:
        return self.eps_r - 1j * self.sigma / (2 * math.pi * f_hz * EPS0)


@dataclass
class Wire:
    p0: tuple
    p1: tuple
    radius: float
    nseg: int | None = None      # None -> automatic from max segment length
    sigma: float = 5.8e7
    name: str = ""
    min_seg: int = 1


@dataclass
class Load:
    wire: int
    at: float                    # position along the wire, 0..1
    fn: Callable[[float], complex]   # series impedance(f_hz)
    label: str = ""


@dataclass
class Source:
    wire: int
    at: float
    volts: complex = 1.0
    label: str = ""


@dataclass
class Structure:
    wires: list = field(default_factory=list)
    loads: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    ground: Ground = field(default_factory=Ground)
    # transmission-line network joining source ports (LPDA etc.)
    lines: list = field(default_factory=list)      # (portA, portB, Z0, length_m, vf, crossed)
    stub_port: int | None = None                   # shorted stub on this port
    stub: tuple | None = None                      # (Z0, length_m, vf)
    feed_port: int = 0

    def add(self, p0, p1, radius, nseg=None, sigma=5.8e7, name="", min_seg=1) -> int:
        self.wires.append(Wire(tuple(map(float, p0)), tuple(map(float, p1)), radius, nseg, sigma, name, min_seg))
        return len(self.wires) - 1


# --------------------------------------------------------------------------- geometry
class Model:
    """Segmented geometry + basis functions for one structure at one max-frequency."""

    def __init__(self, st: Structure, seg_len: float, max_seg: int = 1400):
        self.st = st
        P0, P1, A, SG, WI = [], [], [], [], []
        self.wire_first = []
        self.wire_n = []
        counts = []
        for w in st.wires:
            L = float(np.linalg.norm(np.subtract(w.p1, w.p0)))
            n = w.nseg if w.nseg else max(1, math.ceil(L / seg_len))
            n = max(n, w.min_seg)
            counts.append(n)
        tot = sum(counts)
        if tot > max_seg:                      # coarsen proportionally
            f = max_seg / tot
            counts = [max(w.min_seg, int(c * f)) for c, w in zip(counts, st.wires)]
        for wi, (w, n) in enumerate(zip(st.wires, counts)):
            pts = np.linspace(w.p0, w.p1, n + 1)
            self.wire_first.append(len(P0))
            self.wire_n.append(n)
            for j in range(n):
                P0.append(pts[j]); P1.append(pts[j + 1]); A.append(w.radius); SG.append(w.sigma); WI.append(wi)
        self.P0 = np.array(P0, float)
        self.P1 = np.array(P1, float)
        self.a = np.array(A, float)
        self.sigma = np.array(SG, float)
        self.wi = np.array(WI, int)
        D = self.P1 - self.P0
        self.L = np.linalg.norm(D, axis=1)
        self.d = D / self.L[:, None]
        self.N = len(self.L)
        self._build_bases()

    # nodes / junctions
    def _build_bases(self):
        N = self.N
        ends = np.vstack([self.P0, self.P1])             # index e*N + seg
        ext = float(np.ptp(ends, axis=0).max()) if N else 1.0
        tol = max(1e-9, 1e-6 * max(ext, 1e-3))
        tree = cKDTree(ends)
        pairs = tree.query_pairs(tol, output_type="ndarray")
        if len(pairs):
            g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(2 * N, 2 * N))
            _, lab = connected_components(g, directed=False)
        else:
            lab = np.arange(2 * N)
        nodes: dict[int, list] = {}
        for idx in range(2 * N):
            seg = idx % N
            end = idx // N            # 0 = start (P0), 1 = end (P1)
            nodes.setdefault(int(lab[idx]), []).append((seg, end))
        ground_on = self.st.ground.kind != "free"
        zt = tol * 2
        bases = []   # each: list of halves (seg, end, s, c)
        self.node_of = {}      # (seg,end) -> node id
        self.node_bases = {}
        self.node_pos = {}
        for nid, att in nodes.items():
            seg0, e0 = att[0]
            pos = (self.P1 if e0 else self.P0)[seg0]
            for a in att:
                self.node_of[a] = nid
            self.node_pos[nid] = pos
            on_gnd = ground_on and abs(pos[2]) < zt
            def half_in(sg, en):
                return (sg, en, 1.0 if en == 1 else -1.0, 1.0)
            def half_out(sg, en):
                return (sg, en, 1.0 if en == 0 else -1.0, -1.0)
            mine = []
            if len(att) >= 2:
                for k in range(1, len(att)):
                    mine.append([half_in(*att[0]), half_out(*att[k])])
            if on_gnd:
                mine.append([half_out(*att[0])])
            if len(att) == 1 and not on_gnd:
                continue
            self.node_bases[nid] = list(range(len(bases), len(bases) + len(mine)))
            bases.extend(mine)
        self.bases = bases
        M = len(bases)
        self.M = M
        self.hseg = np.zeros((M, 2), int)
        self.hend = np.zeros((M, 2), int)
        self.hs = np.zeros((M, 2))
        self.hc = np.zeros((M, 2))
        for m, hv in enumerate(bases):
            for a, (sg, en, s, c) in enumerate(hv):
                self.hseg[m, a], self.hend[m, a], self.hs[m, a], self.hc[m, a] = sg, en, s, c

    def basis_at(self, wire: int, at: float) -> int:
        n = self.wire_n[wire]
        j = int(round(at * n))
        j = max(0, min(n, j))
        f = self.wire_first[wire]
        if j == 0:
            key = (f, 0)
        elif j == n:
            key = (f + n - 1, 1)
        else:
            key = (f + j - 1, 1)
        nid = self.node_of[key]
        bl = self.node_bases.get(nid)
        if not bl:
            raise ValueError(f"no basis function at wire {wire} position {at} (free end?)")
        return bl[0]

    def wire_node_position(self, wire: int, at: float):
        n = self.wire_n[wire]
        j = max(0, min(n, int(round(at * n))))
        f = self.wire_first[wire]
        return self.P0[f] if j == 0 else self.P1[f + j - 1]


# --------------------------------------------------------------------------- integrals
def _pair_integrals(P0, d, L, Q0, qd, qL, qa, k):
    """Return (A[N,M,2,2], Phi[N,M]) with 1/4pi included; observation = P-segments, source = Q-segments."""
    N, M = len(L), len(qL)
    K = len(GT)
    A = np.empty((N, M, 2, 2), complex)
    Phi = np.empty((N, M), complex)
    chunk = max(1, int(6e6 // (K * M * K * 3 + 1)))
    qpts = Q0[:, None, :] + (GT[None, :, None] * qL[:, None, None]) * qd[:, None, :]   # (M,K,3)
    Lq = qL[None, None, :]
    a2 = (qa ** 2)[None, None, :]
    inv4pi = 1.0 / (4 * math.pi)
    for s in range(0, N, chunk):
        e = min(N, s + chunk)
        obs = P0[s:e, None, :] + (GT[None, :, None] * L[s:e, None, None]) * d[s:e, None, :]   # (n,K,3)
        r = obs[:, :, None, :] - Q0[None, None, :, :]
        u = np.einsum("nkmc,mc->nkm", r, qd)
        r2 = np.einsum("nkmc,nkmc->nkm", r, r)
        rho2 = np.maximum(r2 - u * u, 0.0) + a2
        rho = np.sqrt(rho2)
        I0 = np.arcsinh((Lq - u) / rho) + np.arcsinh(u / rho)
        I1 = np.sqrt((Lq - u) ** 2 + rho2) - np.sqrt(u * u + rho2) + u * I0
        S1 = I1 / Lq
        S0 = I0 - S1
        rr = obs[:, :, None, None, :] - qpts[None, None, :, :, :]
        R = np.sqrt(np.einsum("nkmjc,nkmjc->nkmj", rr, rr) + a2[..., None])
        g = (np.exp(-1j * k * R) - 1.0) / R
        G0 = np.einsum("nkmj,j->nkm", g, GW) * Lq
        G1 = np.einsum("nkmj,j->nkm", g, GW * GT) * Lq
        T1 = S1 + G1                 # end-1 weighted (t')
        T0 = (I0 + G0) - T1          # end-0 weighted (1-t')
        T = I0 + G0
        Lo = L[s:e, None]
        wk = GW[None, :, None]
        fo1 = GT[None, :, None]
        fo0 = 1.0 - fo1
        Phi[s:e] = inv4pi * Lo * np.sum(wk * T, axis=1)
        A[s:e, :, 1, 1] = inv4pi * Lo * np.sum(wk * fo1 * T1, axis=1)
        A[s:e, :, 1, 0] = inv4pi * Lo * np.sum(wk * fo1 * T0, axis=1)
        A[s:e, :, 0, 1] = inv4pi * Lo * np.sum(wk * fo0 * T1, axis=1)
        A[s:e, :, 0, 0] = inv4pi * Lo * np.sum(wk * fo0 * T0, axis=1)
    return A, Phi


def _gamma_arrays(model: Model, f_hz: float):
    """Image weights W[i,j] (= Gamma_eff) for finite ground, 1 for perfect."""
    g = model.st.ground
    N = model.N
    if g.kind != "real":
        return np.ones((N, N), complex)
    mid = 0.5 * (model.P0 + model.P1)
    zi = mid[:, 2][:, None]
    zj = mid[:, 2][None, :]
    dx = mid[:, 0][:, None] - mid[:, 0][None, :]
    dy = mid[:, 1][:, None] - mid[:, 1][None, :]
    h = np.maximum(zi + zj, 1e-6)
    R = np.sqrt(dx * dx + dy * dy + h * h)
    cth = np.clip(h / R, 1e-4, 1.0)
    sth2 = 1 - cth ** 2
    ec = g.eps_c(f_hz)
    root = np.sqrt(ec - sth2)
    Rh = (cth - root) / (cth + root)
    Rv = (ec * cth - root) / (ec * cth + root)
    fv = (model.d[:, 2] ** 2)[None, :]          # vertical fraction of the source segment
    return fv * Rv + (1 - fv) * (-Rh)


def impedance_matrix(model: Model, f_hz: float) -> np.ndarray:
    k = 2 * math.pi * f_hz / C0
    w = 2 * math.pi * f_hz
    A, Phi = _pair_integrals(model.P0, model.d, model.L, model.P0, model.d, model.L, model.a, k)
    DD = model.d @ model.d.T
    AD = DD[:, :, None, None] * A
    PH = Phi
    if model.st.ground.kind != "free":
        Q0 = model.P0.copy(); Q0[:, 2] *= -1
        qd = model.d.copy(); qd[:, 2] *= -1
        Ai, Pi = _pair_integrals(model.P0, model.d, model.L, Q0, qd, model.L, model.a, k)
        W = -_gamma_arrays(model, f_hz)
        DDi = model.d @ qd.T
        AD = AD + (W * DDi)[:, :, None, None] * Ai
        PH = Phi + W * Pi
    M = model.M
    Zv = np.zeros((M, M), complex)
    Zs = np.zeros((M, M), complex)
    Lh = model.L
    for a in range(2):
        for b in range(2):
            ma = model.hc[:, a] != 0
            mb = model.hc[:, b] != 0
            sa, sb = model.hseg[:, a], model.hseg[:, b]
            ea, eb = model.hend[:, a], model.hend[:, b]
            Ia = sa[:, None]; Ib = sb[None, :]
            val = AD[Ia, Ib, ea[:, None], eb[None, :]] * (model.hs[:, a][:, None] * model.hs[:, b][None, :])
            ph = PH[Ia, Ib] * (model.hc[:, a][:, None] * model.hc[:, b][None, :]) / (Lh[sa][:, None] * Lh[sb][None, :])
            msk = ma[:, None] & mb[None, :]
            Zv += np.where(msk, val, 0)
            Zs += np.where(msk, ph, 0)
    Z = 1j * w * MU0 * Zv - 1j / (w * EPS0) * Zs
    Z += _wire_loss_matrix(model, f_hz)
    return Z


def _wire_loss_matrix(model: Model, f_hz: float) -> np.ndarray:
    w = 2 * math.pi * f_hz
    Rs = np.sqrt(w * MU0 / (2 * model.sigma))
    zl = (1 + 1j) * Rs / (2 * math.pi * model.a)         # ohm per metre
    M = model.M
    Zl = np.zeros((M, M), complex)
    per_seg: dict[int, list] = {}
    for m in range(M):
        for a in range(2):
            if model.hc[m, a] != 0:
                per_seg.setdefault(int(model.hseg[m, a]), []).append((m, int(model.hend[m, a]), model.hs[m, a]))
    for sg, lst in per_seg.items():
        for (m1, e1, s1) in lst:
            for (m2, e2, s2) in lst:
                Zl[m1, m2] += s1 * s2 * zl[sg] * model.L[sg] * (1 / 3 if e1 == e2 else 1 / 6)
    return Zl


# --------------------------------------------------------------------------- solving
@dataclass
class Solution:
    model: Model
    f_hz: float
    I: np.ndarray                 # basis amplitudes
    V: np.ndarray                 # excitation
    port_basis: list
    zin: list
    pin: float                    # input power W
    Z: np.ndarray | None = None

    def seg_currents(self):
        """Current at the two ends of each segment, signed along the segment direction."""
        m = self.model
        Ie = np.zeros((m.N, 2), complex)
        for a in range(2):
            ok = m.hc[:, a] != 0
            np.add.at(Ie, (m.hseg[ok, a], m.hend[ok, a]), (m.hs[ok, a] * self.I[ok]))
        return Ie


def _apply_loads(model: Model, Z: np.ndarray, f_hz: float):
    for ld in model.st.loads:
        m = model.basis_at(ld.wire, ld.at)
        Z[m, m] += ld.fn(f_hz)


def solve(model: Model, f_hz: float, volts: list | None = None, keep_z: bool = False) -> Solution:
    st = model.st
    Z = impedance_matrix(model, f_hz)
    _apply_loads(model, Z, f_hz)
    pb = [model.basis_at(s.wire, s.at) for s in st.sources]
    V = np.zeros(model.M, complex)
    vs = volts if volts is not None else [s.volts for s in st.sources]
    for b, v in zip(pb, vs):
        V[b] += v
    I = np.linalg.solve(Z, V)
    zin = [(V[b] / I[b]) if abs(I[b]) > 0 else complex("inf") for b in pb]
    pin = 0.5 * float(np.real(np.sum(np.conj(I[pb]) * V[pb])))
    return Solution(model, f_hz, I, V, pb, zin, pin, Z if keep_z else None)


def port_impedance_matrix(model: Model, f_hz: float) -> np.ndarray:
    """N-port Z matrix of all declared sources (ports open-circuit driven by unit voltage -> Y -> Z)."""
    st = model.st
    Z = impedance_matrix(model, f_hz)
    _apply_loads(model, Z, f_hz)
    pb = [model.basis_at(s.wire, s.at) for s in st.sources]
    P = len(pb)
    rhs = np.zeros((model.M, P), complex)
    for p, b in enumerate(pb):
        rhs[b, p] = 1.0
    I = np.linalg.solve(Z, rhs)
    Y = I[pb, :]
    return np.linalg.inv(Y), Y


def solve_currents(model: Model, f_hz: float, i_des: np.ndarray) -> Solution:
    """Excite the source ports so the port currents equal i_des (ideal feed network)."""
    Zp, _ = port_impedance_matrix(model, f_hz)
    volts = list(Zp @ np.asarray(i_des, complex))
    return solve(model, f_hz, volts)


def _line_y(z0, length, vf, f_hz, crossed):
    beta = 2 * math.pi * f_hz / (C0 * vf)
    bl = beta * length
    s = math.sin(bl)
    if abs(s) < 1e-9:
        s = 1e-9
    y11 = -1j / (z0 * math.tan(bl) if abs(math.tan(bl)) > 1e-9 else 1e-9)
    y12 = 1j / (z0 * s)
    if crossed:
        y12 = -y12
    return y11, y12


def network_zin_from_yp(Yp, lines, stub_port, stub, feed_port, f_hz):
    """Feed-point impedance of a port admittance matrix joined by transmission lines."""
    P = Yp.shape[0]
    Y = Yp.copy()
    for (a, b, z0, ln, vf, crossed) in lines:
        y11, y12 = _line_y(z0, ln, vf, f_hz, crossed)
        Y[a, a] += y11; Y[b, b] += y11
        Y[a, b] += y12; Y[b, a] += y12
    if stub_port is not None and stub:
        z0, ln, vf = stub
        beta = 2 * math.pi * f_hz / (C0 * vf)
        t = math.tan(beta * ln)
        Y[stub_port, stub_port] += -1j / (z0 * (t if abs(t) > 1e-9 else 1e-9))
    inj = np.zeros(P, complex)
    inj[feed_port] = 1.0
    v = np.linalg.solve(Y, inj)
    return v[feed_port], v


def network_input_impedance(model: Model, f_hz: float):
    """Feed-point impedance of a harness-connected array (LPDA).  Returns (zin, solution)."""
    st = model.st
    Zp, Yp = port_impedance_matrix(model, f_hz)
    zin, v = network_zin_from_yp(Yp, st.lines, st.stub_port, st.stub, st.feed_port, f_hz)
    sol = solve(model, f_hz, list(v))
    return zin, sol


# --------------------------------------------------------------------------- far field
def _fresnel(theta: np.ndarray, g: Ground, f_hz: float):
    ec = g.eps_c(f_hz)
    c = np.cos(theta)
    s2 = np.sin(theta) ** 2
    root = np.sqrt(ec - s2)
    cc = np.where(np.abs(c) < 1e-6, 1e-6, c)
    Rh = (cc - root) / (cc + root)
    Rv = (ec * cc - root) / (ec * cc + root)
    return Rv, Rh


def far_field(sol: Solution, theta: np.ndarray, phi: np.ndarray, block: int = 600):
    """Return (Etheta', Ephi') complex arrays (proportional to the far field; see gain())."""
    m = sol.model
    k = 2 * math.pi * sol.f_hz / C0
    Ie = sol.seg_currents()
    Iq = Ie[:, 0, None] * (1 - GT[None, :]) + Ie[:, 1, None] * GT[None, :]        # (N,3)
    pos = m.P0[:, None, :] + (GT[None, :, None] * m.L[:, None, None]) * m.d[:, None, :]   # (N,3,3)
    wq = (m.L[:, None] * GW[None, :]) * Iq
    J = (wq[:, :, None] * m.d[:, None, :]).reshape(-1, 3)
    pos = pos.reshape(-1, 3)
    gk = m.st.ground.kind
    if gk != "free":
        pos_i = pos.copy(); pos_i[:, 2] *= -1
        di = m.d.copy(); di[:, 2] *= -1
        Ji = (-(wq[:, :, None]) * di[:, None, :]).reshape(-1, 3)
    th = np.asarray(theta, float).ravel()
    ph = np.asarray(phi, float).ravel()
    Et = np.zeros(th.shape, complex)
    Ep = np.zeros(th.shape, complex)
    for s in range(0, len(th), block):
        t = th[s:s + block]; p = ph[s:s + block]
        rh = np.stack([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)], 1)
        thh = np.stack([np.cos(t) * np.cos(p), np.cos(t) * np.sin(p), -np.sin(t)], 1)
        phh = np.stack([-np.sin(p), np.cos(p), np.zeros_like(p)], 1)
        N = np.exp(1j * k * (rh @ pos.T)) @ J
        et = np.einsum("dc,dc->d", thh, N)
        ep = np.einsum("dc,dc->d", phh, N)
        if gk != "free":
            Ni = np.exp(1j * k * (rh @ pos_i.T)) @ Ji
            eti = np.einsum("dc,dc->d", thh, Ni)
            epi = np.einsum("dc,dc->d", phh, Ni)
            if gk == "real":
                Rv, Rh = _fresnel(t, m.st.ground, sol.f_hz)
                eti = eti * Rv
                epi = epi * (-Rh)
            et = et + eti
            ep = ep + epi
            up = (t <= math.pi / 2 + 1e-9)
            et = np.where(up, et, 0)
            ep = np.where(up, ep, 0)
        Et[s:s + block] = et
        Ep[s:s + block] = ep
    return Et.reshape(np.shape(theta)), Ep.reshape(np.shape(theta))


FIELD_K = None  # placeholder for documentation: U = (k^2 eta / 32 pi^2) (|Et|^2+|Ep|^2)


def radiation_intensity(sol: Solution, Et, Ep):
    k = 2 * math.pi * sol.f_hz / C0
    return k * k * ETA0 / (32 * math.pi ** 2) * (np.abs(Et) ** 2 + np.abs(Ep) ** 2)


def unit_intensity(sol: Solution, E):
    k = 2 * math.pi * sol.f_hz / C0
    return k * k * ETA0 / (32 * math.pi ** 2) * np.abs(E) ** 2


def k_const(sol: Solution) -> float:
    k = 2 * math.pi * sol.f_hz / C0
    return k * k * ETA0 / (32 * math.pi ** 2)
