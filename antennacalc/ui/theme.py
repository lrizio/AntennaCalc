"""HamProjects family 'SHACK' palette with a light alternative."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel: str
    edge: str
    btn: str
    btn_edge: str
    text: str
    dim: str
    faint: str
    accent: str
    accent_edge: str
    good: str
    warn: str
    bad: str
    screen: str
    grid: str
    c1: str
    c2: str
    c3: str


SHACK = Theme("SHACK", bg="#14181d", panel="#1a2027", edge="#3a414c", btn="#3a414c", btn_edge="#12161b",
              text="#eef3f8", dim="#a7b3c0", faint="#56606b", accent="#2f6fb0", accent_edge="#6cb6ff",
              good="#57e39a", warn="#ffbf5f", bad="#ff7a6b", screen="#080d10", grid="#27313b",
              c1="#6cb6ff", c2="#ffbf5f", c3="#57e39a")
DAYLIGHT = Theme("DAYLIGHT", bg="#dfe5ea", panel="#f4f7f9", edge="#aab8c3", btn="#ffffff", btn_edge="#9fb0bd",
                 text="#15232d", dim="#566673", faint="#b7c3cc", accent="#bfe9ef", accent_edge="#0b7fa6",
                 good="#0f8a3a", warn="#b87400", bad="#c62828", screen="#ffffff", grid="#d3dde4",
                 c1="#0b7fa6", c2="#c46a00", c3="#0f8a3a")
THEMES = {"SHACK": SHACK, "DAYLIGHT": DAYLIGHT}

_current = SHACK


def current() -> Theme:
    return _current


def set_current(name: str) -> Theme:
    global _current
    _current = THEMES.get(name, SHACK)
    return _current


def shade(hex_color: str, amount: int) -> str:
    h = hex_color.lstrip("#")[-6:]
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    c = lambda v: max(0, min(255, v + amount))
    return f"#{c(r):02x}{c(g):02x}{c(b):02x}"


def _arrow_icons(t: Theme) -> dict:
    """Draw up/down arrow PNGs for the spin boxes (Qt stylesheets need image files for them)."""
    import os
    import tempfile
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
    d = os.path.join(tempfile.gettempdir(), "antennacalc_arrows")
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, pts in (("up", [(1, 7), (5, 2), (9, 7)]), ("down", [(1, 2), (5, 7), (9, 2)]),
                      ("left", [(7, 1), (2, 5), (7, 9)]), ("right", [(2, 1), (7, 5), (2, 9)])):
        path = os.path.join(d, f"{name}_{t.name}.png")
        img = QImage(10, 10, QImage.Format_ARGB32)
        img.fill(0)
        qp = QPainter(img)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(t.text))
        qp.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        qp.end()
        img.save(path)
        out[name] = path.replace("\\", "/")
    return out


def stylesheet(t: Theme) -> str:
    ar = _arrow_icons(t)
    return f"""
    QWidget {{ background: {t.bg}; color: {t.text}; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 19px; font-weight: 700; letter-spacing: 2px; }}
    QLabel#appname {{ font-size: 34px; font-weight: 900; letter-spacing: 6px; color: {t.accent_edge}; padding: 2px 0; }}
    QWidget#titlebar {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.btn, 22)}, stop:1 {shade(t.bg, -4)});
                        border-bottom: 2px solid {t.accent_edge}; }}
    QWidget#titlebar QLabel {{ background: transparent; }}
    QLabel#wintitle {{ font-size: 24px; font-weight: 900; letter-spacing: 3px; color: {t.text}; }}
    QPushButton#winbtn, QPushButton#winclose {{ background: transparent; border: 0; border-radius: 0; font-size: 18px; color: {t.text}; padding: 0; }}
    QPushButton#winbtn:hover {{ background: {shade(t.btn, 30)}; }}
    QPushButton#winclose:hover {{ background: #c42b1c; color: white; }}
    QPushButton#winbtn:pressed, QPushButton#winclose:pressed {{ padding: 0; border: 0; }}
    QLabel#dim {{ color: {t.dim}; }}
    QLabel#section {{ color: {t.accent_edge}; font-weight: 700; letter-spacing: 1px; padding-top: 6px; }}
    QLabel#card_value {{ font-size: 20px; font-weight: 700; }}
    QLabel#card_label {{ color: {t.dim}; font-size: 11px; letter-spacing: 1px; }}
    QFrame#card {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.panel, 26)}, stop:0.5 {t.panel}, stop:1 {shade(t.panel, -10)});
                   border: 1px solid {shade(t.edge, 30)}; border-bottom: 3px solid {shade(t.btn_edge, -8)}; border-radius: 9px; }}
    QFrame#card QLabel {{ background: transparent; }}
    QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.btn, 30)}, stop:1 {shade(t.btn, -10)});
                  border: 1px solid {t.btn_edge}; border-bottom: 3px solid {shade(t.btn_edge, -8)};
                  border-radius: 7px; padding: 6px 14px; color: {t.text}; }}
    QPushButton:hover {{ border-color: {t.accent_edge}; }}
    QPushButton:pressed {{ padding-top: 8px; border-bottom-width: 1px; }}
    QPushButton:disabled {{ color: {t.faint}; }}
    QPushButton#primary {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.accent, 45)}, stop:1 {shade(t.accent, -15)});
                           font-weight: 700; letter-spacing: 1px; border-color: {t.accent_edge}; }}
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.panel, -14)}, stop:1 {shade(t.panel, 6)});
                           border: 1px solid {t.edge}; border-top: 2px solid {shade(t.btn_edge, -8)}; border-bottom: 1px solid {shade(t.edge, 28)}; border-radius: 5px;
                           padding: 3px 6px; min-height: 22px; }}
    QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {t.accent_edge}; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: padding; subcontrol-position: top right; width: 20px; height: 14px;
                           border-left: 1px solid {t.edge}; border-bottom: 1px solid {t.edge}; background: {t.btn}; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: padding; subcontrol-position: bottom right; width: 20px; height: 14px;
                           border-left: 1px solid {t.edge}; background: {t.btn}; }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {t.accent}; }}
    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{ background: {t.accent_edge}; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({ar["up"]}); width: 10px; height: 10px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({ar["down"]}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{ background: {t.panel}; selection-background-color: {t.accent}; border: 1px solid {t.edge}; }}
    QCheckBox {{ spacing: 6px; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {t.edge}; border-radius: 3px; background: {t.panel}; }}
    QCheckBox::indicator:checked {{ background: {t.accent_edge}; }}
    QTabWidget::pane {{ border: 1px solid {t.edge}; border-radius: 6px; top: -1px; }}
    QTabBar::tab {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.btn, 30)}, stop:1 {shade(t.panel, 0)}); border: 1px solid {t.edge}; border-bottom: 0; padding: 7px 16px; margin-right: 2px;
                    border-top-left-radius: 6px; border-top-right-radius: 6px; color: {t.dim}; }}
    QTabBar::tab:selected {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.accent, 50)}, stop:1 {t.accent}); color: {t.text}; border-color: {t.accent_edge}; }}
    QTableWidget {{ background: {t.panel}; gridline-color: {t.grid}; border: 1px solid {t.edge}; alternate-background-color: {shade(t.panel, 6)}; }}
    QHeaderView::section {{ background: {t.btn}; color: {t.text}; border: 0; padding: 5px; font-weight: 600; }}
    QTextBrowser {{ background: {t.panel}; border: 1px solid {t.btn_edge}; border-top: 2px solid {shade(t.btn_edge, -8)}; border-bottom: 1px solid {shade(t.edge, 28)}; border-radius: 6px; }}
    QScrollArea {{ border: 0; }}
    QScrollBar:vertical {{ background: {shade(t.bg, 22)}; width: 20px; margin: 20px 0 20px 0; border-left: 1px solid {t.accent_edge}; }}
    QScrollBar::handle:vertical {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {shade(t.accent_edge, 30)}, stop:1 {shade(t.accent_edge, -20)});
                                  border: 2px solid {t.text}; border-radius: 7px; min-height: 40px; margin: 1px; }}
    QScrollBar::handle:vertical:hover {{ background: {shade(t.accent_edge, 45)}; }}
    QScrollBar:horizontal {{ background: {shade(t.bg, 22)}; height: 20px; margin: 0 20px 0 20px; border-top: 1px solid {t.accent_edge}; }}
    QScrollBar::handle:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {shade(t.accent_edge, 30)}, stop:1 {shade(t.accent_edge, -20)});
                                    border: 2px solid {t.text}; border-radius: 7px; min-width: 40px; margin: 1px; }}
    QScrollBar::handle:horizontal:hover {{ background: {shade(t.accent_edge, 45)}; }}
    QScrollBar::add-line:vertical {{ subcontrol-origin: margin; subcontrol-position: bottom; height: 20px; background: {t.btn}; border: 1px solid {t.edge}; }}
    QScrollBar::sub-line:vertical {{ subcontrol-origin: margin; subcontrol-position: top; height: 20px; background: {t.btn}; border: 1px solid {t.edge}; }}
    QScrollBar::add-line:horizontal {{ subcontrol-origin: margin; subcontrol-position: right; width: 20px; background: {t.btn}; border: 1px solid {t.edge}; }}
    QScrollBar::sub-line:horizontal {{ subcontrol-origin: margin; subcontrol-position: left; width: 20px; background: {t.btn}; border: 1px solid {t.edge}; }}
    QScrollBar::up-arrow:vertical {{ image: url({ar["up"]}); width: 10px; height: 10px; }}
    QScrollBar::down-arrow:vertical {{ image: url({ar["down"]}); width: 10px; height: 10px; }}
    QScrollBar::left-arrow:horizontal {{ image: url({ar["left"]}); width: 10px; height: 10px; }}
    QScrollBar::right-arrow:horizontal {{ image: url({ar["right"]}); width: 10px; height: 10px; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QProgressBar {{ background: {t.panel}; border: 1px solid {t.edge}; border-radius: 5px; text-align: center; min-height: 16px; }}
    QProgressBar::chunk {{ background: {t.accent_edge}; border-radius: 4px; }}
    QMenuBar {{ background: {t.bg}; }}
    QMenuBar::item:selected {{ background: {t.accent}; }}
    QMenu {{ background: {t.panel}; border: 1px solid {t.edge}; }}
    QMenu::item:selected {{ background: {t.accent}; }}
    QToolTip {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.accent_edge}; }}
    QGroupBox {{ border: 1px solid {t.edge}; border-radius: 6px; margin-top: 12px; padding-top: 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {t.accent_edge}; font-weight: 700; }}
    QSplitter::handle {{ background: {t.edge}; }}
    """
