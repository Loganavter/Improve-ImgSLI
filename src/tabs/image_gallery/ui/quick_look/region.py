"""Quick Look region selection — the LMB marquee + image-space mapping.

A left-button press-drag over the preview picks a rectangular region; on release
the crop is sent to Ask AI. The band is a mouse-transparent dashed accent
rectangle (the app's drop-zone border idiom) positioned over the preview slot,
the same overlay slot the first-frame cover uses. The mapping back to image
space is pure (``preview_zoom.widget_rect_to_normalized``).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


def accent_qcolor() -> QColor:
    """The app's blue accent (theme token → light/dark fallback)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        color = try_resolve_theme_color(ThemeManager.get_instance(), "accent")
        if color is not None:
            return color if isinstance(color, QColor) else QColor(color)
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark

        return QColor("#0096FF" if _is_dark() else "#0078D4")
    except Exception:
        return QColor("#0078D4")


class RegionBand(QWidget):
    """Mouse-transparent dashed accent rectangle over the preview slot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        except Exception:
            pass
        self._rect = QRect()
        self.hide()

    def set_band(self, rect: QRect) -> None:
        try:
            self._rect = QRect(rect)
        except Exception:
            self._rect = QRect()
        self.update()

    def clear(self) -> None:
        self._rect = QRect()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        rect = self._rect
        if rect is None or rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        try:
            accent = accent_qcolor()
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            fill = QColor(accent)
            fill.setAlpha(48)
            painter.setBrush(fill)
            pen = QPen(accent, 1.4)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([5.0, 4.0])
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.end()
        except Exception:
            pass


def canvas_view(canvas):
    """``(src_w, src_h, fb_w, fb_h, zoom, pan_x, pan_y)`` for a live canvas, or None."""
    try:
        from engine.store.tiled_pixel_store import pixel_source_size

        store = getattr(canvas, "_store", None)
        if store is None:
            return None
        src_w, src_h = pixel_source_size(store)
        if src_w <= 0 or src_h <= 0:
            return None
        return (
            int(src_w),
            int(src_h),
            max(1, int(canvas.width())),
            max(1, int(canvas.height())),
            float(getattr(canvas, "_zoom", 1.0)),
            float(getattr(canvas, "_pan_x", 0.0)),
            float(getattr(canvas, "_pan_y", 0.0)),
        )
    except Exception:
        return None


def norm_rect_for_band(canvas, band_rect) -> tuple[float, float, float, float] | None:
    """Map a framebuffer-space band rect to normalized image space (l,t,r,b)."""
    view = canvas_view(canvas)
    if view is None:
        return None
    src_w, src_h, fb_w, fb_h, zoom, pan_x, pan_y = view
    try:
        from tabs.image_gallery.ui.quick_look.preview_zoom import (
            widget_rect_to_normalized,
        )

        return widget_rect_to_normalized(
            (band_rect.left(), band_rect.top(), band_rect.right(), band_rect.bottom()),
            src_w,
            src_h,
            fb_w,
            fb_h,
            zoom,
            pan_x,
            pan_y,
        )
    except Exception:
        return None


__all__ = ["RegionBand", "accent_qcolor", "canvas_view", "norm_rect_for_band"]
