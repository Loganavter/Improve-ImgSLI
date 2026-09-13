"""Quick look source inset — amber bordered host + positioning helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px


class _SourceInsetHost(QWidget):
    """Source inset container — paints an amber rounded border (S4-1)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        try:
            from tabs.image_gallery.ui.quick_look.helpers import _token_color

            color = _token_color("warning", "#e8b64c")
            if color is None:
                return
            pen = QPen(color)
            pen.setWidthF(max(1.0, scaled_px(1.5)))
            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                half = pen.widthF() / 2.0
                rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, scaled_px(4), scaled_px(4))
            finally:
                p.end()
        except Exception:
            pass


def reposition_source_inset(overlay) -> None:
    """Anchor source inset bottom-left inside preview with scaled_px margins."""
    try:
        host = getattr(overlay, "_preview_label", None)
        inset = getattr(overlay, "_source_inset_host", None)
        if host is None or inset is None:
            return
        margin = scaled_px(12)
        w = inset.sizeHint().width()
        h = inset.sizeHint().height()
        if w <= 0:
            w = scaled_px(150) + scaled_px(4)
        if h <= 0:
            h = scaled_px(84) + scaled_px(18)
        w = max(w, inset.width() or scaled_px(154))
        h = max(h, inset.height() or scaled_px(106))
        max_w = max(0, host.width() - margin * 2)
        max_h = max(0, host.height() - margin * 2)
        if w > max_w:
            w = max_w
        if h > max_h:
            h = max_h
        inset.setFixedSize(w, h)
        x = margin
        y = max(margin, host.height() - h - margin)
        inset.move(x, y)
        inset.raise_()
    except Exception:
        pass
