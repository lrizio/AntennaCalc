"""Left-hand design input panel."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QLabel, QProgressBar, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import models  # noqa: F401  (registers the antenna models)
from ..common import (BANDS, BAND_BY_LABEL, COAX, COAX_LABELS, DIAMETERS, DIAM_BY_LABEL, GROUNDS, GROUND_BY_LABEL,
                      MATERIALS, TRANSFORMERS)
from ..design import CATEGORIES, REGISTRY, Requirements, Spec, specs_in

CATEGORY_ORDER = ["HF wire antennas", "Vertical antennas", "Directional beams", "Compact antennas",
                  "VHF/UHF/satellite antennas", "Microwave antennas", "Receive-only antennas"]


CUSTOM_DEFAULTS = {"lpda": (14.0, 30.0, 21.0), "discone": (100.0, 1000.0, 500.0)}


def _dspin(lo, hi, val, step=0.1, dec=2, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setValue(val)
    w.setKeyboardTracking(False)
    if suffix:
        w.setSuffix(suffix)
    w.setButtonSymbols(QDoubleSpinBox.NoButtons)
    return w


class InputPanel(QWidget):
    design_requested = Signal()
    optimise_requested = Signal()
    cancel_requested = Signal()
    spec_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spec: Spec | None = None
        self.param_widgets: dict = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        self.form_host = host
        lay = QVBoxLayout(host)
        lay.setContentsMargins(10, 8, 12, 8)
        lay.setSpacing(4)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        def section(text):
            l = QLabel(text.upper())
            l.setObjectName("section")
            lay.addWidget(l)

        # ---- antenna selection
        section("Antenna")
        self.cat = QComboBox()
        cats = [c for c in CATEGORY_ORDER if c in CATEGORIES] + [c for c in CATEGORIES if c not in CATEGORY_ORDER]
        self.cat.addItems(cats)
        self.type = QComboBox()
        self.type.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.type.setMinimumContentsLength(24)
        lay.addWidget(QLabel("Category"))
        lay.addWidget(self.cat)
        lay.addWidget(QLabel("Antenna type"))
        lay.addWidget(self.type)
        self.desc = QLabel("")
        self.desc.setObjectName("dim")
        self.desc.setWordWrap(True)
        lay.addWidget(self.desc)

        # ---- frequency
        section("Frequency")
        self.band = QComboBox()
        self.band.addItems([b[0] for b in BANDS])
        lay.addWidget(self.band)
        fl = QFormLayout()
        fl.setContentsMargins(0, 0, 0, 0)
        self.f0 = _dspin(0.05, 40000, 14.15, 0.05, 4, " MHz")
        self.flo = _dspin(0.05, 40000, 14.0, 0.05, 4, " MHz")
        self.fhi = _dspin(0.05, 40000, 14.35, 0.05, 4, " MHz")
        fl.addRow("Design frequency", self.f0)
        fl.addRow("Band start", self.flo)
        fl.addRow("Band end", self.fhi)
        lay.addLayout(fl)

        # ---- requirements
        section("Requirements")
        row = QHBoxLayout()
        self.gain_on = QCheckBox("Target gain")
        self.gain = _dspin(-30, 60, 10.0, 0.5, 1, " dBi")
        row.addWidget(self.gain_on); row.addWidget(self.gain)
        lay.addLayout(row)
        self.basis = QComboBox()
        self.basis.addItems(["Gain target is free-space gain", "Gain target includes ground reflection"])
        lay.addWidget(self.basis)
        row = QHBoxLayout()
        self.size_on = QCheckBox("Size limit")
        self.size = _dspin(0.05, 500, 10.0, 0.5, 2, " m")
        row.addWidget(self.size_on); row.addWidget(self.size)
        lay.addLayout(row)
        self.size_hint = QLabel("")
        self.size_hint.setObjectName("dim")
        lay.addWidget(self.size_hint)

        # ---- materials
        section("Materials")
        self.mat = QComboBox()
        for k, v in MATERIALS.items():
            self.mat.addItem(v[0], k)
        self.diam = QComboBox()
        for lab, mm in DIAMETERS:
            self.diam.addItem(lab, mm)
        self.diam.addItem("Custom diameter...", None)
        self.diam.setCurrentIndex(4)
        self.diam_custom = _dspin(0.05, 200, 2.0, 0.5, 2, " mm")
        self.diam_custom.setVisible(False)
        self.hollow_on = QCheckBox("Hollow tube, wall")
        self.wall = _dspin(0.1, 10, 1.0, 0.1, 2, " mm")
        lay.addWidget(self.mat)
        lay.addWidget(self.diam)
        lay.addWidget(self.diam_custom)
        row = QHBoxLayout(); row.addWidget(self.hollow_on); row.addWidget(self.wall); lay.addLayout(row)

        # ---- site
        section("Site")
        self.height_lbl = QLabel("Height above ground")
        self.height = _dspin(0.0, 500, 10.0, 0.5, 2, " m")
        self.ground = QComboBox()
        for lab, _ in GROUNDS:
            self.ground.addItem(lab)
        self.ground.setCurrentIndex(4)
        self.power = _dspin(0.01, 100000, 100.0, 10, 1, " W")
        fl2 = QFormLayout(); fl2.setContentsMargins(0, 0, 0, 0)
        fl2.addRow(self.height_lbl, self.height)
        fl2.addRow("Ground", self.ground)
        fl2.addRow("Transmit power", self.power)
        lay.addLayout(fl2)

        # ---- feed
        section("Feed system")
        self.ratio = QComboBox()
        for lab, v in TRANSFORMERS:
            self.ratio.addItem(lab, v)
        self.coax = QComboBox()
        for lab, k in COAX_LABELS:
            self.coax.addItem(lab, k)
        self.coax.setCurrentIndex(3)
        self.coax_len = _dspin(0.0, 1000, 15.0, 1, 1, " m")
        self.zref = _dspin(10, 1000, 50.0, 5, 0, " ohm")
        self.lmatch = QCheckBox("Add automatic L-match at the feedpoint")
        fl3 = QFormLayout(); fl3.setContentsMargins(0, 0, 0, 0)
        fl3.addRow("Transformer", self.ratio)
        fl3.addRow("Coax type", self.coax)
        fl3.addRow("Coax length", self.coax_len)
        fl3.addRow("System impedance", self.zref)
        lay.addLayout(fl3)
        lay.addWidget(self.lmatch)

        # ---- antenna specific options
        self.opt_box = QGroupBox("Antenna options")
        self.opt_form = QFormLayout(self.opt_box)
        lay.addWidget(self.opt_box)

        # ---- run options
        section("Calculation")
        self.quality = QComboBox()
        self.quality.addItem("Fast (12 segments / wavelength)", 12)
        self.quality.addItem("Normal (20 segments / wavelength)", 20)
        self.quality.addItem("Fine (30 segments / wavelength)", 30)
        self.quality.setCurrentIndex(1)
        self.autotune = QCheckBox("Auto-tune to resonance")
        self.autotune.setChecked(True)
        self.optimize = QCheckBox("Optimise gain / front-to-back")
        self.wide = QCheckBox("Sweep the whole HF range (1.8-30 MHz)")
        self.wide.setToolTip("Plot SWR and impedance from 1.8 to 30 MHz with the amateur bands shaded - shows harmonic and multi-band behaviour. Slower.")
        lay.addWidget(self.quality)
        lay.addWidget(self.autotune)
        lay.addWidget(self.optimize)
        lay.addWidget(self.wide)
        lay.addStretch(1)

        # ---- bottom bar (always visible)
        bar = QFrame()
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(10, 6, 12, 8)
        self.btn_design = QPushButton("DESIGN")
        self.btn_design.setObjectName("primary")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_opt = QPushButton("Optimise")
        self.btn_opt.setToolTip("Refine element lengths and spacings for gain and front-to-back (beams)")
        row = QHBoxLayout()
        row.addWidget(self.btn_design, 3)
        row.addWidget(self.btn_opt, 2)
        row.addWidget(self.btn_cancel, 2)
        bl.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.status = QLabel("Choose an antenna and press DESIGN.")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        bl.addWidget(self.progress)
        bl.addWidget(self.status)
        outer.addWidget(bar)

        # ---- wiring
        self.cat.currentTextChanged.connect(self._fill_types)
        self.type.currentIndexChanged.connect(self._type_changed)
        self.band.currentTextChanged.connect(self._band_changed)
        self.diam.currentIndexChanged.connect(lambda _: self.diam_custom.setVisible(self.diam.currentData() is None))
        self.btn_design.clicked.connect(self.design_requested)
        self.btn_cancel.clicked.connect(self.cancel_requested)
        self.btn_opt.clicked.connect(self.optimise_requested)
        self.band.setCurrentText("20 m (14.0-14.35 MHz)")
        self._fill_types(self.cat.currentText())

    # ------------------------------------------------------------------ selection
    def _fill_types(self, cat):
        self.type.blockSignals(True)
        self.type.clear()
        for s in specs_in(cat):
            self.type.addItem(s.name, s.key)
        self.type.blockSignals(False)
        self._type_changed()

    def select(self, key: str):
        spec = REGISTRY[key]
        self.cat.setCurrentText(spec.category)
        i = self.type.findData(key)
        if i >= 0:
            self.type.setCurrentIndex(i)

    def _type_changed(self, *_):
        key = self.type.currentData()
        if not key:
            return
        spec = REGISTRY[key]
        self.spec = spec
        self.desc.setText(spec.desc)
        # defaults
        self.height.setValue(spec.height_default)
        self.height_lbl.setText(spec.height_label)
        self.height.setEnabled(spec.uses_height)
        self.height_lbl.setEnabled(spec.uses_height)
        self.ground.setEnabled(spec.uses_ground)
        if spec.ground_default:
            self.ground.setCurrentText(spec.ground_default)
        elif spec.needs_ground and self.ground.currentIndex() == 0:
            self.ground.setCurrentText(GROUNDS[4][0])
        self.mat.setEnabled(spec.uses_material)
        self.diam.setEnabled(spec.uses_material)
        if spec.band_default:
            self.band.setCurrentText(spec.band_default)
        if spec.key in CUSTOM_DEFAULTS:
            lo, hi, f = CUSTOM_DEFAULTS[spec.key]
            self.flo.setValue(lo); self.fhi.setValue(hi); self.f0.setValue(f)
        self.ratio.setCurrentIndex(max(0, self.ratio.findData(spec.feed_ratio)))
        i = self.coax.findData(spec.feed_coax)
        if i >= 0:
            self.coax.setCurrentIndex(i)
        self.coax_len.setValue(spec.feed_len)
        self.lmatch.setChecked(spec.lmatch_default)
        self.size_hint.setText(spec.size_label + " (largest dimension)")
        self.gain_on.setEnabled(True)
        self.optimize.setVisible(spec.optimizable)
        self.btn_opt.setVisible(spec.optimizable)
        self.optimize.setChecked(spec.optimize_default)
        self.wide.setVisible(spec.wide_ok)
        self.wide.setChecked(spec.wide_default)
        self.autotune.setVisible(not spec.analytic)
        self.quality.setVisible(not spec.analytic)
        self._build_params(spec)
        self.spec_changed.emit(spec)

    def _build_params(self, spec: Spec):
        while self.opt_form.rowCount():
            self.opt_form.removeRow(0)
        self.param_widgets = {}
        self.opt_box.setVisible(bool(spec.params))
        for p in spec.params:
            if p.kind == "choice":
                w = QComboBox()
                for lab, val in p.choices:
                    w.addItem(lab, val)
                for i in range(w.count()):
                    if w.itemData(i) == p.default:
                        w.setCurrentIndex(i)
                        break
            elif p.kind == "int":
                w = QSpinBox()
                w.setRange(int(p.lo), int(p.hi))
                w.setValue(int(p.default))
                w.setSingleStep(int(max(p.step, 1)))
                w.setKeyboardTracking(False)
                if p.unit:
                    w.setSuffix(" " + p.unit)
            elif p.kind == "bool":
                w = QCheckBox()
                w.setChecked(bool(p.default))
            else:
                w = _dspin(p.lo, p.hi, float(p.default), p.step, p.decimals, (" " + p.unit) if p.unit else "")
            if p.tip:
                w.setToolTip(p.tip)
            lbl = QLabel(p.label)
            lbl.setWordWrap(True)
            self.opt_form.addRow(lbl, w)
            self.param_widgets[p.key] = (p, w)

    def _band_changed(self, label):
        b = BAND_BY_LABEL.get(label)
        if not b or b[3] <= 0:
            return
        self.f0.setValue(b[3])
        self.flo.setValue(b[1])
        self.fhi.setValue(b[2])

    # ------------------------------------------------------------------ read / write
    def param_values(self) -> dict:
        out = {}
        for k, (p, w) in self.param_widgets.items():
            if isinstance(w, QComboBox):
                out[k] = w.currentData()
            elif isinstance(w, QCheckBox):
                out[k] = w.isChecked()
            else:
                out[k] = w.value()
        return out

    def requirements(self):
        spec = self.spec
        mat_key = self.mat.currentData()
        mat = MATERIALS[mat_key]
        dmm = self.diam.currentData()
        if dmm is None:
            dmm = self.diam_custom.value()
        f0 = self.f0.value()
        flo, fhi = self.flo.value(), self.fhi.value()
        if fhi <= flo:
            flo, fhi = f0 * 0.98, f0 * 1.02
        g = GROUND_BY_LABEL[self.ground.currentText()]
        from ..mom import Ground
        req = Requirements(
            f_mhz=f0, f_lo=flo, f_hi=fhi, band_label=self.band.currentText(),
            target_gain=self.gain.value() if self.gain_on.isChecked() else None,
            max_size=self.size.value() if self.size_on.isChecked() else 0.0,
            radius=dmm / 2000.0, sigma=mat[1], density=mat[2], material=mat[0], diameter_mm=dmm,
            hollow_wall_mm=self.wall.value() if self.hollow_on.isChecked() else 0.0,
            height=self.height.value(), ground=Ground(g.kind, g.sigma, g.eps_r), power_w=self.power.value(),
            zref=self.zref.value(), ratio=self.ratio.currentData(), coax_key=self.coax.currentData(),
            coax_len=self.coax_len.value(), lmatch=self.lmatch.isChecked(), spw=self.quality.currentData(),
            auto_tune=self.autotune.isChecked(), optimize=self.optimize.isChecked(),
            wide_sweep=bool(spec.wide_ok and self.wide.isChecked()))
        basis = "free" if self.basis.currentIndex() == 0 else "ground"
        return spec, req, self.param_values(), basis

    def set_busy(self, busy: bool):
        self.btn_design.setEnabled(not busy)
        self.btn_opt.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)

    def set_progress(self, frac: float, text: str):
        self.progress.setValue(int(frac * 1000))
        self.status.setText(text)

    # state for save/load
    def state(self) -> dict:
        s = {"type": self.type.currentData(), "band": self.band.currentText(), "f0": self.f0.value(),
             "flo": self.flo.value(), "fhi": self.fhi.value(), "gain_on": self.gain_on.isChecked(), "gain": self.gain.value(),
             "basis": self.basis.currentIndex(), "size_on": self.size_on.isChecked(), "size": self.size.value(),
             "mat": self.mat.currentText(), "diam": self.diam.currentText(), "diam_custom": self.diam_custom.value(),
             "hollow_on": self.hollow_on.isChecked(), "wall": self.wall.value(), "height": self.height.value(),
             "ground": self.ground.currentText(), "power": self.power.value(), "ratio": self.ratio.currentIndex(),
             "coax": self.coax.currentIndex(), "coax_len": self.coax_len.value(), "zref": self.zref.value(),
             "lmatch": self.lmatch.isChecked(), "quality": self.quality.currentIndex(),
             "autotune": self.autotune.isChecked(), "optimize": self.optimize.isChecked(),
             "wide": self.wide.isChecked(), "params": {}}
        for k, (p, w) in self.param_widgets.items():
            if isinstance(w, QComboBox):
                s["params"][k] = w.currentText()
            elif isinstance(w, QCheckBox):
                s["params"][k] = w.isChecked()
            else:
                s["params"][k] = w.value()
        return s

    def set_state(self, s: dict):
        if s.get("type") in REGISTRY:
            self.select(s["type"])
        self.band.blockSignals(True)
        self.band.setCurrentText(s.get("band", self.band.currentText()))
        self.band.blockSignals(False)
        for w, k in ((self.f0, "f0"), (self.flo, "flo"), (self.fhi, "fhi"), (self.gain, "gain"), (self.size, "size"),
                     (self.diam_custom, "diam_custom"), (self.wall, "wall"), (self.height, "height"),
                     (self.power, "power"), (self.coax_len, "coax_len"), (self.zref, "zref")):
            if k in s:
                w.setValue(s[k])
        for w, k in ((self.gain_on, "gain_on"), (self.size_on, "size_on"), (self.hollow_on, "hollow_on"),
                     (self.lmatch, "lmatch"), (self.autotune, "autotune"), (self.optimize, "optimize"),
                     (self.wide, "wide")):
            if k in s:
                w.setChecked(bool(s[k]))
        for w, k in ((self.basis, "basis"), (self.ratio, "ratio"), (self.coax, "coax"), (self.quality, "quality")):
            if k in s:
                w.setCurrentIndex(int(s[k]))
        for w, k in ((self.mat, "mat"), (self.diam, "diam"), (self.ground, "ground")):
            if k in s:
                i = w.findText(s[k])
                if i >= 0:
                    w.setCurrentIndex(i)
        for k, v in s.get("params", {}).items():
            if k in self.param_widgets:
                p, w = self.param_widgets[k]
                if isinstance(w, QComboBox):
                    i = w.findText(v)
                    if i >= 0:
                        w.setCurrentIndex(i)
                elif isinstance(w, QCheckBox):
                    w.setChecked(bool(v))
                else:
                    w.setValue(v)
