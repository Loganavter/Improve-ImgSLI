"""Quick look source inset — amber bordered host + positioning helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px


def _inset_dark_bg() -> QColor:
    """Translucent dark fill for inset chrome (caption strip + host)."""
    try:
        from tabs.image_gallery.ui.quick_look.helpers import _token_rgba_qcolor

        bg = _token_rgba_qcolor("shadow.color", (0, 0, 0, 140))
        if bg is not None:
            # QColor(...) copy: never setAlpha a manager-owned instance in place.
            bg = QColor(bg)
            try:
                if bg.alpha() == 255:
                    bg.setAlpha(140)
            except Exception:
                pass
            return bg
    except Exception:
        pass
    return QColor(0, 0, 0, 140)


class _InsetCaptionStrip(QWidget):
    """Amber-on-dark caption strip overlaid at the inset bottom (W4 item 5).

    S4 v2 LIGHT (svg:53-64): a dark strip pinned to the inset's bottom edge
    carrying the amber ``SOURCE · name · WxH`` caption, elided to the strip
    width — not a VBox label above the thumbnail. Absolutely positioned by
    :func:`reposition_source_inset`; no QSS.
    """

    # svg:62-63: 16px dark strip at the top of the 84px inset; the caption
    # strip here pins to the *bottom* per the frozen item.
    STRIP_PX = 16

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("quicklook_source_inset_caption_strip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(scaled_px(4), 0, scaled_px(4), 0)
        lay.setSpacing(0)
        try:
            from tabs.image_gallery.ui.quick_look.helpers import _make_label, _token_color
        except Exception:
            _make_label = None  # type: ignore
            _token_color = None  # type: ignore
        amber = None
        try:
            amber = _token_color("gallery.status.warn", "#e8b64c")
        except Exception:
            pass
        try:
            self.label = _make_label(
                "SOURCE", parent=self, pixel_size=9, pt=9, color=amber, elide=True
            )
        except Exception:
            from sli_ui_toolkit.widgets import Label

            self.label = Label("SOURCE", pixel_size=9, parent=self)
        self.label.setObjectName("quicklook_source_inset_title")
        try:
            self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        except Exception:
            pass
        lay.addWidget(self.label)
        self._bg = _inset_dark_bg()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _on_theme_changed(self) -> None:
        try:
            self._bg = _inset_dark_bg()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            p = QPainter(self)
            try:
                p.fillRect(self.rect(), self._bg)
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


class _SourceInsetHost(QWidget):
    """Source inset container — paints a shadow fill + amber rounded border (S4-1)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._border_color = self._resolve_border()
        self._bg = self._resolve_bg()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_border() -> QColor | None:
        try:
            from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme, _token_qcolor

            # NOTE: was #e8b64c (dark-only) — now gallery.status.warn light/dark chain.
            return _token_qcolor(
                "gallery.status.warn", "#b77900" if not _is_dark_theme() else "#d9a441"
            )
        except Exception:
            return None

    @staticmethod
    def _resolve_bg() -> QColor:
        return _inset_dark_bg()

    def _on_theme_changed(self) -> None:
        try:
            self._border_color = self._resolve_border()
        except Exception:
            pass
        try:
            self._bg = self._resolve_bg()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event):  # noqa: N802
        try:
            p = QPainter(self)
            try:
                p.fillRect(self.rect(), self._bg)
            except Exception:
                pass
            try:
                color = self._border_color
                if color is not None:
                    pen = QPen(color)
                    pen.setWidthF(max(1.0, scaled_px(1.5)))
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
        try:
            super().paintEvent(event)
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
        # W4 item 5: caption strip pinned to the inset bottom, full width.
        try:
            cap = getattr(overlay, "_source_inset_caption", None)
            if cap is not None:
                cap_h = scaled_px(_InsetCaptionStrip.STRIP_PX)
                cap.setGeometry(0, max(0, h - cap_h), w, cap_h)
                cap.raise_()
        except Exception:
            pass
    except Exception:
        pass
