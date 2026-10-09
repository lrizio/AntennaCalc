import os, sys
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["QT_QPA_FONTDIR"]="C:/Windows/Fonts"
sys.path.insert(0,".")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from antennacalc.ui.main_window import MainWindow
app=QApplication(sys.argv); w=MainWindow(); w.resize(1560,940); w.show()
w.inputs.select("yagi"); w.inputs.gain_on.setChecked(True); w.inputs.gain.setValue(11.0)
w.inputs.size_on.setChecked(True); w.inputs.size.setValue(9.0); w.inputs.optimize.setChecked(True)
msgs=[]
def go():
    w.start_design(False)
    w.worker.progress.connect(lambda f,t: msgs.append((round(f,2),t)))
def poll():
    if w.worker is None and w.result is not None:
        print("steps:", msgs[0], msgs[len(msgs)//3], msgs[-1])
        print("notes:", w.result.design.notes[:2])
        print("n=", w.inputs.param_widgets['n'][1].value(), "G=", w.result.metrics['gain_dbi'], "FB", w.result.metrics['fb'], "SWR", w.result.metrics['swr_f0'])
        for r in report_checks(): print(r)
        w.tabs.setCurrentIndex(0); app.processEvents(); w.grab().save("tests/flow.png")
        app.quit()
from antennacalc import report
def report_checks(): return report.requirement_checks(w.result, w.inputs.spec)
QTimer.singleShot(200,go); t=QTimer(); t.timeout.connect(poll); t.start(500)
QTimer.singleShot(300000,app.quit); app.exec()
