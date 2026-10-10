"""Custom-painted plots: polar pattern, line plot, wire geometry view."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import theme


def _nice_ticks(lo: float, hi: float, n: int = 6):
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    start = math.ceil(lo / step) * step
    ticks = []
    v = start
    while v <= hi + 1e-9:
        ticks.append(v)
        v += step
    return ticks, step


class PolarPlot(QWidget):
    """Antenna pattern in dB.  mode 'az' = compass, 'el' = vertical plane (front horizon on the right)."""

    def __init__(self, mode: str = "az", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.ang = None
        self.series = {}
        self.primary = "total"
        self.title = ""
        self.span = 40.0
        self.ground = False
        self.setMinimumSize(260, 260)
        self.setMouseTracking(True)
        self._hover = None
        self.unit = "dBi"

    def set_data(self, ang, series: dict, primary: str, title: str, ground: bool = False, unit: str = "dBi"):
        self.ang = np.asarray(ang, float)
        self.series = series
        self.primary = primary
        self.title = title
        self.ground = ground
        self.unit = unit
        self.update()

    def clear(self):
        self.ang = None
        self.series = {}
        self.update()

    def _geom(self):
        w, h = self.width(), self.height()
        side = min(w, h) - 70
        c = QPointF(w / 2, h / 2 + 8)
        return c, max(side / 2, 20)

    def _pt(self, ang_deg, r_frac, c, R):
        if self.mode == "az":
            a = math.radians(ang_deg)
            return QPointF(c.x() + R * r_frac * math.sin(a), c.y() - R * r_frac * math.cos(a))
        a = math.radians(ang_deg)
        return QPointF(c.x() + R * r_frac * math.cos(a), c.y() - R * r_frac * math.sin(a))

    def paintEvent(self, e):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.screen))
        c, R = self._geom()
        f = QFont(self.font()); f.setPointSize(8)
        p.setFont(f)
        p.setPen(QColor(t.dim))
        p.drawText(10, 18, self.title)
        if self.ang is None or not self.series:
            p.drawText(self.rect(), Qt.AlignCenter, "No pattern yet")
            return
        y = self.series[self.primary]
        peak = float(np.max(y))
        top = math.ceil(peak / 5.0) * 5.0
        span = self.span
        bot = top - span
        # rings
        ring_pen = QPen(QColor(t.grid)); ring_pen.setWidthF(1)
        p.setPen(ring_pen)
        step = 10.0
        k = 0
        v = top
        while v >= bot - 1e-6:
            fr = (v - bot) / span
            p.setPen(ring_pen)
            p.drawEllipse(c, R * fr, R * fr)
            p.setPen(QColor(t.faint))
            if k > 0 or True:
                p.drawText(QPointF(c.x() + 3, c.y() - R * fr + 11), f"{v:.0f}")
            v -= step
            k += 1
        # ground shading in elevation
        if self.mode == "el" and self.ground:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(120, 90, 50, 50))
            p.drawPie(QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R), 180 * 16, 180 * 16)
        # spokes + labels
        p.setPen(ring_pen)
        for a in range(0, 360, 30):
            q = self._pt(a, 1.0, c, R)
            p.drawLine(c, q)
            lab = self._pt(a, 1.0 + 22 / R, c, R)
            p.setPen(QColor(t.dim))
            if self.mode == "az":
                txt = {0: "N", 90: "E", 180: "S", 270: "W"}.get(a, f"{a}")
            else:
                txt = {0: "front", 90: "zenith", 180: "back", 270: "nadir"}.get(a, f"{a if a <= 180 else 360 - a}")
            fm = p.fontMetrics()
            p.drawText(QPointF(lab.x() - fm.horizontalAdvance(txt) / 2, lab.y() + 4), txt)
            p.setPen(ring_pen)
        # curves
        colors = {"total": t.c1, "vertical": t.c3, "horizontal": t.c2, "rhcp": t.c3, "lhcp": t.c2}
        for name, yy in self.series.items():
            if name != self.primary:
                continue
        order = [n for n in self.series if n != self.primary] + [self.primary]
        for name in order:
            yy = self.series[name]
            fr = np.clip((yy - bot) / span, 0, 1)
            path = QPainterPath()
            for i, (a, rf) in enumerate(zip(self.ang, fr)):
                pt = self._pt(a, rf, c, R)
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            path.closeSubpath()
            col = QColor(colors.get(name, t.c1))
            is_primary = name == self.primary
            if is_primary:
                fill = QColor(col); fill.setAlpha(46)
                p.setBrush(fill)
            else:
                p.setBrush(Qt.NoBrush)
            pen = QPen(col); pen.setWidthF(2.0 if is_primary else 1.2)
            if not is_primary:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawPath(path)
        # peak marker
        i = int(np.argmax(y))
        pk = self._pt(self.ang[i], (y[i] - bot) / span, c, R)
        p.setPen(QPen(QColor(t.bad), 2)); p.setBrush(QColor(t.bad))
        p.drawEllipse(pk, 4, 4)
        p.setPen(QColor(t.text))
        p.drawText(10, self.height() - 10, f"peak {peak:.1f} {self.unit} at {self.ang[i]:.0f} deg   ({span:.0f} dB span)")
        if self._hover is not None:
            ang, val = self._hover
            p.setPen(QColor(t.warn))
            p.drawText(self.width() - 170, 18, f"{ang:5.0f} deg   {val:6.1f} {self.unit}")

    def mouseMoveEvent(self, ev):
        if self.ang is None or not self.series:
            return
        c, R = self._geom()
        dx, dy = ev.position().x() - c.x(), c.y() - ev.position().y()
        if self.mode == "az":
            a = math.degrees(math.atan2(dx, dy)) % 360
        else:
            a = math.degrees(math.atan2(dy, dx)) % 360
        idx = int(round(a)) % len(self.ang)
        self._hover = (self.ang[idx], float(self.series[self.primary][idx]))
        self.update()

    def leaveEvent(self, ev):
        self._hover = None
        self.update()


class LinePlot(QWidget):
    def __init__(self, title: str = "", xlabel: str = "MHz", ylabel: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.series = []        # (name, x, y, color_key)
        self.vlines = []        # (x, label, color_key)
        self.hlines = []        # (y, label, color_key)
        self.band = None        # (x0, x1)
        self.ylim = None
        self.logy = False
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self._hover = None

    def set_series(self, series, vlines=(), hlines=(), band=None, ylim=None, logy=False):
        self.series = list(series)
        self.vlines = list(vlines)
        self.hlines = list(hlines)
        self.band = band
        self.ylim = ylim
        self.logy = logy
        self.update()

    def _rect(self):
        return QRectF(58, 28, self.width() - 78, self.height() - 74)

    def _ranges(self):
        xs = np.concatenate([np.asarray(s[1], float) for s in self.series]) if self.series else np.array([0, 1])
        x0, x1 = float(np.nanmin(xs)), float(np.nanmax(xs))
        if self.ylim:
            y0, y1 = self.ylim
        else:
            ys = np.concatenate([np.asarray(s[2], float) for s in self.series]) if self.series else np.array([0, 1])
            ys = ys[np.isfinite(ys)]
            y0, y1 = (float(ys.min()), float(ys.max())) if len(ys) else (0, 1)
            pad = 0.08 * (y1 - y0 if y1 > y0 else 1)
            y0, y1 = y0 - pad, y1 + pad
        if x1 <= x0:
            x1 = x0 + 1
        return x0, x1, y0, y1

    def _ty(self, v):
        return math.log10(max(v, 1e-6)) if self.logy else v

    def paintEvent(self, e):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.screen))
        f = QFont(self.font()); f.setPointSize(8)
        p.setFont(f)
        r = self._rect()
        p.setPen(QColor(t.dim))
        p.drawText(10, 16, self.title)
        if not self.series:
            p.drawText(self.rect(), Qt.AlignCenter, "No data yet")
            return
        x0, x1, y0, y1 = self._ranges()
        ty0, ty1 = self._ty(y0), self._ty(y1)

        def X(v):
            return r.left() + (v - x0) / (x1 - x0) * r.width()

        def Y(v):
            return r.bottom() - (self._ty(v) - ty0) / (ty1 - ty0) * r.height()
        if self.band:
            bands = self.band if isinstance(self.band, list) else [self.band]
            for b0, b1 in bands:
                if b1 < x0 or b0 > x1:
                    continue
                p.fillRect(QRectF(X(max(b0, x0)), r.top(), max(X(min(b1, x1)) - X(max(b0, x0)), 2), r.height()),
                           QColor(108, 182, 255, 28 if len(bands) == 1 else 46))
        grid = QPen(QColor(t.grid)); grid.setWidthF(1)
        xt, _ = _nice_ticks(x0, x1, 7)
        for v in xt:
            p.setPen(grid); p.drawLine(QPointF(X(v), r.top()), QPointF(X(v), r.bottom()))
            p.setPen(QColor(t.dim)); p.drawText(QPointF(X(v) - 18, r.bottom() + 14), f"{v:.4g}" if abs(v) < 1e4 else f"{v:.0f}")
        if self.logy:
            yt = [v for v in (1, 1.5, 2, 3, 5, 10, 20, 50, 100) if y0 <= v <= y1]
        else:
            yt, _ = _nice_ticks(y0, y1, 6)
        for v in yt:
            p.setPen(grid); p.drawLine(QPointF(r.left(), Y(v)), QPointF(r.right(), Y(v)))
            p.setPen(QColor(t.dim)); p.drawText(QPointF(6, Y(v) + 4), f"{v:.4g}")
        p.setPen(QPen(QColor(t.edge), 1)); p.drawRect(r)
        p.setPen(QColor(t.dim))
        p.drawText(QPointF(r.center().x() - 12, self.height() - 8), self.xlabel)
        p.save(); p.translate(14, r.center().y() + 20); p.rotate(-90); p.drawText(0, 0, self.ylabel); p.restore()
        for (hy, lab, ck) in self.hlines:
            if y0 <= hy <= y1:
                pen = QPen(QColor(getattr(t, ck))); pen.setStyle(Qt.DashLine); p.setPen(pen)
                p.drawLine(QPointF(r.left(), Y(hy)), QPointF(r.right(), Y(hy)))
                p.drawText(QPointF(r.right() - 36, Y(hy) - 3), lab)
        for (vx, lab, ck) in self.vlines:
            if x0 <= vx <= x1:
                pen = QPen(QColor(getattr(t, ck))); pen.setStyle(Qt.DashLine); p.setPen(pen)
                p.drawLine(QPointF(X(vx), r.top()), QPointF(X(vx), r.bottom()))
        p.setClipRect(r)
        for (name, xs, ys, ck) in self.series:
            pen = QPen(QColor(getattr(t, ck)) if hasattr(t, ck) else QColor(ck)); pen.setWidthF(2.0)
            p.setPen(pen)
            path = QPainterPath()
            first = True
            for xv, yv in zip(xs, ys):
                if not np.isfinite(yv):
                    first = True
                    continue
                pt = QPointF(X(xv), Y(yv))
                if first:
                    path.moveTo(pt); first = False
                else:
                    path.lineTo(pt)
            p.drawPath(path)
        p.setClipping(False)
        lx = r.left() + 8
        for (name, xs, ys, ck) in self.series:
            col = QColor(getattr(t, ck)) if hasattr(t, ck) else QColor(ck)
            p.setPen(col)
            p.drawText(QPointF(lx, r.top() + 14), name)
            lx += p.fontMetrics().horizontalAdvance(name) + 16
        if self._hover is not None:
            hx, hv = self._hover
            p.setPen(QColor(t.warn))
            p.drawText(QPointF(r.right() - 150, r.top() + 28), f"{hx:.4f}  ->  {hv:.3g}")

    def mouseMoveEvent(self, ev):
        if not self.series:
            return
        r = self._rect()
        x0, x1, _, _ = self._ranges()
        xv = x0 + (ev.position().x() - r.left()) / max(r.width(), 1) * (x1 - x0)
        name, xs, ys, ck = self.series[0]
        xs = np.asarray(xs, float)
        i = int(np.argmin(np.abs(xs - xv)))
        self._hover = (float(xs[i]), float(ys[i]))
        self.update()

    def leaveEvent(self, ev):
        self._hover = None
        self.update()


class GeometryView(QWidget):
    """Simple orthographic 3-D wire viewer with mouse rotation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wires = []      # (p0, p1, group)
        self.sources = []
        self.loads = []
        self.ground = False
        self.yaw = 30.0
        self.pitch = 25.0
        self.zoom = 1.0
        self._drag = None
        self.setMinimumSize(300, 300)
        self.note = ""

    def set_structure(self, st, note: str = ""):
        self.wires = []
        self.sources = []
        self.loads = []
        self.note = note
        if st is None:
            self.update()
            return
        self.ground = st.ground.kind != "free"
        for w in st.wires:
            self.wires.append((np.array(w.p0, float), np.array(w.p1, float), w.name or ""))
        for s in st.sources:
            w = st.wires[s.wire]
            self.sources.append(np.array(w.p0) + (np.array(w.p1) - np.array(w.p0)) * s.at)
        for l in st.loads:
            w = st.wires[l.wire]
            self.loads.append(np.array(w.p0) + (np.array(w.p1) - np.array(w.p0)) * l.at)
        self.update()

    def set_view(self, yaw, pitch):
        self.yaw, self.pitch = yaw, pitch
        self.update()

    def _proj(self, P):
        P = np.atleast_2d(P)
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        x1 = P[:, 0] * cy - P[:, 1] * sy
        y1 = P[:, 0] * sy + P[:, 1] * cy
        sx = x1
        sy_ = P[:, 2] * cp + y1 * sp
        return np.stack([sx, sy_], 1)

    def paintEvent(self, e):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.screen))
        p.setPen(QColor(t.dim))
        if not self.wires:
            p.drawText(self.rect(), Qt.AlignCenter, self.note or "No wire geometry (closed-form model)")
            return
        pts = np.array([w[0] for w in self.wires] + [w[1] for w in self.wires])
        if self.ground:
            c0 = pts.mean(0)
            pts = np.vstack([pts, [[c0[0], c0[1], 0.0]]])
        ctr = (pts.min(0) + pts.max(0)) / 2
        rad = max(np.linalg.norm(pts - ctr, axis=1).max(), 0.05)
        scale = 0.42 * min(self.width(), self.height()) / rad * self.zoom
        cx, cy_ = self.width() / 2, self.height() / 2

        def S(P):
            q = self._proj(np.asarray(P) - ctr)
            return [QPointF(cx + a * scale, cy_ - b * scale) for a, b in q]
        # ground grid
        if self.ground:
            ext = rad * 1.4
            gz = 0.0 - ctr[2]
            g = QPen(QColor(t.grid)); g.setWidthF(1); p.setPen(g)
            n = 8
            for i in range(-n, n + 1):
                a = i / n * ext
                P0 = np.array([ctr[0] + a, ctr[1] - ext, 0.0]); P1 = np.array([ctr[0] + a, ctr[1] + ext, 0.0])
                Q = S([P0, P1]); p.drawLine(Q[0], Q[1])
                P0 = np.array([ctr[0] - ext, ctr[1] + a, 0.0]); P1 = np.array([ctr[0] + ext, ctr[1] + a, 0.0])
                Q = S([P0, P1]); p.drawLine(Q[0], Q[1])
        if self.ground and self.sources:
            q = S([self.sources[0], np.array([self.sources[0][0], self.sources[0][1], 0.0])])
            dp = QPen(QColor(t.faint)); dp.setStyle(Qt.DotLine); p.setPen(dp)
            p.drawLine(q[0], q[1])
        groups = {}
        palette = [t.c1, t.c2, t.c3, "#d9a8ff", "#ff8fb1", "#7fe3e3", "#c8e36b", "#ffa0a0"]
        for (p0, p1, grp) in self.wires:
            col = groups.setdefault(grp, palette[len(groups) % len(palette)])
            pen = QPen(QColor(col)); pen.setWidthF(2.2)
            p.setPen(pen)
            q = S([p0, p1])
            p.drawLine(q[0], q[1])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.warn))
        for l in self.loads:
            q = S([l])[0]
            p.drawRect(QRectF(q.x() - 4, q.y() - 4, 8, 8))
        p.setBrush(QColor(t.bad))
        for s in self.sources:
            q = S([s])[0]
            p.drawEllipse(q, 5, 5)
        # axes
        ax = [("x", np.array([1.0, 0, 0])), ("y", np.array([0, 1.0, 0])), ("z", np.array([0, 0, 1.0]))]
        ox, oy = 40, self.height() - 40
        p.setPen(QColor(t.dim))
        for nm, v in ax:
            q = self._proj(v)[0]
            p.drawLine(QPointF(ox, oy), QPointF(ox + q[0] * 26, oy - q[1] * 26))
            p.drawText(QPointF(ox + q[0] * 32 - 3, oy - q[1] * 32 + 4), nm)
        ext = pts.max(0) - pts.min(0)
        p.setPen(QColor(t.dim))
        p.drawText(10, 18, f"span: x {ext[0]:.2f} m   y {ext[1]:.2f} m   z {ext[2]:.2f} m    "
                           f"({len(self.wires)} wires)   red = feed, amber = load")
        p.drawText(10, self.height() - 10 + 0, "drag to rotate, wheel to zoom, double-click to reset")

    def mousePressEvent(self, ev):
        self._drag = (ev.position().x(), ev.position().y(), self.yaw, self.pitch)

    def mouseMoveEvent(self, ev):
        if self._drag:
            x0, y0, yaw0, pit0 = self._drag
            self.yaw = yaw0 + (ev.position().x() - x0) * 0.5
            self.pitch = max(-90, min(90, pit0 + (ev.position().y() - y0) * 0.5))
            self.update()

    def mouseReleaseEvent(self, ev):
        self._drag = None

    def wheelEvent(self, ev):
        self.zoom = max(0.2, min(8.0, self.zoom * (1.12 if ev.angleDelta().y() > 0 else 1 / 1.12)))
        self.update()

    def mouseDoubleClickEvent(self, ev):
        self.yaw, self.pitch, self.zoom = 30.0, 25.0, 1.0
        self.update()
