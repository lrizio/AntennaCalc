"""Custom (user-drawn) wire antennas: the Wire Editor drawing model and its MoM builder.

The drawing is plain data (wires, sources, loads, dimension annotations) so it can be saved in a
.antcalc file and passed to the design worker through the extra-parameter dict as ``ex["drawing"]``.
Coordinates are metres; z is the height above ground (z = 0 is the ground plane).
"""
from __future__ import annotations

import cmath
import copy
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .design import Design, Param, Spec, TuneTarget, register
from .mom import Load, Source

EPS = 1e-6          # coordinate tolerance (m) for "same point"


# --------------------------------------------------------------------------- data
@dataclass
class CWire:
    id: int
    p0: list
    p1: list
    label: str = ""
    diam_mm: float = 0.0          # 0 = use the conductor diameter chosen on the input panel

    def length(self) -> float:
        return float(np.linalg.norm(np.subtract(self.p1, self.p0)))

    def point(self, at: float) -> np.ndarray:
        a = np.asarray(self.p0, float)
        return a + (np.asarray(self.p1, float) - a) * at


@dataclass
class CSource:
    id: int
    wire: int                     # wire id
    at: float                     # 0..1 along the wire from p0
    volts: float = 1.0
    phase: float = 0.0            # degrees
    label: str = ""


LOAD_KINDS = [("Fixed R + jX", "fixed"), ("Series R-L-C", "series"), ("Parallel R-L-C (trap)", "parallel")]


@dataclass
class CLoad:
    id: int
    wire: int
    at: float
    kind: str = "series"          # fixed | series | parallel
    r: float = 0.0                # ohm
    x: float = 0.0                # ohm (fixed only)
    l_uh: float = 0.0             # microhenry, 0 = absent
    c_pf: float = 0.0             # picofarad, 0 = absent
    label: str = ""

    def z(self, f_hz: float) -> complex:
        w = 2 * math.pi * f_hz
        if self.kind == "fixed":
            return complex(self.r, self.x)
        zl = 1j * w * self.l_uh * 1e-6 if self.l_uh > 0 else None
        zc = 1 / (1j * w * self.c_pf * 1e-12) if self.c_pf > 0 else None
        if self.kind == "series":
            return self.r + (zl or 0) + (zc or 0)
        y = 0j                     # parallel
        if self.r > 0:
            y += 1 / self.r
        if zl is not None:
            y += 1 / zl
        if zc is not None:
            y += 1 / zc
        return 1 / y if abs(y) > 0 else complex(1e9, 0)

    def describe(self) -> str:
        if self.kind == "fixed":
            return f"{self.r:g} {'+' if self.x >= 0 else '-'} j{abs(self.x):g} ohm"
        parts = []
        if self.r > 0:
            parts.append(f"R {self.r:g} ohm")
        if self.l_uh > 0:
            parts.append(f"L {self.l_uh:g} uH")
        if self.c_pf > 0:
            parts.append(f"C {self.c_pf:g} pF")
        return ("series " if self.kind == "series" else "parallel ") + (", ".join(parts) or "(empty)")


@dataclass
class CDim:
    """Distance annotation between two wire ends: a = (wire id, end 0|1), b likewise."""
    id: int
    a: list
    b: list
    offset: float = 0.0           # perpendicular offset of the dimension line, metres
    label: str = ""


@dataclass
class Drawing:
    wires: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    loads: list = field(default_factory=list)
    dims: list = field(default_factory=list)
    next_id: int = 1
    name: str = "Custom antenna"

    # ---------------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        return {"name": self.name, "next_id": self.next_id,
                "wires": [asdict(w) for w in self.wires], "sources": [asdict(s) for s in self.sources],
                "loads": [asdict(l) for l in self.loads], "dims": [asdict(d) for d in self.dims]}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Drawing":
        d = d or {}
        dr = cls(name=d.get("name", "Custom antenna"), next_id=int(d.get("next_id", 1)))
        dr.wires = [CWire(**w) for w in d.get("wires", [])]
        dr.sources = [CSource(**s) for s in d.get("sources", [])]
        dr.loads = [CLoad(**l) for l in d.get("loads", [])]
        dr.dims = [CDim(**x) for x in d.get("dims", [])]
        ids = [o.id for o in dr.wires + dr.sources + dr.loads + dr.dims]
        dr.next_id = max([dr.next_id] + [i + 1 for i in ids])
        return dr

    def copy(self) -> "Drawing":
        return copy.deepcopy(self)

    # ---------------------------------------------------------------- lookups
    def new_id(self) -> int:
        i = self.next_id
        self.next_id += 1
        return i

    def wire(self, wid: int) -> CWire | None:
        return next((w for w in self.wires if w.id == wid), None)

    def find(self, oid: int):
        for lst in (self.wires, self.sources, self.loads, self.dims):
            for o in lst:
                if o.id == oid:
                    return o
        return None

    def end_point(self, ref) -> np.ndarray | None:
        w = self.wire(ref[0])
        if w is None:
            return None
        return np.asarray(w.p1 if ref[1] else w.p0, float)

    def ends_at(self, p, exclude=None) -> list:
        """All (wire id, end) whose endpoint coincides with p."""
        p = np.asarray(p, float)
        out = []
        for w in self.wires:
            for e, q in ((0, w.p0), (1, w.p1)):
                if (w.id, e) == exclude:
                    continue
                if np.linalg.norm(np.subtract(q, p)) < EPS:
                    out.append((w.id, e))
        return out

    def free_end(self, wid: int, end: int, ground: bool) -> bool:
        w = self.wire(wid)
        p = w.p1 if end else w.p0
        if ground and abs(p[2]) < EPS:
            return False
        return not self.ends_at(p, exclude=(wid, end))

    def default_label(self, prefix: str) -> str:
        used = {o.label for o in self.wires + self.sources + self.loads}
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    # ---------------------------------------------------------------- editing
    def add_wire(self, p0, p1, label="", diam_mm=0.0) -> CWire:
        w = CWire(self.new_id(), [float(v) for v in p0], [float(v) for v in p1], label or self.default_label("W"), diam_mm)
        self.wires.append(w)
        return w

    def move_point(self, old, new):
        """Move every wire end at `old` to `new` (keeps junctions connected)."""
        new = [float(v) for v in new]
        for wid, e in self.ends_at(old):
            w = self.wire(wid)
            if e:
                w.p1 = list(new)
            else:
                w.p0 = list(new)

    def set_length(self, wid: int, length: float, anchor: int = 0):
        """Resize a wire to `length` keeping the `anchor` end fixed; ends joined to the moving end follow."""
        w = self.wire(wid)
        if w is None or length <= 0:
            return
        a = np.asarray(w.p0 if anchor == 0 else w.p1, float)
        b = np.asarray(w.p1 if anchor == 0 else w.p0, float)
        d = b - a
        L = np.linalg.norm(d)
        u = d / L if L > 0 else np.array([1.0, 0, 0])
        self.move_point(b, a + u * length)

    def set_distance(self, dim: CDim, dist: float):
        """Edit a point-to-point dimension: moves end b along the a->b line."""
        pa, pb = self.end_point(dim.a), self.end_point(dim.b)
        if pa is None or pb is None or dist <= 0:
            return
        d = pb - pa
        L = np.linalg.norm(d)
        if L < EPS:
            return
        self.move_point(pb, pa + d / L * dist)

    def split_wire(self, wid: int, at: float) -> tuple:
        """Split a wire at fraction `at` (creates a junction).  Sources and loads keep their physical position.
        Returns (first wire, second wire)."""
        w = self.wire(wid)
        p = list(map(float, w.point(at)))
        w2 = CWire(self.new_id(), p, list(w.p1), self.default_label("W"), w.diam_mm)
        w.p1 = list(p)
        self.wires.insert(self.wires.index(w) + 1, w2)
        for o in self.sources + self.loads:
            if o.wire == wid:
                if o.at > at + 1e-9:
                    o.wire, o.at = w2.id, (o.at - at) / (1 - at)
                else:
                    o.at = o.at / at if at > 0 else 0.0
        for dm in self.dims:            # dimensions on the old far end now refer to the new piece
            for ref in (dm.a, dm.b):
                if ref[0] == wid and ref[1] == 1:
                    ref[0] = w2.id
        return w, w2

    def delete(self, oid: int):
        o = self.find(oid)
        if o is None:
            return
        if isinstance(o, CWire):
            self.wires.remove(o)
            self.sources = [s for s in self.sources if s.wire != oid]
            self.loads = [l for l in self.loads if l.wire != oid]
            self.dims = [d for d in self.dims if d.a[0] != oid and d.b[0] != oid]
        elif isinstance(o, CSource):
            self.sources.remove(o)
        elif isinstance(o, CLoad):
            self.loads.remove(o)
        elif isinstance(o, CDim):
            self.dims.remove(o)

    def scale(self, s: float):
        """Scale the whole antenna (x, y about the origin, z about the lowest point)."""
        if not self.wires:
            return
        zmin = min(min(w.p0[2], w.p1[2]) for w in self.wires)
        for w in self.wires:
            for p in (w.p0, w.p1):
                p[0] *= s; p[1] *= s; p[2] = zmin + (p[2] - zmin) * s

    def bounds(self):
        if not self.wires:
            return None
        pts = np.array([w.p0 for w in self.wires] + [w.p1 for w in self.wires], float)
        return pts.min(axis=0), pts.max(axis=0)

    # ---------------------------------------------------------------- checks
    def problems(self, ground: bool) -> list:
        out = []
        if not self.wires:
            out.append("Draw at least one wire.")
        if not self.sources:
            out.append("Add a source (feed point) to a wire.")
        for w in self.wires:
            if w.length() < 1e-3:
                out.append(f"Wire {w.label} has zero length.")
            if ground and min(w.p0[2], w.p1[2]) < -EPS:
                out.append(f"Wire {w.label} goes below ground (z < 0).")
        for o in self.sources + self.loads:
            w = self.wire(o.wire)
            kind = "Source" if isinstance(o, CSource) else "Load"
            if w is None:
                out.append(f"{kind} {o.label} is not on a wire.")
                continue
            if o.at <= 1e-6 and self.free_end(w.id, 0, ground) or o.at >= 1 - 1e-6 and self.free_end(w.id, 1, ground):
                out.append(f"{kind} {o.label} is at the free end of wire {w.label}; move it inside the wire.")
        return out


# --------------------------------------------------------------------------- templates
def template(name: str, lam: float, h: float = 10.0) -> Drawing:
    """Starter drawings sized for wavelength `lam`."""
    dr = Drawing()
    if name == "dipole":
        half = 0.2375 * lam
        w = dr.add_wire((-half, 0, h), (half, 0, h), "Dipole")
        dr.sources.append(CSource(dr.new_id(), w.id, 0.5, label="S1"))
    elif name == "invv":
        half = 0.245 * lam
        dz = half * math.sin(math.radians(30))
        dx = half * math.cos(math.radians(30))
        a = dr.add_wire((-dx, 0, h - dz), (0, 0, h), "Leg L")
        dr.add_wire((0, 0, h), (dx, 0, h - dz), "Leg R")
        dr.sources.append(CSource(dr.new_id(), a.id, 1.0, label="S1"))
    elif name == "vertical":
        q = 0.25 * lam
        v = dr.add_wire((0, 0, 0), (0, 0, q * 0.97), "Radiator")
        dr.sources.append(CSource(dr.new_id(), v.id, 0.0, label="S1"))
    elif name == "gp":
        q = 0.25 * lam
        base = max(h, 3.0)
        v = dr.add_wire((0, 0, base), (0, 0, base + q * 0.97), "Radiator")
        for i, (x, y) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
            c = math.cos(math.radians(45))
            dr.add_wire((0, 0, base), (x * q * c, y * q * c, base - q * c), f"Radial {i + 1}")
        dr.sources.append(CSource(dr.new_id(), v.id, 0.0, label="S1"))
    elif name == "loop":
        s = 0.255 * lam
        pts = [(-s / 2, 0, h), (s / 2, 0, h), (s / 2, 0, h + s), (-s / 2, 0, h + s)]
        ws = [dr.add_wire(pts[i], pts[(i + 1) % 4], ["Bottom", "Right", "Top", "Left"][i]) for i in range(4)]
        dr.sources.append(CSource(dr.new_id(), ws[0].id, 0.5, label="S1"))
    return dr


TEMPLATES = [("Empty", "empty"), ("Half-wave dipole", "dipole"), ("Inverted-V", "invv"),
             ("Ground-mounted vertical", "vertical"), ("Ground plane (elevated)", "gp"), ("Full-wave quad loop", "loop")]


# --------------------------------------------------------------------------- builder
def build_structure(dr: Drawing, st, req, scale: float = 1.0):
    """Fill a mom.Structure from the drawing.  Wires are split at every source and load so each one sits
    exactly on a segment junction.  Returns {(kind, id): (struct wire, at)}."""
    zmin = min(min(w.p0[2], w.p1[2]) for w in dr.wires) if dr.wires else 0.0

    def tf(p):
        return (p[0] * scale, p[1] * scale, zmin + (p[2] - zmin) * scale)
    where = {}
    ground = st.ground.kind != "free"

    def eff_at(o, w):
        """A source/load on a wire end where three or more wires meet would sit between just two of them,
        so move it a short feed gap into its own wire (as the built-in ground-plane models do)."""
        at = min(max(o.at, 0.0), 1.0)
        if at < 1e-4:                   # typed / rounded positions this close to an end mean the end
            at = 0.0
        elif at > 1 - 1e-4:
            at = 1.0
        if 0.0 < at < 1.0:
            return at
        end = 1 if at >= 1.0 else 0
        p = w.p1 if end else w.p0
        others = len(dr.ends_at(p, exclude=(w.id, end)))
        if others < 2 and not (others >= 1 and ground and abs(p[2]) < EPS):
            return at
        gap = min(0.05 * w.length(), req.lam / 500.0) / max(w.length(), 1e-9)
        return 1.0 - gap if end else gap
    eff = {o.id: eff_at(o, dr.wire(o.wire)) for o in dr.sources + dr.loads if dr.wire(o.wire)}
    for w in dr.wires:
        cuts = sorted({eff[o.id] for o in dr.sources + dr.loads if o.wire == w.id} - {0.0, 1.0})
        merged = []
        for c in cuts:
            if not merged or c - merged[-1] > 1e-4:
                merged.append(c)
        fr = [0.0] + merged + [1.0]
        radius = (w.diam_mm / 2000.0) if w.diam_mm > 0 else req.radius
        idx = []
        for a, b in zip(fr[:-1], fr[1:]):
            idx.append(st.add(tf(w.point(a)), tf(w.point(b)), radius, sigma=req.sigma, name=w.label, min_seg=1))
        for o in dr.sources + dr.loads:
            if o.wire != w.id:
                continue
            at = eff[o.id]
            if at <= 0.0:
                loc = (idx[0], 0.0)
            elif at >= 1.0:
                loc = (idx[-1], 1.0)
            else:
                k = min(range(len(merged)), key=lambda i: abs(merged[i] - at))
                loc = (idx[k], 1.0)
            where[("S" if isinstance(o, CSource) else "L", o.id)] = loc
    return where


def b_custom(req, ex, sc):
    from .mhelp import new_struct
    # no drawing passed (scripts, self-test): use the starter dipole so the spec still builds
    dr = Drawing.from_dict(ex["drawing"]) if ex.get("drawing") else template("dipole", req.lam, req.height)
    d = Design("custom", dr.name or "Custom wire antenna")
    st = new_struct(req, d)
    ground = st.ground.kind != "free"
    probs = dr.problems(ground)
    if probs:
        raise ValueError("The Wire Editor drawing is not ready:\n - " + "\n - ".join(probs))
    s = float(sc.get("scale", 1.0))
    where = build_structure(dr, st, req, s)
    for src in dr.sources:            # drawing order = port order; the first source is the feed point
        wi, at = where[("S", src.id)]
        st.sources.append(Source(wi, at, cmath.rect(src.volts, math.radians(src.phase)), src.label))
    for ld in dr.loads:
        wi, at = where[("L", ld.id)]
        st.loads.append(Load(wi, at, ld.z, ld.label))
    if ex.get("tune") == "scale":
        d.tune = [TuneTarget("scale", req.f_mhz, "x0", lo=0.5, hi=1.8, label="overall size")]
    d.pol = "mixed"
    total = 0.0
    for w in dr.wires:
        L = w.length() * s
        total += L
        dia = w.diam_mm if w.diam_mm > 0 else req.diameter_mm
        a, b = (tuple(round(v, 3) for v in p) for p in (w.p0, w.p1))
        d.dim(f"Wire {w.label}", 1, L, f"dia {dia:g} mm; drawn from {a} to {b} m"
              + (f", scaled x{s:.4f}" if s != 1.0 else ""))
    for i, src in enumerate(dr.sources):
        w = dr.wire(src.wire)
        d.dim(f"Source {src.label}" + (" (feed point)" if i == 0 else ""), 1, src.at * w.length() * s,
              f"from the start of wire {w.label}; {src.volts:g} V at {src.phase:g} deg")
    for ld in dr.loads:
        w = dr.wire(ld.wire)
        d.dim(f"Load {ld.label}", 1, ld.at * w.length() * s, f"from the start of wire {w.label}; {ld.describe()}")
    d.dim("Total wire", 1, total)
    if s != 1.0:
        d.notes.append(f"Auto-tune scaled the whole drawing by {s:.4f} to reach resonance at {req.f_mhz:.3f} MHz "
                       "(use 'Apply tuned size' on the Wire Editor page to copy it back to the drawing).")
    if len(dr.sources) > 1:
        d.notes.append("Several sources: the SWR and impedance shown are for the first source; "
                       "the port table lists every source.")
    d.notes += ["Geometry, sources and loads come from the Wire Editor page. Wires touching z = 0 are connected to "
                "ground when a ground is selected.",
                "Wire ends that share a point are joined. A wire end landing on the middle of another wire is joined "
                "by splitting that wire (the editor does this automatically)."]
    return d


register(Spec("custom", "Custom wire antenna (Wire Editor)", "Custom", b_custom,
              params=[Param("tune", "Auto-tune", "choice", "none",
                            choices=[("Use the drawing as-is", "none"), ("Scale whole antenna to resonance", "scale")],
                            tip="Scale every dimension together until the first source has zero reactance at the design frequency.")],
              desc="Your own wire antenna, drawn on the Wire Editor page: draw wires, label and dimension them, "
                   "and place sources and loads anywhere on them.",
              height_default=10.0, height_label="Height (set in the drawing)", uses_height=False))
