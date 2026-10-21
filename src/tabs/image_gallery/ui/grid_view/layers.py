"""Gallery grid painter layers + band separator (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Layer, OverlayScrollArea

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import (
    GALLERY_CARD_H,
    GALLERY_CARD_W,
    apply_gallery_selection,
    build_gallery_card,
    gallery_selection_accent,
    update_gallery_card,
)
from tabs.image_gallery.ui.card.activity_pulse import ActivityPulse
from tabs.image_gallery.ui.list.card import (
    LIST_CARD_H,
    _bind_list_row,
    build_gallery_list_card,
    update_gallery_list_card,
)
from ui.widgets.shelf import OpaqueFillHost, apply_opaque_widget_fill

logger = logging.getLogger("ImproveImgSLI")

from tabs.image_gallery.ui.grid_view import GRID_SEPARATOR_COL_W

def _is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``."""
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return True

def _resolve_section_bar_color(collapsible: bool):
    """Section header bar color with a light/dark-aware fallback.

    Collapsible series: ``gallery.accent.bar`` → ``accent`` →
    ``#0078D4`` (light) / ``#0096FF`` (dark). UNGROUPED tail:
    ``dialog.border`` → ``#c0c0c0`` (light) / ``#555555`` (dark).
    """
    from PySide6.QtGui import QColor as _QC

    try:
        from sli_ui_toolkit.managers import ThemeManager as _TM
        from ui.theming import try_resolve_theme_color as _trc

        mgr = _TM.get_instance()
        if collapsible:
            for tok in ("gallery.accent.bar", "accent"):
                c = _trc(mgr, tok)
                if c is not None:
                    return _QC(c) if isinstance(c, str) else c
        else:
            c = _trc(mgr, "dialog.border")
            if c is not None:
                return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    if collapsible:
        return _QC("#0096FF") if _is_dark() else _QC("#0078D4")
    return _QC("#555555") if _is_dark() else _QC("#c0c0c0")

def _gallery_header_text_color():
    """Series header text: ``gallery.header.text`` → light/dark fallback."""
    from PySide6.QtGui import QColor as _QC

    try:
        from sli_ui_toolkit.managers import ThemeManager as _TM
        from ui.theming import try_resolve_theme_color as _trc

        c = _trc(_TM.get_instance(), "gallery.header.text")
        if c is not None:
            return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    if _is_dark():
        return _QC(154, 154, 154)
    return _QC(0x38, 0x38, 0x38)

def _grid_substrate_color():
    """Grid viewport substrate: gallery-scoped, NOT the global surface.

    Chain: ``gallery.grid.background`` → ``surface.background`` →
    ``#ffffff`` (light) / ``#2b2b2b`` (dark). White-cards + visible-borders
    philosophy (mockups v2/v3/v4-light): the grid is white and cards read
    via their 1px ``gallery.card.border`` hairline — the gray substrate is
    dead. ``Window``/``surface.background`` stay app-global near-white (a
    global ``#cecece`` leaked into every autoFillBackground widget app-wide —
    see plan 2026-09-23 rescope).
    Rule A: keyed on ``is_dark()`` (light default).
    """
    from PySide6.QtGui import QColor as _QC

    try:
        from sli_ui_toolkit.managers import ThemeManager as _TM
        from ui.theming import try_resolve_theme_color as _trc

        mgr = _TM.get_instance()
        for tok in ("gallery.grid.background", "surface.background"):
            c = _trc(mgr, tok)
            if c is not None:
                return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    if _is_dark():
        return _QC(0x2B, 0x2B, 0x2B)
    return _QC(0xFF, 0xFF, 0xFF)

class _SeriesHeaderAccentLayer(Layer):
    """Section bar painted on the header button's own left edge.

    Simple-flyout pattern (``CurrentIndicatorLayer`` in
    ``ui/actions/palette/row.py``): the 3×14 accent bar
    is a painter layer of the header ``Button`` itself, not a sibling widget —
    bar and label share one geometry/hover lifecycle and can never drift
    apart. Color resolves per-paint, so theme flips need no cached state
    (the button repaints via its ``theme_changed`` → ``update`` hookup).
    """

    scope = "widget"

    def __init__(self, collapsible: bool = True) -> None:
        self._collapsible = bool(collapsible)

    def draw(self, ctx, tm) -> None:  # type: ignore[no-untyped-def]
        try:
            rect = ctx.rect.toRect() if hasattr(ctx.rect, "toRect") else ctx.rect
            color = _resolve_section_bar_color(self._collapsible)
            try:
                bar_w = int(scaled_px(3))
                bar_h = int(scaled_px(14))
            except Exception:
                bar_w, bar_h = 3, 14
            x = int(rect.left())
            y = int(rect.top() + (rect.height() - bar_h) // 2)
            ctx.painter.fillRect(x, y, bar_w, bar_h, color)
        except Exception:
            pass

class _SeriesDropTargetLayer(Layer):
    """Colored landing indicator for card DnD (Wave E).

    Same pattern as ``_SeriesHeaderAccentLayer``: a painter layer of the
    header ``Button`` itself (no sibling widgets, no QSS — the painter
    pipeline owns all visuals). Paints a full-width accent underline while
    the header is the live drop target; the flag lives on the button
    (``btn._gallery_drop_target``, toggled by ``ui/drag_drop`` highlight
    set/clear + ``btn.update()``), the color resolves per-paint from the
    selection-accent token so light/dark flips need no cached state.
    Off while the flag is absent/False — zero paint cost outside drags.
    """

    scope = "widget"

    def draw(self, ctx, tm) -> None:  # type: ignore[no-untyped-def]
        try:
            widget = getattr(ctx, "widget", None)
            if not bool(getattr(widget, "_gallery_drop_target", False)):
                return
            rect = ctx.rect.toRect() if hasattr(ctx.rect, "toRect") else ctx.rect
            color = gallery_selection_accent()
            try:
                from PySide6.QtGui import QColor as _QC

                if color is None or (hasattr(color, "isValid") and not color.isValid()):
                    color = _QC("#0078D4")
            except Exception:
                pass
            try:
                bar_h = int(scaled_px(3))
            except Exception:
                bar_h = 3
            ctx.painter.fillRect(
                int(rect.left()), int(rect.bottom()) - bar_h,
                int(rect.width()), bar_h, color,
            )
            try:
                from PySide6.QtGui import QColor as _QC2

                # Copy before setAlpha: the accent helper may hand out a
                # shared/cached instance — never mutate it in place.
                tint = _QC2(color) if not callable(color) else _QC2(color())
                if not tint.isValid():
                    tint = _QC2("#0078D4")
                tint.setAlpha(36)
                ctx.painter.fillRect(
                    int(rect.left()), int(rect.top()),
                    int(rect.width()), int(rect.height()) - bar_h, tint,
                )
            except Exception:
                pass
        except Exception:
            pass

class _BandSeparatorHandle(QWidget):
    """Draggable center splitter between side-by-side series bands.

    Thin (8px) widget living in its own ``QGridLayout`` column, spanning all
    rows. Horizontal drag adjusts the left-band width; the grid replans live
    as column boundaries are crossed (no-op while inside one column — the
    surgical reconcile in ``_rebuild_series`` converges without teardown).
    Paints nothing (transparent); the SplitHCursor + tooltip afford dragging.
    """

    def __init__(self, view, parent=None) -> None:
        super().__init__(parent)
        self._view = view
        self._press_x: int | None = None
        try:
            self.setObjectName("GalleryBandSeparator")
            self.setCursor(Qt.CursorShape.SplitHCursor)
            tip = self._resize_tooltip()
            if tip:
                self.setToolTip(tip)
            self.setMouseTracking(True)
            self.setFixedWidth(scaled_px(GRID_SEPARATOR_COL_W))
        except Exception:
            pass

    def _resize_tooltip(self) -> str | None:
        """Localized handle tooltip via the owning grid's translator chain.

        No local fallback literal: the grid's ``_activity_translate`` is
        fail-open (returns the EN default itself), so an unavailable
        translator just leaves the tooltip unset rather than duplicating text.
        """
        try:
            tr = getattr(self._view, "_activity_translate", None)
            if callable(tr):
                return str(tr("image_gallery.grid.resize_tooltip", "Drag to resize series panes"))
        except Exception:
            pass
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._press_x = int(event.globalPosition().x())
                event.accept()
                return
        except Exception:
            pass
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        try:
            if self._press_x is not None and bool(event.buttons() & Qt.MouseButton.LeftButton):
                view = self._view
                dx = int(event.globalPosition().x()) - int(self._press_x)
                try:
                    stride = int(view._grid_stride_px())
                except Exception:
                    stride = 0
                if stride > 0 and abs(dx) >= stride // 2:
                    try:
                        if bool(view._nudge_split_by_px(dx)):
                            self._press_x = int(event.globalPosition().x())
                    except Exception:
                        pass
                event.accept()
                return
        except Exception:
            pass
        try:
            super().mouseMoveEvent(event)
        except Exception:
            pass

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        try:
            self._press_x = None
        except Exception:
            pass
        try:
            super().mouseReleaseEvent(event)
        except Exception:
            pass

def _strip_header_arrow(text: str) -> str:
    """Header title without a trailing collapse arrow (owned by a layer)."""
    display = str(text or "").strip()
    if display.endswith("▼") or display.endswith("▶"):
        display = display[:-1].strip()
    return display

def _disconnect_btn_theme(btn) -> None:
    """Drop a header button's ``theme_changed → update`` slot, if present.

    Header buttons outlive nothing: without this, every destroyed grid
    leaves dangling Python slots on the singleton signal, and a later
    theme flip re-enters them from the Qt event loop (order-dependent
    event-loop errors/segfaults across tests and folder switches).
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        ThemeManager.get_instance().theme_changed.disconnect(btn.update)
    except Exception:
        pass

class _SeriesCollapseArrowLayer(Layer):
    """Collapse arrow painted at the header button's own right edge.

    Same pattern as ``_SeriesHeaderAccentLayer``: the ▼/▶ affordance is a
    painter layer of the header ``Button`` itself, not trailing text — a
    long hub name elides (``ElideRight``) without ever clipping the arrow
    mid-glyph. The title row reserves this width via right
    ``content_padding``. Color resolves per-paint from the header-text
    token, so theme flips need no cached state.
    """

    scope = "widget"

    def __init__(self, collapsible: bool = True, collapsed: bool = False) -> None:
        self._collapsible = bool(collapsible)
        self._collapsed = bool(collapsed)

    def draw(self, ctx, tm) -> None:  # type: ignore[no-untyped-def]
        try:
            if not self._collapsible:
                return
            rect = ctx.rect.toRect() if hasattr(ctx.rect, "toRect") else ctx.rect
            arrow = "▶" if self._collapsed else "▼"
            color = _gallery_header_text_color()
            p = ctx.painter
            try:
                p.save()
            except Exception:
                pass
            try:
                font = p.font()
                try:
                    font.setPixelSize(int(scaled_px(14)))
                except Exception:
                    pass
                p.setFont(font)
            except Exception:
                pass
            try:
                p.setPen(color)
            except Exception:
                pass
            try:
                p.drawText(
                    rect,
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    arrow,
                )
            except Exception:
                pass
            try:
                p.restore()
            except Exception:
                pass
        except Exception:
            pass
