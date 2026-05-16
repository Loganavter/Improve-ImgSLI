from __future__ import annotations

from PyQt6.QtCore import QDate, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QSizePolicy

class CalendarDayButton(QPushButton):
    date_clicked = pyqtSignal(QDate)
    date_context_menu = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("day-button", True)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clicked.connect(self._on_click)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.date: QDate | None = None

    def set_date(self, date: QDate) -> None:
        self.date = date

    def _on_click(self):
        if self.date:
            self.date_clicked.emit(self.date)

    def _on_context_menu(self, pos):
        if self.date:
            self.date_context_menu.emit(self.date)

    def sizeHint(self):
        return QSize(50, 70)
