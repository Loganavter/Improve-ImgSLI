"""Ask AI flyout resize grip (split out of ask_ai.py for the size contract).

Bottom-right drag handle that resizes the flyout (an in-window child). A real
``QSizeGrip`` only resizes top-level windows, so this drives the flyout's
geometry via ``flyout.apply_user_size``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px

if TYPE_CHECKING:
    from tabs.image_gallery.ui.ask_ai import AskAiFlyout


class AskAiResizeGrip(QWidget):
    """Bottom-right drag handle for the Ask AI flyout."""

    def __init__(self, flyout: "AskAiFlyout") -> None:
        super().__init__(flyout)
        self._flyout = flyout
        self._start = None
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setFixedSize(scaled_px(16), scaled_px(16))
        try:
            self.setObjectName("gallery_ask_ai_resize_grip")
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        try:
            from PySide6.QtGui import QColor, QPainter, QPen

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(150, 150, 150, 170), 1.4))
            w, h = self.width(), self.height()
            for off in (3, 7, 11):
                p.drawLine(w - off, h - 2, w - 2, h - off)
            p.end()
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = (event.globalPosition().toPoint(), self._flyout.size())
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start is None:
            return
        start, size0 = self._start
        pos = event.globalPosition().toPoint()
        self._flyout.apply_user_size(
            size0.width() + (pos.x() - start.x()),
            size0.height() + (pos.y() - start.y()),
        )
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._start = None
        event.accept()


__all__ = ["AskAiResizeGrip"]
