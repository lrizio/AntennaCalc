"""UI check: run a built-in design, copy it into the Wire Editor, analyse the copy, save it and open it again."""
import json, os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"; os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, ".")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from antennacalc.ui.main_window import MainWindow

KEY = sys.argv[1] if len(sys.argv) > 1 else "trap_dipole"
msgs = []
QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2]) or QMessageBox.Ok)
app = QApplication(sys.argv); w = MainWindow(); w.resize(1560, 940); w.show()
w.inputs.select(KEY)
band0, ground0 = w.inputs.band.currentText(), w.inputs.ground.currentText()
stage = {"n": 0}
path = os.path.join(tempfile.mkdtemp(), "copy.antcalc")


def poll():
    if w.worker is not None or w.result is None:
        return
    if stage["n"] == 0:
        stage["first"] = w.result.metrics["z_ant"], w.result.metrics["gain_dbi"]
        w.copy_to_editor()
        print("message:", msgs[-1].replace("\n", " | "))
        print("type now:", w.inputs.spec.key, "| band kept:", w.inputs.band.currentText() == band0,
              "| ground kept:", w.inputs.ground.currentText() == ground0)
        print("drawing:", w.editor.drawing.name, len(w.editor.drawing.wires), "wires")
        w.result = None
        stage["n"] = 1
        w.analyse_drawing()
    elif stage["n"] == 1:
        print("built-in Z/G:", stage["first"], " copy Z/G:", (w.result.metrics["z_ant"], w.result.metrics["gain_dbi"]))
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (path, ""))
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ""))
        w.save_design()
        w.editor.set_drawing(None)
        w.open_design()
        d = json.load(open(path))
        print("saved type:", d["state"]["type"], "| reopened wires:", len(w.editor.drawing.wires))
        w.editor.undo()
        print("undo after open -> wires:", len(w.editor.drawing.wires))
        app.quit()


QTimer.singleShot(200, lambda: w.start_design(False))
t = QTimer(); t.timeout.connect(poll); t.start(300)
QTimer.singleShot(300000, app.quit); app.exec()
