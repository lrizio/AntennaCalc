"""Renders the screenshots used by build_user_guide.py into docs/guide/ (offscreen Qt)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "guide")
os.makedirs(OUT, exist_ok=True)

from PySide6.QtWidgets import QApplication

from antennacalc.ui.main_window import MainWindow
from antennacalc.ui.worker import DesignWorker

app = QApplication(sys.argv)
w = MainWindow()
w.resize(1500, 900)
w.show()
app.processEvents()


def design(key, setup=None):
    w.inputs.select(key)
    app.processEvents()
    if setup:
        setup(w.inputs)
    spec, req, ex, basis = w.inputs.requirements()
    wk = DesignWorker(spec, req, ex, basis)
    wk.finished_ok.connect(lambda r, e: w._done(r, e))
    wk.failed.connect(lambda m: print("FAILED", m))
    wk.run()
    app.processEvents()


FULL = {"01_main.png", "02_yagi_summary.png", "12_inputs.png"}


def shot(name, tab, crop=None):
    w.tabs.setCurrentIndex(tab)
    app.processEvents()
    pm = w.grab()
    if crop:
        pm = pm.copy(*crop)
    elif name not in FULL:
        pm = pm.copy(385, 20, pm.width() - 385, pm.height() - 40)
    pm.save(os.path.join(OUT, name))
    print("wrote", name)


T = {"summary": 0, "dims": 1, "patterns": 2, "swr": 3, "geo": 4, "surf": 5, "matching": 6, "bands": 7, "notes": 8}

design("dipole")
shot("01_main.png", T["summary"])

def yagi(i):
    i.band.setCurrentText("20 m (14.0-14.35 MHz)")
    i.gain_on.setChecked(True); i.gain.setValue(11.0)
    i.size_on.setChecked(True); i.size.setValue(18.0)
    i.height.setValue(15.0)
design("yagi", yagi)
shot("02_yagi_summary.png", T["summary"])
shot("03_patterns.png", T["patterns"])
shot("04_swr.png", T["swr"])
w.geo.set_view(35, 25)
shot("05_geometry.png", T["geo"])
shot("05b_surface.png", T["surf"])
shot("06_dimensions.png", T["dims"])
shot("12_inputs.png", T["summary"], crop=(0, 20, 400, 900))

def ocfd(i):
    i.band.setCurrentText("40 m (7.0-7.3 MHz)")
    i.height.setValue(12.0)
design("ocfd", ocfd)
shot("07_matching.png", T["matching"])
shot("08_multiband.png", T["bands"])

def lpda(i):
    pass
design("lpda", lpda)
shot("09_lpda.png", T["patterns"])
shot("09b_lpda_swr.png", T["swr"])

def dish(i):
    i.band.setCurrentText("13 cm (2300-2450 MHz)")
    i.gain_on.setChecked(True); i.gain.setValue(28.0)
design("dish", dish)
shot("10_dish.png", T["patterns"])
shot("10b_dish_dims.png", T["dims"])

def trap(i):
    i.band.setCurrentText("20 m (14.0-14.35 MHz)")
    for k, (p, wd) in i.param_widgets.items():
        if k == "b2":
            wd.setCurrentIndex(wd.findText("40 m (7.0-7.3 MHz)"))
design("trap_dipole", trap)
shot("11_trap.png", T["bands"])
shot("11b_trap_dims.png", T["dims"])

# ---- wire arrays added in v1.4.0 -------------------------------------------------------------
def _band(label):
    def f(i):
        i.band.setCurrentText(label)
    return f

def _opt(i, **kw):
    i.gain_on.setChecked(False); i.size_on.setChecked(False)      # state left over from the dish example
    for k, (p, wd) in i.param_widgets.items():
        if k in kw:
            v = kw[k]
            if hasattr(wd, "findData") and hasattr(wd, "setCurrentIndex") and not hasattr(wd, "setChecked"):
                wd.setCurrentIndex(max(wd.findData(v), 0))
            elif hasattr(wd, "setChecked"):
                wd.setChecked(bool(v))
            else:
                wd.setValue(v)

def bobtail(i):
    i.band.setCurrentText("40 m (7.0-7.3 MHz)"); _opt(i, variant="bobtail")
design("curtain", bobtail)
shot("13_bobtail_patterns.png", T["patterns"])
w.geo.set_view(35, 25)
shot("13b_bobtail_geo.png", T["geo"])

def bruce(i):
    i.band.setCurrentText("40 m (7.0-7.3 MHz)"); _opt(i, n=6)
design("bruce", bruce)
shot("14_bruce_patterns.png", T["patterns"])
w.geo.set_view(35, 25)
shot("14b_bruce_geo.png", T["geo"])

def sterba(i):
    i.band.setCurrentText("20 m (14.0-14.35 MHz)"); _opt(i, nsec=4, reflector=True)
design("sterba", sterba)
shot("15_sterba_patterns.png", T["patterns"])
w.geo.set_view(35, 25)
shot("15b_sterba_geo.png", T["geo"])

def w8jk(i):
    i.gain_on.setChecked(False); i.size_on.setChecked(False)
    i.band.setCurrentText("20 m (14.0-14.35 MHz)")
design("w8jk", w8jk)
shot("16_w8jk_patterns.png", T["patterns"])
w.geo.set_view(35, 25)
shot("16b_w8jk_geo.png", T["geo"])
print("done")
