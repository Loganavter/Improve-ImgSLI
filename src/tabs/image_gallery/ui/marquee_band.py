"""In-paint marquee band for the gallery grid (Dolphin-style).

Replaces the window-level ``MarqueeBandOverlay`` on the gallery path with a
band painted in the content host's own paint pass: one widget dies, one
paint pass remains. No overlay, no restack, no cross-space mapping.

``MarqueeState`` is pure gesture state (Dolphin ``kitemlistrubberband``
parity: origin/active + content-space rects) plus the short-lived
``QApplication`` event filter for move/release tracking. ``MarqueeHost``
is the content well that paints the band under its cards.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ui.widgets.shelf import OpaqueFillHost

MIN_DRAG_PX = 3


def _mdbg(msg: str, *args) -> None:
    """Marquee trace via gallery_debug (env-gated, fail-open)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(msg, *args)
    except Exception:
        pass


def _default_accent() -> QColor:
    try:
        from tabs.image_gallery.ui.card import gallery_selection_accent

        accent = gallery_selection_accent()
        if accent is not None and accent.isValid():
            return QColor(accent)
    except Exception:
        pass
    return QColor("#0078D4")


class MarqueeHost(OpaqueFillHost):
    """Content host that paints the selection band in its own paint pass.

    Subclass — the shared ``OpaqueFillHost`` is never modified (session
    shelf unaffected). The band paints after the base fill and before
    children (cards), i.e. under the cards, Dolphin ``CE_RubberBand``
    parity. Paint clips to widget bounds inherently: dragging outside the
    host shows the intersected visible part, with no hide/show flicker.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.band_rect: QRect | None = None
        self._band_accent = _default_accent()

    def set_accent(self, color) -> None:
        try:
            accent = QColor(color)
            if accent.isValid():
                self._band_accent = accent
                if self.band_rect is not None:
                    self.update()
        except Exception:
            pass

    def set_band_rect(self, rect: QRect | None) -> None:
        """Assign the band (host-local) and repaint; skip when unchanged.

        ``None`` (or an invalid/empty rect) clears the band. No restack, no
        show/hide, no stacking calls — Qt compresses ``update()`` to frame
        rate, so per-mousemove calls are free.
        """
        try:
            norm = QRect(rect) if rect is not None and rect.isValid() and not rect.isEmpty() else None
        except Exception:
            norm = None
        try:
            if norm == self.band_rect or (norm is not None and self.band_rect is not None and norm == self.band_rect):
                return
        except Exception:
            pass
        self.band_rect = norm
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        rect = self.band_rect
        if rect is None or rect.isEmpty() or not rect.isValid():
            return
        try:
            painter = QPainter(self)
            fill = QColor(self._band_accent)
            fill.setAlpha(48)
            border = QColor(self._band_accent)
            border.setAlpha(200)
            painter.fillRect(rect, fill)
            painter.setPen(QPen(border, 1))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.end()
        except Exception:
            pass


class MarqueeState(QObject):
    """Gallery marquee gesture state + drag tracker (no overlay widget).

    Content-space only: ``start``/``update_at``/``finish_at`` take and
    return host-local rects — ``band == QRect(origin, pos).normalized()``,
    no window round-trip, so clip-vs-hit divergence cannot occur. Degenerate
    start==end is a 1x1 rect (Qt rects are inclusive), never invalid.
    Tiny bands (both axes below ``min_drag_px``) finish as ``QRect()``.

    Mouse routing mirrors the toolkit gesture exactly: moves consumed while
    dragging (``True``), LeftButton release passes through (``False``) so
    Qt press-tracking stays balanced (hover-loss fix preserved).
    """

    def __init__(
        self,
        host: QWidget | None,
        *,
        parent: QObject | None = None,
        min_drag_px: int = MIN_DRAG_PX,
        on_update=None,
        on_finish=None,
    ) -> None:
        super().__init__(parent if parent is not None else host)
        self._host = host
        self._min_drag_px = max(1, int(min_drag_px))
        self._on_update = on_update
        self._on_finish = on_finish
        self._origin: QPoint | None = None
        self._app_filter = False
        self._clip_widget: QWidget | None = None
        self._accent: QColor | None = None

    @property
    def active(self) -> bool:
        return self._origin is not None

    @property
    def app_filter_installed(self) -> bool:
        return self._app_filter

    def set_accent(self, color) -> None:
        try:
            self._accent = QColor(color)
        except Exception:
            self._accent = None
        try:
            host = self._host
            if host is not None and hasattr(host, "set_accent"):
                host.set_accent(color)
        except Exception:
            pass

    def set_clip_widget(self, clip_widget: QWidget | None) -> None:
        """Accepted for API parity; host paint clips inherently (unused)."""
        self._clip_widget = clip_widget

    def set_on_update(self, callback) -> None:
        self._on_update = callback

    def set_on_finish(self, callback) -> None:
        self._on_finish = callback

    def start(self, content_pos: QPoint) -> bool:
        """Begin a band at host-local *content_pos*."""
        host = self._host
        if host is None:
            return False
        try:
            self._origin = QPoint(content_pos)
        except Exception:
            return False
        rect = QRect(self._origin, self._origin).normalized()
        self._paint_band(rect)
        self._install_app_filter()
        _mdbg("marquee press START pos=%s (in-paint)", content_pos)
        if self._on_update is not None:
            try:
                self._on_update(QRect(rect))
            except Exception:
                pass
        return True

    def update_at(self, content_pos: QPoint) -> QRect:
        """Band for the current pointer (host-local, pure)."""
        if self._origin is None:
            return QRect()
        return QRect(self._origin, QPoint(content_pos)).normalized()

    def finish_at(self, content_pos: QPoint) -> QRect:
        """Final band (host-local, pure); tiny drags finish as ``QRect()``."""
        rect = self.update_at(content_pos)
        if rect.isEmpty():
            return QRect()
        if rect.width() < self._min_drag_px and rect.height() < self._min_drag_px:
            return QRect()
        return rect

    def cancel(self) -> None:
        """Hide the band without calling ``on_finish``."""
        self._origin = None
        self._clear_band()
        self._remove_app_filter()

    def eventFilter(self, watched: QObject, event) -> bool:  # noqa: N802
        del watched
        if not self._app_filter or self._origin is None:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        et = event.type()
        if et == event.Type.MouseButtonPress and event.button() != Qt.MouseButton.LeftButton:
            return False
        if et == event.Type.MouseButtonRelease and event.button() != Qt.MouseButton.LeftButton:
            return False
        if et == event.Type.MouseMove and (event.buttons() & Qt.MouseButton.LeftButton):
            try:
                pos = self._host.mapFromGlobal(event.globalPosition().toPoint())
            except Exception:
                return False
            rect = self.update_at(pos)
            self._paint_band(rect)
            if self._on_update is not None:
                try:
                    self._on_update(QRect(rect))
                except Exception:
                    pass
            return True
        if et == event.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            try:
                pos = self._host.mapFromGlobal(event.globalPosition().toPoint())
            except Exception:
                pos = QPoint(self._origin)
            origin = self._origin
            rect = self.finish_at(pos)
            del origin
            self._origin = None
            self._clear_band()
            self._remove_app_filter()
            _mdbg("marquee FINISH rect=(%d,%d %dx%d)", rect.x(), rect.y(), rect.width(), rect.height())
            if self._on_finish is not None:
                try:
                    self._on_finish(QRect(rect))
                except Exception:
                    pass
            # Pass the release through (return False): same balanced-routing
            # contract as the toolkit gesture (hover-loss fix).
            return False
        return False

    def _paint_band(self, rect: QRect) -> None:
        try:
            host = self._host
            if host is not None and hasattr(host, "set_band_rect"):
                host.set_band_rect(rect)
        except Exception:
            pass

    def _clear_band(self) -> None:
        try:
            host = self._host
            if host is not None and hasattr(host, "set_band_rect"):
                host.set_band_rect(None)
        except Exception:
            pass

    def _install_app_filter(self) -> None:
        if self._app_filter:
            return
        try:
            app = QApplication.instance()
        except Exception:
            app = None
        if app is None:
            return
        try:
            app.installEventFilter(self)
        except Exception:
            return
        self._app_filter = True

    def _remove_app_filter(self) -> None:
        if not self._app_filter:
            return
        try:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except Exception:
            pass
        self._app_filter = False
