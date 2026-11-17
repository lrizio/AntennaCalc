"""Common-mode (coax shield) current estimate.

The outside of the coax shield is a conductor of its own: whatever current the balun lets through flows on it,
radiates, and comes back into the shack.  It is modelled NEC-style as a wire that runs from the balun to the radio,
joined to the antenna through the balun's common-mode impedance.

* Balun at the feedpoint: the shield wire is added to the antenna model itself, on one side of the feed gap, with
  the choke as a series load where it joins.  The SWR, pattern and gain then include the coax.
* Balun at the bottom of a feed line (ladder line): the feed line is treated as balanced, so the coax is driven by
  half the voltage across the balun.  The common-mode path is the coax on one side and the feed line plus the
  antenna on the other; it is solved separately and does not change the main result.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from . import mom
from .mom import Load, Source, Structure

BALUN_TYPES = [("Current balun / choke", "current"), ("Voltage balun", "voltage"), ("Unun / direct coax (no choke)", "unun")]
BALUN_TYPE_NAME = {k: lab for lab, k in BALUN_TYPES}
UNUN_DEFAULT = {"vhw", "longwire", "efhw", "beverage"}
VOLTAGE_BALUN_L = 6.8e-6           # a voltage balun's common-mode impedance is about its winding reactance (~300 ohm at 7 MHz)
COAX_OD_MM = {"rg58": 5.0, "rg8x": 6.1, "rg213": 10.3, "lmr400": 10.3, "lmr600": 15.0, "hard12": 16.0, "rg59": 6.1, "rg6": 6.9}
RUN_HEIGHT = 1.0                   # m: height of the horizontal run of the coax
LADDER_BOTTOM = 2.0                # m: lowest point of a ladder line before it turns toward the shack
LADDER_EQ_RADIUS = 0.005           # m: a two-wire line acts as one conductor of about this radius for common mode


def default_balun_type(spec) -> str:
    return "unun" if (spec.key in UNUN_DEFAULT or spec.category == "Vertical antennas") else "current"


def zcm(kind: str, choke_ohm: float, f_hz: float) -> complex:
    if kind == "current":
        return complex(max(choke_ohm, 0.0), 0.0)
    if kind == "voltage":
        return complex(0.0, 2 * math.pi * f_hz * VOLTAGE_BALUN_L)
    return 0j


# --------------------------------------------------------------------------- geometry helpers
def _flip(st: Structure, i: int):
    w = st.wires[i]
    w.p0, w.p1 = w.p1, w.p0
    for o in st.sources + st.loads:
        if o.wire == i:
            o.at = 1.0 - o.at


def _split(st: Structure, i: int, at: float) -> int:
    """Split wire i at fraction `at`; wire i keeps the first part, the second part is appended.  Returns its index."""
    w = st.wires[i]
    a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
    p = tuple(map(float, a + (b - a) * at))
    k = st.add(p, w.p1, w.radius, None, w.sigma, w.name, 1)
    w.p1 = p
    for o in st.sources + st.loads:
        if o.wire == i:
            if o.at > at + 1e-9:
                o.wire, o.at = k, (o.at - at) / (1 - at)
            else:
                o.at = o.at / at if at > 0 else 0.0
    return k


def _ends_at(st: Structure, p, tol):
    out = []
    for i, w in enumerate(st.wires):
        for e, q in ((0, w.p0), (1, w.p1)):
            if np.linalg.norm(np.subtract(q, p)) < tol:
                out.append((i, e))
    return out


def _run_dir(st: Structure, req=None) -> np.ndarray:
    """Horizontal direction for the coax run: the user's bearing (degrees from +X toward +Y), or by default at right
    angles to the antenna's longest horizontal extent."""
    deg = getattr(req, "coax_dir", -1.0) if req is not None else -1.0
    if deg is not None and deg >= 0:
        a = math.radians(deg)
        return np.array([math.cos(a), math.sin(a), 0.0])
    pts = np.array([w.p0 for w in st.wires] + [w.p1 for w in st.wires], float)
    ext = np.ptp(pts, axis=0)
    return np.array([0.0, 1.0, 0.0]) if ext[0] >= ext[1] else np.array([1.0, 0.0, 0.0])


def _blocked_down(st: Structure, p, tol) -> bool:
    """True if a wire leaves point p within about 25 degrees of straight down (the route would lie on top of it)."""
    p = np.asarray(p, float)
    for w in st.wires:
        for q0, q1 in ((w.p0, w.p1), (w.p1, w.p0)):
            if np.linalg.norm(np.subtract(q0, p)) < tol:
                d = np.subtract(q1, q0)
                n = np.linalg.norm(d)
                if n > 0 and -d[2] / n > 0.9:
                    return True
    return False


def route(start, length: float, run: np.ndarray, grounded: bool, ground_on: bool, low: float = RUN_HEIGHT,
          sideways: float = 0.0):
    """Polyline of the coax (or feed line) from `start`: `sideways` metres along `run` first (to clear a wire hanging
    below the start), then straight down to `low`, then horizontally along `run`; if grounded, a final drop to the
    ground at the radio."""
    p = np.asarray(start, float)
    pts = [p.copy()]
    left = max(length, 0.0)
    if sideways > 0 and left > sideways:
        p = p + run * sideways; pts.append(p.copy()); left -= sideways
    drop = max(p[2] - low, 0.0)
    d = min(drop, left)
    if d > 1e-3:
        p = p + np.array([0, 0, -d]); pts.append(p.copy()); left -= d
    if left > 1e-3:
        p = p + run * left; pts.append(p.copy()); left = 0.0
    if grounded and ground_on and p[2] > 1e-3:
        pts.append(np.array([p[0], p[1], 0.0]))
    return pts


def _add_path(st: Structure, pts, radius, sigma, name, stub_len=None):
    """Add wires along pts (pts[0] is the attachment point).  With stub_len, the first piece is a short stub whose far
    end is pts[0] (p1 = attachment point); returns (stub index or None, [wire indices])."""
    idx = []
    stub = None
    pts = [np.asarray(q, float) for q in pts]
    if stub_len and len(pts) >= 2:
        a, b = pts[0], pts[1]
        u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        s = a + u * min(stub_len, 0.5 * np.linalg.norm(b - a))
        rest = [s] + pts[1:]
        for q0, q1 in zip(rest[:-1], rest[1:]):
            idx.append(st.add(q0, q1, radius, None, sigma, name, 1))
        stub = st.add(s, a, radius, 1, sigma, name + " (at the balun)", 1)     # appended last, ends at the balun
        idx.append(stub)
    else:
        for q0, q1 in zip(pts[:-1], pts[1:]):
            idx.append(st.add(q0, q1, radius, None, sigma, name, 1))
    return stub, idx


def _ext_tol(st: Structure) -> float:
    ext = max(float(np.ptp(np.array([q for wi in st.wires for q in (wi.p0, wi.p1)]), axis=0).max()), 1e-3)
    return max(1e-9, 1e-6 * ext)


def plan(st: Structure, P, req, line) -> dict:
    """Where the feed line and the coax run, from feedpoint P: shared by the common-mode model and the drawing."""
    ground_on = st.ground.kind != "free"
    run = _run_dir(st, req)
    side = 1.0 if _blocked_down(st, P, _ext_tol(st)) else 0.0
    grounded = bool(getattr(req, "cm_grounded", True))
    low_c = float(getattr(req, "coax_height", RUN_HEIGHT))
    lpts = None
    if line:
        lpts = route(P, line[3], run, False, ground_on, low=float(getattr(req, "feeder_bottom", LADDER_BOTTOM)), sideways=side)
        B = lpts[-1]
        cpts = route(B, req.coax_len, run, grounded, ground_on, low=low_c)
    else:
        B = np.asarray(P, float)
        cpts = route(P, req.coax_len, run, grounded, ground_on, low=low_c, sideways=side)
    if req.coax_key == "none" or req.coax_len <= 0:
        cpts = [B]
    return {"feedpoint": np.asarray(P, float), "feedline": lpts, "balun": B, "coax": cpts, "run": run,
            "grounded": grounded and ground_on, "low": low_c}


def _insert_at_distance(pts, d):
    """Insert a point `d` metres along the polyline.  Returns (new points, index of that point) or (pts, None)."""
    pts = [np.asarray(q, float) for q in pts]
    run = 0.0
    for i in range(len(pts) - 1):
        seg = float(np.linalg.norm(pts[i + 1] - pts[i]))
        if d < run + seg - 1e-6:
            if d - run <= 1e-6:
                return pts, i
            q = pts[i] + (pts[i + 1] - pts[i]) * ((d - run) / seg)
            return pts[:i + 1] + [q] + pts[i + 1:], i + 1
        run += seg
    return pts, None


def _add_coax(st: Structure, pts, req, name="Coax shield (outside)"):
    """Add the coax shield along pts (pts[0] = the balun), the balun's common-mode impedance where it joins, and the
    optional extra choke `choke2_dist` metres down the coax.  Returns info: stub, wires in path order, balun_load,
    choke2 (wire starting at the extra choke) or None, beyond (wires past the extra choke)."""
    od = COAX_OD_MM.get(req.coax_key, 8.0)
    stub_len = min(0.05, req.lam / 400)
    c2_ohm = float(getattr(req, "choke2_ohm", 0.0) or 0.0)
    c2_d = float(getattr(req, "choke2_dist", 0.0) or 0.0)
    c2_point = None
    note = ""
    if c2_ohm > 0:
        d = max(c2_d, 2 * stub_len)                         # keep the extra choke clear of the balun stub
        pts2, k = _insert_at_distance(pts, d)
        if k is None:
            note = f"the extra choke at {c2_d:g} m is beyond the end of the {req.coax_len:g} m coax, so it was left out"
        else:
            pts, c2_point = pts2, pts2[k]
    radius = od / 2000.0
    a, b = pts[0], pts[1]
    u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
    s = a + u * min(stub_len, 0.5 * np.linalg.norm(b - a))
    rest = [s] + pts[1:]
    path = []
    for q0, q1 in zip(rest[:-1], rest[1:]):
        path.append(st.add(q0, q1, radius, None, 5.8e7, name, 1))
    stub = st.add(s, a, radius, 1, 5.8e7, name + " (at the balun)", 1)    # appended last, ends at the balun
    kind = getattr(req, "balun_type", "current")
    choke = getattr(req, "choke_ohm", 2000.0)
    balun_load = kind != "unun"
    if balun_load:
        st.loads.append(Load(stub, 0.0, lambda f, k=kind, c=choke: zcm(k, c, f), "Balun common-mode impedance"))
    c2_wire, beyond = None, set()
    if c2_point is not None:
        for j, wi in enumerate(path):
            if np.linalg.norm(np.subtract(st.wires[wi].p0, c2_point)) < 1e-6:
                c2_wire = wi
                beyond = set(path[j:])
                break
        if c2_wire is not None:
            st.loads.append(Load(c2_wire, 0.0, lambda f, c=c2_ohm: complex(c, 0.0), "Coax choke"))
    return {"stub": stub, "path": path, "shield": set(path) | {stub}, "balun_load": balun_load, "kind": kind,
            "choke": choke, "choke2": c2_wire, "choke2_ohm": c2_ohm, "beyond": beyond, "note": note}


def _measure(model, I, ie, info, scale, i_feed, f_hz) -> dict:
    """Common-mode figures from a solution (basis currents I, segment-end currents ie), scaled by `scale`."""
    cur = _shield_currents(model, ie, info["shield"]) * scale
    stub = info["stub"]
    i_balun = abs(ie[model.wire_first[stub], 1]) * scale            # stub end at the balun
    last = info["path"][-1] if info["path"] else stub
    i_radio = abs(ie[model.wire_first[last] + model.wire_n[last] - 1, 1]) * scale
    p_choke = 0.0
    if info["balun_load"]:
        bl = model.basis_at(stub, 0.0)
        p_choke = 0.5 * abs(I[bl] * scale) ** 2 * zcm(info["kind"], info["choke"], f_hz).real
    out = _pack(i_feed, i_balun, float(cur.max()) if len(cur) else i_balun, i_radio, p_choke)
    if info["choke2"] is not None:
        bl2 = model.basis_at(info["choke2"], 0.0)
        i2 = abs(I[bl2] * scale)
        beyond = _shield_currents(model, ie, info["beyond"]) * scale
        b_max = float(beyond.max()) if len(beyond) else i2
        r = 1 / math.sqrt(2)
        out.update({"cm_i_choke2": i2 * r, "cm_p_choke2": 0.5 * i2 ** 2 * info["choke2_ohm"],
                    "cm_i_beyond": b_max * r,
                    "cm_ratio_db": 20 * math.log10(max(b_max, 1e-12) / max(i_feed, 1e-12))})   # what reaches the shack
    if info.get("note"):
        out["cm_note"] = info["note"]
    return out


# --------------------------------------------------------------------------- balun at the feedpoint
def attach_shield(design, req) -> dict:
    """Add the coax shield to the antenna model (balun at the feedpoint).  Returns info for `results`, or {'skip': why}."""
    st = design.structure
    if st is None or design.analytic is not None or design.imp_override is not None:
        return {"skip": "this antenna has no wire model"}
    if design.mode != "single" or st.lines or len(st.sources) != 1:
        return {"skip": "the antenna has several feed points or a feed network"}
    if req.coax_key == "none" or req.coax_len <= 0:
        return {"skip": "there is no coax"}
    ground_on = st.ground.kind != "free"
    s0 = st.sources[0]
    w = st.wires[s0.wire]
    a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
    P = a + (b - a) * s0.at
    if ground_on and P[2] < 0.5:
        return {"skip": "the feedpoint is at ground level, where the coax shield is part of the ground system"}
    if 1e-6 < s0.at < 1 - 1e-6:
        _split(st, s0.wire, s0.at)
    ext = max(float(np.ptp(np.array([q for wi in st.wires for q in (wi.p0, wi.p1)]), axis=0).max()), 1e-3)
    tol = max(1e-9, 1e-6 * ext)
    att = _ends_at(st, P, tol)
    if len(att) != 2:
        return {"skip": f"{len(att)} wires meet at the feedpoint"}
    # the shield joins the shorter side (the counterpoise of an end-fed antenna; either side of a centre-fed one)
    lens = [np.linalg.norm(np.subtract(st.wires[i].p1, st.wires[i].p0)) for i, _ in att]
    (xi, xe), (yi, ye) = att if lens[0] <= lens[1] else att[::-1]
    if xe == 1:
        _flip(st, xi)            # side X starts at the feedpoint, side Y ends there, the shield stub ends there:
    if ye == 0:                  # the node's first attachment is X, so the feed gap is X-Y and the shield joins X
        _flip(st, yi)
    pts = plan(st, P, req, None)["coax"]
    if len(pts) < 2:
        return {"skip": "the coax is too short to model"}
    info = _add_coax(st, pts, req)
    extra = ""
    if info["choke2"] is not None:
        extra = f" A {info['choke2_ohm']:.0f} ohm choke sits {max(getattr(req, 'choke2_dist', 0.0), 0.1):g} m down the coax."
    design.notes.append("Coax common mode: the outside of the coax shield is part of this model - it runs from the balun "
                        f"{'straight down then ' if P[2] > getattr(req, 'coax_height', RUN_HEIGHT) else ''}along at "
                        f"{getattr(req, 'coax_height', RUN_HEIGHT):g} m height to the radio"
                        + (", where it is grounded." if getattr(req, "cm_grounded", True) and ground_on else ".")
                        + extra + " SWR, pattern and gain include it.")
    info.update({"mode": "feedpoint", "sides": (xi, yi)})
    return info


def check_model(info: dict, model, st) -> bool:
    """The feed gap must be between the two antenna sides, not between the antenna and the shield."""
    if info.get("mode") != "feedpoint":
        return True
    s0 = st.sources[0]
    bsis = model.basis_at(s0.wire, s0.at)
    wires = {int(model.wi[sg]) for sg in model.hseg[bsis]}
    return not (wires & info["shield"])


def _shield_currents(model, I_seg, shield: set):
    """|current| at each segment end of the shield wires (peak, per the solution's scale)."""
    sel = np.isin(model.wi, list(shield))
    return np.abs(I_seg[sel]).ravel()


def results_feedpoint(info: dict, sol, p_ant: float) -> dict:
    """Common-mode figures from the main solution (1 V source) scaled to the power reaching the antenna."""
    if sol.pin <= 0:
        return {}
    k = math.sqrt(max(p_ant, 0.0) / sol.pin)
    i_feed = abs(sol.I[sol.port_basis[0]]) * k
    out = _measure(sol.model, sol.I, sol.seg_currents(), info, k, i_feed, sol.f_hz)
    out["cm_mode"] = "feedpoint"
    return out


def _pack(i_feed, i_balun, i_max, i_radio, p_choke):
    r = 1 / math.sqrt(2)                                  # peak -> rms
    ratio = 20 * math.log10(max(i_max, 1e-12) / max(i_feed, 1e-12))
    return {"cm_i_feed": i_feed * r, "cm_i_balun": i_balun * r, "cm_i_max": i_max * r,
            "cm_i_radio": i_radio * r, "cm_ratio_db": ratio, "cm_p_choke": p_choke}


# --------------------------------------------------------------------------- balun at the bottom of a feed line
def estimate_with_feedline(design, req, line, z_bottom: complex, p_balun: float, f_mhz: float, seg_len: float) -> dict:
    """Common mode on the coax when a (balanced) feed line runs from the antenna to the balun."""
    st0 = design.structure
    if st0 is None or design.analytic is not None or design.imp_override is not None or not st0.sources:
        return {"cm_skip": "this antenna has no wire model"}
    if req.coax_key == "none" or req.coax_len <= 0:
        return {"cm_skip": "there is no coax"}
    st = Structure(wires=copy.deepcopy(st0.wires), loads=copy.deepcopy(st0.loads), sources=[], ground=st0.ground)
    s0 = st0.sources[0]
    w = st.wires[s0.wire]
    a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
    P = a + (b - a) * s0.at
    ground_on = st.ground.kind != "free"
    if 1e-6 < s0.at < 1 - 1e-6:
        st.sources = [Source(s0.wire, s0.at)]
        _split(st, s0.wire, s0.at)
        st.sources = []
    pl = plan(st, P, req, line)
    lpts, cpts = pl["feedline"], pl["coax"]
    if len(lpts) < 2:
        return {"cm_skip": "the feed line is too short to model"}
    _add_path(st, lpts, LADDER_EQ_RADIUS, 5.8e7, "Feed line (common mode)")
    if len(cpts) < 2:
        return {"cm_skip": "the coax is too short to model"}
    info = _add_coax(st, cpts, req)
    st.sources = [Source(info["stub"], 1.0)]              # common-mode drive at the balun, between feed line and coax
    model = mom.Model(st, seg_len)
    f = f_mhz * 1e6
    # half the voltage across the balanced side of the balun drives the coax against the feed line
    rz = max(z_bottom.real, 1e-6)
    i_diff = math.sqrt(2 * max(p_balun, 0.0) / rz)        # peak
    v_cm = 0.5 * i_diff * abs(z_bottom)
    sol = mom.solve(model, f, volts=[v_cm])
    out = _measure(model, sol.I, sol.seg_currents(), info, 1.0, i_diff, f)
    out["cm_mode"] = "feedline"
    out["cm_v"] = v_cm / math.sqrt(2)
    ib = sol.I[sol.port_basis[0]]
    out["cm_zpath"] = v_cm / ib if abs(ib) > 0 else complex("inf")
    return out


# --------------------------------------------------------------------------- drawing
def feed_layout(design, req, line) -> dict | None:
    """The feed system as installed, for the Geometry view: feed line, balun, coax, chokes, radio, ground."""
    from .common import COAX
    from .design import TUNERS
    st = design.structure
    if st is None or design.analytic is not None or not st.sources:
        return None
    s0 = st.sources[0]
    w = st.wires[s0.wire]
    a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
    P = a + (b - a) * s0.at
    pl = plan(st, P, req, line)
    kind = getattr(req, "balun_type", "current")
    ratio = design.force_ratio or req.ratio
    pl["balun_label"] = (f"{ratio:g}:1 " + {"current": "current balun", "voltage": "voltage balun", "unun": "unun"}[kind]
                         if (kind != "unun" or ratio != 1.0) else "")
    if line:
        fk = getattr(req, "feeder_key", "model")
        pl["feedline_label"] = (COAX[fk][0] if fk in COAX else f"{line[0]:.0f} ohm line") + f", {line[3]:g} m"
    pl["coax_label"] = f"{COAX[req.coax_key][0]}, {req.coax_len:g} m" if len(pl["coax"]) > 1 else ""
    c2 = float(getattr(req, "choke2_ohm", 0.0) or 0.0)
    pl["choke2"] = None
    if c2 > 0 and len(pl["coax"]) > 1:
        pts, k = _insert_at_distance(pl["coax"], max(float(getattr(req, "choke2_dist", 0.0)), 0.1))
        if k is not None:
            pl["choke2"] = pts[k]
            pl["choke2_label"] = f"choke {c2:.0f} ohm"
    tk = getattr(req, "tuner", "none")
    tn = next((lab for lab, k, _ in TUNERS if k == tk), "")
    pl["radio_label"] = "Radio" + (f" + {tn.split(' (')[0]}" if tk != "none" else "")
    end = pl["coax"][-1]
    pl["radio"] = end if not pl["grounded"] else pl["coax"][-2] if len(pl["coax"]) > 1 else end
    return pl
