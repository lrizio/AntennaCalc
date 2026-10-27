"""AntennaCalc - amateur radio antenna design and simulation."""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))


def selftest(path):
    """Headless check used to verify a frozen build: runs a few designs and writes the numbers to a file."""
    from antennacalc import VERSION, engine, models  # noqa: F401
    from antennacalc.common import BAND_BY_LABEL
    from antennacalc.design import REGISTRY, Requirements
    lines = [f"AntennaCalc {VERSION} selftest"]
    b = BAND_BY_LABEL["20 m (14.0-14.35 MHz)"]
    for key in ("dipole", "yagi", "lpda", "dish", "helix"):
        spec = REGISTRY[key]
        ex = {p.key: p.default for p in spec.params}
        req = Requirements(f_mhz=b[3], f_lo=b[1], f_hi=b[2], radius=1e-3, height=spec.height_default)
        if key == "lpda":
            req.f_mhz, req.f_lo, req.f_hi = 21.0, 14.0, 30.0
        if key in ("dish", "helix"):
            nb = BAND_BY_LABEL["70 cm (430-440 MHz)"]
            req.f_mhz, req.f_lo, req.f_hi = nb[3], nb[1], nb[2]
        sc = engine.tune(spec, req, ex, {}) if not spec.analytic else {}
        r = engine.evaluate(spec, req, ex, sc, do_sweep=False)
        m = r.metrics
        lines.append(f"{key}: gain {m['gain_dbi']:.2f} dBi, Z {m['z_ant']:.1f}, SWR {m['swr_f0']:.2f}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    if "--selftest" in sys.argv:
        out = sys.argv[sys.argv.index("--selftest") + 1] if len(sys.argv) > sys.argv.index("--selftest") + 1 else "selftest.txt"
        selftest(out)
        return
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QSplashScreen
    app = QApplication(sys.argv)
    app.setApplicationName("AntennaCalc")
    app.setOrganizationName("HamProjects")

    pm = QPixmap(460, 200)
    pm.fill(QColor("#15202b"))
    p = QPainter(pm)
    p.setPen(QColor("#e6edf3"))
    f = QFont("Segoe UI", 24, QFont.Bold)
    p.setFont(f)
    p.drawText(pm.rect().adjusted(0, 30, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "AntennaCalc")
    p.setPen(QColor("#8fb8de"))
    p.setFont(QFont("Segoe UI", 12))
    p.drawText(pm.rect().adjusted(0, 90, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "Loading, please wait...")
    p.end()
    splash = QSplashScreen(pm, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    def note(msg):
        splash.showMessage(msg, Qt.AlignHCenter | Qt.AlignBottom, QColor("#8fb8de"))
        app.processEvents()

    note("Loading simulation engine...")
    from antennacalc.ui.main_window import MainWindow
    note("Building the user interface...")
    w = MainWindow()
    w.show()
    splash.finish(w)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
