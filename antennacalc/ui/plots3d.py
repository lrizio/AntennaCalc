"""Shaded 3-D looking views: tube-style wire geometry and the radiation-pattern surface."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import theme
from .plots import GeometryView


def _background(p: QPainter, w: QWidget):
    t = theme.current()
    bg = QLinearGradient(0, 0, 0, w.height())
    bg.setColorAt(0, QColor(t.screen).lighter(135))
    bg.setColorAt(1, QColor(t.screen))
    p.fillRect(w.rect(), bg)


class GeometryView3D(GeometryView):
    """Wire view with depth sorting, tube shading, ground slab, shadows and glossy feed markers."""

    def paintEvent(self, e):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        _background(p, self)
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
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))

        def S(P):
            q = self._proj(np.asarray(P) - ctr)
            return [QPointF(cx + a * scale, cy_ - b * scale) for a, b in q]

        def depth(P):
            v = np.asarray(P) - ctr
            return ((v[0] * sy + v[1] * cy) * cp - v[2] * sp) / rad

        if self.ground:
            ext = rad * 1.4
            corners = [np.array([ctr[0] + a * ext, ctr[1] + b * ext, 0.0]) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            gc = QColor(t.accent_edge); gc.setAlpha(34)
            p.setPen(QPen(QColor(t.edge), 1)); p.setBrush(gc)
            p.drawPolygon(QPolygonF(S(corners)))
            g = QPen(QColor(t.grid)); g.setWidthF(1); p.setPen(g)
            n = 8
            for i in range(-n, n + 1):
                a = i / n * ext
                q = S([np.array([ctr[0] + a, ctr[1] - ext, 0.0]), np.array([ctr[0] + a, ctr[1] + ext, 0.0])]); p.drawLine(q[0], q[1])
                q = S([np.array([ctr[0] - ext, ctr[1] + a, 0.0]), np.array([ctr[0] + ext, ctr[1] + a, 0.0])]); p.drawLine(q[0], q[1])
            sh = QPen(QColor(0, 0, 0, 90)); sh.setWidthF(4.0); sh.setCapStyle(Qt.RoundCap); p.setPen(sh)
            for (p0, p1, grp) in self.wires:
                q = S([np.array([p0[0], p0[1], 0.0]), np.array([p1[0], p1[1], 0.0])])
                p.drawLine(q[0], q[1])
            if self.sources:
                q = S([self.sources[0], np.array([self.sources[0][0], self.sources[0][1], 0.0])])
                dp = QPen(QColor(t.faint)); dp.setStyle(Qt.DotLine); p.setPen(dp)
                p.drawLine(q[0], q[1])
        groups = {}
        palette = [t.c1, t.c2, t.c3, "#d9a8ff", "#ff8fb1", "#7fe3e3", "#c8e36b", "#ffa0a0"]
        for (p0, p1, grp) in sorted(self.wires, key=lambda w: -depth((w[0] + w[1]) / 2)):
            col = QColor(groups.setdefault(grp, palette[len(groups) % len(palette)]))
            fade = max(0.55, min(1.0, 0.85 - 0.3 * depth((p0 + p1) / 2)))
            q = S([p0, p1])
            base = QColor(col)
            base.setHsv(base.hue(), base.saturation(), int(base.value() * fade))
            for width, colr in ((5.4, base.darker(300)), (3.6, base), (1.2, base.lighter(175))):
                pen = QPen(colr); pen.setWidthF(width); pen.setCapStyle(Qt.RoundCap); p.setPen(pen)
                off = QPointF(-0.9, -0.9) if width < 2 else QPointF(0, 0)
                p.drawLine(q[0] + off, q[1] + off)
        p.setPen(Qt.NoPen)
        for l in self.loads:
            q = S([l])[0]
            p.setBrush(QColor(t.warn).darker(160)); p.drawRect(QRectF(q.x() - 5, q.y() - 5, 10, 10))
            p.setBrush(QColor(t.warn)); p.drawRect(QRectF(q.x() - 4, q.y() - 4, 8, 8))
        for s_ in self.sources:
            q = S([s_])[0]
            rg = QRadialGradient(q.x() - 2, q.y() - 2, 8)
            rg.setColorAt(0, QColor("#ffd0c8")); rg.setColorAt(0.5, QColor(t.bad)); rg.setColorAt(1, QColor(t.bad).darker(220))
            p.setBrush(rg); p.drawEllipse(q, 6, 6)
        ox, oy = 40, self.height() - 40
        p.setPen(QColor(t.dim))
        for nm, v in (("x", np.array([1.0, 0, 0])), ("y", np.array([0, 1.0, 0])), ("z", np.array([0, 0, 1.0]))):
            q = self._proj(v)[0]
            p.drawLine(QPointF(ox, oy), QPointF(ox + q[0] * 26, oy - q[1] * 26))
            p.drawText(QPointF(ox + q[0] * 32 - 3, oy - q[1] * 32 + 4), nm)
        ext3 = pts.max(0) - pts.min(0)
        p.drawText(10, 18, f"span: x {ext3[0]:.2f} m   y {ext3[1]:.2f} m   z {ext3[2]:.2f} m    "
                           f"({len(self.wires)} wires)   red = feed, amber = load")
        p.drawText(10, self.height() - 10, "drag to rotate, wheel to zoom, double-click to reset")


class PatternSurface(QWidget):
    """Shaded 3-D radiation-pattern surface (radius = gain above the floor), rotatable."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.raw = None
        self.span = 40.0
        self.yaw, self.pitch, self.zoom = 30.0, 28.0, 1.0
        self._drag = None
        self.ground = False
        self.unit = "dBi"
        self.wires = []
        self.sources = []
        self.show_antenna = True
        self.setMinimumSize(300, 300)

    def set_structure(self, st):
        self.wires, self.sources = [], []
        if st is not None:
            self.wires = [(np.array(w.p0, float), np.array(w.p1, float)) for w in st.wires]
            for sc_ in st.sources:
                w = st.wires[sc_.wire]
                self.sources.append(np.array(w.p0) + (np.array(w.p1) - np.array(w.p0)) * sc_.at)
        self.update()

    def set_show_antenna(self, on):
        self.show_antenna = bool(on)
        self.update()

    @staticmethod
    def _smooth(sphere, up=3):
        """Bicubic upsampling of the dB grid (periodic in azimuth) for a smooth surface."""
        from scipy.interpolate import RectBivariateSpline
        th, ph, db = sphere
        th = np.asarray(th, float); ph = np.asarray(ph, float)
        pad = 4
        db_p = np.concatenate([db[:, -pad:], db, db[:, :pad]], axis=1)
        ph_p = np.concatenate([ph[-pad:] - 360.0, ph, ph[:pad] + 360.0])
        floor = float(db.max()) - 80.0
        spl = RectBivariateSpline(th, ph_p, np.maximum(db_p, floor), kx=3, ky=3, s=0)
        th_f = np.linspace(th[0], th[-1], (len(th) - 1) * up + 1)
        step = (ph[1] - ph[0]) / up
        ph_f = np.arange(0.0, 360.0, step)
        return th_f, ph_f, spl(th_f, ph_f)

    def set_data(self, sphere, span=40.0, ground=False, unit="dBi"):
        self.raw = sphere
        self.data = self._smooth(sphere) if sphere is not None else None
        self.span, self.ground, self.unit = span, ground, unit
        self.update()

    def set_view(self, yaw, pitch):
        self.yaw, self.pitch = yaw, pitch
        self.update()

    @staticmethod
    def _cmap(f):
        f = np.clip(np.asarray(f, float), 0, 1)
        stops = np.array([[0.10, 0.20, 0.65], [0.10, 0.65, 0.80], [0.20, 0.80, 0.35], [0.95, 0.85, 0.20], [0.90, 0.25, 0.15]])
        x = f * (len(stops) - 1)
        i = np.minimum(x.astype(int), len(stops) - 2)
        u = (x - i)[..., None]
        return stops[i] * (1 - u) + stops[i + 1] * u

    def paintEvent(self, e):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        _background(p, self)
        p.setPen(QColor(t.dim))
        if self.data is None:
            p.drawText(self.rect(), Qt.AlignCenter, "No pattern yet")
            return
        th, ph, db = self.raw if (self._drag and self.raw is not None) else self.data
        top = math.ceil(float(db.max()) / 5.0) * 5.0
        r = np.clip((db - (top - self.span)) / self.span, 0.02, 1.0)
        T, P = np.meshgrid(np.radians(th), np.radians(ph), indexing="ij")
        X = r * np.sin(T) * np.cos(P)
        Y = r * np.sin(T) * np.sin(P)
        Z = r * np.cos(T)
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        x1 = X * cy - Y * sy
        y1 = X * sy + Y * cy
        VX, VY, VZ = x1, Z * cp + y1 * sp, y1 * cp - Z * sp
        scale = 0.50 * min(self.width(), self.height()) * self.zoom
        cx = self.width() / 2
        cyy = self.height() / 2 + (0.22 if self.ground else 0.08) * self.height()

        def wrap(a):
            return np.concatenate([a, a[:, :1]], axis=1)
        VXw, VYw, VZw, rw = wrap(VX), wrap(VY), wrap(VZ), wrap(r)
        nT, nP = VXw.shape
        qi, qj = np.meshgrid(np.arange(nT - 1), np.arange(nP - 1), indexing="ij")
        qi, qj = qi.ravel(), qj.ravel()
        offs = ((0, 0), (1, 0), (1, 1), (0, 1))
        pts3 = np.stack([np.stack([VXw[qi + a, qj + b], VYw[qi + a, qj + b], VZw[qi + a, qj + b]], -1) for a, b in offs], 1)
        nrm = np.cross(pts3[:, 1] - pts3[:, 0], pts3[:, 3] - pts3[:, 0])
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        light = np.array([-0.35, 0.55, -0.75]); light /= np.linalg.norm(light)
        shade = 0.40 + 0.60 * np.abs(nrm @ light)
        fr = np.mean([rw[qi + a, qj + b] for a, b in offs], axis=0)
        rgb = self._cmap(fr) * shade[:, None]
        order = np.argsort(-pts3[:, :, 2].mean(1))

        def scr(x, y, z):
            xx = x * cy - y * sy
            yy = x * sy + y * cy
            return QPointF(cx + xx * scale, cyy - (z * cp + yy * sp) * scale)
        rp = QPen(QColor(t.grid)); rp.setWidthF(1); p.setPen(rp)
        ang = np.linspace(0, 2 * math.pi, 73)
        for frac in (0.5, 1.0):
            p.drawPolyline(QPolygonF([scr(math.cos(a) * frac, math.sin(a) * frac, 0.0) for a in ang]))
        p.setPen(QColor(t.dim))
        for lab, (ax, ay) in (("N", (0, 1.12)), ("E", (1.12, 0)), ("S", (0, -1.12)), ("W", (-1.12, 0))):
            q = scr(ax, ay, 0.0)
            p.drawText(QPointF(q.x() - 4, q.y() + 4), lab)
        ant = None
        if self.show_antenna and self.wires:
            allp = np.array([w[0] for w in self.wires] + [w[1] for w in self.wires])
            ctr = (allp.min(0) + allp.max(0)) / 2
            rr = max(np.linalg.norm(allp - ctr, axis=1).max(), 1e-6)
            k_ = 0.5 / rr                       # antenna drawn at about half the pattern radius
            ant = (ctr, k_)

            def A(pt):
                v = (np.asarray(pt) - ctr) * k_
                return v, scr(v[0], v[1], v[2])
        # back half of the surface, then the antenna, then the front half, so the antenna sits inside the lobes
        n_back = len(order) // 2 if ant else 0
        def draw_quads(idx):
            for k in idx:
                c = rgb[k]
                col = QColor(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))
                if ant:
                    col.setAlpha(170)
                p.setBrush(col)
                p.setPen(Qt.NoPen if ant else QPen(col, 0.9))
                p.drawPolygon(QPolygonF([QPointF(cx + pts3[k, m, 0] * scale, cyy - pts3[k, m, 1] * scale) for m in range(4)]))

        def draw_antenna():
            for (p0, p1) in self.wires:
                (_, a), (_, b) = A(p0), A(p1)
                for width, colr in ((5.6, QColor(0, 0, 0)), (3.4, QColor("#ffffff")), (1.4, QColor(t.accent_edge))):
                    pen = QPen(colr); pen.setWidthF(width); pen.setCapStyle(Qt.RoundCap); p.setPen(pen)
                    p.drawLine(a, b)
            p.setPen(Qt.NoPen)
            for s_ in self.sources:
                _, q = A(s_)
                p.setBrush(QColor(t.bad)); p.drawEllipse(q, 5, 5)
        if ant:
            draw_quads(order[:n_back])
            draw_antenna()
            draw_quads(order[n_back:])
        else:
            draw_quads(order)
        bx, by, bh = self.width() - 40, 40, self.height() - 120
        for i in range(60):
            c = self._cmap(1 - i / 59) * 255
            p.fillRect(QRectF(bx, by + i * bh / 60, 14, bh / 60 + 1), QColor(int(c[0]), int(c[1]), int(c[2])))
        p.setPen(QColor(t.text))
        p.drawText(QPointF(bx - 12, by - 6), f"{top:.0f} {self.unit}")
        p.drawText(QPointF(bx - 4, by + bh + 14), f"{top - self.span:.0f}")
        p.setPen(QColor(t.dim))
        p.drawText(10, 18, f"3-D pattern: distance from the centre and colour show gain ({self.span:.0f} dB range); north is +y")
        p.drawText(10, self.height() - 10, "drag to rotate, wheel to zoom, double-click to reset")

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
        self.update()

    def wheelEvent(self, ev):
        self.zoom = max(0.3, min(4.0, self.zoom * (1.1 if ev.angleDelta().y() > 0 else 1 / 1.1)))
        self.update()

    def mouseDoubleClickEvent(self, ev):
        self.yaw, self.pitch, self.zoom = 30.0, 28.0, 1.0
        self.update()
