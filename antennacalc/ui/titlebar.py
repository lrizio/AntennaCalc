"""Custom title bar (frameless window) with a large bold app name + version."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class TitleBar(QWidget):
    def __init__(self, window, text: str, icon_path: str | None):
        super().__init__()
        self.win = window
        self.setObjectName("titlebar")
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(0)
        if icon_path:
            ic = QLabel()
            ic.setPixmap(QPixmap(icon_path).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lay.addWidget(ic)
            lay.addSpacing(10)
        self.label = QLabel(text)
        self.label.setObjectName("wintitle")
        lay.addWidget(self.label)
        lay.addStretch(1)
        self.btn_min = QPushButton("—")
        self.btn_max = QPushButton("□")
        self.btn_close = QPushButton("✕")
        for b, name in ((self.btn_min, "winbtn"), (self.btn_max, "winbtn"), (self.btn_close, "winclose")):
            b.setObjectName(name)
            b.setFixedSize(58, 46)
            b.setFocusPolicy(Qt.NoFocus)
            lay.addWidget(b)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max)
        self.btn_close.clicked.connect(window.close)

    def set_text(self, text):
        self.label.setText(text)

    def toggle_max(self):
        w = self.win
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def sync(self):
        self.btn_max.setText("❐" if self.win.isMaximized() else "□")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.toggle_max()
