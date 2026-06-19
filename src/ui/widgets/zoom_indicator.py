from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from resources.translations import tr
from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon
from ui.widgets.rounded_overlay import RoundedOverlayWidget


class ZoomIndicator(RoundedOverlayWidget):
    """Overlay showing current zoom percent with a reset button.

    Self-contained: takes a `lang_provider` callback to localize its prefix.
    The owning UI is responsible for connecting `btn_zoom_reset.clicked`.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        lang_provider: Callable[[], str] = lambda: "en",
        target_widget: QWidget | None = None,
    ):
        super().__init__(parent, bg_color=QColor(0, 0, 0, 140), radius=6)
        self._lang_provider = lang_provider
        self._target_widget = target_widget

        self.setObjectName("ZoomIndicator")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        self._label = QLabel("100%", self)
        layout.addWidget(self._label)

        self.btn_zoom_reset = Button(AppIcon.SYNC, parent=self)
        self.btn_zoom_reset.setFixedSize(QSize(22, 22))
        self.btn_zoom_reset.setToolTip("Reset zoom")
        layout.addWidget(self.btn_zoom_reset)

        self.adjustSize()
        self.hide()
        self.update_zoom(1.0)

    def set_target(self, target: QWidget):
        self._target_widget = target

    def update_zoom(self, zoom: float, pan_x: float = 0.0, pan_y: float = 0.0):
        percent = int(round(float(zoom) * 100))
        prefix = tr("label.zoom", self._lang_provider())
        self._label.setText(f"{prefix}: {percent}%")
        self.adjustSize()
        visible = (
            abs(float(zoom) - 1.0) > 1e-3
            or abs(float(pan_x)) > 1e-4
            or abs(float(pan_y)) > 1e-4
        )
        self.setVisible(visible)
        if visible:
            self.sync_position()
            self.raise_()

    def sync_position(self):
        if not self.isVisible() or self._target_widget is None:
            return
        target_geo = self._target_widget.geometry()
        margin = 8
        w = self.width()
        h = self.height()
        x = target_geo.right() - w - margin
        y = target_geo.top() + margin
        self.move(x, y)
        self.raise_()
