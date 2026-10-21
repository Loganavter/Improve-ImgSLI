"""In-window lightbox for Help figures (dimmed scrim + zoom + pan).

Moved out of the toolkit with the text-unification wave C (PR #98 removed
``composite/help_document/*``): the Help dialog owns its TOC and lightbox
chrome, so this widget lives with its only owner.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar

_SCRIM = QColor(0, 0, 0, 200)
_MIN_ZOOM = 0.25
_MAX_ZOOM = 8.0
_ZOOM_STEP = 1.15
_FIT_MARGIN = 48


class HelpImageLightbox(QWidget):
    """Overlay over the Help *content* area (below CSD title bar).

    - Wheel / ``+`` ``-`` zoom; ``0`` resets fit + pan
    - Middle-mouse drag pans
    - Left/right click or Esc dismisses
    """

    closed = Signal()

    def __init__(self, host_window: QWidget) -> None:
        super().__init__(host_window)
        self.setObjectName("HelpImageLightbox")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.hide()

        self._host = host_window
        self._pixmap = QPixmap()
        self._zoom = 1.0
        self._fit_zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._panning = False
        self._pan_last: QPointF | None = None
        self._host.installEventFilter(self)

    def show_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap is None or pixmap.isNull():
            return
        self._pixmap = pixmap
        self._pan = QPointF(0.0, 0.0)
        self._panning = False
        self._pan_last = None
        self._sync_geometry()
        self._fit_zoom = self._compute_fit_zoom()
        self._zoom = self._fit_zoom
        self.show()
        self.raise_()
        self._raise_title_bar_above()
        if not self.isActiveWindow():
            self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self.update()

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        self._pixmap = QPixmap()
        self._panning = False
        self._pan_last = None
        self.unsetCursor()
        self.closed.emit()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # ``getattr`` guards events that arrive before ``__init__`` finishes
        # or during teardown (a partially-constructed lightbox must not
        # raise inside the event loop).
        host = getattr(self, "_host", None)
        if host is not None and watched is host and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Move,
        }:
            if self.isVisible():
                self._sync_geometry()
                self._raise_title_bar_above()
                self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), _SCRIM)
        if self._pixmap.isNull():
            return
        dest = self._image_rect()
        painter.drawPixmap(dest.toRect(), self._pixmap)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._pixmap.isNull():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return
        factor = _ZOOM_STEP if delta > 0 else 1.0 / _ZOOM_STEP
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = QPointF(event.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() in {
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
        }:
            self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._panning and self._pan_last is not None:
            pos = QPointF(event.position())
            delta = pos - self._pan_last
            self._pan = QPointF(self._pan.x() + delta.x(), self._pan.y() + delta.y())
            self._pan_last = pos
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self._pan_last = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Plus, Qt.Key.Key_Equal}:
            self._zoom = min(_MAX_ZOOM, self._zoom * _ZOOM_STEP)
            self.update()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Minus, Qt.Key.Key_Underscore}:
            self._zoom = max(_MIN_ZOOM, self._zoom / _ZOOM_STEP)
            self.update()
            event.accept()
            return
        if event.key() == Qt.Key.Key_0:
            self._zoom = self._fit_zoom
            self._pan = QPointF(0.0, 0.0)
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def _title_bar_height(self) -> int:
        title_bar = getattr(self._host, "_csd_title_bar", None)
        if title_bar is None:
            return 0
        if not title_bar.isVisible():
            return 0
        height = int(title_bar.height())
        if height > 0:
            return height
        from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

        return scaled_px(CustomTitleBar.HEIGHT)

    def _raise_title_bar_above(self) -> None:
        title_bar = getattr(self._host, "_csd_title_bar", None)
        if title_bar is not None:
            title_bar.raise_()

    def _sync_geometry(self) -> None:
        """Cover only the client content below the CSD title bar."""
        host_rect = self._host.rect()
        top = self._title_bar_height()
        self.setGeometry(
            QRect(0, top, host_rect.width(), max(1, host_rect.height() - top))
        )

    def _compute_fit_zoom(self) -> float:
        if self._pixmap.isNull():
            return 1.0
        avail_w = max(1, self.width() - _FIT_MARGIN * 2)
        avail_h = max(1, self.height() - _FIT_MARGIN * 2)
        sx = avail_w / max(1, self._pixmap.width())
        sy = avail_h / max(1, self._pixmap.height())
        return max(_MIN_ZOOM, min(1.0, sx, sy))

    def _image_rect(self) -> QRectF:
        pw = self._pixmap.width() * self._zoom
        ph = self._pixmap.height() * self._zoom
        x = (self.width() - pw) / 2.0 + self._pan.x()
        y = (self.height() - ph) / 2.0 + self._pan.y()
        return QRectF(x, y, pw, ph)
