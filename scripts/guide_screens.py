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
# Guide screenshots use the light DAYLIGHT theme: the dark SHACK theme is hard to read in the PDF.
# Set it directly rather than with w._apply_theme(), which would also save it as the user's own theme setting.
from antennacalc.ui import theme
app.setStyleSheet(theme.stylesheet(theme.set_current("DAYLIGHT")))
w.inputs._fit_width()
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


# ---- Wire Editor (v1.6.0) -----------------------------------------------------------------------
def editor_shots():
    from antennacalc.custom import CLoad, CSource, CDim, Drawing
    from antennacalc.ui.wire_editor import LoadDialog

    def setup(i):
        i.band.setCurrentText("40 m (7.0-7.3 MHz)")
        i.gain_on.setChecked(False); i.size_on.setChecked(False)
    w.inputs.select("custom")
    setup(w.inputs)
    dr = Drawing(name="40 m shortened dipole")
    a = dr.add_wire((-6, 0, 10), (0, 0, 10), "Left leg")
    b = dr.add_wire((0, 0, 10), (6, 0, 10), "Right leg")
    dr.sources.append(CSource(dr.new_id(), a.id, 1.0, label="S1"))
    dr.loads.append(CLoad(dr.new_id(), a.id, 0.5, "series", r=3, l_uh=15.6, label="Coil L"))
    dr.loads.append(CLoad(dr.new_id(), b.id, 0.5, "series", r=3, l_uh=15.6, label="Coil R"))
    dr.dims.append(CDim(dr.new_id(), [a.id, 0], [b.id, 1], 0.6, "Span"))
    ed = w.editor
    ed.set_drawing(dr.to_dict())
    ed.grid.setCurrentIndex(ed.grid.findData(1.0))
    w.tabs.setCurrentWidget(w.editor_page)
    app.processEvents()
    ed.canvas.fit()
    ed.select(dr.loads[0].id)
    ed.side.setCurrentWidget(ed.t_wires)
    app.processEvents()
    pm = w.grab()
    pm.copy(385, 20, pm.width() - 385, pm.height() - 40).save(os.path.join(OUT, "19_editor.png"))
    print("wrote 19_editor.png")
    ed.side.setCurrentWidget(ed.t_load)
    app.processEvents()
    pm = ed.side.grab()
    pm.copy(0, 0, pm.width(), min(pm.height(), 130)).save(os.path.join(OUT, "19c_editor_loads.png"))
    print("wrote 19c_editor_loads.png")
    dlg = LoadDialog(dr.loads[0], a.length(), w)
    dlg.show(); app.processEvents()
    dlg.grab().save(os.path.join(OUT, "19b_load_dialog.png"))
    dlg.close()
    print("wrote 19b_load_dialog.png")
    # rubber band while drawing a wire, in a fresh empty drawing
    ed.set_drawing({"name": "Drawing", "wires": []})
    ed.grid.setCurrentIndex(ed.grid.findData(0.5))
    cv = ed.canvas
    from PySide6.QtCore import QPointF
    cv.k = 34.0; cv.off = QPointF(cv.width() / 2, cv.height() - 70); cv._fitted = True
    ed.drawing.add_wire((-5, 0, 6), (0, 0, 9), "W1")
    ed.refresh()
    ed.set_tool("wire")
    import numpy as np
    cv.wire_start = np.array([0.0, 0, 9]); cv.cursor3 = np.array([5.0, 0, 6])
    app.processEvents()
    cv.grab().save(os.path.join(OUT, "19d_drawing.png"))
    print("wrote 19d_drawing.png")
    ed.set_tool("select")
    # analyse the shortened dipole
    ed.set_drawing(dr.to_dict())
    spec, req, ex, basis = w.inputs.requirements()
    ex["drawing"] = ed.drawing.to_dict()
    wk = DesignWorker(spec, req, ex, basis)
    wk.finished_ok.connect(lambda r, e: w._done(r, e))
    wk.failed.connect(lambda m: print("FAILED", m))
    wk.run()
    app.processEvents()
    shot("19e_editor_summary.png", T["summary"])
    shot("19f_editor_swr.png", T["swr"])


def feed_shots():
    from antennacalc.custom import CSource, Drawing
    from PySide6.QtWidgets import QScrollArea
    ip = w.inputs
    ip.select("custom")
    ip.band.setCurrentText("40 m (7.0-7.3 MHz)")
    ip.gain_on.setChecked(False); ip.size_on.setChecked(False)
    dr = Drawing(name="40 m doublet, 2 x 20 m")
    a = dr.add_wire((-20, 0, 10), (0, 0, 10), "Left"); dr.add_wire((0, 0, 10), (20, 0, 10), "Right")
    dr.sources.append(CSource(dr.new_id(), a.id, 1.0, label="Feed"))
    w.editor.set_drawing(dr.to_dict())
    ip.feeder.setCurrentIndex(ip.feeder.findData("ladder450")); ip.feeder_len.setValue(20)
    ip.balun_type.setCurrentIndex(ip.balun_type.findData("current"))
    ip.ratio.setCurrentIndex(ip.ratio.findData(9.0)); ip.balun_loss.setValue(0.3)
    ip.coax.setCurrentIndex(ip.coax.findData("rg213")); ip.coax_len.setValue(10)
    ip.tuner.setCurrentIndex(ip.tuner.findData("rig10"))
    spec, req, ex, basis = ip.requirements()
    ex["drawing"] = w.editor.drawing.to_dict()
    wk = DesignWorker(spec, req, ex, basis)
    wk.finished_ok.connect(lambda r, e: w._done(r, e))
    wk.failed.connect(lambda m: print("FAILED", m))
    wk.run()
    app.processEvents()
    sa = ip.findChild(QScrollArea)
    sa.ensureWidgetVisible(ip.cm_grounded, 10, 10)
    app.processEvents()
    top = ip.feeder.mapTo(ip, ip.feeder.rect().topLeft()).y() - 40
    bot = ip.cm_grounded.mapTo(ip, ip.cm_grounded.rect().bottomLeft()).y() + 8
    ip.grab().copy(0, max(top, 0), ip.width() - 22, bot - max(top, 0)).save(os.path.join(OUT, "20_feed_panel.png"))
    print("wrote 20_feed_panel.png")
    w.tabs.setCurrentWidget(w.matching)
    app.processEvents()
    pm = w.grab()
    pm.copy(w.matching.mapTo(w, w.matching.rect().topLeft()).x(), 80, pm.width() - 420, 520).save(os.path.join(OUT, "20b_feed_system.png"))
    print("wrote 20b_feed_system.png")
    w.tabs.setCurrentIndex(T["geo"])
    w.geo.set_view(-55, 20)
    app.processEvents()
    w.geo.grab().save(os.path.join(OUT, "20c_feed_geometry.png"))
    print("wrote 20c_feed_geometry.png")
    ip.feeder.setCurrentIndex(0); ip.balun_loss.setValue(0.0); ip.tuner.setCurrentIndex(0)


def copy_menu_shot():
    """Design menu open on 'Copy this design into the Wire Editor', drawn under the window's menu bar."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPainter, QPixmap
    design("loaded_dipole", lambda i: i.band.setCurrentText("40 m (7.0-7.3 MHz)"))
    w.tabs.setCurrentIndex(T["summary"])
    app.processEvents()
    from PySide6.QtWidgets import QMenuBar
    mb = w.menuWidget().findChild(QMenuBar)            # the menu bar sits under the custom title bar
    dm = next(a for a in mb.actions() if a.text().replace("&", "") == "Design")
    menu = dm.menu()
    item = next(a for a in menu.actions() if a.text().startswith("Copy this design"))
    mb.setActiveAction(dm)                              # Design title shown pressed
    r = mb.actionGeometry(dm)
    menu.popup(mb.mapToGlobal(r.bottomLeft()))
    menu.setActiveAction(item)                          # the new item highlighted
    app.processEvents()
    win, mp = w.grab(), menu.grab()
    o = mb.mapTo(w, QPoint(r.left(), r.bottom() + 1))
    width = min(win.width(), max(o.x() + mp.width() + 260, 720))
    height = o.y() + mp.height() + 30
    pm = QPixmap(width, height)
    p = QPainter(pm)
    p.drawPixmap(0, 0, win, 0, 0, width, height)
    p.drawPixmap(o.x(), o.y(), mp)
    p.end()
    menu.hide(); mb.setActiveAction(None)
    pm.save(os.path.join(OUT, "19g_copy_menu.png"))
    print("wrote 19g_copy_menu.png")


if "--copy-menu-only" in sys.argv:
    copy_menu_shot()
    sys.exit(0)
if "--editor-only" in sys.argv:
    editor_shots()
    sys.exit(0)
if "--feed-only" in sys.argv:
    feed_shots()
    sys.exit(0)

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

# ---- EFHW wide sweep and delta loop (v1.5.0) ----------------------------------------------------
def efhw80(i):
    i.gain_on.setChecked(False); i.size_on.setChecked(False)
    i.band.setCurrentText("80 m (3.5-4.0 MHz)")
design("efhw", efhw80)
shot("17_efhw_swr.png", T["swr"])
shot("17b_efhw_bands.png", T["bands"])

def delta_up(i):
    i.gain_on.setChecked(False); i.size_on.setChecked(False)
    i.band.setCurrentText("20 m (14.0-14.35 MHz)"); i.height.setValue(8.0)
design("delta", delta_up)
shot("18_delta_patterns.png", T["patterns"])
w.geo.set_view(35, 25)
shot("18b_delta_geo.png", T["geo"])

def delta_down(i):
    i.gain_on.setChecked(False); i.size_on.setChecked(False)
    i.band.setCurrentText("20 m (14.0-14.35 MHz)"); i.height.setValue(8.0)
    _opt(i, orient="down")
design("delta", delta_down)
w.geo.set_view(35, 25)
shot("18c_delta_down_geo.png", T["geo"])
editor_shots()
copy_menu_shot()
feed_shots()
print("done")
