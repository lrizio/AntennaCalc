"""Export helpers: NEC-2 deck, CSV cut list."""
from __future__ import annotations

import csv
import math

import numpy as np

from .common import fmt_len
from .engine import Result
from . import VERSION
from .mom import Model


def nec_deck(res: Result) -> str:
    d, req = res.design, res.req
    st = d.structure
    if st is None or res.model is None:
        raise ValueError("This antenna uses a closed-form model - there is no wire geometry to export.")
    m: Model = res.model
    g0 = st.ground
    gtxt = {"free": "free space", "perfect": "perfect ground"}.get(g0.kind, f"real ground, sigma {g0.sigma:g} S/m, eps_r {g0.eps_r:g}")
    lines = [f"CM AntennaCalc v{VERSION}: {d.title}",
             f"CM Design frequency {req.f_mhz:.5f} MHz, band {req.f_lo:.4f}-{req.f_hi:.4f} MHz",
             f"CM Conductor {req.material}, diameter {req.diameter_mm:.2f} mm; ground: {gtxt}",
             "CM Wire loading and source/load positions are approximations of the AntennaCalc model",
             "CM Open in 4nec2 (File > Open > Nec-file) or any NEC-2 program; units are metres",
             "CE"]
    for wi, w in enumerate(st.wires):
        n = m.wire_n[wi]
        lines.append(f"GW {wi + 1:3d} {n:4d} {w.p0[0]:.5f} {w.p0[1]:.5f} {w.p0[2]:.5f} {w.p1[0]:.5f} {w.p1[1]:.5f} {w.p1[2]:.5f} {w.radius:.6f}")
    g = st.ground
    lines.append(f"GE {0 if g.kind == 'free' else 1}")
    if g.kind == "perfect":
        lines.append("GN  1")
    elif g.kind == "real":
        lines.append(f"GN  0 0 0 0 {g.eps_r:.3f} {g.sigma:.5f}")
    else:
        lines.append("GN -1")
    f0 = req.f_mhz
    w = 2 * math.pi * f0 * 1e6
    # wire conductivity (use the first wire's value for all)
    sig = st.wires[0].sigma
    lines.append(f"LD  5 0 0 0 {sig:.4g}")
    for ld in st.loads:
        n = m.wire_n[ld.wire]
        seg = max(1, min(n, int(round(ld.at * n)) or 1))
        z = ld.fn(f0 * 1e6)
        r = max(z.real, 0.0)
        if z.imag >= 0:
            lines.append(f"LD  0 {ld.wire + 1:3d} {seg:3d} {seg:3d} {r:.5g} {z.imag / w:.6g} 0")
        else:
            lines.append(f"LD  0 {ld.wire + 1:3d} {seg:3d} {seg:3d} {r:.5g} 0 {-1.0 / (w * z.imag):.6g}")
    # sources
    vs = [s.volts for s in st.sources]
    if res.sol0 is not None and d.mode in ("currents", "network"):
        vs = [res.sol0.V[b] for b in res.sol0.port_basis]
    for s, v in zip(st.sources, vs):
        n = m.wire_n[s.wire]
        seg = max(1, min(n, int(round(s.at * n)) or 1))
        lines.append(f"EX  0 {s.wire + 1:3d} {seg:3d} 0 {complex(v).real:.6g} {complex(v).imag:.6g}")
    for (a, b, z0, ln, vf, crossed) in st.lines:
        wa, wb = st.sources[a].wire, st.sources[b].wire
        sa = max(1, min(m.wire_n[wa], int(round(st.sources[a].at * m.wire_n[wa])) or 1))
        sb = max(1, min(m.wire_n[wb], int(round(st.sources[b].at * m.wire_n[wb])) or 1))
        lines.append(f"TL  {wa + 1:3d} {sa:3d} {wb + 1:3d} {sb:3d} {-z0 if crossed else z0:.4g} {ln:.5g} 0 0 0 0")
    plain = not st.loads and not st.lines          # nothing frequency dependent, so a sweep is meaningful
    if plain and req.f_hi > req.f_lo and d.mode == "single":
        npts = 11
        step = (req.f_hi - req.f_lo) / (npts - 1)
        lines.append(f"CM Frequency sweep across the band (SWR plot in 4nec2); the pattern is computed at every step")
        lines.append(f"FR  0 {npts} 0 0 {req.f_lo:.5f} {step:.5f}")
    else:
        lines.append(f"FR  0 1 0 0 {f0:.5f} 0")
    lines.append("RP  0 91 73 1000 0 0 2 5")
    lines.append("EN")
    return "\n".join(lines) + "\n"


def cutlist_csv(res: Result, path: str):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Item", "Qty", "Length (m)", "Length (ft)", "Note"])
        for x in res.design.dims:
            w.writerow([x.item, x.qty, f"{x.length_m:.4f}" if x.length_m else "", f"{x.length_m / 0.3048:.3f}" if x.length_m else "", x.note])


def sweep_csv(res: Result, path: str):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["MHz", "R_antenna", "X_antenna", "R_feed", "X_feed", "SWR_at_coax_input", "SWR_at_feed"])
        for i, f in enumerate(res.f):
            w.writerow([f"{f:.5f}", f"{res.zant[i].real:.3f}", f"{res.zant[i].imag:.3f}",
                        f"{res.zfeed[i].real:.3f}", f"{res.zfeed[i].imag:.3f}", f"{res.swr_rig[i]:.3f}", f"{res.swr_feed[i]:.3f}"])
