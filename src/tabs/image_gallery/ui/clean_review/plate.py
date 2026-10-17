"""S3 clean-review card plate — painter-pipeline surface for the modal + filmstrip cells.

Split out of the clean-review overlay module (plan-gallery-split-2026-10-17,
Part C3):
``_ReviewPlate`` is the shared rounded card (``gallery.panel.background`` fill +
border, rx12) used by the overlay's modal plate and its filmstrip cells. The
overlay shell (``CleanReviewOverlay``) stays in this package's ``__init__``.
Moved verbatim — same class name, same ``paintEvent``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

# Phase 1 — card plate radius (mockup v3: 900x440 white card, rx12).
REVIEW_CARD_RADIUS_PX = 12


class _ReviewPlate(QWidget):
    """S3 clean-review card plate — ``gallery.panel.background`` fill + border, rx12.

    Mirrors quick-look ``_CardPlate``
    (``ui/quick_look/overlay_build/widgets.py``): painter pipeline owns visuals
    (explicit paintEvent, theme-subscribed); no QSS, no palette. The plate
    shares the scroll-host panel token (``_apply_panel_background``) so the
    overlay is ONE flat surface — dark mockup svg:42 pins the plate at
    ``#303030``, not the grid-card ``#383838``. All QColor() calls take
    resolved variables — never literals
    (contracts/test_no_hardcoded_qcolor.py baseline).
    """

    def __init__(self, parent=None, *, hover_wash: bool = False) -> None:
        super().__init__(parent)
        self._bg = self._resolve_bg()
        self._border = self._resolve_border()
        # Hover wash only for filmstrip cards (the modal plate itself must
        # not tint when the mouse crosses empty dialog areas).
        self._hover_wash_enabled = bool(hover_wash)
        self._hovered = False
        self._hover = self._resolve_hover()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        # HoverCoordinator contract: the filmstrip cell is one hover surface.
        # Registered (not raw enter/leave) so the wash survives the pointer
        # moving onto a child (thumb / Restore) — raw leaveEvent fires per
        # child and would drop the wash. The inner Restore button declares this
        # cell as its hover host so the card lights it from the same source.
        if self._hover_wash_enabled:
            try:
                from sli_ui_toolkit.ui.widgets.helpers import register_hover_widget

                register_hover_widget(self)
            except Exception:
                pass

    @staticmethod
    def _resolve_bg():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.panel.background", "gallery.card.background", "surface.list", "surface.background"):
                c = try_resolve_theme_color(mgr, token)
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _is_dark_theme, _token_color

            return _token_color(
                "gallery.panel.background", "#ffffff" if not _is_dark_theme() else "#303030"
            )
        except Exception:
            return None

    @staticmethod
    def _resolve_border():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.card.border", "flyout.border"):
                try:
                    c = try_resolve_theme_color(mgr, token)
                except Exception:
                    c = None
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _is_dark_theme, _token_color

            return _token_color(
                "gallery.card.border", "#e2e4e8" if not _is_dark_theme() else "#4a4a4a"
            )
        except Exception:
            return None

    @staticmethod
    def _resolve_hover():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            dark = bool(ThemeManager.get_instance().is_dark())
        except Exception:
            dark = False
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _token_rgba_qcolor

            c = _token_rgba_qcolor(
                "list_item.background.hover",
                (255, 255, 255, 38) if dark else (0, 0, 0, 26),
            )
            if c is not None:
                return c
        except Exception:
            pass
        return QColor(0, 0, 0, 0)

    def _on_theme_changed(self) -> None:
        try:
            self._bg = self._resolve_bg()
        except Exception:
            pass
        try:
            self._border = self._resolve_border()
        except Exception:
            pass
        try:
            self._hover = self._resolve_hover()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def setHoverActive(self, active: bool) -> None:
        """HoverCoordinator contract — wash the whole cell as one surface.

        The coordinator owns on/off (not raw enter/leave, which fire per
        child): the wash stays on while the pointer is anywhere in the cell
        subtree, and the embedded Restore button's hover host is this cell,
        so hovering the card lights the button too.
        """
        if not self._hover_wash_enabled:
            return
        active = bool(active)
        if active == self._hovered:
            return
        self._hovered = active
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPen

            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                r = QRectF(self.rect())
                rx = scaled_px(REVIEW_CARD_RADIUS_PX)
                p.setPen(Qt.PenStyle.NoPen)
                try:
                    bg = self._bg
                except Exception:
                    bg = self._resolve_bg()
                p.setBrush(bg)
                p.drawRoundedRect(r, rx, rx)
                if self._hover_wash_enabled and self._hovered:
                    try:
                        wash = self._hover
                    except Exception:
                        wash = self._resolve_hover()
                    if wash is not None:
                        p.setBrush(wash)
                        p.drawRoundedRect(r, rx, rx)
                try:
                    border = self._border
                except Exception:
                    border = self._resolve_border()
                try:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(border, 1))
                    # Border fully inside the widget rect (not straddling):
                    # the outer half of a straddled 1px pen is clipped and
                    # its AA fade makes the visible line sit ~1px off.
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rx, rx)
                except Exception:
                    pass
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass
