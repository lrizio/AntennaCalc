"""Wire Editor page: draw a wire antenna, label and dimension it, place sources and loads.

The canvas shows one orthographic view (front X-Z, top X-Y or side Y-Z).  New points are created in the
view plane at the chosen depth; snapping to wire ends joins wires, snapping onto the middle of a wire
splits it so the two are connected.  Everything is also editable numerically in the tables on the right.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from ..custom import EPS, LOAD_KINDS, TEMPLATES, CDim, CLoad, CSource, CWire, Drawing, template
from . import theme

PLANES = {  # key: (horizontal axis, vertical axis, depth axis, title)
    "front": (0, 2, 1, "Front view (X-Z)"),
    "top": (0, 1, 2, "Top view (X-Y)"),
    "side": (1, 2, 0, "Side view (Y-Z)"),
}
AX = "XYZ"
GRIDS = [0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]


def _spin(lo, hi, val, dec=3, step=0.1, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi); s.setDecimals(dec); s.setSingleStep(step); s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def fmt_m(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:.1f} m"
    if a >= 1:
        return f"{v:.3f} m"
    return f"{v * 100:.1f} cm"


# =========================================================================== dialogs
class WireDialog(QDialog):
    def __init__(self, w: CWire, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Wire {w.label}")
        f = QFormLayout(self)
        self.label = QLineEdit(w.label)
        f.addRow("Label", self.label)
        self.pts = []
        for name, p in (("Start", w.p0), ("End", w.p1)):
            row = QHBoxLayout()
            sp = [_spin(-1e5, 1e5, v, 4, 0.1) for v in p]
            for a, s in zip(AX, sp):
                row.addWidget(QLabel(a)); row.addWidget(s)
            self.pts.append(sp)
            f.addRow(f"{name} (m)", row)
        self.diam = _spin(0, 500, w.diam_mm, 2, 0.5, " mm")
        self.diam.setSpecialValueText("conductor from input panel")
        f.addRow("Diameter", self.diam)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self):
        return (self.label.text().strip(), [s.value() for s in self.pts[0]], [s.value() for s in self.pts[1]],
                self.diam.value())


class LengthDialog(QDialog):
    def __init__(self, title, text, value, anchor_choice=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        f = QFormLayout(self)
        self.val = _spin(0.001, 1e5, value, 4, 0.01, " m")
        self.ft = QLabel("")
        self.val.valueChanged.connect(lambda v: self.ft.setText(f"{v / 0.3048:.3f} ft"))
        self.val.valueChanged.emit(self.val.value())
        f.addRow(text, self.val)
        f.addRow("", self.ft)
        self.anchor = QComboBox()
        for lab, v in (("Start end", 0), ("End end", 1), ("Centre", 2)):
            self.anchor.addItem(lab, v)
        if anchor_choice:
            f.addRow("Keep fixed", self.anchor)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.val.setFocus(); self.val.selectAll()


class SourceDialog(QDialog):
    def __init__(self, s: CSource, wire_len: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Source {s.label}")
        f = QFormLayout(self)
        self.label = QLineEdit(s.label)
        self.pos = _spin(0, wire_len, s.at * wire_len, 4, 0.01, " m")
        self.pos0 = self.pos.value()
        self.volts = _spin(0.0, 1e4, s.volts, 3, 0.1, " V")
        self.phase = _spin(-360, 360, s.phase, 1, 5, " deg")
        f.addRow("Label", self.label)
        f.addRow("Position from wire start", self.pos)
        f.addRow("Voltage", self.volts)
        f.addRow("Phase", self.phase)
        n = QLabel("The first source is the feed point used for SWR and impedance. Use voltage and phase "
                   "for phased arrays.")
        n.setWordWrap(True); n.setObjectName("dim")
        f.addRow(n)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)


class LoadDialog(QDialog):
    def __init__(self, ld: CLoad, wire_len: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Load {ld.label}")
        f = QFormLayout(self)
        self.label = QLineEdit(ld.label)
        self.pos = _spin(0, wire_len, ld.at * wire_len, 4, 0.01, " m")
        self.pos0 = self.pos.value()
        self.kind = QComboBox()
        for lab, v in LOAD_KINDS:
            self.kind.addItem(lab, v)
        self.kind.setCurrentIndex(max(0, self.kind.findData(ld.kind)))
        self.r = _spin(0, 1e7, ld.r, 3, 1, " ohm")
        self.x = _spin(-1e7, 1e7, ld.x, 3, 1, " ohm")
        self.l = _spin(0, 1e6, ld.l_uh, 4, 0.1, " uH")
        self.c = _spin(0, 1e7, ld.c_pf, 3, 1, " pF")
        f.addRow("Label", self.label)
        f.addRow("Position from wire start", self.pos)
        f.addRow("Type", self.kind)
        f.addRow("Resistance R", self.r)
        self.x_lbl = QLabel("Reactance X")
        f.addRow(self.x_lbl, self.x)
        self.l_lbl, self.c_lbl = QLabel("Inductance L"), QLabel("Capacitance C")
        f.addRow(self.l_lbl, self.l)
        f.addRow(self.c_lbl, self.c)
        self.hint = QLabel("")
        self.hint.setWordWrap(True); self.hint.setObjectName("dim")
        f.addRow(self.hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.kind.currentIndexChanged.connect(self._kind)
        self._kind()

    def _kind(self, *_):
        k = self.kind.currentData()
        fixed = k == "fixed"
        for w in (self.x, self.x_lbl):
            w.setVisible(fixed)
        for w in (self.l, self.l_lbl, self.c, self.c_lbl):
            w.setVisible(not fixed)
        self.hint.setText({"fixed": "Same impedance at every frequency.",
                           "series": "R, L and C in series; leave a value at 0 to leave it out (e.g. a loading coil: "
                                     "L plus its loss resistance).",
                           "parallel": "R, L and C in parallel; a trap is L parallel C (resonant at 1/(2 pi sqrt(LC))). "
                                       "Leave a value at 0 to leave it out."}[k])

    def apply(self, ld: CLoad, wire_len: float):
        ld.label = self.label.text().strip() or ld.label
        if self.pos.value() != self.pos0 and wire_len > 0:
            ld.at = self.pos.value() / wire_len
        ld.kind = self.kind.currentData()
        ld.r, ld.x, ld.l_uh, ld.c_pf = self.r.value(), self.x.value(), self.l.value(), self.c.value()


# =========================================================================== canvas
class WireCanvas(QWidget):
    status = Signal(str)

    def __init__(self, editor: "WireEditor"):
        super().__init__(editor)
        self.ed = editor
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(240, 240)
        self.plane = "front"
        self.depth = 0.0
        self.grid = 0.5
        self.snap = True
        self.show_lengths = True
        self.show_labels = True
        self.tool = "select"
        self.k = 20.0                    # pixels per metre
        self.off = QPointF(200, 300)     # screen position of the origin
        self.wire_start = None           # 3-D point while drawing a wire
        self.cursor3 = None
        self.dim_first = None            # (wire id, end) while placing a dimension
        self.drag = None                 # current drag state
        self.hover = None
        self.text_hits = []              # [(QRectF, kind, id)] dimension texts from the last paint
        self._fitted = False

    # ------------------------------------------------------------------ transforms
    @property
    def dr(self) -> Drawing:
        return self.ed.drawing

    def axes(self):
        return PLANES[self.plane][:3]

    def to_screen(self, p) -> QPointF:
        h, v, _ = self.axes()
        return QPointF(self.off.x() + p[h] * self.k, self.off.y() - p[v] * self.k)

    def to_uv(self, pt: QPointF):
        return (pt.x() - self.off.x()) / self.k, (self.off.y() - pt.y()) / self.k

    def make3(self, u, v, base=None):
        h, vv, d = self.axes()
        p = np.zeros(3) if base is None else np.array(base, float)
        p[h], p[vv] = u, v
        if base is None:
            p[d] = self.depth
        return p

    def fit(self):
        b = self.dr.bounds()
        h, v, _ = self.axes()
        if b is None:
            lo, hi = np.array([-5.0, -5.0, 0.0]), np.array([5.0, 5.0, 10.0])
        else:
            lo, hi = b
        if self.plane != "top":
            lo = np.minimum(lo, 0.0)     # keep the ground line in view
        w = max(hi[h] - lo[h], 1.0)
        ht = max(hi[v] - lo[v], 1.0)
        W, H = max(self.width(), 100), max(self.height(), 100)
        self.k = min((W - 120) / w, (H - 120) / ht)
        self.k = max(self.k, 1e-3)
        cu, cv = (lo[h] + hi[h]) / 2, (lo[v] + hi[v]) / 2
        self.off = QPointF(W / 2 - cu * self.k, H / 2 + cv * self.k)
        self._fitted = True
        self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if not self._fitted:
            self.fit()

    # ------------------------------------------------------------------ hit testing
    @staticmethod
    def _seg_dist(p: QPointF, a: QPointF, b: QPointF):
        ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 < 1e-9:
            return math.hypot(p.x() - ax, p.y() - ay), 0.0
        t = max(0.0, min(1.0, ((p.x() - ax) * dx + (p.y() - ay) * dy) / l2))
        return math.hypot(p.x() - (ax + t * dx), p.y() - (ay + t * dy)), t

    def hit_end(self, pt, tol=9.0, exclude=None):
        best = None
        for w in self.dr.wires:
            for e, p in ((0, w.p0), (1, w.p1)):
                if exclude and (w.id, e) in exclude:
                    continue
                q = self.to_screen(p)
                d = math.hypot(q.x() - pt.x(), q.y() - pt.y())
                if d < tol and (best is None or d < best[0]):
                    best = (d, w.id, e)
        return best[1:] if best else None

    def hit_wire(self, pt, tol=7.0, exclude=None):
        best = None
        for w in self.dr.wires:
            if exclude and w.id in exclude:
                continue
            d, t = self._seg_dist(pt, self.to_screen(w.p0), self.to_screen(w.p1))
            if d < tol and (best is None or d < best[0]):
                best = (d, w.id, t)
        return best[1:] if best else None

    def marker_pos(self, o):
        w = self.dr.wire(o.wire)
        return self.to_screen(w.point(o.at)) if w else None

    def hit_marker(self, pt, tol=10.0):
        best = None
        for o in self.dr.sources + self.dr.loads:
            q = self.marker_pos(o)
            if q is None:
                continue
            d = math.hypot(q.x() - pt.x(), q.y() - pt.y())
            if d < tol and (best is None or d < best[0]):
                best = (d, o.id)
        return best[1] if best else None

    def hit_text(self, pt):
        for r, kind, oid in reversed(self.text_hits):
            if r.adjusted(-3, -3, 3, 3).contains(pt):
                return kind, oid
        return None

    def snap_point(self, pt, origin=None, constrain=False, exclude_ends=None, exclude_wires=None):
        """-> (3-D point, description).  Order: wire end, point on a wire, grid."""
        e = self.hit_end(pt, exclude=exclude_ends)
        if e:
            p = np.array(self.dr.end_point(e), float)
            return p, f"end of {self.dr.wire(e[0]).label}"
        u, v = self.to_uv(pt)
        if constrain and origin is not None:
            h, vv, _ = self.axes()
            du, dv = u - origin[h], v - origin[vv]
            ang = round(math.degrees(math.atan2(dv, du)) / 15.0) * 15.0
            ln = math.hypot(du, dv)
            if self.snap:
                ln = round(ln / self.grid) * self.grid
            u = origin[h] + ln * math.cos(math.radians(ang))
            v = origin[vv] + ln * math.sin(math.radians(ang))
            return self.make3(u, v, None if origin is None else self._depth_of(origin)), f"{ang:.0f} deg"
        hw = self.hit_wire(pt, exclude=exclude_wires)
        if hw:
            w = self.dr.wire(hw[0])
            t = self._snap_t(w, hw[1], pt)
            if 0.0 < t < 1.0:
                return w.point(t), f"on {w.label} (joins it)"
        if self.snap:
            u = round(u / self.grid) * self.grid
            v = round(v / self.grid) * self.grid
        return self.make3(u, v), ""

    def _depth_of(self, p):
        """A base point carrying the depth of p, so constrained points stay in p's plane."""
        q = np.zeros(3)
        q[self.axes()[2]] = p[self.axes()[2]]
        return q

    def _snap_t(self, w: CWire, t: float, pt=None):
        """Snap a fraction along a wire: to the ends / middle when close on screen, else to a tidy distance."""
        L = w.length()
        a, b = self.to_screen(w.p0), self.to_screen(w.p1)
        plen = math.hypot(b.x() - a.x(), b.y() - a.y())
        for tt in (0.0, 0.5, 1.0):
            if abs(t - tt) * plen < 8:
                return tt
        if self.snap and L > 0:
            step = max(self.grid / 10.0, 0.001)
            t = round(t * L / step) * step / L
        return min(max(t, 0.0), 1.0)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, ev):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.screen))
        self._paint_grid(p, t)
        self.text_hits = []
        dr = self.dr
        sel = self.ed.selected
        small = QFont("Segoe UI", 8)
        lab = QFont("Segoe UI", 9, QFont.Bold)
        # wires
        for w in dr.wires:
            a, b = self.to_screen(w.p0), self.to_screen(w.p1)
            col = QColor(t.accent_edge if w.id == sel else (t.text if w.id == self.hover else t.c1))
            pen = QPen(col, 3.2 if w.id == sel else 2.2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            if math.hypot(b.x() - a.x(), b.y() - a.y()) < 2:      # wire along the view direction
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(a, 6, 6)
                p.drawLine(a + QPointF(-4, -4), a + QPointF(4, 4))
            else:
                p.drawLine(a, b)
        # wire ends (joined ends filled, free ends hollow)
        ground = True
        for w in dr.wires:
            for e, q in ((0, w.p0), (1, w.p1)):
                s = self.to_screen(q)
                joined = not dr.free_end(w.id, e, ground)
                p.setPen(QPen(QColor(t.c1), 1.4))
                p.setBrush(QColor(t.c1) if joined else QColor(t.screen))
                p.drawEllipse(s, 3.6, 3.6)
        # wire length dimensions and labels
        for w in dr.wires:
            if self.show_lengths or w.id == sel:
                self._paint_wire_dim(p, t, w, small, w.id == sel)
            if self.show_labels:
                self._paint_label(p, t, w, lab)
        # point-to-point dimensions
        for dm in dr.dims:
            self._paint_dim(p, t, dm, small, dm.id == sel)
        # sources and loads
        for s in dr.sources:
            self._paint_source(p, t, s, s.id == sel, dr.sources.index(s) == 0)
        for ld in dr.loads:
            self._paint_load(p, t, ld, ld.id == sel)
        # rubber band
        if self.tool == "wire" and self.wire_start is not None and self.cursor3 is not None:
            a, b = self.to_screen(self.wire_start), self.to_screen(self.cursor3)
            p.setPen(QPen(QColor(t.warn), 2, Qt.DashLine))
            p.drawLine(a, b)
            L = float(np.linalg.norm(self.cursor3 - self.wire_start))
            h, v, _ = self.axes()
            ang = math.degrees(math.atan2(self.cursor3[v] - self.wire_start[v], self.cursor3[h] - self.wire_start[h]))
            self._tag(p, t, b + QPointF(14, -14), f"{fmt_m(L)}  {ang:.0f} deg")
        if self.tool == "dim" and self.dim_first is not None:
            pa = self.dr.end_point(self.dim_first)
            if pa is not None and self.cursor3 is not None:
                p.setPen(QPen(QColor(t.warn), 1.4, Qt.DashLine))
                p.drawLine(self.to_screen(pa), self.to_screen(self.cursor3))
        if self.cursor3 is not None and self.tool in ("wire", "dim"):
            c = self.to_screen(self.cursor3)
            p.setPen(QPen(QColor(t.warn), 1.2))
            p.drawLine(c + QPointF(-7, 0), c + QPointF(7, 0)); p.drawLine(c + QPointF(0, -7), c + QPointF(0, 7))
        # view title / help
        p.setPen(QColor(t.dim))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        d = self.axes()[2]
        p.drawText(QPointF(10, 18), f"{PLANES[self.plane][3]}   drawing plane {AX[d]} = {self.depth:g} m   grid {self.grid:g} m")
        p.end()

    def _help(self):
        return {"select": "Click to select, drag ends / wires / sources to move, double-click to edit. Wheel zooms, "
                          "right or middle drag pans. Del deletes.",
                "wire": "Click the start, then each next point (Shift = 15 deg steps). Right-click or Esc ends the run. "
                        "Ends snap to wire ends and onto wires.",
                "source": "Click on a wire to place a source (feed point).",
                "load": "Click on a wire to place a load (resistor, coil, capacitor or trap).",
                "dim": "Click a wire end, then another wire end to add a dimension. Double-click its value to edit."}[self.tool]

    def _paint_grid(self, p, t):
        W, H = self.width(), self.height()
        g = self.grid
        while g * self.k < 8:
            g *= 5
        u0, v1 = self.to_uv(QPointF(0, 0))
        u1, v0 = self.to_uv(QPointF(W, H))
        p.setPen(QPen(QColor(t.grid), 1))
        i0, i1 = math.floor(u0 / g), math.ceil(u1 / g)
        if i1 - i0 < 600:
            for i in range(i0, i1 + 1):
                x = self.off.x() + i * g * self.k
                p.drawLine(QPointF(x, 0), QPointF(x, H))
        j0, j1 = math.floor(v0 / g), math.ceil(v1 / g)
        if j1 - j0 < 600:
            for j in range(j0, j1 + 1):
                y = self.off.y() - j * g * self.k
                p.drawLine(QPointF(0, y), QPointF(W, y))
        h, v, _ = self.axes()
        p.setPen(QPen(QColor(t.faint), 1.2))
        p.drawLine(QPointF(self.off.x(), 0), QPointF(self.off.x(), H))
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(t.dim))
        p.drawText(QPointF(W - 22, self.off.y() - 6), f"{AX[h]}+")
        p.drawText(QPointF(self.off.x() + 6, 34), f"{AX[v]}+")
        if self.plane != "top":            # ground line
            y = self.off.y()
            p.setPen(QPen(QColor(t.c3), 1.6))
            p.drawLine(QPointF(0, y), QPointF(W, y))
            p.setPen(QPen(QColor(t.c3), 1.0))
            for x in range(0, W, 14):
                p.drawLine(QPointF(x, y), QPointF(x - 8, y + 8))
            p.drawText(QPointF(8, y + 20), "ground (z = 0)")
        else:
            p.setPen(QPen(QColor(t.faint), 1.2))
            p.drawLine(QPointF(0, self.off.y()), QPointF(W, self.off.y()))

    def _tag(self, p, t, at: QPointF, text: str):
        fm = QFontMetricsF(p.font())
        r = fm.boundingRect(text).adjusted(-5, -3, 5, 3)
        r.moveTopLeft(at)
        p.setPen(QPen(QColor(t.warn), 1))
        p.setBrush(QColor(t.panel))
        p.drawRoundedRect(r, 4, 4)
        p.setPen(QColor(t.text))
        p.drawText(r, Qt.AlignCenter, text)

    def _dim_line(self, p, t, a: QPointF, b: QPointF, off_px: float, text: str, kind: str, oid: int, hot: bool):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(dx, dy)
        if L < 4:
            return
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        if ny > 0 or (abs(ny) < 1e-9 and nx < 0):   # put the dimension above / left of the wire by default
            nx, ny = -nx, -ny
        o = QPointF(nx * off_px, ny * off_px)
        a2, b2 = a + o, b + o
        col = QColor(t.warn if hot else t.dim)
        p.setPen(QPen(col, 1))
        ext = QPointF(nx * 4, ny * 4)
        p.drawLine(a + QPointF(nx * 3, ny * 3), a2 + ext)
        p.drawLine(b + QPointF(nx * 3, ny * 3), b2 + ext)
        p.drawLine(a2, b2)
        for tip, sgn in ((a2, 1), (b2, -1)):
            back = QPointF(ux * 7 * sgn, uy * 7 * sgn)
            side = QPointF(nx * 3, ny * 3)
            p.setBrush(col)
            p.drawPolygon(QPolygonF([tip, tip + back + side, tip + back - side]))
        mid = (a2 + b2) / 2
        ang = math.degrees(math.atan2(dy, dx))
        if ang > 90:
            ang -= 180
        elif ang <= -90:
            ang += 180
        fm = QFontMetricsF(p.font())
        tw, th = fm.horizontalAdvance(text) + 8, fm.height() + 2
        p.save()
        p.translate(mid)
        p.rotate(ang)
        r = QRectF(-tw / 2, -th / 2, tw, th)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.screen))
        p.drawRect(r)
        p.setPen(QColor(t.warn if hot else t.text))
        p.drawText(r, Qt.AlignCenter, text)
        p.restore()
        s = max(tw, th)
        self.text_hits.append((QRectF(mid.x() - s / 2, mid.y() - th, s, 2 * th), kind, oid))

    def _paint_wire_dim(self, p, t, w, font, hot):
        p.setFont(font)
        a, b = self.to_screen(w.p0), self.to_screen(w.p1)
        self._dim_line(p, t, a, b, 16, fmt_m(w.length()), "wlen", w.id, hot)

    def _paint_label(self, p, t, w, font):
        a, b = self.to_screen(w.p0), self.to_screen(w.p1)
        marks = [self.marker_pos(o) for o in self.dr.sources + self.dr.loads if o.wire == w.id]
        mid = (a + b) / 2
        for f in (0.5, 0.3, 0.7, 0.2, 0.8):          # keep the label clear of sources and loads
            c = a + (b - a) * f
            if all(math.hypot(c.x() - m.x(), c.y() - m.y()) > 34 for m in marks):
                mid = c
                break
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        if ny < 0 or (abs(ny) < 1e-9 and nx > 0):     # opposite side to the dimension
            nx, ny = -nx, -ny
        p.setFont(font)
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(w.label)
        c = mid + QPointF(nx * 14, ny * 14)
        p.setPen(QColor(t.accent_edge if w.id == self.ed.selected else t.c1))
        p.drawText(QPointF(c.x() - tw / 2, c.y() + fm.ascent() / 2), w.label)

    def _paint_dim(self, p, t, dm: CDim, font, hot):
        pa, pb = self.dr.end_point(dm.a), self.dr.end_point(dm.b)
        if pa is None or pb is None:
            return
        p.setFont(font)
        d = float(np.linalg.norm(pb - pa))
        text = (dm.label + " " if dm.label else "") + fmt_m(d)
        self._dim_line(p, t, self.to_screen(pa), self.to_screen(pb), 30 + dm.offset * self.k, text, "dim", dm.id, hot)

    def _paint_source(self, p, t, s: CSource, hot, feed):
        q = self.marker_pos(s)
        if q is None:
            return
        col = QColor(t.accent_edge if hot else t.c2)
        p.setPen(QPen(col, 2))
        p.setBrush(QColor(t.screen))
        p.drawEllipse(q, 8, 8)
        path = QPainterPath(q + QPointF(-5, 0))
        path.cubicTo(q + QPointF(-2.5, -6), q + QPointF(-0.5, -6), q)
        path.cubicTo(q + QPointF(0.5, 6), q + QPointF(2.5, 6), q + QPointF(5, 0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if self.show_labels:
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(col)
            p.drawText(q + QPointF(11, 30), s.label + (" (feed)" if feed else ""))

    def _paint_load(self, p, t, ld: CLoad, hot):
        q = self.marker_pos(ld)
        if q is None:
            return
        w = self.dr.wire(ld.wire)
        a, b = self.to_screen(w.p0), self.to_screen(w.p1)
        ang = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
        col = QColor(t.accent_edge if hot else t.c3)
        p.save()
        p.translate(q)
        p.rotate(ang)
        p.setPen(QPen(col, 2))
        p.setBrush(QColor(t.screen))
        p.drawRect(QRectF(-11, -6, 22, 12))
        zz = QPolygonF([QPointF(-8, 0), QPointF(-6, -4), QPointF(-3, 4), QPointF(0, -4), QPointF(3, 4),
                        QPointF(6, -4), QPointF(8, 0)])
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(zz)
        p.restore()
        if self.show_labels:
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(col)
            p.drawText(q + QPointF(13, 30), ld.label)

    # ------------------------------------------------------------------ mouse
    def wheelEvent(self, ev):
        f = 1.15 ** (ev.angleDelta().y() / 120.0)
        pos = ev.position()
        u, v = self.to_uv(pos)
        self.k = min(max(self.k * f, 1e-3), 1e6)
        self.off = QPointF(pos.x() - u * self.k, pos.y() + v * self.k)
        self._fitted = True
        self.update()

    def mousePressEvent(self, ev):
        pos = ev.position()
        self.setFocus()
        if ev.button() in (Qt.MiddleButton,) or (ev.button() == Qt.RightButton and self.tool == "select"
                                                  and not self._hit_any(pos)):
            self.drag = {"kind": "pan", "start": pos, "off": QPointF(self.off), "moved": False,
                         "right": ev.button() == Qt.RightButton}
            return
        if ev.button() == Qt.RightButton:
            if self.tool == "wire" and self.wire_start is not None:
                self.wire_start = None
                self.update()
                return
            if self.tool == "dim" and self.dim_first is not None:
                self.dim_first = None
                self.update()
                return
            self._context(pos, ev.globalPosition().toPoint())
            return
        if ev.button() != Qt.LeftButton:
            return
        getattr(self, f"_press_{self.tool}")(pos, ev)

    def _hit_any(self, pos):
        return bool(self.hit_marker(pos) or self.hit_text(pos) or self.hit_end(pos) or self.hit_wire(pos))

    def _press_select(self, pos, ev):
        m = self.hit_marker(pos)
        if m:
            self.ed.select(m)
            self.drag = {"kind": "marker", "id": m, "snap": self.dr.to_dict(), "moved": False}
            return
        ht = self.hit_text(pos)
        if ht and ht[0] == "dim":
            self.ed.select(ht[1])
            dm = self.dr.find(ht[1])
            self.drag = {"kind": "dimoff", "id": ht[1], "start": pos, "off0": dm.offset, "snap": self.dr.to_dict(), "moved": False}
            return
        e = self.hit_end(pos)
        if e:
            self.ed.select(e[0])
            p0 = self.dr.end_point(e)
            self.drag = {"kind": "end", "ref": e, "orig": p0.copy(), "cur": p0.copy(),
                         "snap": self.dr.to_dict(), "moved": False,
                         "group": set(self.dr.ends_at(p0))}
            return
        hw = self.hit_wire(pos)
        if hw:
            self.ed.select(hw[0])
            w = self.dr.wire(hw[0])
            self.drag = {"kind": "wire", "id": hw[0], "start": pos, "p0": np.array(w.p0), "p1": np.array(w.p1),
                         "snap": self.dr.to_dict(), "moved": False}
            return
        if ht and ht[0] == "wlen":
            self.ed.select(ht[1])
            return
        self.ed.select(None)
        self.drag = {"kind": "pan", "start": pos, "off": QPointF(self.off), "moved": False, "right": False}

    def _press_wire(self, pos, ev):
        constrain = bool(ev.modifiers() & Qt.ShiftModifier)
        p3, _ = self.snap_point(pos, self.wire_start, constrain and self.wire_start is not None)
        if self.wire_start is None:
            self.wire_start = p3
            self.cursor3 = p3
            self.update()
            return
        if np.linalg.norm(p3 - self.wire_start) < 1e-4:
            return
        self.ed.push_undo()
        w = self.dr.add_wire(self.wire_start, p3)
        self.ed.join_at(w.p0, exclude=w.id)
        self.ed.join_at(w.p1, exclude=w.id)
        self.wire_start = p3
        self.ed.select(w.id, refresh=False)
        self.ed.refresh()

    def _press_source(self, pos, ev):
        self._place(pos, "source")

    def _press_load(self, pos, ev):
        self._place(pos, "load")

    def _place(self, pos, kind):
        hw = self.hit_wire(pos, tol=10)
        if not hw:
            self.status.emit("Click on a wire.")
            return
        w = self.dr.wire(hw[0])
        at = self._snap_t(w, hw[1])
        self.ed.add_marker(kind, w.id, at)

    def _press_dim(self, pos, ev):
        e = self.hit_end(pos, tol=12)
        if not e:
            self.status.emit("Click on a wire end.")
            return
        if self.dim_first is None:
            self.dim_first = e
            self.update()
            return
        pa, pb = self.dr.end_point(self.dim_first), self.dr.end_point(e)
        if np.linalg.norm(pb - pa) < EPS:
            return
        self.ed.push_undo()
        dm = CDim(self.dr.new_id(), list(self.dim_first), list(e))
        self.dr.dims.append(dm)
        self.dim_first = None
        self.ed.select(dm.id, refresh=False)
        self.ed.refresh()

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        d = self.drag
        constrain = bool(ev.modifiers() & Qt.ShiftModifier)
        if d and d["kind"] == "pan":
            self.off = d["off"] + (pos - d["start"])
            d["moved"] = d["moved"] or (pos - d["start"]).manhattanLength() > 3
            self._fitted = True
            self.update()
            return
        if d and d["kind"] == "end":
            others = [r for r in d["group"]]
            other_end = (d["ref"][0], 1 - d["ref"][1])
            p3, why = self.snap_point(pos, self.dr.end_point(other_end), constrain, exclude_ends=set(others),
                                      exclude_wires={r[0] for r in others})
            if not constrain and why == "" and not self.hit_end(pos, exclude=set(others)):
                p3 = self.make3(*self._grid_uv(pos), base=d["cur"])   # keep the point's own depth
            if np.linalg.norm(p3 - d["cur"]) > 0:
                for wid, e in d["group"]:
                    w = self.dr.wire(wid)
                    if w is None:
                        continue
                    if e:
                        w.p1 = list(map(float, p3))
                    else:
                        w.p0 = list(map(float, p3))
                d["cur"] = p3
                d["moved"] = True
                w = self.dr.wire(d["ref"][0])
                self.status.emit(f"{w.label}: length {fmt_m(w.length())}   end at ({p3[0]:.3f}, {p3[1]:.3f}, {p3[2]:.3f}) m  {why}")
                self.update()
            return
        if d and d["kind"] == "wire":
            du, dv = self.to_uv(pos)
            su, sv = self.to_uv(d["start"])
            h, v, _ = self.axes()
            delta = np.zeros(3)
            delta[h], delta[v] = du - su, dv - sv
            if self.snap:
                delta = np.round(delta / self.grid) * self.grid
            w = self.dr.wire(d["id"])
            new0, new1 = d["p0"] + delta, d["p1"] + delta
            if np.linalg.norm(np.subtract(w.p0, new0)) > 0 or np.linalg.norm(np.subtract(w.p1, new1)) > 0:
                self.dr.move_point(w.p0, new0)
                self.dr.move_point(w.p1, new1)
                d["moved"] = True
                self.status.emit(f"Moving {w.label} by ({delta[0]:.3f}, {delta[1]:.3f}, {delta[2]:.3f}) m")
                self.update()
            return
        if d and d["kind"] == "marker":
            o = self.dr.find(d["id"])
            hw = self.hit_wire(pos, tol=40)
            if hw:
                w = self.dr.wire(hw[0])
                at = self._snap_t(w, hw[1])
                if (o.wire, o.at) != (w.id, at):
                    o.wire, o.at = w.id, at
                    d["moved"] = True
                    self.status.emit(f"{o.label}: {fmt_m(at * w.length())} from the start of {w.label} ({at * 100:.1f} %)")
                    self.update()
            return
        if d and d["kind"] == "dimoff":
            dm = self.dr.find(d["id"])
            pa, pb = self.dr.end_point(dm.a), self.dr.end_point(dm.b)
            a, b = self.to_screen(pa), self.to_screen(pb)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            if ny > 0 or (abs(ny) < 1e-9 and nx < 0):
                nx, ny = -nx, -ny
            mv = pos - d["start"]
            dm.offset = d["off0"] + (mv.x() * nx + mv.y() * ny) / self.k
            d["moved"] = True
            self.update()
            return
        # hover / rubber band
        if self.tool == "wire":
            self.cursor3, why = self.snap_point(pos, self.wire_start, constrain and self.wire_start is not None)
            c = self.cursor3
            self.status.emit(f"({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}) m  {why}")
        elif self.tool == "dim":
            e = self.hit_end(pos, tol=12)
            self.cursor3 = self.dr.end_point(e) if e else self.make3(*self.to_uv(pos))
        else:
            u, v = self.to_uv(pos)
            c = self.make3(u, v)
            hw = self.hit_wire(pos)
            self.hover = hw[0] if hw else None
            extra = ""
            if hw:
                w = self.dr.wire(hw[0])
                extra = f"   {w.label}: {fmt_m(w.length())}  ({w.length() / 0.3048:.2f} ft)"
            h, vv, _ = self.axes()
            self.status.emit(f"{AX[h]} {c[h]:.3f} m, {AX[vv]} {c[vv]:.3f} m{extra}")
        self.update()

    def _grid_uv(self, pos):
        u, v = self.to_uv(pos)
        if self.snap:
            u, v = round(u / self.grid) * self.grid, round(v / self.grid) * self.grid
        return u, v

    def mouseReleaseEvent(self, ev):
        d = self.drag
        self.drag = None
        if not d:
            return
        if d["kind"] == "pan":
            if d.get("right") and not d["moved"]:
                self._context(ev.position(), ev.globalPosition().toPoint())
            return
        if d.get("moved"):
            self.ed.push_undo(d["snap"])
            if d["kind"] == "end":
                self.ed.join_at(d["cur"], exclude_ids={r[0] for r in d["group"]})
            if d["kind"] == "wire":
                w = self.dr.wire(d["id"])
                if w:
                    self.ed.join_at(w.p0, exclude=w.id)
                    self.ed.join_at(w.p1, exclude=w.id)
            self.ed.refresh()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        pos = ev.position()
        if self.tool == "wire":
            self.wire_start = None
            self.update()
            return
        if self.tool != "select":
            return
        m = self.hit_marker(pos)
        if m:
            self.ed.edit_object(m)
            return
        ht = self.hit_text(pos)
        if ht:
            if ht[0] == "wlen":
                self.ed.edit_length(ht[1])
            else:
                self.ed.edit_dim(ht[1])
            return
        hw = self.hit_wire(pos)
        if hw:
            self.ed.edit_object(hw[0])

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Escape:
            if self.wire_start is not None or self.dim_first is not None:
                self.wire_start = None
                self.dim_first = None
            else:
                self.ed.set_tool("select")
            self.update()
        elif k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.ed.delete_selected()
        elif not ev.modifiers():
            tool = {Qt.Key_V: "select", Qt.Key_W: "wire", Qt.Key_S: "source", Qt.Key_L: "load", Qt.Key_D: "dim"}.get(k)
            if tool:
                self.ed.set_tool(tool)
            elif k == Qt.Key_F:
                self.fit()
            else:
                super().keyPressEvent(ev)
        else:
            super().keyPressEvent(ev)

    def leaveEvent(self, ev):
        self.hover = None
        self.update()

    def _context(self, pos, gpos):
        menu = QMenu(self)
        m = self.hit_marker(pos)
        hw = self.hit_wire(pos)
        ht = self.hit_text(pos)
        if m:
            self.ed.select(m)
            menu.addAction("Properties...", lambda: self.ed.edit_object(m))
            menu.addAction("Delete", lambda: self.ed.delete(m))
        elif ht and ht[0] == "dim":
            self.ed.select(ht[1])
            menu.addAction("Edit distance...", lambda: self.ed.edit_dim(ht[1]))
            menu.addAction("Delete dimension", lambda: self.ed.delete(ht[1]))
        elif hw:
            w = self.dr.wire(hw[0])
            at = self._snap_t(w, hw[1])
            self.ed.select(w.id)
            menu.addAction("Properties...", lambda: self.ed.edit_object(w.id))
            menu.addAction("Set length...", lambda: self.ed.edit_length(w.id))
            menu.addSeparator()
            menu.addAction(f"Add source here ({fmt_m(at * w.length())} from start)", lambda: self.ed.add_marker("source", w.id, at))
            menu.addAction("Add load here", lambda: self.ed.add_marker("load", w.id, at))
            if 0 < at < 1:
                menu.addAction("Split wire here", lambda: self.ed.split(w.id, at))
            menu.addAction("Add length dimension", lambda: self.ed.add_dim([w.id, 0], [w.id, 1]))
            menu.addSeparator()
            menu.addAction("Delete wire", lambda: self.ed.delete(w.id))
        menu.addAction("Fit view", self.fit)
        menu.exec(gpos)


# =========================================================================== page
class WireEditor(QWidget):
    analyse_requested = Signal()
    changed = Signal()

    def __init__(self, lam_fn=None, parent=None):
        super().__init__(parent)
        self.lam_fn = lam_fn or (lambda: 21.2)
        self.drawing = template("dipole", self.lam_fn())
        self.selected = None
        self.undo_stack, self.redo_stack = [], []
        self.tuned_scale = None
        self._refreshing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        self.setStyleSheet("QPushButton { padding-left: 9px; padding-right: 9px; }")   # compact toolbar
        # ---- toolbar row 1: file-ish / view
        r1 = QHBoxLayout()
        self.name = QLineEdit(self.drawing.name)
        self.name.setPlaceholderText("Antenna name")
        self.name.setMinimumWidth(120)
        self.name.setMaximumWidth(260)
        self.name.editingFinished.connect(self._name_changed)
        r1.addWidget(QLabel("Name")); r1.addWidget(self.name)
        self.tmpl = QComboBox()
        for lab, key in TEMPLATES:
            self.tmpl.addItem(lab, key)
        self.tmpl.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.tmpl.setMinimumContentsLength(10)
        self.tmpl.setToolTip("Start a new drawing from a template sized for the design frequency")
        b_new = QPushButton("New from template")
        b_new.clicked.connect(self.new_from_template)
        r1.addWidget(self.tmpl); r1.addWidget(b_new)
        r1.addSpacing(8)
        self.b_undo = QPushButton("Undo"); self.b_undo.clicked.connect(self.undo); self.b_undo.setShortcut("Ctrl+Z")
        self.b_redo = QPushButton("Redo"); self.b_redo.clicked.connect(self.redo); self.b_redo.setShortcut("Ctrl+Y")
        self.b_del = QPushButton("Delete"); self.b_del.clicked.connect(self.delete_selected)
        b_clear = QPushButton("Clear"); b_clear.clicked.connect(self.clear)
        for b in (self.b_undo, self.b_redo, self.b_del, b_clear):
            r1.addWidget(b)
        r1.addStretch(1)
        root.addLayout(r1)
        rv = QHBoxLayout()                # view row (kept separate so the page can be narrow)
        self.view = QComboBox()
        self.view.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.view.setMinimumContentsLength(14)
        for key, v in PLANES.items():
            self.view.addItem(v[3], key)
        self.view.currentIndexChanged.connect(self._view_changed)
        rv.addWidget(self.view)
        self.depth_lbl = QLabel("Plane Y =")
        self.depth = _spin(-1e4, 1e4, 0.0, 3, 0.5, " m")
        self.depth.setToolTip("Coordinate of the drawing plane along the viewing direction; new points are placed in it")
        self.depth.valueChanged.connect(self._depth_changed)
        rv.addWidget(self.depth_lbl); rv.addWidget(self.depth)
        self.grid = QComboBox()
        for g in GRIDS:
            self.grid.addItem(f"grid {g:g} m", g)
        self.grid.setCurrentIndex(GRIDS.index(0.5))
        self.grid.currentIndexChanged.connect(self._grid_changed)
        rv.addWidget(self.grid)
        self.snap = QCheckBox("Snap"); self.snap.setChecked(True)
        self.snap.toggled.connect(self._opts)
        self.lens = QCheckBox("Lengths"); self.lens.setChecked(True)
        self.lens.toggled.connect(self._opts)
        self.labels = QCheckBox("Labels"); self.labels.setChecked(True)
        self.labels.toggled.connect(self._opts)
        for w in (self.snap, self.lens, self.labels):
            rv.addWidget(w)
        b_fit = QPushButton("Fit")
        b_fit.setToolTip("Fit the drawing in the view (F)")
        rv.addWidget(b_fit)
        rv.addStretch(1)
        root.addLayout(rv)
        # ---- toolbar row 2: tools / actions
        r2 = QHBoxLayout()
        self.tool_btns = {}
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for key, text, tip in (("select", "Select", "Select, move and edit (V)"), ("wire", "Wire", "Draw wires (W)"),
                               ("source", "Source", "Place a source / feed point on a wire (S)"),
                               ("load", "Load", "Place a load: R, L, C or trap (L)"),
                               ("dim", "Dimension", "Dimension between two wire ends (D)")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.set_tool(k))
            grp.addButton(b)
            r2.addWidget(b)
            self.tool_btns[key] = b
        r2.addStretch(1)
        self.b_scale = QPushButton("Apply tuned size")
        self.b_scale.setToolTip("Copy the size found by auto-tune back into the drawing")
        self.b_scale.clicked.connect(self.apply_tuned_scale)
        self.b_scale.hide()
        r2.addWidget(self.b_scale)
        b_go = QPushButton("ANALYSE  (F5)")
        b_go.setObjectName("primary")
        b_go.setToolTip("Simulate this drawing with the band, ground, conductor and feed settings on the left")
        b_go.clicked.connect(self.analyse_requested.emit)
        r2.addWidget(b_go)
        root.addLayout(r2)

        # ---- canvas + side panel
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.canvas = WireCanvas(self)
        b_fit.clicked.connect(self.canvas.fit)
        ll.addWidget(self.canvas, 1)
        self.status = QLabel("")
        self.status.setObjectName("dim")
        self.status.setMinimumWidth(10)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        ll.addWidget(self.status)
        self.canvas.status.connect(self.status.setText)
        split.addWidget(left)

        self.side = QTabWidget()
        self.t_wires = self._table(["Label", "X1", "Y1", "Z1", "X2", "Y2", "Z2", "Length (m)", "Dia (mm)"])
        self.t_src = self._table(["Label", "Wire", "Position (m)", "Volts", "Phase (deg)"])
        self.t_load = self._table(["Label", "Wire", "Position (m)", "Type", "Value"])
        self.t_dims = self._table(["Label", "From", "To", "Distance (m)"])
        for t, name in ((self.t_wires, "Wires"), (self.t_src, "Sources"), (self.t_load, "Loads"), (self.t_dims, "Dimensions")):
            self.side.addTab(t, name)
        self.t_wires.itemChanged.connect(self._wire_cell)
        self.t_src.itemChanged.connect(self._src_cell)
        self.t_load.itemChanged.connect(self._load_cell)
        self.t_dims.itemChanged.connect(self._dim_cell)
        side_w = QWidget()
        sl = QVBoxLayout(side_w)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.side, 1)
        self.check = QLabel("")
        self.check.setWordWrap(True)
        sl.addWidget(self.check)
        hint = QLabel("Edit numbers directly in the tables. Double-click a non-editable cell (wire, type, value) "
                      "to open the full properties.")
        hint.setWordWrap(True); hint.setObjectName("dim")
        sl.addWidget(hint)
        split.addWidget(side_w)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([760, 460])
        root.addWidget(split, 1)
        self.set_tool("select")
        self.refresh()

    # ------------------------------------------------------------------ helpers
    def _table(self, heads):
        t = QTableWidget(0, len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        t.setAlternatingRowColors(True)
        t.itemSelectionChanged.connect(lambda tt=t: self._table_sel(tt))
        t.itemDoubleClicked.connect(self._table_dbl)
        return t

    def push_undo(self, snap=None):
        self.undo_stack.append(snap if snap is not None else self.drawing.to_dict())
        del self.undo_stack[:-200]
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.drawing.to_dict())
        self.drawing = Drawing.from_dict(self.undo_stack.pop())
        self._after_replace()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.drawing.to_dict())
        self.drawing = Drawing.from_dict(self.redo_stack.pop())
        self._after_replace()

    def _after_replace(self):
        if self.selected is not None and self.drawing.find(self.selected) is None:
            self.selected = None
        self.name.setText(self.drawing.name)
        self.refresh()

    def set_drawing(self, d: dict | None, fit=True):
        self.drawing = Drawing.from_dict(d) if d else Drawing()
        self.undo_stack.clear(); self.redo_stack.clear()
        self.selected = None
        self.name.setText(self.drawing.name)
        self.refresh()
        if fit:
            self.canvas.fit()

    def set_tool(self, tool):
        self.canvas.tool = tool
        self.canvas.wire_start = None
        self.canvas.dim_first = None
        self.canvas.setCursor(Qt.ArrowCursor if tool == "select" else Qt.CrossCursor)
        self.tool_btns[tool].setChecked(True)
        self.canvas.update()
        self.canvas.status.emit(self.canvas._help())

    def select(self, oid, refresh=True):
        self.selected = oid
        if refresh:
            self._sync_table_sel()
            self.canvas.update()

    def join_at(self, p, exclude=None, exclude_ids=None):
        """If point p lies on the inside of another wire, split that wire there so the two are joined."""
        p = np.asarray(p, float)
        ex = set(exclude_ids or ())
        if exclude is not None:
            ex.add(exclude)
        for w in list(self.drawing.wires):
            if w.id in ex:
                continue
            a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
            d = b - a
            L2 = float(d @ d)
            if L2 < 1e-12:
                continue
            t = float((p - a) @ d / L2)
            if 1e-6 < t < 1 - 1e-6 and np.linalg.norm(a + d * t - p) < 1e-5:
                self.drawing.split_wire(w.id, t)
                return

    # ------------------------------------------------------------------ actions
    def add_marker(self, kind, wid, at):
        dr = self.drawing
        self.push_undo()
        if kind == "source":
            o = CSource(dr.new_id(), wid, at, label=dr.default_label("S"))
            dr.sources.append(o)
        else:
            o = CLoad(dr.new_id(), wid, at, "series", r=1.0, l_uh=10.0, label=dr.default_label("L"))
            dr.loads.append(o)
        self.selected = o.id
        self.refresh()
        if not self.edit_object(o.id, new=True):
            self.drawing = Drawing.from_dict(self.undo_stack.pop())
            self.selected = None
            self.refresh()

    def add_dim(self, a, b):
        self.push_undo()
        dm = CDim(self.drawing.new_id(), list(a), list(b), 0.0)
        self.drawing.dims.append(dm)
        self.selected = dm.id
        self.refresh()

    def split(self, wid, at):
        self.push_undo()
        self.drawing.split_wire(wid, at)
        self.refresh()

    def delete(self, oid):
        if oid is None or self.drawing.find(oid) is None:
            return
        self.push_undo()
        self.drawing.delete(oid)
        if self.selected == oid:
            self.selected = None
        self.refresh()

    def delete_selected(self):
        self.delete(self.selected)

    def clear(self):
        if not self.drawing.wires:
            return
        if QMessageBox.question(self, "Wire Editor", "Remove every wire, source, load and dimension?") != QMessageBox.Yes:
            return
        self.push_undo()
        name = self.drawing.name
        self.drawing = Drawing(name=name)
        self.selected = None
        self.refresh()

    def new_from_template(self):
        key = self.tmpl.currentData()
        self.push_undo()
        self.drawing = Drawing() if key == "empty" else template(key, self.lam_fn())
        self.drawing.name = self.tmpl.currentText() if key != "empty" else "Custom antenna"
        self.name.setText(self.drawing.name)
        self.selected = None
        self.tuned_scale = None
        self.b_scale.hide()
        self.refresh()
        self.canvas.fit()

    def set_tuned_scale(self, s):
        self.tuned_scale = s if (s and abs(s - 1.0) > 1e-6) else None
        self.b_scale.setVisible(self.tuned_scale is not None)
        if self.tuned_scale:
            self.b_scale.setText(f"Apply tuned size (x{self.tuned_scale:.4f})")

    def apply_tuned_scale(self):
        if not self.tuned_scale:
            return
        self.push_undo()
        self.drawing.scale(self.tuned_scale)
        self.set_tuned_scale(None)
        self.refresh()
        self.canvas.status.emit("Tuned size applied. Set auto-tune back to 'Use the drawing as-is' to keep it exactly.")

    def edit_length(self, wid):
        w = self.drawing.wire(wid)
        if w is None:
            return
        dlg = LengthDialog("Wire length", f"Length of {w.label}", w.length(), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.push_undo()
        L = dlg.val.value()
        anc = dlg.anchor.currentData()
        if anc == 2:
            a, b = np.asarray(w.p0, float), np.asarray(w.p1, float)
            c, d = (a + b) / 2, b - a
            u = d / (np.linalg.norm(d) or 1.0)
            self.drawing.move_point(a, c - u * L / 2)
            self.drawing.move_point(b, c + u * L / 2)
        else:
            self.drawing.set_length(wid, L, anc)
        self.refresh()

    def edit_dim(self, did):
        dm = self.drawing.find(did)
        if not isinstance(dm, CDim):
            return
        pa, pb = self.drawing.end_point(dm.a), self.drawing.end_point(dm.b)
        dlg = LengthDialog("Dimension", "Distance", float(np.linalg.norm(pb - pa)), anchor_choice=False, parent=self)
        lab = QLineEdit(dm.label)
        dlg.layout().insertRow(0, "Label", lab)
        n = QLabel("Changing the distance moves the second end (and anything joined to it) along the dimension line.")
        n.setWordWrap(True); n.setObjectName("dim")
        dlg.layout().insertRow(3, n)
        if dlg.exec() != QDialog.Accepted:
            return
        self.push_undo()
        dm.label = lab.text().strip()
        self.drawing.set_distance(dm, dlg.val.value())
        self.refresh()

    def edit_object(self, oid, new=False) -> bool:
        o = self.drawing.find(oid)
        if o is None:
            return False
        snap = self.drawing.to_dict()
        if isinstance(o, CWire):
            dlg = WireDialog(o, self)
            if dlg.exec() != QDialog.Accepted:
                return False
            label, p0, p1, dia = dlg.values()
            if np.linalg.norm(np.subtract(p0, p1)) < 1e-4:
                QMessageBox.warning(self, "Wire Editor", "The two ends must be different points.")
                return False
            self.push_undo(snap)
            o.label = label or o.label
            o.diam_mm = dia
            if np.linalg.norm(np.subtract(o.p0, p0)) > 0:
                self.drawing.move_point(o.p0, p0)
            if np.linalg.norm(np.subtract(o.p1, p1)) > 0:
                self.drawing.move_point(o.p1, p1)
            self.join_at(o.p0, exclude=o.id)
            self.join_at(o.p1, exclude=o.id)
        elif isinstance(o, CSource):
            L = self.drawing.wire(o.wire).length()
            dlg = SourceDialog(o, L, self)
            if dlg.exec() != QDialog.Accepted:
                return False
            if not new:
                self.push_undo(snap)
            o.label = dlg.label.text().strip() or o.label
            if dlg.pos.value() != dlg.pos0 and L > 0:
                o.at = dlg.pos.value() / L
            o.volts, o.phase = dlg.volts.value(), dlg.phase.value()
        elif isinstance(o, CLoad):
            L = self.drawing.wire(o.wire).length()
            dlg = LoadDialog(o, L, self)
            if dlg.exec() != QDialog.Accepted:
                return False
            if not new:
                self.push_undo(snap)
            dlg.apply(o, L)
        elif isinstance(o, CDim):
            self.edit_dim(oid)
            return True
        self.refresh()
        return True

    # ------------------------------------------------------------------ view options
    def _view_changed(self, *_):
        self.canvas.plane = self.view.currentData()
        d = PLANES[self.canvas.plane][2]
        self.depth_lbl.setText(f"Plane {AX[d]} =")
        self.depth.blockSignals(True)
        self.depth.setValue(0.0 if d != 2 else self._default_top_depth())
        self.depth.blockSignals(False)
        self.canvas.depth = self.depth.value()
        self.canvas.wire_start = None
        self.canvas.fit()

    def _default_top_depth(self):
        b = self.drawing.bounds()
        return float(b[1][2]) if b is not None else 10.0

    def _depth_changed(self, v):
        self.canvas.depth = v
        self.canvas.update()

    def _grid_changed(self, *_):
        self.canvas.grid = self.grid.currentData()
        self.canvas.update()

    def _opts(self, *_):
        self.canvas.snap = self.snap.isChecked()
        self.canvas.show_lengths = self.lens.isChecked()
        self.canvas.show_labels = self.labels.isChecked()
        self.canvas.update()

    def _name_changed(self):
        self.drawing.name = self.name.text().strip() or "Custom antenna"
        self.changed.emit()

    # ------------------------------------------------------------------ tables
    def refresh(self):
        self._refreshing = True
        dr = self.drawing
        lbl = {w.id: w.label for w in dr.wires}

        def item(text, editable=True, data=None):
            it = QTableWidgetItem(str(text))
            if not editable:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if data is not None:
                it.setData(Qt.UserRole, data)
            return it
        t = self.t_wires
        t.setRowCount(len(dr.wires))
        for r, w in enumerate(dr.wires):
            t.setItem(r, 0, item(w.label, data=w.id))
            for c, v in enumerate(list(w.p0) + list(w.p1)):
                t.setItem(r, 1 + c, item(f"{v:.4f}"))
            t.setItem(r, 7, item(f"{w.length():.4f}"))
            t.setItem(r, 8, item(f"{w.diam_mm:g}" if w.diam_mm > 0 else "default"))
        t = self.t_src
        t.setRowCount(len(dr.sources))
        for r, s in enumerate(dr.sources):
            w = dr.wire(s.wire)
            t.setItem(r, 0, item(s.label + (" *" if r == 0 else ""), data=s.id))
            t.setItem(r, 1, item(lbl.get(s.wire, "?"), False))
            t.setItem(r, 2, item(f"{s.at * w.length():.4f}" if w else "-"))
            t.setItem(r, 3, item(f"{s.volts:g}"))
            t.setItem(r, 4, item(f"{s.phase:g}"))
        t = self.t_load
        t.setRowCount(len(dr.loads))
        for r, ld in enumerate(dr.loads):
            w = dr.wire(ld.wire)
            t.setItem(r, 0, item(ld.label, data=ld.id))
            t.setItem(r, 1, item(lbl.get(ld.wire, "?"), False))
            t.setItem(r, 2, item(f"{ld.at * w.length():.4f}" if w else "-"))
            t.setItem(r, 3, item(dict((v, k) for k, v in LOAD_KINDS)[ld.kind], False))
            t.setItem(r, 4, item(ld.describe(), False))
        t = self.t_dims
        t.setRowCount(len(dr.dims))
        for r, dm in enumerate(dr.dims):
            pa, pb = dr.end_point(dm.a), dr.end_point(dm.b)
            t.setItem(r, 0, item(dm.label, data=dm.id))
            t.setItem(r, 1, item(f"{lbl.get(dm.a[0], '?')} {'end' if dm.a[1] else 'start'}", False))
            t.setItem(r, 2, item(f"{lbl.get(dm.b[0], '?')} {'end' if dm.b[1] else 'start'}", False))
            t.setItem(r, 3, item(f"{np.linalg.norm(pb - pa):.4f}" if pa is not None and pb is not None else "-"))
        self._refreshing = False
        probs = dr.problems(ground=True)
        if probs:
            self.check.setText("<span style='color:%s'>To analyse: %s</span>" % (theme.current().warn, " ".join(probs)))
        else:
            tot = sum(w.length() for w in dr.wires)
            self.check.setText(f"<span style='color:{theme.current().good}'>Ready: {len(dr.wires)} wires, "
                               f"{tot:.2f} m of wire, {len(dr.sources)} source(s), {len(dr.loads)} load(s).</span>")
        self.b_undo.setEnabled(bool(self.undo_stack))
        self.b_redo.setEnabled(bool(self.redo_stack))
        self._sync_table_sel()
        self.canvas.update()
        self.changed.emit()

    def _sync_table_sel(self):
        self._refreshing = True
        for i, t in enumerate((self.t_wires, self.t_src, self.t_load, self.t_dims)):
            t.clearSelection()
            for r in range(t.rowCount()):
                it = t.item(r, 0)
                if it is not None and it.data(Qt.UserRole) == self.selected and self.selected is not None:
                    t.selectRow(r)
                    if self.side.currentWidget() is not t and self.isVisible():
                        self.side.setCurrentIndex(i)
        self._refreshing = False

    def _row_id(self, t, row):
        it = t.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def _table_sel(self, t):
        if self._refreshing:
            return
        rows = t.selectionModel().selectedRows()
        if rows:
            self.selected = self._row_id(t, rows[0].row())
            self.canvas.update()

    def _table_dbl(self, it):
        if it.flags() & Qt.ItemIsEditable:
            return
        oid = self._row_id(it.tableWidget(), it.row())
        if oid is not None:
            self.edit_object(oid)

    @staticmethod
    def _num(text):
        try:
            return float(str(text).replace(",", ".").split()[0])
        except (ValueError, IndexError):
            return None

    def _wire_cell(self, it):
        if self._refreshing:
            return
        w = self.drawing.wire(self._row_id(self.t_wires, it.row()))
        if w is None:
            return
        c = it.column()
        snap = self.drawing.to_dict()
        if c == 0:
            w.label = it.text().strip() or w.label
        elif 1 <= c <= 6:
            v = self._num(it.text())
            if v is None:
                return self.refresh()
            old = list(w.p0 if c <= 3 else w.p1)
            new = list(old)
            new[(c - 1) % 3] = v
            self.drawing.move_point(old, new)
            self.join_at(new, exclude=w.id)
        elif c == 7:
            v = self._num(it.text())
            if not v or v <= 0:
                return self.refresh()
            self.drawing.set_length(w.id, v, 0)
        elif c == 8:
            v = self._num(it.text())
            w.diam_mm = max(v, 0.0) if v is not None else 0.0
        self.push_undo(snap)
        self.refresh()

    def _src_cell(self, it):
        if self._refreshing:
            return
        s = self.drawing.find(self._row_id(self.t_src, it.row()))
        if s is None:
            return
        snap = self.drawing.to_dict()
        c, v = it.column(), self._num(it.text())
        w = self.drawing.wire(s.wire)
        if c == 0:
            s.label = it.text().replace("*", "").strip() or s.label
        elif c == 2 and v is not None and w:
            s.at = min(max(v / w.length(), 0.0), 1.0)
        elif c == 3 and v is not None:
            s.volts = v
        elif c == 4 and v is not None:
            s.phase = v
        self.push_undo(snap)
        self.refresh()

    def _load_cell(self, it):
        if self._refreshing:
            return
        ld = self.drawing.find(self._row_id(self.t_load, it.row()))
        if ld is None:
            return
        snap = self.drawing.to_dict()
        c, v = it.column(), self._num(it.text())
        w = self.drawing.wire(ld.wire)
        if c == 0:
            ld.label = it.text().strip() or ld.label
        elif c == 2 and v is not None and w:
            ld.at = min(max(v / w.length(), 0.0), 1.0)
        self.push_undo(snap)
        self.refresh()

    def _dim_cell(self, it):
        if self._refreshing:
            return
        dm = self.drawing.find(self._row_id(self.t_dims, it.row()))
        if dm is None:
            return
        snap = self.drawing.to_dict()
        if it.column() == 0:
            dm.label = it.text().strip()
        elif it.column() == 3:
            v = self._num(it.text())
            if v and v > 0:
                self.drawing.set_distance(dm, v)
        self.push_undo(snap)
        self.refresh()
