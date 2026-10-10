"""AntennaCalc main window."""
from __future__ import annotations

import base64
import html
import json
import os
import sys

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QAction, QDesktopServices, QIcon, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (QSizePolicy, QScrollArea, QGraphicsDropShadowEffect, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QMainWindow, QMessageBox, QPushButton, QSplitter, QStatusBar, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from .. import VERSION, engine, export, report
from ..updatecheck import PAGE_URL, UpdateChecker
from ..common import fmt_len
from . import theme
from .inputs import InputPanel
from .plots import LinePlot, PolarPlot
from .plots3d import GeometryView3D, PatternSurface
from .titlebar import TitleBar
from .worker import DesignWorker

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", APP_DIR)
    return os.path.join(base, name)


class Card(QFrame):
    def __init__(self, label):
        super().__init__()
        self.setObjectName("card")
        l = QVBoxLayout(self)
        l.setContentsMargins(12, 8, 12, 8)
        l.setSpacing(0)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(14)
        sh.setOffset(0, 3)
        sh.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(sh)
        self.lab = QLabel(label)
        self.lab.setObjectName("card_label")
        self.val = QLabel("-")
        self.val.setObjectName("card_value")
        l.addWidget(self.lab)
        l.addWidget(self.val)

    def set(self, label, value, tone):
        t = theme.current()
        col = {"good": t.good, "warn": t.warn, "bad": t.bad}.get(tone, t.text)
        self.lab.setText(label)
        self.val.setText(value)
        self.val.setStyleSheet(f"color: {col}; background: transparent;")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AntennaCalc v{VERSION}")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setMouseTracking(True)
        ico = resource_path("icon.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))
        self.settings = QSettings("HamProjects", "AntennaCalc")
        avail = self.screen().availableGeometry()
        self.resize(min(1560, int(avail.width() * 0.95)), min(940, int(avail.height() * 0.93)))
        self.setMinimumSize(min(760, avail.width()), min(520, avail.height()))
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.result = None
        self.worker = None

        split = QSplitter(Qt.Horizontal)
        self.inputs = InputPanel()
        self.inputs.setMinimumWidth(300)
        self.inputs.setMaximumWidth(480)
        split.addWidget(self.inputs)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 8, 8, 4)
        head = QHBoxLayout()
        self.title_lbl = QLabel("")
        self.title_lbl.setObjectName("title")
        self.title_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.title_lbl, 1)
        rl.addLayout(head)
        cardrow = QHBoxLayout()
        self.cards = [Card("-") for _ in range(6)]
        for c in self.cards:
            cardrow.addWidget(c)
        rl.addLayout(cardrow)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        rl.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([380, 1180])
        self.setCentralWidget(split)
        # children inherit the window's resize cursor otherwise, leaving it stuck as a double arrow
        split.setCursor(Qt.ArrowCursor)

        self._build_tabs()
        self._build_menu()
        self.titlebar = TitleBar(self, f"AntennaCalc v{VERSION}", ico if os.path.exists(ico) else None)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self.titlebar)
        hl.addWidget(self.menuBar())
        self.setMenuWidget(holder)
        holder.setCursor(Qt.ArrowCursor)
        self.setContentsMargins(5, 5, 5, 5)
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.setCursor(Qt.ArrowCursor)
        self.ver_lbl = QLabel(f"AntennaCalc v{VERSION}  |  built-in thin-wire moment-method engine")
        self.ver_lbl.setObjectName("footer")
        sb.addPermanentWidget(self.ver_lbl)
        self.update_btn = QPushButton("")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setStyleSheet("color: #ffbf5f; font-weight: 700; border: 0; background: transparent; padding: 0 8px;")
        self.update_btn.hide()
        sb.addPermanentWidget(self.update_btn)
        self._update_url = PAGE_URL
        self.update_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._update_url)))
        self.updater = UpdateChecker(VERSION, self)
        self.updater.found.connect(self._update_found)
        if self.settings.value("check_updates", True, type=bool):    # one quiet look at GitHub after start
            QTimer.singleShot(4000, self.updater.start)

        self.inputs.design_requested.connect(lambda: self.start_design(False))
        self.inputs.cancel_requested.connect(self.cancel)
        self.inputs.optimise_requested.connect(self.start_optimise)
        self.inputs.spec_changed.connect(self._spec_changed)
        self.inputs.select("dipole")
        self._spec_changed(self.inputs.spec)
        self._apply_theme(self.settings.value("theme", "SHACK"))
        self.show_welcome()

    # ------------------------------------------------------------------ tabs
    def _page(self, w, title):
        """Add a tab page inside a scroll area so the window can shrink below the page's natural size."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(w)
        self.tabs.addTab(sa, title)

    def _build_tabs(self):
        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(True)
        self.tabs.addTab(self.summary, "Summary")

        dim = QWidget(); dl = QVBoxLayout(dim)
        self.dim_table = QTableWidget(0, 5)
        self.dim_table.setHorizontalHeaderLabels(["Item", "Qty", "Length (m)", "Length (ft / in)", "Note"])
        self.dim_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.dim_table.setAlternatingRowColors(True)
        self.dim_table.verticalHeader().setVisible(False)
        self.dim_table.setEditTriggers(QTableWidget.NoEditTriggers)
        dl.addWidget(self.dim_table, 1)
        self.dim_foot = QLabel("")
        self.dim_foot.setWordWrap(True)
        dl.addWidget(self.dim_foot)
        row = QHBoxLayout()
        b1 = QPushButton("Export cut list (CSV)...")
        b1.clicked.connect(self.export_cutlist)
        b2 = QPushButton("Copy to clipboard")
        b2.clicked.connect(self.copy_cutlist)
        row.addWidget(b1); row.addWidget(b2); row.addStretch(1)
        dl.addLayout(row)
        self._page(dim, "Dimensions")

        pat = QWidget(); pl = QVBoxLayout(pat)
        row = QHBoxLayout()
        row.addWidget(QLabel("Show"))
        self.comp = QComboBox()
        for lab, k in (("Total", "total"), ("Vertical component", "vertical"), ("Horizontal component", "horizontal"),
                       ("Right-hand circular", "rhcp"), ("Left-hand circular", "lhcp")):
            self.comp.addItem(lab, k)
        self.comp.currentIndexChanged.connect(self._update_patterns)
        self.overlay = QCheckBox("overlay other polarisations")
        self.overlay.stateChanged.connect(self._update_patterns)
        row.addWidget(self.comp); row.addWidget(self.overlay); row.addStretch(1)
        self.span = QComboBox()
        for s in (20, 30, 40, 60):
            self.span.addItem(f"{s} dB scale", s)
        self.span.setCurrentIndex(2)
        self.span.currentIndexChanged.connect(self._update_patterns)
        self.span.currentIndexChanged.connect(lambda _: self.result and self._update_surface(self.result))
        row.addWidget(self.span)
        pl.addLayout(row)
        prow = QHBoxLayout()
        self.az_plot = PolarPlot("az")
        self.el_plot = PolarPlot("el")
        prow.addWidget(self.az_plot, 1); prow.addWidget(self.el_plot, 1)
        pl.addLayout(prow, 1)
        self.pat_info = QLabel("")
        self.pat_info.setObjectName("dim")
        self.pat_info.setWordWrap(True)
        pl.addWidget(self.pat_info)
        self._page(pat, "Patterns")

        swr = QWidget(); sl = QVBoxLayout(swr)
        row = QHBoxLayout()
        row.addWidget(QLabel("SWR measured at"))
        self.swr_at = QComboBox()
        self.swr_at.addItem("coax input (transmitter end)", "rig")
        self.swr_at.addItem("feedpoint after matching", "feed")
        self.swr_at.addItem("on the feeder line / antenna", "line")
        self.swr_at.currentIndexChanged.connect(self._update_swr)
        row.addWidget(self.swr_at)
        b = QPushButton("Export sweep (CSV)...")
        b.clicked.connect(self.export_sweep)
        row.addStretch(1); row.addWidget(b)
        sl.addLayout(row)
        self.swr_plot = LinePlot("SWR", "MHz", "SWR (x:1)")
        self.z_plot = LinePlot("Impedance at the feedpoint", "MHz", "ohm")
        sl.addWidget(self.swr_plot, 1)
        sl.addWidget(self.z_plot, 1)
        self._page(swr, "SWR / Impedance")

        geo = QWidget(); gl = QVBoxLayout(geo)
        row = QHBoxLayout()
        self.geo = GeometryView3D()
        for lab, yaw, pit in (("Isometric", 30, 25), ("Top", 0, 90), ("Side", 0, 0), ("Front", 90, 0)):
            b = QPushButton(lab)
            b.clicked.connect(lambda _=False, y=yaw, p=pit: self.geo.set_view(y, p))
            row.addWidget(b)
        row.addStretch(1)
        gl.addLayout(row)
        gl.addWidget(self.geo, 1)
        self._page(geo, "Geometry")

        surf = QWidget()
        sfl = QVBoxLayout(surf)
        row = QHBoxLayout()
        self.surface = PatternSurface()
        for lab, yaw, pit in (("Oblique", 30, 28), ("Top", 0, 90), ("Side", 0, 0), ("Front", 90, 0)):
            b = QPushButton(lab)
            b.clicked.connect(lambda _=False, y=yaw, pp=pit: self.surface.set_view(y, pp))
            row.addWidget(b)
        self.show_ant = QCheckBox("show antenna in the pattern")
        self.show_ant.setChecked(True)
        self.show_ant.stateChanged.connect(lambda _: self.surface.set_show_antenna(self.show_ant.isChecked()))
        row.addWidget(self.show_ant)
        row.addStretch(1)
        sfl.addLayout(row)
        sfl.addWidget(self.surface, 1)
        self._page(surf, "3D Pattern")

        self.matching = QTextBrowser()
        self.tabs.addTab(self.matching, "Matching")
        bands = QWidget(); bl = QVBoxLayout(bands)
        self.band_table = QTableWidget(0, 6)
        self.band_table.setHorizontalHeaderLabels(["Band", "MHz", "Feed impedance", "SWR", "Gain (dBi)", "Take-off (deg)"])
        self.band_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.band_table.setAlternatingRowColors(True)
        self.band_note = QLabel("")
        self.band_note.setObjectName("dim")
        self.band_note.setWordWrap(True)
        bl.addWidget(self.band_table, 1); bl.addWidget(self.band_note)
        self._page(bands, "Multi-band")
        self.notes = QTextBrowser()
        self.tabs.addTab(self.notes, "Notes")

    def _build_menu(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        for text, fn, key in (("Open design...", self.open_design, "Ctrl+O"), ("Save design...", self.save_design, "Ctrl+S"),
                              (None, None, None),
                              ("Export report (PDF)...", self.export_pdf, "Ctrl+P"),
                              ("Export NEC-2 deck...", self.export_nec, None),
                              ("Export cut list (CSV)...", self.export_cutlist, None),
                              ("Export sweep (CSV)...", self.export_sweep, None),
                              (None, None, None),
                              ("Quit", self.close, "Ctrl+Q")):
            if text is None:
                f.addSeparator(); continue
            a = QAction(text, self)
            if key:
                a.setShortcut(key)
            a.triggered.connect(fn)
            f.addAction(a)
        d = mb.addMenu("&Design")
        a = QAction("Design", self); a.setShortcut("F5"); a.triggered.connect(lambda: self.start_design(False)); d.addAction(a)
        a = QAction("Optimise (beams)", self); a.setShortcut("F6"); a.triggered.connect(self.start_optimise); d.addAction(a)
        v = mb.addMenu("&View")
        for name in theme.THEMES:
            a = QAction(f"{name.title()} theme", self)
            a.triggered.connect(lambda _=False, n=name: self._apply_theme(n))
            v.addAction(a)
        h = mb.addMenu("&Help")
        a = QAction("User guide (PDF)", self); a.setShortcut("F1"); a.triggered.connect(self.open_guide); h.addAction(a)
        a = QAction("Check for updates when the program starts", self); a.setCheckable(True)
        a.setChecked(self.settings.value("check_updates", True, type=bool))
        a.toggled.connect(lambda on: self.settings.setValue("check_updates", on))
        a.setToolTip("Looks on GitHub for a newer release (one small request, nothing is downloaded).")
        h.addAction(a)
        a = QAction("About AntennaCalc", self); a.triggered.connect(self.about); h.addAction(a)

    # ------------------------------------------------------------------ theme
    def _apply_theme(self, name):
        t = theme.set_current(name)
        QApplication.instance().setStyleSheet(theme.stylesheet(t))
        self.settings.setValue("theme", name)
        if self.result is not None:
            self.show_result(self.result)
        else:
            self.show_welcome()
        for w in (self.az_plot, self.el_plot, self.swr_plot, self.z_plot, self.geo, self.surface):
            w.update()

    def _css(self):
        t = theme.current()
        return (f"<style>body{{color:{t.text}; font-family:'Segoe UI'; font-size:13px}} h3{{color:{t.accent_edge}}} "
                f"h2{{color:{t.accent_edge}}} table{{border-collapse:collapse}} td,th{{padding:3px 10px;border-bottom:1px solid {t.edge}}} "
                f"th{{text-align:left;color:{t.dim}}} .good{{color:{t.good}}} .warn{{color:{t.warn}}} .bad{{color:{t.bad}}} "
                f".dim{{color:{t.dim}}}</style>")

    def show_welcome(self):
        self.summary.setHtml(self._css() + f"""
        <h2>AntennaCalc</h2>
        <p>Design amateur-radio antennas to your requirements. Pick an antenna type, band, size and material on the left,
        then press <b>DESIGN</b> (F5).</p>
        <ul><li><b>51 antenna designs</b> covering wires, verticals, beams, compact and loaded antennas, VHF/UHF/satellite,
        microwave and receive-only types.</li>
        <li>Wire antennas are simulated with a built-in thin-wire moment-method solver: real impedance, SWR sweep, gain, pattern and ground effects.</li>
        <li>Set a <b>target gain</b> and <b>size limit</b> and beams choose their element count for you.</li>
        <li>Results: cut list, patterns, SWR, matching network values, multi-band table, and an NEC-2 deck export.</li></ul>
        <p class='dim'>Version {VERSION}.</p>""")
        for c in self.cards:
            c.set("-", "-", "text")

    def _spec_changed(self, spec):
        self.title_lbl.setText(spec.name if spec else "AntennaCalc")

    # ------------------------------------------------------------------ run
    def start_design(self, optimise_only=False):
        if self.worker is not None:
            return
        spec, req, ex, basis = self.inputs.requirements()
        if optimise_only and not spec.optimizable:
            self.inputs.set_progress(0, "This antenna has no optimiser; it is designed directly.")
            return
        self.worker = DesignWorker(spec, req, ex, basis, scales=(self.result.scales if (optimise_only and self.result) else None),
                                   optimise_only=optimise_only)
        self.worker.progress.connect(self.inputs.set_progress)
        self.worker.finished_ok.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.inputs.set_busy(True)
        self.inputs.set_progress(0.0, "Starting...")
        self.worker.start()

    def start_optimise(self):
        self.start_design(optimise_only=True)

    def cancel(self):
        if self.worker:
            self.worker.cancel()

    def _finish_worker(self):
        w = self.worker
        self.worker = None
        self.inputs.set_busy(False)
        if w:
            w.wait(2000)

    def _failed(self, msg):
        self._finish_worker()
        self.inputs.set_progress(0.0, msg.split("\n")[0])
        if not msg.startswith("Cancelled"):
            QMessageBox.warning(self, "AntennaCalc", msg)

    def _done(self, res, ex):
        self._finish_worker()
        # reflect the automatically chosen size in the option widgets
        for k, v in ex.items():
            if k in self.inputs.param_widgets:
                p, w = self.inputs.param_widgets[k]
                if hasattr(w, "setValue") and not isinstance(w, QComboBox):
                    w.blockSignals(True); w.setValue(v); w.blockSignals(False)
        self.result = res
        self.inputs.set_progress(1.0, "Done.")
        self.show_result(res)

    # ------------------------------------------------------------------ display
    def show_result(self, res):
        spec = res.spec or self.inputs.spec
        m = res.metrics
        d = res.design
        self.title_lbl.setText(d.title)
        cards = report.metric_cards(res, spec)
        for c, (lab, val, tone) in zip(self.cards, cards):
            c.set(lab, val, tone)
        for c in self.cards[len(cards):]:
            c.set("", "", "text")
        self._show_summary(res, spec)
        self._show_dims(res)
        self._update_patterns()
        self._update_swr()
        self._update_surface(res)
        self.surface.set_structure(res.design.structure)
        self.geo.set_structure(d.structure, "Closed-form model: there is no wire geometry to draw." if d.structure is None else "")
        self.matching.setHtml(self._css() + report.matching_html(res))
        self._show_bands(res)
        self.notes.setHtml(self._css() + report.notes_html(res, spec))

    def _show_summary(self, res, spec):
        chk = report.requirement_checks(res, spec)
        parts = [self._css(), f"<h2>{html.escape(res.design.title)}</h2>"]
        parts.append("<table>")
        for a, ok, b in chk:
            parts.append(f"<tr><td class='{'good' if ok else 'bad'}'><b>{'PASS' if ok else 'FAIL'}</b></td><td>{html.escape(a)}</td><td class='dim'>{html.escape(b)}</td></tr>")
        parts.append("</table><br><table>")
        for a, b in report.summary_table(res, spec):
            parts.append(f"<tr><th>{html.escape(a)}</th><td>{html.escape(b)}</td></tr>")
        parts.append("</table>")
        if res.design.warnings:
            parts.append("<h3 class='warn'>Warnings</h3><ul>" + "".join(f"<li class='warn'>{html.escape(w)}</li>" for w in res.design.warnings) + "</ul>")
        self.summary.setHtml("".join(parts))

    def _show_dims(self, res):
        d = res.design
        t = self.dim_table
        t.setRowCount(len(d.dims))
        for r, x in enumerate(d.dims):
            vals = [x.item, str(x.qty), f"{x.length_m:.4f}" if x.length_m else "", fmt_len(x.length_m).split("(")[1].rstrip(")") if x.length_m else "", x.note]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (1, 2):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        mk = report.mass_kg(res)
        txt = f"Conductor: {res.req.material}, {res.req.diameter_mm:.2f} mm"
        if res.req.hollow_wall_mm > 0:
            txt += f" tube, {res.req.hollow_wall_mm:.1f} mm wall"
        if d.structure is not None:
            txt += f"   |   total wire {d.total_wire_m():.1f} m ({d.total_wire_m() / 0.3048:.0f} ft)   |   about {mk:.2f} kg"
        txt += "   |   Lengths are tip to tip along the conductor; add a few centimetres for wrapping at insulators, and trim to the SWR minimum."
        self.dim_foot.setText(txt)

    def _update_patterns(self, *_):
        res = self.result
        if not res or not res.pattern:
            return
        p = res.pattern
        d = res.design
        key = self.comp.currentData()
        head = "rhcp" if d.cp == "R" else "lhcp" if d.cp == "L" else "total"
        if self.sender() is None or not isinstance(self.sender(), (QComboBox, QCheckBox)):
            self.comp.blockSignals(True)
            self.comp.setCurrentIndex(self.comp.findData(head))
            self.comp.blockSignals(False)
            key = head
        gnd = d.structure is not None and d.structure.ground.kind != "free" or (d.analytic is not None and d.analytic.upper_only)
        for plot, ang, db, title in ((self.az_plot, p.az_ang, p.az_db, f"Azimuth at {p.takeoff:.0f} deg elevation"),
                                     (self.el_plot, p.el_ang, p.el_db, f"Elevation plane through bearing {p.peak_bearing:.0f} deg")):
            series = {key: db[key]}
            if self.overlay.isChecked():
                for k in ("vertical", "horizontal"):
                    if k != key:
                        series[k] = db[k]
            plot.span = float(self.span.currentData())
            plot.set_data(ang, series, key, title, ground=gnd, unit="dBic" if key in ("rhcp", "lhcp") else "dBi")
        pk = p.comp_peak
        self.pat_info.setText(
            f"Peak total {pk['total']:.1f} dBi  |  vertical {pk['vertical']:.1f}  horizontal {pk['horizontal']:.1f}  "
            f"RHCP {pk['rhcp']:.1f}  LHCP {pk['lhcp']:.1f} dB   |   polarisation: {p.pol}   |   take-off {p.takeoff:.0f} deg   |   "
            "hover the plots to read values")

    def _update_surface(self, res):
        p = res.pattern
        if p is None or p.sphere is None:
            self.surface.set_data(None)
            return
        d = res.design
        gnd = (d.structure is not None and d.structure.ground.kind != "free") or (d.analytic is not None and d.analytic.upper_only)
        self.surface.set_data(p.sphere, span=float(self.span.currentData()), ground=gnd, unit="dBic" if d.cp else "dBi")

    def _update_swr(self, *_):
        res = self.result
        if not res:
            return
        mode = self.swr_at.currentData()
        sw = {"rig": res.swr_rig, "feed": res.swr_feed, "line": res.swr_line}[mode]
        req = res.req
        sw = np.clip(sw, 1.0, 20.0)
        band = (req.f_lo, req.f_hi) if req.f_hi > req.f_lo else None
        if res.design.shade_bands:
            band = list(res.design.shade_bands)
        self.swr_plot.set_series([("SWR", res.f, sw, "c1")], vlines=[(req.f_mhz, "f0", "good")],
                                 hlines=[(2.0, "2:1", "warn"), (1.5, "1.5:1", "good")], band=band, ylim=(1.0, 10.0), logy=True)
        z = res.zfeed
        self.z_plot.set_series([("R", res.f, z.real, "c3"), ("X", res.f, z.imag, "c2")],
                               vlines=[(req.f_mhz, "f0", "good")], hlines=[(0.0, "0", "dim"), (req.zref, "Z0", "dim")], band=band)

    def _show_bands(self, res):
        rows = report.bands_rows(res) if res.bands else []
        t = self.band_table
        t.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                it = QTableWidgetItem(v)
                try:
                    if c == 3 and float(v) > 2.0:
                        it.setForeground(Qt.red)
                except ValueError:
                    pass
                t.setItem(r, c, it)
        if not rows:
            self.band_note.setText("This antenna is a single-band design - there is no multi-band table.")
        else:
            self.band_note.setText("Performance at the centre of each band the antenna can work on, using the same dimensions (no re-tuning). SWR is at the coax input; antennas with a tuner need it for the poorer bands.")

    # ------------------------------------------------------------------ files
    def _need(self):
        if self.result is None:
            QMessageBox.information(self, "AntennaCalc", "Run a design first.")
            return False
        return True

    def save_design(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save design", "", "AntennaCalc design (*.antcalc);;JSON (*.json)")
        if not path:
            return
        data = {"app": "AntennaCalc", "version": VERSION, "state": self.inputs.state(),
                "scales": (self.result.scales if self.result else {})}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        self.statusBar().showMessage(f"Saved {path}", 4000)

    def open_design(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open design", "", "AntennaCalc design (*.antcalc *.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.inputs.set_state(data["state"])
            self.inputs.set_progress(0, "Design loaded. Press DESIGN to calculate.")
        except Exception as e:
            QMessageBox.warning(self, "AntennaCalc", f"Could not open the design: {e}")

    def export_cutlist(self):
        if not self._need():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export cut list", "cutlist.csv", "CSV (*.csv)")
        if path:
            export.cutlist_csv(self.result, path)

    def copy_cutlist(self):
        if not self._need():
            return
        lines = ["Item\tQty\tLength (m)\tNote"] + [f"{x.item}\t{x.qty}\t{x.length_m:.4f}\t{x.note}" if x.length_m else f"{x.item}\t{x.qty}\t\t{x.note}" for x in self.result.design.dims]
        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage("Cut list copied.", 3000)

    def export_sweep(self):
        if not self._need():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export sweep", "sweep.csv", "CSV (*.csv)")
        if path:
            export.sweep_csv(self.result, path)

    def export_nec(self):
        if not self._need():
            return
        try:
            deck = export.nec_deck(self.result)
        except Exception as e:
            QMessageBox.information(self, "AntennaCalc", str(e))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export NEC-2 deck", "antenna.nec", "NEC deck (*.nec)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(deck)

    def _png_b64(self, widget) -> str:
        pm = widget.grab()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pm.save(buf, "PNG")
        return base64.b64encode(bytes(ba)).decode("ascii")

    def export_pdf(self):
        if not self._need():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export report", "AntennaCalc report.pdf", "PDF (*.pdf)")
        if not path:
            return
        res = self.result
        imgs = {}
        self._update_patterns()
        imgs["Azimuth pattern"] = self._png_b64(self.az_plot)
        imgs["Elevation pattern"] = self._png_b64(self.el_plot)
        imgs["SWR"] = self._png_b64(self.swr_plot)
        if res.design.structure is not None:
            imgs["Geometry"] = self._png_b64(self.geo)
        html_ = report.full_report_html(res, res.spec or self.inputs.spec, imgs)
        doc = QTextDocument()
        doc.setHtml(html_)
        w = QPdfWriter(path)
        w.setPageSize(QPageSize(QPageSize.A4))
        w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
        doc.print_(w)
        self.statusBar().showMessage(f"Report written to {path}", 5000)

    # ------------------------------------------------------------------ help
    def open_guide(self):
        for name in ("AntennaCalc User Guide.pdf", os.path.join("build", "AntennaCalc User Guide.pdf"), os.path.join("docs", "AntennaCalc User Guide.pdf")):
            p = resource_path(name)
            if os.path.exists(p):
                QDesktopServices.openUrl(QUrl.fromLocalFile(p))
                return
        QMessageBox.information(self, "AntennaCalc", "The user guide PDF was not found next to the program.")

    def _update_found(self, version, url):
        self._update_url = url
        self.update_btn.setText(f"UPDATE v{version} AVAILABLE")
        self.update_btn.setToolTip("A newer AntennaCalc is on GitHub. Click to open the download page.")
        self.update_btn.show()

    def about(self):
        QMessageBox.about(self, "About AntennaCalc",
                          f"<b>AntennaCalc v{VERSION}</b><br>Amateur radio antenna design and simulation.<br><br>"
                          "Wire antennas are solved with a built-in thin-wire method-of-moments engine "
                          "(mixed-potential EFIE, rooftop basis, image ground). Microwave antennas use closed-form models.<br><br>"
                          "Results are engineering estimates: always trim on an antenna analyser.")

    # ---- frameless window: edge resize and maximise handling
    def _edges(self, pos):
        m = 6
        e = Qt.Edges()
        if pos.x() <= m: e |= Qt.LeftEdge
        if pos.x() >= self.width() - m: e |= Qt.RightEdge
        if pos.y() <= m: e |= Qt.TopEdge
        if pos.y() >= self.height() - m: e |= Qt.BottomEdge
        return e

    def mouseMoveEvent(self, ev):
        e = self._edges(ev.position().toPoint()) if not self.isMaximized() else Qt.Edges()
        if e in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif e in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif e & (Qt.LeftEdge | Qt.RightEdge):
            self.setCursor(Qt.SizeHorCursor)
        elif e & (Qt.TopEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()

    def leaveEvent(self, ev):
        self.unsetCursor()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and not self.isMaximized():
            e = self._edges(ev.position().toPoint())
            if e and self.windowHandle():
                self.windowHandle().startSystemResize(e)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if hasattr(self, "titlebar"):
            self.titlebar.sync()
            m = 0 if self.isMaximized() else 5
            self.setContentsMargins(m, m, m, m)

    def closeEvent(self, ev):
        self.settings.setValue("geometry", self.saveGeometry())
        if self.worker:
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(ev)
