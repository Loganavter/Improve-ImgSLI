"""Source-inset chrome: geometry constants + the rounded clip/border frame.

``plan-gallery-ql-source-canvas``: the Quick Look source inset's image
surface is a second engine canvas (``quick_look.source_canvas``). Geometry
lives here so the plate button (``build.py``), the inset canvas and this
frame cannot drift; the frame itself re-paints the plate's rounded thumb
clip ABOVE the canvas, because a ``QRhiWidget`` presents its own native
surface and cannot be rounded by widget painting alone.

Painter pipeline only — explicit ``paintEvent``, theme-subscribed, no QSS,
no palette. Mouse-transparent + NoFocus: the overlay's navigation and
region-select routing stay exactly the plate's.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

# Geometry mirrors ``overlay_build.build_overlay_ui``: the plate Button is a
# 150x84 image + 4px pad on every side (158x92), the outer plate radius is 8
# and the image rounding is 5.
SOURCE_INSET_W = 150
SOURCE_INSET_H = 84
SOURCE_INSET_PAD = 4
SOURCE_INSET_FRAME_RADIUS = 8
SOURCE_INSET_THUMB_RADIUS = 5

SOURCE_INSET_FRAME_OBJECT = "quicklook_source_inset_frame"


class SourceInsetFrame(QWidget):
    """Paint-only rounded clip + border above the inset canvas (inert).

    The corner wedges outside the rounded path are filled with the plate
    surface color and the path is stroked with the plate border; everything
    else is transparent. The plate Button is ``variant="surface"``, so the
    wedges resolve ``button.dialog.default.background`` / ``.border`` — the
    same tokens its painter uses.
    """

    def __init__(self, parent=None, *, radius_px: int = SOURCE_INSET_THUMB_RADIUS) -> None:
        super().__init__(parent)
        self._radius = max(0, int(radius_px))
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        except Exception:
            pass
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        except Exception:
            pass
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        except Exception:
            pass
        try:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        except Exception:
            pass
        self._fill = self._resolve_fill()
        self._border = self._resolve_border()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def radius_px(self) -> int:
        """Design-px corner radius of the clipped image (contract value)."""
        return self._radius

    @staticmethod
    def _resolve_fill():
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import (
                _is_dark_theme,
                _token_color,
            )

            return _token_color(
                "button.dialog.default.background",
                "#3c3c3c" if _is_dark_theme() else "#ffffff",
            )
        except Exception:
            return None

    @staticmethod
    def _resolve_border():
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _token_color

            return _token_color("button.dialog.default.border", "#1E000000")
        except Exception:
            return None

    def _on_theme_changed(self) -> None:
        try:
            self._fill = self._resolve_fill()
        except Exception:
            pass
        try:
            self._border = self._resolve_border()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                radius = float(max(0, scaled_px(self._radius)))
                r = QRectF(self.rect())
                pen_w = max(1.0, scaled_px(1))
                half = pen_w / 2.0
                inner = QRectF(r).adjusted(half, half, -half, -half)
                outer_path = QPainterPath()
                outer_path.addRect(r)
                inner_path = QPainterPath()
                inner_path.addRoundedRect(inner, radius, radius)
                fill = getattr(self, "_fill", None)
                if fill is not None:
                    # Only the corner wedges outside the rounded clip.
                    p.fillPath(outer_path.subtracted(inner_path), fill)
                border = getattr(self, "_border", None)
                if border is not None:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(border, pen_w))
                    p.drawPath(inner_path)
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass
