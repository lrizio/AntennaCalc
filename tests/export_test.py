import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["QT_QPA_FONTDIR"]="C:/Windows/Fonts"
sys.path.insert(0,".")
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QTimer
from antennacalc.ui import main_window as mw
app=QApplication(sys.argv); w=mw.MainWindow(); w.show()
tmp=tempfile.mkdtemp()
cur={}
QFileDialog.getSaveFileName=staticmethod(lambda *a, **k: (os.path.join(tmp, cur['name']), ""))
QFileDialog.getOpenFileName=staticmethod(lambda *a, **k: (os.path.join(tmp, cur['name']), ""))
def run_for(key):
    w.inputs.select(key)
    w.start_design(False)
    return key
state={'i':0}
keys=['lpda','trap_dipole','dish']
def poll():
    if w.worker is None and w.result is not None and state.get('started'):
        key=keys[state['i']]
        for name,fn in (("a.nec",w.export_nec),("a.csv",w.export_cutlist),("s.csv",w.export_sweep),("r.pdf",w.export_pdf),("d.antcalc",w.save_design)):
            cur['name']=f"{key}_{name}"
            fn()
        cur['name']=f"{key}_d.antcalc"; w.open_design()
        print(key, sorted(os.listdir(tmp))[-5:], [os.path.getsize(os.path.join(tmp,f)) for f in sorted(os.listdir(tmp))[-5:]])
        state['i']+=1; state['started']=False; w.result=None
        if state['i']>=len(keys): print(open(os.path.join(tmp,'lpda_a.nec')).read()[:900]); app.quit(); return
    if not state.get('started') and w.worker is None:
        k=keys[state['i']]
        if k=='lpda':
            pass
        w.inputs.select(k); w.start_design(False); state['started']=True
t=QTimer(); t.timeout.connect(poll); t.start(500)
QTimer.singleShot(200000,app.quit); app.exec()
