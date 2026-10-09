import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen"); os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from antennacalc.ui.main_window import MainWindow
app = QApplication(sys.argv)
w = MainWindow(); w.resize(1560, 940); w.show()
key = sys.argv[1] if len(sys.argv) > 1 else "yagi"
out = sys.argv[2] if len(sys.argv) > 2 else "shot.png"
tab = int(sys.argv[3]) if len(sys.argv) > 3 else 0
w.inputs.select(key)
if key=='lpda': pass
def go():
    w.start_design(False)
def poll():
    if w.worker is None and w.result is not None:
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i); app.processEvents()
            if tab < 0 or tab == i:
                w.grab().save(out.replace('.png', f'_{i}.png'))
        print("saved", out, w.result.metrics['gain_dbi'])
        app.quit()
QTimer.singleShot(200, go)
t = QTimer(); t.timeout.connect(poll); t.start(500)
QTimer.singleShot(240000, app.quit)
app.exec()
