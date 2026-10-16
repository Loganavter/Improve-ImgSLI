"""Virtualized grid for the Image Gallery tab — Stage 1 MVP.
Audit-Meta: pattern=state-machine size=exempt reason="single virtualized grid view — grid_columns/series headers/pool/marquee share one layout lifecycle"

Uses ``OverlayScrollArea`` + ``OpaqueFillHost`` + ``QGridLayout`` with a
reused ``Button`` pool (responsive columns, rebuild_grid / refresh_card /
set_card_visible / apply_selection). Wide viewports grow past GRID_COLUMNS
so cards fill the right half; with 2+ sections and enough width the first
section lays out left and the rest right with a draggable center splitter.
Keeps the same contracts as
``session_picker/recent/items_view.py``: list mode reuses this ONE view and
only swaps the card builders (``ui/list/``) + placement columns.
``scaled_px`` is used for every geometry constant; no ad-hoc stylesheets —
painter pipeline owns visuals.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Label, Layer, OverlayScrollArea

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

# View modes (recent items_view parity): one view, builders + columns swap.
VIEW_GRID = "grid"
VIEW_LIST = "list"

# real_design.md:2.3 — gap 24, root pad already 24, inner margins 0
GRID_COLUMNS = 4
GRID_SPACING = 24
GRID_MARGIN = 0
GRID_MARGIN_TOP = 0
GRID_MARGIN_BOTTOM = 0
# Responsive grid: wide viewports grow past GRID_COLUMNS so the right half
# fills instead of staying empty (fixed 4 left the whole right side blank
# on ~1900px windows). Never shrinks below GRID_COLUMNS (narrow parity +
# offscreen tests stay at 4).
GRID_COLUMNS_MAX = 12
# Side-by-side series bands need at least this many total columns: the first
# section goes left, the rest stack right, with a draggable separator column
# between them (the "center splitter"). Below this — single stacked band.
GRID_BAND_MIN_TOTAL = 6
GRID_SEPARATOR_COL_W = 8
# Series-header collapse arrow: painted as a button layer at the right
# edge (never trailing text) — long hub names elide without eating it.
# The title row reserves this width via right content_padding.
SERIES_ARROW_RESERVE = 22

# Optional virtual buffer for later full virtualization; not used in MVP rebuild
# but kept for marquee hit-testing parity.
VIRTUAL_ROW_BUFFER = 1


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


# -- Wave A drag source (QDrag off gallery cards) ---------------------------
#
# Frozen seam with Wave B: mime ``application/x-imgsli-gallery-paths``
# (defined ONCE in ``ui/card.py`` as ``GALLERY_PATHS_MIME``). Payload =
# newline-separated ``file://`` URLs PLUS ``QMimeData.setUrls()`` with the
# same files (copy semantics on drop; files stay on disk — no source
# deletion anywhere). Dragged set: current selection in ``selected_order``
# when the pressed card is inside it, else the single pressed card.


def dragged_paths_for_press(owner, pressed_path: Path) -> list[Path]:
    """Cards a press-drag carries (file-manager rule, mirrors Reject).

    Pressed-inside-selection → whole selection (``selected_order`` first);
    pressed-outside → just the pressed card. Read-only (no selection write).
    """
    try:
        from tabs.image_gallery.ui.card.context_actions import _action_targets

        return list(_action_targets(owner, pressed_path))
    except Exception:
        try:
            return [pressed_path if isinstance(pressed_path, Path) else Path(pressed_path)]
        except Exception:
            return []


def build_gallery_drag_mime(paths: list[Path]) -> QMimeData:
    """Mime for a card drag: ``file://`` URLs + ``setUrls`` (same files)."""
    from tabs.image_gallery.ui.card import GALLERY_PATHS_MIME

    urls = [QUrl.fromLocalFile(str(p)) for p in (paths or [])]
    mime = QMimeData()
    try:
        mime.setData(GALLERY_PATHS_MIME, "\n".join(u.toString() for u in urls).encode("utf-8"))
    except Exception:
        pass
    try:
        mime.setUrls(urls)
    except Exception:
        pass
    return mime


def should_start_gallery_drag(press_pos: QPoint | None, cur_pos: QPoint | None) -> bool:
    """True once the press-move passes ``QApplication.startDragDistance``."""
    try:
        if press_pos is None or cur_pos is None:
            return False
        from PySide6.QtWidgets import QApplication

        return (cur_pos - press_pos).manhattanLength() >= int(QApplication.startDragDistance())
    except Exception:
        return False


def resolve_gallery_drag_pixmap(card, owner, first_path: Path):
    """Preview pixmap for a card drag (preview-only, never written back).

    Pressed card cover pixmap → item thumbnail → disk preview. May be None
    (the QDrag then carries no pixmap); callers check ``isNull`` themselves.
    """
    try:
        region = card.region("cover") if card is not None and hasattr(card, "region") else None
        pix = getattr(region, "pixmap", None)
        if pix is not None and not pix.isNull():
            return pix
    except Exception:
        pass
    try:
        items = getattr(getattr(owner, "state", None), "items", None) or []
        for it in items:
            try:
                if Path(getattr(it, "path")) == Path(first_path):
                    thumb = getattr(it, "thumbnail", None)
                    if thumb is not None and not thumb.isNull():
                        return thumb
                    break
            except Exception:
                continue
    except Exception:
        pass
    try:
        from events.image_carry import preview_pixmap_for_path

        return preview_pixmap_for_path(Path(first_path))
    except Exception:
        return None


#: QDrag preview edge (px): card covers are grid-sized (~200px+) — too big
#: to aim with under the cursor. Shrunk with aspect kept.
GALLERY_DRAG_PREVIEW_EDGE = 112


def compose_gallery_drag_pixmap(base, count: int = 1):
    """Shrink a drag source pixmap + count badge for multi-drags.

    Single image → small preview only; N > 1 → blue pill with the white
    count at the preview's top-right corner, half hanging outside
    (circle for a single digit, capsule beyond — file-manager parity). Returns None when *base* is null so callers keep
    the no-pixmap fallback.
    """
    try:
        n = int(count or 0)
    except Exception:
        n = 0
    try:
        if base is None or base.isNull():
            return None
    except Exception:
        return None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

        scaled = base.scaled(
            GALLERY_DRAG_PREVIEW_EDGE,
            GALLERY_DRAG_PREVIEW_EDGE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if n <= 1:
            return scaled
        # White on gallery-accent blue: max contrast for a small readout
        # on any thumbnail underneath (dark pills wash out on dark photos).
        # Single digit → circle; 10+ → capsule (like card pills) so the
        # text fits. Right edge pinned half-outside the preview.
        font = QFont()
        font.setBold(True)
        font.setPixelSize(18)
        badge_h = 30
        if len(str(n)) < 2:
            pill_w = badge_h
        else:
            from PySide6.QtGui import QFontMetrics

            pill_w = QFontMetrics(font).horizontalAdvance(str(n)) + 20
        badge_r = badge_h // 2
        overhang = badge_r
        out = QPixmap(scaled.width() + overhang, scaled.height() + badge_r)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        try:
            painter.drawPixmap(0, badge_r, scaled)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#0096FF"))
            bx = scaled.width() + overhang - pill_w
            painter.drawRoundedRect(bx, 0, pill_w, badge_h, badge_r, badge_r)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                bx, 0, pill_w, badge_h,
                Qt.AlignmentFlag.AlignCenter, str(n),
            )
        finally:
            painter.end()
        return out
    except Exception:
        try:
            return base
        except Exception:
            return None


def _card_drag_path(card) -> Path | None:
    """Path carried by *card* (same resolution as ``_bind_gallery_card``)."""
    try:
        item = getattr(card, "_gallery_item", None)
        path = getattr(item, "path", None) if item is not None else None
        if path is None:
            path = Path(str(card.property("gallery_path") or ""))
        return Path(path) if not isinstance(path, Path) else path
    except Exception:
        return None


class _CardPressDragFilter(QObject):
    """Card press-move → QDrag kickoff (Wave A drag source).

    Installed on each pooled card (see ``GalleryGridView._ensure_card_drag``).
    Observes only — returns False except for the release that ends a completed
    drag (swallowed so no click activates after a drop). Marquee is
    unaffected: it starts on empty-host presses only.
    """

    def __init__(self, card, view) -> None:  # type: ignore[no-untyped-def]
        super().__init__(card)
        self._card = card
        self._view = view
        self._dragged = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._card:
            return False
        try:
            etype = event.type()
        except Exception:
            return False
        if etype == QEvent.Type.MouseButtonPress:
            try:
                if event.button() == Qt.MouseButton.LeftButton:
                    path = _card_drag_path(self._card)
                    if path is not None:
                        self._dragged = False
                        self._view.note_card_press(path, event.globalPosition().toPoint())
            except Exception:
                pass
        elif etype == QEvent.Type.MouseMove:
            try:
                if (
                    not self._dragged
                    and bool(event.buttons() & Qt.MouseButton.LeftButton)
                    and self._view.maybe_start_card_drag(self._card, event.globalPosition().toPoint())
                ):
                    self._dragged = True
            except Exception:
                pass
        elif etype == QEvent.Type.MouseButtonRelease:
            try:
                self._view.clear_card_press()
            except Exception:
                pass
            if self._dragged:
                self._dragged = False
                return True
        return False


class _CardKeyFilter(QObject):
    """Card-focused keyboard policy (installed on every pooled card).

    Mirrors the session-picker card grid (``tabs.session_picker.recent
    .items_view`` — ``navigate_focus`` / ``activate_focused_card`` /
    ``_ensure_index_visible``): arrows/Home/End/Menu drive focus inside the
    grid and Return activates the focused card. This filter runs *before*
    the toolkit ``Button``'s own ``keyPressEvent``, which would otherwise
    treat Space/Return as an activation click — Space must stay
    "remove from view" for the gallery, so it is routed back to the owner
    widget's triage handler instead (``ui/card.py`` card vs ``triage_ui``).

    Pool-safe: parented to *card* (Qt keeps it alive), idempotently marked by
    ``GalleryGridView._ensure_card_keys``.
    """

    def __init__(self, card, view) -> None:  # type: ignore[no-untyped-def]
        super().__init__(card)
        self._card = card
        self._view = view

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._card:
            return False
        try:
            if event.type() != QEvent.Type.KeyPress:
                return False
        except Exception:
            return False
        try:
            key = event.key()
            mods = event.modifiers()
        except Exception:
            return False
        # Arrows / Home / End / context-menu key → grid focus navigation.
        try:
            if self._view.handle_navigation_key(event):
                return True
        except Exception:
            pass
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            try:
                if self._view._activate_card(self._card):
                    return True
            except Exception:
                pass
            return False
        try:
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        except Exception:
            ctrl = False
        if ctrl and key == Qt.Key.Key_A:
            try:
                if self._view.select_all_cards():
                    return True
            except Exception:
                pass
            return False
        if key in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Escape,
        ):
            # Preserve the gallery's remove-from-view / close semantics: the
            # Button would otherwise activate the card on Space.
            try:
                return bool(self._view.forward_key_to_owner(event))
            except Exception:
                return False
        return False


class GalleryGridNavSection:
    """``NavigationSection`` for the gallery card grid (NavigationManager).

    Registered by ``ImageGalleryTab`` under the grid view so the app-wide
    ``NavigationManager`` owns arrow consumption on cards and can trial-dispatch
    an edge press to the neighbouring section (the toolbar above the grid → an
    Up at the first row hands off; Down from the toolbar enters the grid).
    Left/Right are opted into here (``extra_keys``) because the grid is a real
    2D layout: the manager routes all four arrows to :meth:`navigate`, and a
    row-edge press declines (``False``) instead of being remapped.

    ``owns`` claims only live cards — never the toolbar, series headers or the
    host — so the toolbar rows section and this one stay disjoint.
    """

    def __init__(self, view: "GalleryGridView") -> None:
        self._view = view

    @property
    def extra_keys(self) -> frozenset:
        # Grid layout legitimately maps all four arrows spatially.
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

    def owns(self, widget) -> bool:
        try:
            if widget in set(self._view._cards_by_path.values()):
                return True
            # The empty grid area below the cards (grid host / scroll viewport,
            # incl. its viewport): a click there realigns the ring onto the
            # scroll area, which owns no keys — arrows died "reveal-only" and
            # nothing was reachable by keyboard. Claiming the scroll subtree
            # routes arrows to the grid so a key reaches the nearest card.
            scroll = getattr(self._view, "scroll_area", None)
            if scroll is not None and (
                widget is scroll
                or bool(getattr(scroll, "isAncestorOf", lambda _w: False)(widget))
            ):
                return True
            return False
        except Exception:
            return False

    def navigate(self, key: int, widget) -> bool:
        try:
            return bool(self._view.move_focus(key))
        except Exception:
            return False

    def focus_first(self, ref_x=None, *, reason):
        try:
            return bool(self._view.focus_first_card(reason=reason))
        except Exception:
            return False

    def focus_last(self, ref_x=None, *, reason):
        try:
            return bool(self._view.focus_last_card(reason=reason))
        except Exception:
            return False


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


def _section_members(entry) -> list:
    """Member list of one cluster (Series dataclass or plain list)."""
    try:
        if hasattr(entry, "members"):
            return list(getattr(entry, "members", None) or [])
        if isinstance(entry, (list, tuple)):
            return list(entry)
    except Exception:
        pass
    return []


def _cluster_series_id(cluster) -> str:
    """The owning series id of a member cluster (stable across all members)."""
    for member in cluster or ():
        sid = getattr(member, "series_id", None)
        if sid:
            return str(sid)
    return ""


def _header_button(hdr):
    """Focusable ``Button`` inside a series/tail header container, or None."""
    if hdr is None:
        return None
    if isinstance(hdr, Button):
        return hdr
    try:
        return hdr.findChild(Button)
    except Exception:
        return None


class GalleryGridView(QWidget):
    """Scrollable 4-column gallery grid with pooled Button cards."""

    # Phase 2a — visible-range signals (wave B prioritizes these paths).
    # Emitted (debounced) with a ``list[Path]`` payload in display order.
    visible_range_changed = Signal(object)
    VISIBLE_RANGE_DEBOUNCE_MS = 120
    # Overscan above/below the viewport, in screenfuls.
    VISIBLE_RANGE_OVERSCAN_SCREENS = 1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GalleryGridView")
        self._items: list[GalleryItem] = []
        self._cards_by_path: dict[str, object] = {}
        self._pool: list[object] = []
        self._selection: set[str] = set()
        self._selection_accent = gallery_selection_accent()
        self._on_toggle = None
        self._on_context_menu = None
        self._on_empty_context_menu = None
        self._on_series_context_menu = None
        self._series_header_labels: dict[int, str] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = OverlayScrollArea(self)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.set_reserve_scrollbar_space(False)
        scroll.set_corner_radius(0)
        scroll.setAcceptDrops(True)
        root.addWidget(scroll, 1)
        self.scroll_area = scroll

        host = OpaqueFillHost()
        host.setAcceptDrops(True)
        host.setMouseTracking(True)
        host.installEventFilter(self)
        scroll.setWidget(host)
        self.items_host = host

        layout = QGridLayout()
        layout.setContentsMargins(
            scaled_px(GRID_MARGIN),
            scaled_px(GRID_MARGIN_TOP),
            scaled_px(GRID_MARGIN),
            scaled_px(GRID_MARGIN_BOTTOM),
        )
        layout.setHorizontalSpacing(scaled_px(GRID_SPACING))
        layout.setVerticalSpacing(scaled_px(GRID_SPACING))
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        host.setLayout(layout)
        self.items_layout = layout

        # Phase 2a — debounced visible-range recompute. Rapid scrolls
        # restart the single-shot timer, so per-pixel valueChanged storms
        # coalesce into one emit (see _emit_visible_range).
        self._visible_debounce = QTimer(self)
        self._visible_debounce.setSingleShot(True)
        self._visible_debounce.setInterval(self.VISIBLE_RANGE_DEBOUNCE_MS)
        self._visible_debounce.timeout.connect(self._emit_visible_range)
        self._last_visible_paths: list[str] | None = None
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._schedule_visible_range_emit)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._schedule_visible_range_emit)

        # Marquee gesture lives on the host; created lazily via marquee module.
        self._marquee_gesture = None
        self._marquee_additive = False
        self._marquee_base: set[str] = set()

        # Wave A drag source: card-press origin (global pos + path). Card
        # press-drag starts a QDrag; empty-host press-drag stays marquee
        # (marquee refuses non-empty hosts) — never both from one gesture.
        self._drag_press_path: str | None = None
        self._drag_press_pos: QPoint | None = None

        # Stage 2 series grouping — headers only for clusters ≥2, singles under UNGROUPED tail.
        self._series: list[list[GalleryItem]] | None = None
        # Cross-series routing hint (task-gallery-ai-routing-jev-2026-10-09):
        # series ids that need a human first — rendered as a marker on the
        # series header. Additive; empty = no marker.
        self._series_attention: set[str] = set()
        self._ungrouped: list[GalleryItem] = []
        self._series_headers: list[QWidget] = []
        self._hub_names: list[str | None] = []
        self._collapsed: dict[int, bool] = {}
        # UNGROUPED tail collapse (index-less section) — same affordance as a
        # series header, so the provisional pool is a normal group from the
        # first frame instead of a dead, glyph-less header.
        self._tail_collapsed: bool = False
        self._series_cards: dict[int, list[object]] = {}
        # View mode: grid (4-col cards) or list (1-col rows). Pool is
        # flushed on switch so builders never mix (see set_view_mode).
        self._view_mode: str = VIEW_GRID
        # Responsive columns: how many card columns the last layout used.
        # Grows past GRID_COLUMNS on wide viewports (right half fills);
        # offscreen/hidden views stay at GRID_COLUMNS (test parity).
        self._applied_columns: int = GRID_COLUMNS
        # Center-splitter override: left-band column count set by dragging
        # the band separator (None = auto half). Reset on width change.
        self._split_left: int | None = None
        # Last side-by-side band geometry: (left_cols, right_cols, sep_col)
        # or None when sections stack in one full-width band.
        self._band_state: tuple[int, int, int] | None = None
        self._band_separator: QWidget | None = None
        # Debounced column adaptation on resizes (dragging a window edge
        # must not replan per pixel — one reflow after it settles).
        self._activity = ActivityPulse(self, translate=self._activity_translate)
        self._adapt_timer = QTimer(self)
        self._adapt_timer.setSingleShot(True)
        try:
            self._adapt_timer.setInterval(150)
        except Exception:
            pass
        try:
            self._adapt_timer.timeout.connect(self._adapt_columns_and_reflow)
        except Exception:
            pass
        # A2: mode for per-dot card colors (fidelity/camera/batch_synthetic) — proxied from widget set_triage.
        self._mode: object = None
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_gallery_theme_changed)
        except Exception:
            pass
        # Teardown hygiene: header buttons (and this view) hold
        # ``theme_changed`` slots on a process-wide singleton that does NOT
        # auto-disconnect dead Python callables — drop them when the C++
        # object dies so later theme flips never re-enter the event loop
        # through destroyed widgets (see _disconnect_btn_theme).
        try:
            self.destroyed.connect(self._disconnect_theme_slots)
        except Exception:
            pass
        try:
            self.set_fill_color(_grid_substrate_color())
        except Exception:
            pass
        # NavigationManager section (registered by the tab on activate): the
        # grid owns arrow keys on live cards + cross-section trial-dispatch.
        self._nav_section = GalleryGridNavSection(self)

    @property
    def nav_section(self) -> "GalleryGridNavSection":
        """The ``NavigationSection`` describing the card grid's arrows."""
        return self._nav_section

    def _disconnect_theme_slots(self, _obj=None) -> None:
        """Drop all ``theme_changed`` slots owned by this view (teardown).

        Runs on ``destroyed``: only signal-side surgery (no C++ touches),
        so it is safe while children are already half-gone.
        """
        try:
            from sli_ui_toolkit.managers import ThemeManager

            sig = ThemeManager.get_instance().theme_changed
        except Exception:
            return
        try:
            sig.disconnect(self._on_gallery_theme_changed)
        except Exception:
            pass
        try:
            headers = list(getattr(self, "_series_headers", []) or [])
        except Exception:
            headers = []
        for hdr in headers:
            try:
                btn = hdr.findChild(Button)
            except Exception:
                btn = None
            if btn is None:
                continue
            try:
                sig.disconnect(btn.update)
            except Exception:
                pass

    def _on_gallery_theme_changed(self) -> None:
        """Repaint grid surfaces on theme flip: accent, card fills, selection."""
        try:
            self.set_fill_color(_grid_substrate_color())
        except Exception:
            pass
        try:
            self._selection_accent = gallery_selection_accent()
        except Exception:
            pass
        try:
            cards = list(self._cards_by_path.values()) + list(self._pool)
            for card in cards:
                try:
                    card.update()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.apply_selection(self._selection)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    # -- configuration -----------------------------------------------------

    def configure(
        self,
        *,
        on_toggle=None,
        on_context_menu=None,
        on_empty_context_menu=None,
        on_series_context_menu=None,
    ) -> None:
        self._on_toggle = on_toggle
        self._on_context_menu = on_context_menu
        self._on_empty_context_menu = on_empty_context_menu
        if on_series_context_menu is not None:
            self._on_series_context_menu = on_series_context_menu

    # -- view mode (recent items_view parity) --------------------------------

    def set_view_mode(self, mode: object) -> None:
        """Switch grid/list builders + placement (one view, recent parity).

        Accepts ``"grid"``/``"list"`` (``VIEW_GRID``/``VIEW_LIST``) or bool
        (``True`` = list, matching the toolbar toggle). Destroys the card
        pool and live cards (builders must never mix), then rebuilds from
        the current items and re-applies the live series state.
        """
        try:
            if isinstance(mode, bool):
                want = VIEW_LIST if mode else VIEW_GRID
            else:
                want = VIEW_LIST if str(mode).lower() == VIEW_LIST else VIEW_GRID
        except Exception:
            want = VIEW_GRID
        if want == self._view_mode and self._cards_by_path:
            return
        # Capture keyboard focus BEFORE the pool teardown (cards are destroyed
        # and rebuilt in the new builder) so it returns to the same path.
        _focus_snapshot = self._focus_snapshot()
        try:
            series = list(self._series) if self._series is not None else None
            hubs = list(self._hub_names)
            collapsed = dict(self._collapsed)
        except Exception:
            series, hubs, collapsed = None, [], {}
        # Destroy pool (mixed builders must never share it).
        try:
            for card in list(self._pool):
                try:
                    # Hide before unparenting: a still-visible widget handed a
                    # new top-level parent can flash for a frame.
                    card.hide()
                    card.setParent(None)
                    card.deleteLater()
                except Exception:
                    pass
            self._pool = []
        except Exception:
            pass
        self._view_mode = want
        if want == VIEW_GRID:
            # Fresh mode: re-derive responsive columns for this viewport
            # (a list→grid switch must not inherit a stale narrow count).
            try:
                self._applied_columns = int(self._compute_columns())
            except Exception:
                pass
        try:
            items = list(self._items)
        except Exception:
            items = []
        try:
            self.rebuild_grid(items)
        except Exception:
            return
        if series is not None:
            try:
                self.set_series(series, hub_names=hubs, collapsed=collapsed)
            except Exception:
                pass
        # Belt-and-braces commit: the flat rebuild and the series relayout
        # each activate their own branch, but the mode swap must never leave
        # a stale frame even if one of those branches fail-opened above.
        try:
            self.items_layout.activate()
        except Exception:
            logger.debug("set_view_mode: layout activate failed", exc_info=True)
        self._restore_focus(_focus_snapshot)

    def _card_height_px(self) -> int:
        return scaled_px(LIST_CARD_H) if self._view_mode == VIEW_LIST else scaled_px(GALLERY_CARD_H)

    def _sync_series_column_widths(self, *, series_mode: bool) -> None:
        """Keep series headers full-width when clusters collapse.

        A header spans ``grid_columns``. With every cluster collapsed the
        layout holds no cards, so ``QGridLayout`` shrinks its columns to
        zero and the header ``Button`` elides its text (``ElideRight``) —
        e.g. ``SERIES 1 · hub · 3 VARIANTS ▼`` degrades to ``SERIES 1 ·``.
        Pinning each column to the card width in series mode keeps the
        header at the full grid width; flat mode resets to 0 so a
        partially-filled last row does not force extra width.

        The layout is NOT recreated across a grid↔list switch, so every
        column a previous mode may have pinned has to be reset — leftover
        min-widths on the now-empty grid columns (1..3 in list mode) squeeze
        column 0 to its sizeHint and the series header elides/disappears.
        """
        try:
            cols = int(self.grid_columns)
        except Exception:
            return
        # Reset EVERY column the layout currently carries, not just the ones
        # the current mode uses: the responsive/banded grid can pin more than
        # GRID_COLUMNS (wide viewports grow, bands add a separator column), and
        # a grid→list switch keeps the same QGridLayout. Leftover card-width
        # minimums on those higher columns (e.g. 4,5 after a 6-col banded grid)
        # steal width from the stretched list column and leave a dead strip on
        # the right.
        try:
            _layout_cols = int(self.items_layout.columnCount())
        except Exception:
            _layout_cols = 0
        max_cols = max(int(GRID_COLUMNS), int(cols or 1), int(_layout_cols))
        is_list = self._view_mode == VIEW_LIST
        try:
            # List: fill horizontally (one stretched column). Grid: natural
            # left-aligned card layout.
            self.items_layout.setAlignment(
                Qt.AlignmentFlag.AlignTop
                if is_list
                else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            )
        except Exception:
            pass
        for c in range(max_cols):
            try:
                self.items_layout.setColumnStretch(c, 1 if (is_list and c == 0) else 0)
            except Exception:
                continue
            try:
                self.items_layout.setColumnMinimumWidth(c, 0)
            except Exception:
                continue
        if is_list or not series_mode or cols <= 1:
            return
        try:
            card_w = int(scaled_px(GALLERY_CARD_W))
        except Exception:
            return
        for c in range(cols):
            try:
                self.items_layout.setColumnMinimumWidth(c, card_w)
            except Exception:
                continue

    def _grid_stride_px(self) -> int:
        """Card width + gap: horizontal pitch of one grid column."""
        try:
            return int(scaled_px(GALLERY_CARD_W)) + int(scaled_px(GRID_SPACING))
        except Exception:
            return 274

    def _available_grid_width(self) -> int:
        """Viewport width available for cards (0 when unknown/hidden)."""
        try:
            for src in (self.scroll_area.viewport(), self.items_host, self):
                try:
                    w = int(src.width())
                except Exception:
                    continue
                if w > 0:
                    return w
        except Exception:
            pass
        return 0

    def _compute_columns(self) -> int:
        """Column count for the current viewport width.

        Wide viewports grow past GRID_COLUMNS so cards fill the right half
        instead of hugging the left edge. Never shrinks below GRID_COLUMNS
        (narrow-window parity; hidden/offscreen views keep 4).
        """
        if self._view_mode == VIEW_LIST:
            return 1
        try:
            if not self.isVisible():
                return GRID_COLUMNS
        except Exception:
            return GRID_COLUMNS
        avail = self._available_grid_width()
        if avail <= 0:
            return GRID_COLUMNS
        try:
            spacing = int(scaled_px(GRID_SPACING))
        except Exception:
            spacing = 24
        stride = self._grid_stride_px()
        if stride <= 0:
            return GRID_COLUMNS
        try:
            fit = int((avail + spacing) // stride)
        except Exception:
            return GRID_COLUMNS
        if fit < GRID_COLUMNS:
            return GRID_COLUMNS
        return max(GRID_COLUMNS, min(GRID_COLUMNS_MAX, fit))

    def resizeEvent(self, event) -> None:  # noqa: N802
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self._adapt_timer.start()
        except Exception:
            pass

    def _adapt_columns_and_reflow(self) -> None:
        """Recompute columns after a resize settles; reflow when changed."""
        try:
            if self._view_mode == VIEW_LIST:
                return
            new = int(self._compute_columns())
        except Exception:
            return
        try:
            if new == int(self._applied_columns):
                return
            self._applied_columns = int(new)
            self._split_left = None
        except Exception:
            return
        try:
            if self._series is not None:
                self._rebuild_series()
            elif getattr(self, "_rebuild_pending", None) is not None:
                try:
                    self._rebuild_pending = None
                    self._rebuild_index = 0
                except Exception:
                    pass
                self._reflow_flat()
            else:
                self._reflow_flat()
        except Exception:
            logger.debug("_adapt_columns_and_reflow failed", exc_info=True)

    def _reflow_flat(self) -> None:
        """Re-place flat-grid cards for a new column count (no pool churn).

        Unlike ``rebuild_grid`` this never recycles cards: live widgets are
        only re-added at new positions, so a window-edge drag reflows
        without content refreshes.
        """
        try:
            items = list(self._items or [])
        except Exception:
            items = []
        if not items:
            try:
                self._hide_band_separator()
            except Exception:
                pass
            self._sync_series_column_widths(series_mode=False)
            self._update_host_height(0)
            return
        while self.items_layout.count():
            try:
                self.items_layout.takeAt(0)
            except Exception:
                break
        try:
            self._hide_band_separator()
        except Exception:
            pass
        for idx, item in enumerate(items):
            try:
                key = str(item.path)
            except Exception:
                continue
            card = self._cards_by_path.get(key)
            if card is None:
                try:
                    card = self._acquire_card(item)
                except Exception:
                    continue
                self._cards_by_path[key] = card
            try:
                r, c = divmod(idx, self.grid_columns)
            except Exception:
                r, c = idx, 0
            try:
                self.items_layout.addWidget(card, r, c)
                card.show()
            except Exception:
                logger.debug("_reflow_flat: card placement failed", exc_info=True)
        try:
            self.apply_selection(self._selection)
        except Exception:
            pass
        self._sync_series_column_widths(series_mode=False)
        self._update_host_height(len(items))
        try:
            self.items_layout.activate()
        except Exception:
            logger.debug("_reflow_flat: layout activate failed", exc_info=True)
        try:
            self._schedule_visible_range_emit()
        except Exception:
            pass

    # -- side-by-side series bands + center splitter ---------------------

    def _bands_active(self) -> bool:
        """True when the last series layout split sections into two bands."""
        try:
            return self._band_state is not None
        except Exception:
            return False

    def _plan_bands(self, sections: list[dict]) -> list[tuple[list[dict], int, int]]:
        """Split *sections* into layout bands.

        Returns ``[(sections, band_cols, col_offset), ...]`` — one entry for
        the stacked full-width band, two when the viewport fits side-by-side
        series (first section left, the rest right, separator column between).
        """
        try:
            total = int(self.grid_columns)
        except Exception:
            total = GRID_COLUMNS
        if self._view_mode == VIEW_LIST or total < GRID_BAND_MIN_TOTAL or len(sections) < 2:
            return [(list(sections), int(total), 0)]
        left = self._split_left
        try:
            left = int(left) if left is not None else int(total // 2)
        except Exception:
            left = int(total // 2)
        left = max(2, min(int(total) - 3, int(left)))
        right = int(total) - int(left) - 1  # one column for the separator
        if left < 2 or right < 2:
            return [(list(sections), int(total), 0)]
        return [([sections[0]], int(left), 0), (list(sections[1:]), int(right), int(left) + 1)]

    def _plan_band_entries(
        self,
        subset: list[dict],
        band_cols: int,
        col_off: int,
        base_row: int,
        headers: list,
        hdr_start: int,
    ) -> tuple[list[tuple], int, int]:
        """Plan entries for one band; returns (entries, rows_used, hdr_next)."""
        entries: list[tuple] = []
        row = int(base_row)
        hi = int(hdr_start)
        for sec in subset:
            try:
                header = headers[hi]
                hi += 1
            except Exception:
                continue
            entries.append((header, row, int(col_off), 1, int(band_cols)))
            row += 1
            if sec.get("collapsed"):
                continue
            for pos, item in enumerate(sec.get("items") or []):
                try:
                    card = self._cards_by_path.get(str(item.path))
                except Exception:
                    card = None
                if card is None:
                    continue
                try:
                    r, c = divmod(int(pos), max(1, int(band_cols)))
                except Exception:
                    r, c = int(pos), 0
                entries.append((card, row + r, int(col_off) + c, 1, 1))
            try:
                n = len(sec.get("items") or [])
                rows_needed = (n + int(band_cols) - 1) // int(band_cols) if n else 0
            except Exception:
                rows_needed = 0
            row += int(rows_needed)
        return entries, int(row - base_row), int(hi)

    def _ensure_band_separator(self):
        """Lazily create the draggable center-splitter handle."""
        sep = getattr(self, "_band_separator", None)
        try:
            import shiboken6

            if sep is not None and not shiboken6.isValid(sep):
                sep = None
        except Exception:
            pass
        if sep is None:
            try:
                sep = _BandSeparatorHandle(self, self.items_host)
                self._band_separator = sep
            except Exception:
                return None
        return sep

    def _hide_band_separator(self) -> None:
        try:
            sep = getattr(self, "_band_separator", None)
            if sep is not None:
                try:
                    self.items_layout.removeWidget(sep)
                except Exception:
                    pass
                try:
                    sep.hide()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._band_state = None
        except Exception:
            pass

    def _nudge_split_by_px(self, dx: int) -> bool:
        """Shift the center split by a drag delta; True when replanned."""
        try:
            if self._view_mode == VIEW_LIST or not self._bands_active():
                return False
            total = int(self._applied_columns)
            st = self._band_state or (total // 2, total - total // 2 - 1, total // 2)
            left = int(st[0])
            stride = self._grid_stride_px()
            if stride <= 0:
                return False
            step = int(round(float(dx) / float(stride)))
            if step == 0:
                return False
            want = max(2, min(int(total) - 3, int(left) + int(step)))
            if want == int(left):
                return False
            self._split_left = int(want)
            self._rebuild_series()
            return True
        except Exception:
            return False

    def set_split_left(self, left_cols: int) -> None:
        """Programmatic center-split (tests / restore); replans when banded."""
        try:
            total = int(self._applied_columns)
            self._split_left = max(2, min(int(total) - 3, int(left_cols)))
        except Exception:
            return
        try:
            if self._series is not None:
                self._rebuild_series()
        except Exception:
            pass

    def nav_columns_for(self, path=None) -> int:
        """Up/Down arrow step for *path*'s band (band width when banded)."""
        try:
            if self._view_mode == VIEW_LIST:
                return 1
            st = getattr(self, "_band_state", None)
            if not st:
                return int(self.grid_columns)
            left, right, sep_col = int(st[0]), int(st[1]), int(st[2])
            col = None
            if path is not None:
                try:
                    card = self._cards_by_path.get(str(path))
                    if card is not None:
                        idx = self.items_layout.indexOf(card)
                        if idx >= 0:
                            col = int(self.items_layout.getItemPosition(idx)[1])
                except Exception:
                    col = None
            if col is None:
                return int(self.grid_columns)
            return int(left if col < sep_col else right)
        except Exception:
            try:
                return int(self.grid_columns)
            except Exception:
                return GRID_COLUMNS

    # -- keyboard focus navigation (grid + list) ---------------------------
    #
    # Mirrors the working sibling ``tabs.session_picker.recent.items_view``:
    # index-driven focus movement over the live cards with an explicit
    # "scroll target into view" pass. Cards keep *real* Qt focus (the toolkit
    # Button ring / NavigationManager model) — no second focus model, no
    # custom "current index" ring.

    def _focus_reason(self):
        """FocusReason for navigation grants (keyboard ring follows the manager)."""
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

            return NavigationManager.get_instance().current_focus_reason()
        except Exception:
            return Qt.FocusReason.OtherFocusReason

    def _live_cards_in_order(self) -> list:
        """Live, enabled cards in layout (row, col) display order.

        Series headers and recycled pool cards are excluded; banded layouts
        are read row-major (col offset orders left band before right band
        within a row), which is the same order ``_plan_band_entries`` lays
        them out.
        """
        out: list[tuple[int, int, object]] = []
        for _path, card in list(getattr(self, "_cards_by_path", {}).items()):
            try:
                if not card.isEnabled():
                    continue
            except Exception:
                continue
            try:
                idx = self.items_layout.indexOf(card)
            except Exception:
                idx = -1
            if idx < 0:
                continue
            try:
                pos = self.items_layout.getItemPosition(idx)
                r, c = int(pos[0]), int(pos[1])
            except Exception:
                r, c = int(idx), 0
            out.append((r, c, card))
        out.sort(key=lambda t: (t[0], t[1]))
        return [c for _r, _c, c in out]

    def _live_headers_in_order(self) -> list:
        """Live, enabled series/tail header ``Button``s in layout (row, col) order."""
        out: list[tuple[int, int, object]] = []
        for hdr in list(getattr(self, "_series_headers", []) or []):
            btn = _header_button(hdr)
            if btn is None:
                continue
            try:
                if not btn.isEnabled():
                    continue
            except Exception:
                continue
            try:
                idx = self.items_layout.indexOf(hdr)
            except Exception:
                idx = -1
            if idx < 0:
                continue
            try:
                pos = self.items_layout.getItemPosition(idx)
                r, c = int(pos[0]), int(pos[1])
            except Exception:
                r, c = int(idx), 0
            out.append((r, c, btn))
        out.sort(key=lambda t: (t[0], t[1]))
        return [b for _r, _c, b in out]

    def focused_card(self):
        """The live card holding Qt focus, or None (mirrors RecentItemsView)."""
        try:
            from PySide6.QtWidgets import QApplication

            focused = QApplication.focusWidget()
        except Exception:
            return None
        if focused is None:
            return None
        for card in list(getattr(self, "_cards_by_path", {}).values()):
            if card is focused:
                return card
        return None

    def focused_header(self):
        """The live series/tail header ``Button`` holding Qt focus, or None."""
        try:
            from PySide6.QtWidgets import QApplication

            focused = QApplication.focusWidget()
        except Exception:
            return None
        if focused is None:
            return None
        for hdr in list(getattr(self, "_series_headers", []) or []):
            btn = _header_button(hdr)
            if btn is not None and (btn is focused or hdr is focused):
                return btn
        return None

    def ensure_card_visible(self, card) -> None:
        """Scroll the focused card into the viewport (RecentItemsView parity)."""
        try:
            from sli_ui_toolkit.managers import scaled_px as _scaled

            margin = int(_scaled(GRID_SPACING))
        except Exception:
            margin = 24
        try:
            self.scroll_area.ensureWidgetVisible(card, 0, margin)
        except Exception:
            pass

    def focus_card(self, card, reason=None) -> bool:
        """Grant keyboard focus to *card* (or header Button) and reveal it.

        *reason* (a ``NavigationSection.focus_first/focus_last`` grant) wins;
        otherwise the ring modality comes from
        ``NavigationManager.current_focus_reason()`` — never a literal
        ``OtherFocusReason``.
        """
        if card is None:
            return False
        if not isinstance(card, Button):
            btn = _header_button(card)
            if btn is not None:
                card = btn
        grant = reason if reason is not None else self._focus_reason()
        try:
            card.setFocus(grant)
        except Exception:
            try:
                card.setFocus(self._focus_reason())
            except Exception:
                return False
        self.ensure_card_visible(card)
        return True

    def focus_first_card(self, reason=None) -> bool:
        cards = self._live_cards_in_order()
        if cards:
            return self.focus_card(cards[0], reason=reason)
        headers = self._live_headers_in_order()
        return self.focus_card(headers[0], reason=reason) if headers else False

    def focus_last_card(self, reason=None) -> bool:
        cards = self._live_cards_in_order()
        if cards:
            return self.focus_card(cards[-1], reason=reason)
        headers = self._live_headers_in_order()
        return self.focus_card(headers[-1], reason=reason) if headers else False

    def _nav_bands(self) -> list[list[dict]]:
        """Vertical bands of ``{header, cards, cols}`` blocks for Up/Down nav."""
        try:
            base_cols = max(1, int(self.grid_columns))
        except Exception:
            base_cols = GRID_COLUMNS
        hdr_entries: list[tuple[int, int, object]] = []
        for hdr in list(getattr(self, "_series_headers", []) or []):
            btn = _header_button(hdr)
            if btn is None:
                continue
            try:
                if not btn.isEnabled():
                    continue
                idx = self.items_layout.indexOf(hdr)
            except Exception:
                idx = -1
            if idx < 0:
                continue
            try:
                pos = self.items_layout.getItemPosition(idx)
                r, c = int(pos[0]), int(pos[1])
            except Exception:
                r, c = int(idx), 0
            hdr_entries.append((r, c, btn))
        if not hdr_entries:
            return [[{
                "header": None,
                "cards": self._live_cards_in_order(),
                "cols": base_cols,
            }]]
        card_entries: list[tuple[int, int, object]] = []
        for _path, card in list(getattr(self, "_cards_by_path", {}).items()):
            try:
                if not card.isEnabled():
                    continue
                idx = self.items_layout.indexOf(card)
            except Exception:
                idx = -1
            if idx < 0:
                continue
            try:
                pos = self.items_layout.getItemPosition(idx)
                r, c = int(pos[0]), int(pos[1])
            except Exception:
                r, c = int(idx), 0
            card_entries.append((r, c, card))
        st = getattr(self, "_band_state", None)
        if st:
            left_cols, right_cols, sep_col = int(st[0]), int(st[1]), int(st[2])
            band_specs = [(0, max(1, left_cols)), (1, max(1, right_cols))]
        else:
            sep_col = None
            band_specs = [(0, base_cols)]
        bands: list[list[dict]] = []
        for band_id, band_cols in band_specs:
            b_hdrs = [
                (r, c, btn)
                for r, c, btn in hdr_entries
                if (0 if (sep_col is None or c < sep_col) else 1) == band_id
            ]
            b_hdrs.sort(key=lambda t: (t[0], t[1]))
            if not b_hdrs:
                continue
            b_cards = [
                (r, c, card)
                for r, c, card in card_entries
                if (0 if (sep_col is None or c < sep_col) else 1) == band_id
            ]
            b_cards.sort(key=lambda t: (t[0], t[1]))
            blocks = [
                {"header": btn, "row": r, "cards": [], "cols": band_cols}
                for r, _c, btn in b_hdrs
            ]
            for cr, _cc, card in b_cards:
                target_block = blocks[0]
                for blk in blocks:
                    if int(blk["row"]) <= cr:
                        target_block = blk
                    else:
                        break
                target_block["cards"].append(card)
            bands.append(blocks)
        return bands

    @staticmethod
    def _block_entry(blk):
        """Target entering *blk* from a neighbouring row: header, else 1st card."""
        if blk.get("header") is not None:
            return blk["header"]
        cards = blk.get("cards") or []
        return cards[0] if cards else None

    @staticmethod
    def _block_exit(blk):
        """Target leaving *blk* upward: first card of its last row, else header."""
        cards = blk.get("cards") or []
        if not cards:
            return blk.get("header")
        cols = max(1, int(blk.get("cols") or 1))
        return cards[((len(cards) - 1) // cols) * cols]

    def move_focus(self, key) -> bool:
        """Move focus one step for *key*: 2D in grid, Up/Down in list.

        Series headers participate in vertical navigation:
        - Up from the first row of a series block -> that series' header.
        - Down from a header -> the first card of its series (or next header
          when collapsed).
        - Up from the topmost header (or first row with no header) -> yields
          (``False``) so NavigationManager hands off upward.
        - Left/Right on a header yield at row edges without wrapping.

        Side-by-side bands are one vertical strip per band, so Up/Down walk
        on into the adjacent band instead of dead-ending at its edge.
        """
        cards = self._live_cards_in_order()
        headers = self._live_headers_in_order()
        if not cards and not headers:
            return False
        cur_card = self.focused_card()
        cur_hdr = self.focused_header() if cur_card is None else None
        if (cur_card is None or cur_card not in cards) and (
            cur_hdr is None or cur_hdr not in headers
        ):
            return self.focus_card(cards[0] if cards else headers[0])

        if cur_hdr is not None:
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self.ensure_card_visible(cur_hdr)
                return False
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                bands = self._nav_bands()
                for band_i, band_blocks in enumerate(bands):
                    for bi, blk in enumerate(band_blocks):
                        if blk["header"] is not cur_hdr:
                            continue
                        if key == Qt.Key.Key_Down:
                            if blk["cards"]:
                                return self.focus_card(blk["cards"][0])
                            nxt = None
                            if bi + 1 < len(band_blocks):
                                nxt = self._block_entry(band_blocks[bi + 1])
                            elif band_i + 1 < len(bands) and bands[band_i + 1]:
                                nxt = self._block_entry(bands[band_i + 1][0])
                            if nxt is not None:
                                return self.focus_card(nxt)
                            self.ensure_card_visible(cur_hdr)
                            return False
                        # Key_Up
                        prev = band_blocks[bi - 1] if bi > 0 else None
                        if prev is None and band_i > 0 and bands[band_i - 1]:
                            prev = bands[band_i - 1][-1]
                        if prev is not None:
                            tgt = self._block_exit(prev)
                            if tgt is not None:
                                return self.focus_card(tgt)
                        self.ensure_card_visible(cur_hdr)
                        return False
                self.ensure_card_visible(cur_hdr)
                return False
            return False

        try:
            idx = cards.index(cur_card)
        except ValueError:
            return self.focus_card(cards[0])
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = -1 if key == Qt.Key.Key_Left else 1
            target = idx + step
            if target < 0 or target >= len(cards):
                self.ensure_card_visible(cur_card)
                return False
            return self.focus_card(cards[target])
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            try:
                cols = int(self.nav_columns_for(_card_drag_path(cur_card)))
            except Exception:
                cols = int(self.grid_columns)
            if cols < 1:
                cols = 1
            bands = self._nav_bands()
            for band_i, band_blocks in enumerate(bands):
                for bi, blk in enumerate(band_blocks):
                    blk_cards = blk["cards"]
                    if cur_card not in blk_cards:
                        continue
                    pos = blk_cards.index(cur_card)
                    if key == Qt.Key.Key_Up:
                        if pos >= cols:
                            return self.focus_card(blk_cards[pos - cols])
                        if blk["header"] is not None:
                            return self.focus_card(blk["header"])
                        prev = band_blocks[bi - 1] if bi > 0 else None
                        if prev is None and band_i > 0 and bands[band_i - 1]:
                            prev = bands[band_i - 1][-1]
                        if prev is not None:
                            tgt = self._block_exit(prev)
                            if tgt is not None:
                                return self.focus_card(tgt)
                        self.ensure_card_visible(cur_card)
                        return False
                    # Key_Down
                    if pos + cols < len(blk_cards):
                        return self.focus_card(blk_cards[pos + cols])
                    nxt = None
                    if bi + 1 < len(band_blocks):
                        nxt = self._block_entry(band_blocks[bi + 1])
                    elif band_i + 1 < len(bands) and bands[band_i + 1]:
                        nxt = self._block_entry(bands[band_i + 1][0])
                    if nxt is not None:
                        return self.focus_card(nxt)
                    self.ensure_card_visible(cur_card)
                    return False
            step = -cols if key == Qt.Key.Key_Up else cols
            target = idx + step
            if target < 0 or target >= len(cards):
                self.ensure_card_visible(cur_card)
                return False
            return self.focus_card(cards[target])
        return False

    def _activate_card(self, card) -> bool:
        """Activate *card* via the existing click path (→ Quick Look)."""
        path = _card_drag_path(card)
        if path is None:
            return False
        try:
            self._handle_toggle(path)
            return True
        except Exception:
            return False

    def _menu_card(self, card) -> bool:
        """Open *card*'s context menu via the existing host callback."""
        path = _card_drag_path(card)
        if path is None:
            return False
        try:
            self._handle_context_menu(path)
            return True
        except Exception:
            return False

    def select_all_cards(self) -> bool:
        """Ctrl+A → select every pooled item (``use_cases.selection``)."""
        try:
            from tabs.image_gallery.use_cases import selection as _selection

            owner = self._drag_owner()
            if owner is None:
                return False
            _selection.select_all(owner)
            return True
        except Exception:
            return False

    def forward_key_to_owner(self, event) -> bool:
        """Route *event* to the owner widget's triage key handler.

        Space/Delete remove-from-view and Escape live in
        ``triage_ui.handle_key`` (reached through ``ImageGalleryWidget
        .keyPressEvent``); forwarding keeps one implementation of those
        semantics instead of a second copy here.
        """
        owner = getattr(self, "_gallery_widget", None)
        if owner is None:
            return False
        try:
            owner.keyPressEvent(event)
            return True
        except Exception:
            return False

    def handle_navigation_key(self, event) -> bool:
        """Consume navigation keys (arrows / Home / End / Menu) for the grid.

        Called from ``GalleryGridView.keyPressEvent`` and from the owner
        widget's ``keyPressEvent`` (focus on the widget but not yet a card)
        and from ``_CardKeyFilter`` (card focused). Returns True when the
        event was handled.
        """
        try:
            key = event.key()
        except Exception:
            return False
        cards = self._live_cards_in_order()
        headers = self._live_headers_in_order()
        if not cards and not headers:
            return False
        # Two branches on purpose (not one four-key tuple): the grid maps all
        # four arrows, but the arrow-redirection dogma forbids grouping
        # Down+Right / Up+Left in a single test expression.
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            return bool(self.move_focus(key))
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return bool(self.move_focus(key))
        if key == Qt.Key.Key_Home:
            return bool(self.focus_first_card())
        if key == Qt.Key.Key_End:
            return bool(self.focus_last_card())
        if key == Qt.Key.Key_Menu:
            card = self.focused_card() or (cards[0] if cards else None)
            return bool(self._menu_card(card)) if card is not None else False
        return False

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Grid view itself focused (widget-level arrows bootstrap onto the
        # first card); ignore otherwise so unhandled keys keep propagating.
        try:
            if self.handle_navigation_key(event):
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def _focus_snapshot(self):
        """(path/header-id, order index) of the focused card or header."""
        card = self.focused_card()
        if card is not None:
            path = _card_drag_path(card)
            try:
                index = self._live_cards_in_order().index(card)
            except Exception:
                index = None
            return (str(path) if path is not None else None, index)
        hdr = self.focused_header()
        if hdr is not None:
            try:
                name = str(hdr.objectName() or "")
            except Exception:
                name = ""
            try:
                index = self._live_headers_in_order().index(hdr)
            except Exception:
                index = None
            return (f"header:{name}" if name else None, index)
        return (None, None)

    def _restore_focus(self, snapshot) -> bool:
        """Re-focus a :meth:`_focus_snapshot` after a rebuild/recycle.

        Never grants focus when the snapshot was empty (focus was not on a
        card or header) — a rebuild driven by the toolbar filter must not
        steal focus.
        """
        try:
            path, index = snapshot if snapshot else (None, None)
        except Exception:
            path, index = None, None
        if isinstance(path, str) and path.startswith("header:"):
            want_name = path[len("header:"):]
            headers = self._live_headers_in_order()
            for btn in headers:
                try:
                    if str(btn.objectName() or "") == want_name and btn.isVisible() and btn.isEnabled():
                        return bool(self.focus_card(btn))
                except Exception:
                    continue
            if headers and index is not None:
                try:
                    target = max(0, min(int(index), len(headers) - 1))
                except Exception:
                    target = 0
                return bool(self.focus_card(headers[target]))
            cards = self._live_cards_in_order()
            return bool(self.focus_card(cards[0])) if cards else False
        if path:
            card = self._cards_by_path.get(str(path))
            if card is not None:
                try:
                    if card.isVisible() and card.isEnabled():
                        return bool(self.focus_card(card))
                except Exception:
                    pass
        if index is None:
            return False
        cards = self._live_cards_in_order()
        if not cards:
            headers = self._live_headers_in_order()
            return bool(self.focus_card(headers[0])) if headers else False
        try:
            target = max(0, min(int(index), len(cards) - 1))
        except Exception:
            target = 0
        return bool(self.focus_card(cards[target]))

    # -- public API expected by controller/widget --------------------------

    # Systemic fix 2026-08-26: O(N) sync rebuild blocked UI for 1k+ items
    # (measured 7s for 1037). Chunk via event-loop so UI stays responsive.
    _REBUILD_CHUNK = 80
    _rebuild_pending: list[GalleryItem] | None = None
    _rebuild_index: int = 0

    def _resolve_mode(self, explicit: object = None) -> object:
        """Resolve current gallery mode (fidelity/camera/batch_synthetic) for per-dot colors."""
        if explicit is not None:
            return explicit
        if getattr(self, "_mode", None) is not None:
            return self._mode  # type: ignore[attr-defined]
        # Fallback: walk parent / window for _mode or state.mode (widget/controller).
        for obj in (self.parent(), self.window()):
            if obj is None:
                continue
            m = getattr(obj, "_mode", None)
            if m is not None:
                return m
            st = getattr(obj, "state", None)
            if st is not None:
                m2 = getattr(st, "mode", None)
                if m2 is not None:
                    return m2
            # Direct parent widget (ImageGalleryWidget) may hold _mode
            try:
                pw = obj
                if hasattr(pw, "_mode") and getattr(pw, "_mode") is not None:
                    return getattr(pw, "_mode")
            except Exception:
                pass
        # Also try parent chain for cards host
        try:
            p = self.parent()
            while p is not None:
                m = getattr(p, "_mode", None)
                if m is not None:
                    return m
                p = p.parent()  # type: ignore[attr-defined]
        except Exception:
            pass
        return None

    def rebuild_grid(self, items: list[GalleryItem], mode: object = None, *, paint_selection: bool = True, flat_ungrouped: bool = False) -> None:
        """Clear and rebuild the 4-column grid from *items* (pool-reusing Buttons).

        ``mode`` controls per-dot artifact palette; proxied to ``build_gallery_card``.
        ``paint_selection=False`` skips the closing selection sweep — the
        widget passes it when a series restore follows in the same tick and
        sweeps once itself (else every rebuild pays two full sweeps).
        ``flat_ungrouped=True`` wraps a header-less flat pool in a single
        ``UNGROUPED`` section on the SAME pass, so a fresh pool never paints
        nameless while the triage worker is pending. Opt-in: the widget asks
        for it on a first load (no series to restore); callers that restore a
        live series in the same tick keep the flat primitive.
        """
        # Keyboard focus continuity: cards are recycled and re-acquired, so
        # capture the focused path now and re-focus its card once the pool is
        # rebuilt (mirrors _rebuild_series' focus preserve).
        _focus_snapshot = self._focus_snapshot()
        if mode is not None:
            self._mode = mode
        else:
            # Try to keep last mode or resolve from parent if not yet set.
            resolved = self._resolve_mode()
            if resolved is not None and getattr(self, "_mode", None) is None:
                self._mode = resolved
        # Cancel pending chunk if rebuild called again (e.g. folder switch)
        try:
            self._rebuild_pending = None
            self._rebuild_index = 0
        except Exception:
            pass
        # Return live cards to pool.
        for path in list(self._cards_by_path):
            self._recycle_card(path)
        # Remove any leftover widgets from layout (headers + empty label etc. not managed here).
        self._clear_series_headers()
        try:
            self._hide_band_separator()
        except Exception:
            pass
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            w = item.widget()
            if w is not None and w not in list(self._cards_by_path.values()) and w not in self._pool and w not in self._series_headers:
                try:
                    # Stillborn-toplevel guard (see _clear_series_headers):
                    # never orphan a visible widget.
                    w.hide()
                except Exception:
                    pass
                w.setParent(None)

        self._items = list(items)
        self._series = None
        self._ungrouped = []
        self._hub_names = []
        self._collapsed = {}
        self._series_cards = {}
        self._cards_by_path.clear()

        # Eager responsive columns for THIS build. Otherwise the first frame
        # lays out at the stale count (GRID_COLUMNS=4) and only the debounced
        # ``_adapt_timer`` (150 ms) grows it — the "first frames in 2 rows, then
        # one row" jump (log: cols=4 at rebuild -> cols=9 +135 ms).
        if self._view_mode == VIEW_GRID:
            try:
                self._applied_columns = int(self._compute_columns())
            except Exception:
                pass

        if not items:
            self._sync_series_column_widths(series_mode=False)
            self._update_host_height(0)
            return

        # Large folders: chunk to keep event loop alive (systemic vs 1037 sync)
        if len(items) > self._REBUILD_CHUNK * 2:
            self._rebuild_pending = list(items)
            self._rebuild_index = 0
            self._rebuild_flat_ungrouped = bool(flat_ungrouped)
            self._rebuild_focus_path = _focus_snapshot
            self._update_host_height(len(items))  # reserve height early so scrollbar correct
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._rebuild_next_chunk)
            return

        for idx, item in enumerate(items):
            card = self._acquire_card(item)
            self._cards_by_path[str(item.path)] = card
            r, c = divmod(idx, self.grid_columns)
            self.items_layout.addWidget(card, r, c)
            card.show()

        if paint_selection:
            self.apply_selection(self._selection)
        self._sync_series_column_widths(series_mode=False)
        self._update_host_height(len(items))
        # Commit the rows' geometry synchronously. Without this the added
        # cards only lay out on the following event-loop turn, so a view
        # switch on a flat (no live series yet) grid paints one frame of
        # uncommitted rows — list columns collapse to the thumb width and
        # the title elides/overlaps until the layout catches up.
        try:
            self.items_layout.activate()
        except Exception:
            logger.debug("rebuild_grid: layout activate failed", exc_info=True)
        self._schedule_visible_range_emit()
        if flat_ungrouped:
            self._promote_flat_ungrouped()
        # Re-focus the card that held focus before the rebuild (a rebuilt
        # header/group move must not drop the keyboard ring; a removed focused
        # card falls through to the nearest still-live card).
        self._restore_focus(_focus_snapshot)

    def _promote_flat_ungrouped(self) -> None:
        """Wrap a header-less flat pool in a single ``UNGROUPED`` section.

        A flat rebuild must not paint nameless cards while the triage worker
        is pending: every item belongs under ``UNGROUPED`` from the first
        frame. No-op when a series view is already live (``_series`` is not
        ``None``) or the pool is empty. Reuses the already-built cards —
        ``set_series`` routes through ``_rebuild_series``, which recycles and
        reflows them in place.
        """
        if getattr(self, "_series", None) is not None:
            return
        try:
            if not list(getattr(self, "_items", None) or []):
                return
        except Exception:
            return
        try:
            self.set_series([], hub_names=[], collapsed={})
        except Exception:
            logger.debug("rebuild_grid: flat→UNGROUPED promotion failed", exc_info=True)

    def _rebuild_next_chunk(self) -> None:
        pending = getattr(self, "_rebuild_pending", None)
        if pending is None:
            return
        start = getattr(self, "_rebuild_index", 0)
        end = min(start + self._REBUILD_CHUNK, len(pending))
        for idx in range(start, end):
            item = pending[idx]
            card = self._acquire_card(item)
            self._cards_by_path[str(item.path)] = card
            r, c = divmod(idx, self.grid_columns)
            self.items_layout.addWidget(card, r, c)
            card.show()
        self._rebuild_index = end
        if end < len(pending):
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._rebuild_next_chunk)
        else:
            # Done — finalize selection after all chunks
            self._rebuild_pending = None
            self._rebuild_index = 0
            self.apply_selection(self._selection)
            # Chunked fill finished — now wrap the flat pool in UNGROUPED
            # (deferred so the chunks stay responsive; the header lands the
            # moment the pool is complete).
            if getattr(self, "_rebuild_flat_ungrouped", False):
                self._promote_flat_ungrouped()
            # Same synchronous commit as the non-chunked path: the last
            # chunk must not leave the tail rows unlaid-out for a frame.
            try:
                self.items_layout.activate()
            except Exception:
                logger.debug("_rebuild_next_chunk: layout activate failed", exc_info=True)
            self._schedule_visible_range_emit()
            self._restore_focus(getattr(self, "_rebuild_focus_path", None))
            self._rebuild_focus_path = None

    # -- Phase 2a visible range ----------------------------------------
    # Wave B (thumbnail prioritization) calls visible_paths() and listens
    # to visible_range_changed. Geometry comes from layout/card geometry
    # only — never from pixmap data or arrival order. Pure additive API:
    # no existing rebuild/refresh/selection/scroll path changes behavior.

    def visible_paths(self) -> list[Path]:
        """Paths of cards intersecting the viewport (+ vertical overscan).

        Returns the ``item.path`` objects (the same identity
        ``controller._find_item`` compares with ``==``), in top-to-bottom
        display order (card ``y``, then ``x``). A partially visible card
        at the viewport edge counts as visible. Empty grid -> ``[]``.
        """
        try:
            items = list(getattr(self, "_items", None) or [])
        except Exception:
            return []
        if not items:
            return []
        try:
            viewport = self.scroll_area.viewport()
            vh = viewport.height()
            vw = viewport.width()
        except Exception:
            return [it.path for it in items]
        if vh <= 0 or vw <= 0:
            # Not laid out yet (never shown): fail open with everything
            # in display order so callers never starve thumbnails.
            return [it.path for it in items]
        try:
            vbar = self.scroll_area.verticalScrollBar()
            hbar = self.scroll_area.horizontalScrollBar()
            vval = int(vbar.value())
            hval = int(hbar.value())
        except Exception:
            vval, hval = 0, 0
        try:
            overscan = int(vh * self.VISIBLE_RANGE_OVERSCAN_SCREENS)
        except Exception:
            overscan = int(vh)
        y0 = vval - overscan
        y1 = vval + vh + overscan
        x0 = hval
        x1 = hval + vw
        scored: list[tuple[int, int, object]] = []
        for item in items:
            try:
                card = self._cards_by_path.get(str(item.path))
            except Exception:
                card = None
            if card is None:
                continue
            try:
                g = card.geometry()
            except Exception:
                continue
            # Card geometry is in items_host coordinates; the visible
            # host rect starts at the scrollbar values. Inclusive edges:
            # a partially visible card at the boundary counts.
            if g.right() >= x0 and g.left() <= x1 and g.bottom() >= y0 and g.top() <= y1:
                scored.append((int(g.y()), int(g.x()), item.path))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [p for _, _, p in scored]

    def _schedule_visible_range_emit(self, *_args) -> None:
        """Restart the single-shot debounce timer (scroll storms coalesce)."""
        try:
            self._visible_debounce.start()
        except Exception:
            pass

    def _emit_visible_range(self) -> None:
        """Recompute and emit visible_range_changed if the set changed."""
        try:
            paths = self.visible_paths()
        except Exception:
            return
        try:
            key = [str(p) for p in paths]
        except Exception:
            return
        if key == self._last_visible_paths:
            return
        self._last_visible_paths = key
        try:
            self.visible_range_changed.emit(list(paths))
        except Exception:
            pass

    # -- Stage 2 series grouping ----------------------------------------

    def set_series(
        self,
        series: list[list[GalleryItem]] | None,
        hub_names: list[str | None] | None = None,
        collapsed: dict[int, bool] | set[int] | list[bool] | None = None,
        mode: object = None,
    ) -> None:
        """Rebuild grid with series sections.

        *series* — list of clusters as member lists (``Series`` dataclasses
        accepted too). Clusters with ≥1 members render as own SERIES
        sections — 1-member manual sections (S2 sync-move leftovers) stay
        visible instead of dissolving. Items in no cluster are collected
        under an ``UNGROUPED`` tail. ``None`` or empty clears series mode
        and falls back to the flat UNGROUPED view for all items.
        *hub_names* — per-series hub display name (e.g. source file name).
        *collapsed* — mapping of series index → collapsed bool (or set of collapsed indices).
        *mode* — gallery mode for per-dot colors (fidelity/camera/batch_synthetic), proxied to cards.
        """
        # Full rebuild like rebuild_grid — cancel a pending chunked rebuild
        # first, or its QTimer tick would re-add cards on top of the series.
        try:
            self._rebuild_pending = None
            self._rebuild_index = 0
        except Exception:
            pass
        if mode is not None:
            self._mode = mode
        else:
            resolved = self._resolve_mode()
            if resolved is not None and getattr(self, "_mode", None) is None:
                self._mode = resolved
        if not series:
            # No clusters — show UNGROUPED section for all items (real_design.md:59)
            filtered: list[list[GalleryItem]] = []
            # Fall through to UNGROUPED handling below
        else:
            # S2: keep every non-empty cluster as its own section
            # (1-member manual sections stay visible); Series dataclasses
            # and plain member lists both accepted.
            filtered = [_section_members(s) for s in series if len(_section_members(s)) >= 1]
        if not filtered:
            # No valid clusters — all items are ungrouped, show UNGROUPED header
            try:
                all_items = list(self._items) if getattr(self, "_items", None) else []
            except Exception:
                all_items = []
            self._series = []
            self._ungrouped = list(all_items)
            self._hub_names = []
            # Preserve collapsed
            try:
                self._collapsed = dict(getattr(self, "_collapsed", {}) or {})
            except Exception:
                self._collapsed = {}
            # Ensure host shows UNGROUPED even for 1 item
            self._rebuild_series()
            return
        # Determine ungrouped as items not in any cluster.
        try:
            member_paths = {str(it.path) for cl in filtered for it in cl}
        except Exception:
            member_paths = set()
        try:
            all_items = list(self._items)
        except Exception:
            all_items = []
        # If _items was not yet populated (caller passed series before flat list),
        # derive flat list from series + maybe explicit ungrouped tail inside series.
        if not all_items:
            all_items = [it for cl in filtered for it in cl]
            member_paths = {str(it.path) for cl in filtered for it in cl}
        ungrouped = [it for it in all_items if str(it.path) not in member_paths]
        self._series = filtered
        self._ungrouped = ungrouped
        if hub_names is not None:
            try:
                self._hub_names = list(hub_names)[: len(filtered)]
                while len(self._hub_names) < len(filtered):
                    self._hub_names.append(None)
            except Exception:
                self._hub_names = [None] * len(filtered)
        else:
            self._hub_names = [None] * len(filtered)
        norm_collapsed: dict[int, bool] = {}
        try:
            if isinstance(collapsed, dict):
                for k, v in collapsed.items():
                    try:
                        norm_collapsed[int(k)] = bool(v)
                    except Exception:
                        continue
            elif isinstance(collapsed, set):
                for k in collapsed:
                    try:
                        norm_collapsed[int(k)] = True
                    except Exception:
                        continue
            elif isinstance(collapsed, list):
                for idx, val in enumerate(collapsed):
                    if bool(val):
                        norm_collapsed[idx] = True
            elif collapsed is None:
                norm_collapsed = dict(getattr(self, "_collapsed", {}) or {})
                # keep only indices within range
                norm_collapsed = {k: v for k, v in norm_collapsed.items() if 0 <= k < len(filtered)}
            else:
                norm_collapsed = {}
        except Exception:
            norm_collapsed = {}
        self._collapsed = norm_collapsed
        self._rebuild_series()

    def _retitle_header(self, header, text: str, index, collapsed: bool = False) -> None:
        """Refresh a reused series header in place (no destroy/create).

        Updates the label text, object names and the collapse-button closure
        (which captures the section index — a reused widget at a new
        position must toggle the new section). UNGROUPED headers (index
        None) get their toggle disconnected. The collapse arrow stays a
        painter layer (never text): flags + title reserve flip here so a
        series ↔ UNGROUPED slot reuse never clips the arrow.
        """
        is_series = index is not None
        display = _strip_header_arrow(text)
        try:
            header.setObjectName(
                f"GallerySeriesHeader_{index}" if is_series else "GallerySeriesHeader_ungrouped"
            )
        except Exception:
            pass
        try:
            btn = header.findChild(Button)
        except Exception:
            btn = None
        if btn is None:
            return
        # Keep the click affordance in sync with the slot's new role: a
        # header reused from an UNGROUPED slot (created disabled) must become
        # clickable when it now fronts a real, collapsible series — and vice
        # versa. Without this the collapse toggle is dead on a retitled slot.
        try:
            # Every header (series OR the UNGROUPED tail) is a normal,
            # clickable collapsible group.
            btn.setEnabled(True)
        except Exception:
            pass
        try:
            btn.setObjectName(
                f"GallerySeriesHeaderBtn_{index}" if is_series else "GallerySeriesHeader_ungrouped_btn"
            )
        except Exception:
            pass
        try:
            btn.update_region(
                "_main",
                rows=[ButtonRow(
                    text=display.upper(), size=16, color=_gallery_header_text_color(),
                    h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0, elide=True,
                )],
            )
        except Exception:
            pass
        try:
            # A reused header slot may flip series ↔ UNGROUPED: repoint the
            # accent layer's palette (accent vs dialog.border) with it, flip
            # the arrow layer's visibility/state, and reserve/clear the
            # title's right padding so the arrow never overlaps text.
            _painter = getattr(btn, "_painter", None)
            for _layer in list(getattr(_painter, "layers", None) or []):
                if isinstance(_layer, _SeriesHeaderAccentLayer):
                    _layer._collapsible = bool(is_series)
                elif isinstance(_layer, _SeriesCollapseArrowLayer):
                    _layer._collapsible = True
                    _layer._collapsed = bool(collapsed)
            try:
                btn.setContentPadding(
                    (scaled_px(15), 0, scaled_px(SERIES_ARROW_RESERVE), 0)
                )
            except Exception:
                pass
            btn.update()
        except Exception:
            pass
        try:
            btn.clicked.disconnect()
        except Exception:
            pass
        # Only disconnect what was actually wired: an UNGROUPED header slot is
        # built WITHOUT a customContextMenuRequested connection, and a bare
        # disconnect() on an unconnected signal emits a RuntimeWarning (not an
        # exception, so the except below would not catch it).
        if getattr(btn, "_gallery_ctx_menu_wired", False):
            try:
                btn.customContextMenuRequested.disconnect()
            except Exception:
                pass
            try:
                btn._gallery_ctx_menu_wired = False  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            btn.clicked.connect(lambda _checked=False, idx=index: self._toggle_collapse(idx))  # type: ignore[misc]
        except Exception:
            pass
        if is_series:
            try:
                self._series_header_labels[index] = display
            except Exception:
                pass
            # A reused header slot may have been built for the UNGROUPED tail
            # (no menu wiring); (re)attach the series context menu here too.
            try:
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda _pos, i=index, b=btn: self._handle_series_context(b, i, _pos)
                )
                btn._gallery_ctx_menu_wired = True  # type: ignore[attr-defined]
            except Exception:
                pass

    def set_series_attention(self, series_ids) -> None:
        """Mark series that need a human first (additive routing hint).

        Stores the id set rendered as a series-header marker and re-titles in
        place (never a teardown). Empty/None clears the marker. Never touches
        cards, rank or selection.
        """
        try:
            self._series_attention = {str(s) for s in (series_ids or ()) if s}
        except Exception:
            self._series_attention = set()
        try:
            self._rebuild_series()
        except Exception:
            pass

    def _rebuild_series(self) -> None:
        """Internal: rebuild with series headers + UNGROUPED tail."""
        # Preserve scroll + keyboard focus across the teardown: heights land
        # identical, but the intermediate collapse clamps the scrollbar to 0
        # and reparenting drops focus to None (keyboard dead until a click).
        try:
            _bar = self.scroll_area.verticalScrollBar()
            _saved_scroll = int(_bar.value())
        except Exception:
            _bar = None
            _saved_scroll = 0
        _focus_snapshot = self._focus_snapshot()
        # --- surgical reconcile (no teardown) ---
        # Reuses header widgets (text refreshed in place) and surviving
        # cards (content updated, never hidden/reparented). Previously every
        # regroup destroyed all headers (deleteLater) and round-tripped all
        # cards through hide+reparent+show — per-card ParentChange storms,
        # badge resyncs, focus loss and header-button blink, log-proven on
        # every drop.
        if self._series is None:
            for path in list(self._cards_by_path):
                self._recycle_card(path)
            self._clear_series_headers()
            try:
                self._hide_band_separator()
            except Exception:
                pass
            while self.items_layout.count():
                try:
                    self.items_layout.takeAt(0)
                except Exception:
                    break
            self._cards_by_path.clear()
            self._series_cards = {}
            self._sync_series_column_widths(series_mode=False)
            return
        try:
            _mode = self._resolve_mode()
        except Exception:
            _mode = None
        # 1. plan sections (same order/texts as the old full rebuild).
        def _hdr(key: str, default: str, **kw) -> str:
            try:
                return str(self._activity_translate(key, default)).format(**kw)
            except Exception:
                return default.format(**kw)

        _sections: list[dict] = []
        for idx, cluster in enumerate(list(self._series or [])):
            hub = self._hub_names[idx] if idx < len(self._hub_names) else None
            is_collapsed = bool(self._collapsed.get(idx, False))
            if hub:
                header_text = _hdr(
                    "image_gallery.series.header_hub",
                    "SERIES {n} · {hub} · {count} VARIANTS",
                    n=idx + 1, hub=hub, count=len(cluster),
                )
            else:
                header_text = _hdr(
                    "image_gallery.series.header",
                    "SERIES {n} · {count} images",
                    n=idx + 1, count=len(cluster),
                )
            if _cluster_series_id(cluster) in self._series_attention:
                header_text = (
                    f"{header_text} · "
                    f"{_hdr('image_gallery.series.needs_attention', 'NEEDS ATTENTION')}"
                )
            _sections.append({
                "kind": "series", "index": idx, "hub": hub,
                "collapsed": is_collapsed, "text": header_text,
                "items": list(cluster) if not is_collapsed else [],
            })
        if list(getattr(self, "_ungrouped", []) or []):
            _ung = list(getattr(self, "_ungrouped", []) or [])
            _sections.append({
                "kind": "tail", "index": None, "hub": None,
                "collapsed": bool(getattr(self, "_tail_collapsed", False)),
                "text": _hdr(
                    "image_gallery.series.ungrouped",
                    "UNGROUPED · {count}",
                    count=len(_ung),
                ),
                "items": _ung,
            })
        # 2. cards: recycle gone paths only.
        try:
            _wanted = {str(getattr(it, "path", None)) for s in _sections for it in s["items"]}
        except Exception:
            _wanted = set()
        for path in list(self._cards_by_path):
            try:
                if str(path) not in _wanted:
                    self._recycle_card(path)
            except Exception:
                continue
        # 3. cards: update kept in place (no hide/reparent — filters, pins
        # and focus survive), acquire genuinely new ones.
        self._series_cards = {}
        for sec in _sections:
            if sec["kind"] == "series" and sec["collapsed"]:
                continue
            cards: list[object] = []
            for item in sec["items"]:
                try:
                    sp = str(item.path)
                except Exception:
                    continue
                card = self._cards_by_path.get(sp)
                if card is None:
                    try:
                        card = self._acquire_card(item)
                    except Exception:
                        continue
                    self._cards_by_path[sp] = card
                else:
                    try:
                        update_gallery_card(card, item, mode=_mode)  # type: ignore[arg-type]
                    except Exception:
                        pass
                cards.append(card)
            if sec["kind"] == "series":
                self._series_cards[sec["index"]] = cards
        # 4. headers: reuse by position (text refreshed, collapse rebound),
        # destroy extras, create missing.
        try:
            _old_headers = list(getattr(self, "_series_headers", []) or [])
        except Exception:
            _old_headers = []
        _new_headers: list = []
        for pos, sec in enumerate(_sections):
            if pos < len(_old_headers):
                hdr = _old_headers[pos]
                try:
                    self._retitle_header(hdr, sec["text"], sec["index"], sec["collapsed"])
                except Exception:
                    pass
                _new_headers.append(hdr)
            else:
                try:
                    hdr = self._make_series_header(
                        sec["text"], len(sec["items"]), hub_name=sec["hub"],
                        collapsed=sec["collapsed"], index=sec["index"],
                    )
                except Exception:
                    continue
                _new_headers.append(hdr)
        for hdr in _old_headers[len(_new_headers):]:
            try:
                self.items_layout.removeWidget(hdr)
            except Exception:
                pass
            try:
                # Hide before orphaning (stillborn-toplevel guard).
                hdr.hide()
                hdr.setParent(None)
                hdr.deleteLater()
            except Exception:
                pass
        self._series_headers = _new_headers
        # 5. plan target cells, then relayout ONLY when the live grid already
        # diverges. Append already places the fresh card at the tail; the
        # set_triage that follows describes the SAME plan. Re-adding every
        # widget identically there is a second visible reposition (bug 3:
        # "jumps twice"). Compute the target and skip the takeAt/addWidget
        # storm when the layout already matches — set_series then converges
        # to a no-op instead of jumping.
        #
        # Wide viewports split sections into two side-by-side bands (first
        # section left, the rest right, draggable separator between) so the
        # right half fills instead of staying empty; narrow windows stack
        # every section full-width as before.
        _plan: list[tuple] = []
        # Same eager responsive columns as rebuild_grid: a series view built
        # before the adapt timer must not plan at the stale GRID_COLUMNS.
        if self._view_mode == VIEW_GRID:
            try:
                self._applied_columns = int(self._compute_columns())
            except Exception:
                pass
        # Discriminator for the "splitter flashes on the first frames" report:
        # banding needs >= 2 sections, so log the section set + band inputs at
        # every series rebuild. Run with IMGSLI_GALLERY_DEBUG=1 to capture it.
        try:
            from tabs.image_gallery.debug import gallery_debug as _gdbg

            _gdbg(
                "layout: sections=%d kinds=%s ungrouped=%d cols=%s split_left=%s band_state=%s",
                len(_sections),
                [s.get("kind") for s in _sections],
                len(list(getattr(self, "_ungrouped", []) or [])),
                getattr(self, "grid_columns", None),
                getattr(self, "_split_left", None),
                getattr(self, "_band_state", None),
            )
        except Exception:
            pass
        try:
            _bands = self._plan_bands(_sections)
        except Exception:
            _bands = [(_sections, self.grid_columns, 0)]
        _band_state_new = None
        _plan_rows = 0
        _plan_hdr = 0
        for _subset, _bcols, _coff in _bands:
            try:
                _entries, _used, _plan_hdr = self._plan_band_entries(
                    _subset, int(_bcols), int(_coff), 0, _new_headers, int(_plan_hdr))
            except Exception:
                continue
            _plan.extend(_entries)
            _plan_rows = max(int(_plan_rows), int(_used))
        if len(_bands) > 1:
            try:
                _sep = self._ensure_band_separator()
                _sep_col = int(_bands[0][1])  # left band width == separator column
                if _sep is not None:
                    _plan.append((_sep, 0, _sep_col, max(1, int(_plan_rows)), 1))
                    _band_state_new = (int(_bands[0][1]), int(_bands[1][1]), int(_sep_col))
            except Exception:
                _band_state_new = None
        try:
            self._band_state = _band_state_new
        except Exception:
            pass
        _layout_matches = False
        try:
            _layout_matches = self.items_layout.count() == len(_plan)
            if _layout_matches:
                for _w, _r, _c, _rs, _cs in _plan:
                    _idx = self.items_layout.indexOf(_w)
                    if _idx < 0:
                        _layout_matches = False
                        break
                    _gr, _gc, _grs, _gcs = self.items_layout.getItemPosition(_idx)
                    if (int(_gr), int(_gc), int(_grs), int(_gcs)) != (_r, _c, _rs, _cs):
                        _layout_matches = False
                        break
        except Exception:
            _layout_matches = False
        if _layout_matches:
            current_row = _plan_rows
            for _w, _r, _c, _rs, _cs in _plan:
                try:
                    _w.show()
                except Exception:
                    logger.debug("_rebuild_series: reveal matched widget failed", exc_info=True)
        else:
            # Drop layout items only (widgets stay alive/parented), re-add per
            # plan (stacked or banded — same math as the plan above).
            while self.items_layout.count():
                try:
                    self.items_layout.takeAt(0)
                except Exception:
                    break
            if _band_state_new is None:
                try:
                    self._hide_band_separator()
                except Exception:
                    pass
            current_row = 0
            for _w, _r, _c, _rs, _cs in _plan:
                try:
                    self.items_layout.addWidget(_w, _r, _c, _rs, _cs)
                    _w.show()
                except Exception:
                    logger.debug("_rebuild_series: widget placement failed", exc_info=True)
            current_row = _plan_rows

        self._sync_series_column_widths(series_mode=True)
        try:
            # The separator column is a thin handle, not a card column —
            # _sync above pins every column to the card width.
            if self._band_state is not None:
                self.items_layout.setColumnMinimumWidth(
                    int(self._band_state[2]), scaled_px(GRID_SEPARATOR_COL_W))
        except Exception:
            pass
        self.apply_selection(self._selection)
        self._update_host_height_for_series(current_row)
        if not _layout_matches:
            # Commit the new geometry synchronously before the next paint.
            # Without this the re-added cards lay out only on the following
            # event-loop turn, so an already-visible neighbour (e.g. the
            # UNGROUPED tail sliding up/down) keeps its stale rect for one
            # frame and paints over the freshly revealed series cards.
            try:
                self.items_layout.activate()
            except Exception:
                logger.debug("_rebuild_series: layout activate failed", exc_info=True)
        try:
            if _bar is not None:
                _bar.setValue(min(int(_saved_scroll), int(_bar.maximum())))
        except Exception:
            pass
        try:
            self._restore_focus(_focus_snapshot)
        except Exception:
            pass

    def append_new_cards(self, items: list[GalleryItem]) -> None:
        """Append-only fast path for pool growth (drop-append).

        Keeps every painted card/header in place — no flat teardown, no
        restore pass. New cards land in the UNGROUPED tail when a series
        view is live (creating the tail header on first use). A flat
        pre-triage pool (no headers yet) is promoted to a single UNGROUPED
        section in the SAME pass, so the freshly appended card(s) are
        grouped immediately instead of waiting for the triage worker
        (bug 2: first-drop grouping delay). Falls back to a full
        ``rebuild_grid`` when there is no safe incremental plan (e.g. a
        chunked rebuild still in flight).
        """
        fresh = [it for it in (items or [])]
        if not fresh:
            return
        if getattr(self, "_rebuild_pending", None) is not None:
            self.rebuild_grid(list(getattr(self, "_items", []) or []) + list(fresh))
            return
        try:
            self._items = list(getattr(self, "_items", []) or []) + list(fresh)
        except Exception:
            logger.debug("append_new_cards: item-list update failed", exc_info=True)
        if getattr(self, "_series", None) is None:
            # Flat, pre-triage pool (no headers yet): promote the whole pool
            # to one UNGROUPED section now. `_rebuild_series` reuses the
            # already-parented cards and lays them under the new tail header
            # in one pass — the appended card is grouped the moment it
            # arrives, with no reliance on a later triage delivery.
            try:
                self._series = []
                self._ungrouped = list(getattr(self, "_items", []) or [])
                self._hub_names = []
                # _rebuild_series sweeps selection itself — no second sweep.
                self._rebuild_series()
            except Exception:
                logger.debug(
                    "append_new_cards: flat→UNGROUPED promotion failed", exc_info=True
                )
            return
        try:
            ungrouped = list(getattr(self, "_ungrouped", []) or [])
            # Side-by-side bands anchor the tail in the right band with its
            # own column math — the incremental rowCount plan below only fits
            # the stacked band, so banded appends go through the surgical
            # _rebuild_series instead (reuses every live card/header).
            try:
                _n_series = len(list(getattr(self, "_series", []) or []))
                _tail_after = len(ungrouped) + len(fresh)
                _secs_after = int(_n_series) + (1 if int(_tail_after) > 0 else 0)
            except Exception:
                _secs_after = 0
            if self._bands_active() or self._would_band_with(_secs_after):
                try:
                    self._ungrouped = ungrouped + list(fresh)
                except Exception:
                    logger.debug("append_new_cards: ungrouped sync failed", exc_info=True)
                for item in fresh:
                    try:
                        _card = self._acquire_card(item)
                        self._cards_by_path[str(item.path)] = _card
                    except Exception:
                        continue
                try:
                    self._rebuild_series()
                except Exception:
                    logger.debug("append_new_cards: banded rebuild failed", exc_info=True)
                return
            # Ensure exactly one UNGROUPED tail header widget exists. State
            # (_ungrouped) and the actual header widget can disagree after a
            # fail-open earlier pass; anchoring cards to a header that isn't
            # there is what threw the appended card to a default position.
            headers = list(getattr(self, "_series_headers", []) or [])
            has_tail = any(
                getattr(h, "objectName", lambda: "")() == "GallerySeriesHeader_ungrouped"
                for h in headers
            )
            total = len(ungrouped) + len(fresh)
            if has_tail:
                self._refresh_ungrouped_header_count(total)
            else:
                row = int(self.items_layout.rowCount())
                header = self._make_series_header(
                    self._ungrouped_header_text(total), total,
                    hub_name=None,
                    collapsed=bool(getattr(self, "_tail_collapsed", False)), index=None,
                )
                self._series_headers.append(header)
                self.items_layout.addWidget(header, row, 0, 1, self._tail_header_span())
                header.show()
            base = int(self.items_layout.rowCount())
            pos0 = len(ungrouped)
            # Anchor new cards to the live ungrouped block, not to
            # rowCount: rowCount counts header rows too, so continuing
            # from it overshoots one row per header above (live: the
            # 2nd card lands a row low on its own — reads as a nameless
            # group until triage rebuilds). The tail block is last and
            # compact, so its start row = rowCount - its row span.
            try:
                _cols = max(1, int(self.grid_columns))
            except Exception:
                _cols = 1
            try:
                _span = -(-int(pos0) // _cols) if pos0 else 0
                _start = int(base) - int(_span) if _span else int(base)
            except Exception:
                _start = int(base)
            for pos, item in enumerate(fresh):
                card = self._acquire_card(item)
                self._cards_by_path[str(item.path)] = card
                r, c = divmod(pos0 + pos, _cols)
                self.items_layout.addWidget(card, _start + r, c)
                card.show()
            try:
                self._ungrouped = ungrouped + list(fresh)
            except Exception:
                logger.debug("append_new_cards: ungrouped sync failed", exc_info=True)
        except Exception:
            logger.debug("append_new_cards: grouped tail append failed", exc_info=True)
        try:
            self._update_host_height_for_series(int(self.items_layout.rowCount()))
        except Exception:
            logger.debug("append_new_cards: host height sync failed", exc_info=True)
        try:
            self.apply_selection(self._selection)
        except Exception:
            logger.debug("append_new_cards: selection sweep failed", exc_info=True)

    def _tail_header_span(self) -> int:
        """Column span for the UNGROUPED tail header (right band when split)."""
        try:
            st = getattr(self, "_band_state", None)
            if st:
                return max(1, int(st[1]))
        except Exception:
            pass
        try:
            return max(1, int(self.grid_columns))
        except Exception:
            return GRID_COLUMNS

    def _would_band_with(self, sections_count: int) -> bool:
        """True when *sections_count* sections would lay out side-by-side."""
        try:
            if self._view_mode == VIEW_LIST:
                return False
            return int(self._applied_columns) >= GRID_BAND_MIN_TOTAL and int(sections_count) >= 2
        except Exception:
            return False

    def _refresh_ungrouped_header_count(self, total: int) -> None:
        """Recreate only the UNGROUPED tail header with a fresh count.

        One widget swapped in place (layout row preserved) — not the full
        teardown ``_rebuild_series`` performs. Everything else (series
        headers, all cards) is untouched.
        """
        try:
            headers = list(getattr(self, "_series_headers", []) or [])
            pos = next(
                (i for i, h in enumerate(headers)
                 if getattr(h, "objectName", lambda: "")() == "GallerySeriesHeader_ungrouped"),
                None,
            )
            if pos is None:
                return
            old = headers[pos]
            try:
                row = self._row_of(old)
            except Exception:
                row = None
            try:
                self.items_layout.removeWidget(old)
            except Exception:
                pass
            try:
                _old_btn = old.findChild(Button)
                if _old_btn is not None:
                    _disconnect_btn_theme(_old_btn)
            except Exception:
                pass
            try:
                # Same stillborn-toplevel guard as _clear_series_headers:
                # hide before setParent(None), or the visible header maps
                # its own toplevel + activation token for a few ms.
                old.hide()
            except Exception:
                pass
            try:
                old.setParent(None)
                old.deleteLater()
            except Exception:
                pass
            header = self._make_series_header(
                self._ungrouped_header_text(int(total)), int(total),
                hub_name=None,
                collapsed=bool(getattr(self, "_tail_collapsed", False)), index=None,
            )
            headers[pos] = header
            self._series_headers = headers
            try:
                if row is None:
                    row = int(self.items_layout.rowCount())
                self.items_layout.addWidget(header, row, 0, 1, self._tail_header_span())
                header.show()
            except Exception:
                pass
        except Exception:
            pass

    def _row_of(self, widget) -> int | None:
        """Layout row of *widget* in the items grid (None when absent)."""
        try:
            idx = self.items_layout.indexOf(widget)
            if idx < 0:
                return None
            r, _, _, _ = self.items_layout.getItemPosition(idx)
            return int(r)
        except Exception:
            return None

    def _make_series_header(
        self,
        text: str,
        count: int = 0,
        hub_name: str | None = None,
        collapsed: bool = False,
        index: int | None = None,
    ) -> QWidget:
        """Series header — ghost Button with the 3×14 accent bar as its own layer (real_design.md:59)."""
        is_collapsible = index is not None
        # The collapse arrow is a painter layer at the button's right edge,
        # never trailing text — long hub names elide without clipping it.
        display = _strip_header_arrow(text)
        # Container with 3×14 bar
        container = QWidget(self.items_host)
        container.setObjectName(f"GallerySeriesHeader_{index}" if is_collapsible else "GallerySeriesHeader_ungrouped")
        try:
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
        lay.setSpacing(0)
        if is_collapsible:
            _header_col3 = _gallery_header_text_color()

            btn = Button(
                regions=[
                    ButtonRegion(
                        id="_main",
                        rows=[ButtonRow(text=display.upper(), size=16, color=_header_col3, h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0, elide=True)],
                    )
                ],
                variant="ghost",
                size=(0, scaled_px(24)),
                # 3px bar + 12px gap the sibling widget used to occupy;
                # right reserve keeps the elided title clear of the arrow layer.
                content_padding=(scaled_px(15), 0, scaled_px(SERIES_ARROW_RESERVE), 0),
                extra_layers=[_SeriesHeaderAccentLayer(collapsible=is_collapsible),
                                _SeriesDropTargetLayer(),
                                _SeriesCollapseArrowLayer(collapsible=True, collapsed=collapsed)],
                parent=container,
            )
            btn.setObjectName(f"GallerySeriesHeaderBtn_{index}")
            # NOTE: no theme_changed.connect(btn.update) here on purpose —
            # Button.__init__ already subscribes, and a duplicate connection
            # is undisconnectable by slot (disconnect removes one, later
            # calls return False), leaving a stale slot that fires into the
            # dead wrapper on the next theme flip (order-dependent suite
            # crash: stale Button.update with garbage self).
            try:
                btn.clicked.connect(lambda _checked=False, idx=index: self._toggle_collapse(idx))  # type: ignore[misc]
            except Exception:
                pass
            try:
                self._series_header_labels[index] = display
            except Exception:
                pass
            # Right-click on the series header opens a menu (Ask AI over the
            # whole series); left-click still collapses/expands.
            try:
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda _pos, i=index, b=btn: self._handle_series_context(b, i, _pos)
                )
                btn._gallery_ctx_menu_wired = True  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                btn.setFixedHeight(scaled_px(24))
            except Exception:
                pass
            lay.addWidget(btn, 1)
            try:
                lay.setAlignment(btn, Qt.AlignmentFlag.AlignVCenter)
            except Exception:
                pass
            return container
        try:
            _header_col4 = _gallery_header_text_color()

            btn = Button(
                regions=[
                    ButtonRegion(
                        id="_main",
                        rows=[ButtonRow(text=display.upper(), size=16, color=_header_col4, h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0, elide=True)],
                    )
                ],
                variant="ghost",
                size=(0, scaled_px(24)),
                # 3px bar + 12px gap the sibling widget used to occupy; the
                # right reserve keeps the elided title clear of the arrow
                # layer. UNGROUPED is a NORMAL collapsible group (same
                # affordance as a series), so the provisional pool is not a
                # dead, glyph-less header while clustering runs.
                content_padding=(scaled_px(15), 0, scaled_px(SERIES_ARROW_RESERVE), 0),
                extra_layers=[_SeriesHeaderAccentLayer(collapsible=is_collapsible),
                                _SeriesDropTargetLayer(),
                                _SeriesCollapseArrowLayer(collapsible=True, collapsed=bool(collapsed))],
                parent=container,
            )
            btn.setObjectName("GallerySeriesHeader_ungrouped_btn")
            # NOTE: no theme_changed.connect(btn.update) — see above,
            # Button.__init__ already subscribes; duplicates are
            # undisconnectable and crash the suite via stale slots.
            try:
                btn.setFixedHeight(scaled_px(24))
            except Exception:
                pass
            try:
                btn.clicked.connect(lambda _checked=False: self._toggle_collapse(None))  # type: ignore[misc]
            except Exception:
                pass
            lay.addWidget(btn, 1)
            return container
        except Exception:
            # Fallback: Label container with theme token
            container = QWidget(self.items_host)
            container.setObjectName("GallerySeriesHeader")
            from PySide6.QtWidgets import QHBoxLayout

            lay = QHBoxLayout(container)
            lay.setContentsMargins(scaled_px(8), scaled_px(4), scaled_px(8), scaled_px(4))
            lay.setSpacing(0)
            lbl = Label(display, pixel_size=16, parent=container)
            lbl.setObjectName("GallerySeriesHeaderLabel")
            try:
                lbl.setBold(True)
            except Exception:
                pass
            lay.addWidget(lbl)
            lay.addStretch(1)
            try:
                from sli_ui_toolkit.managers import ThemeManager
                from ui.theming import resolve_theme_color

                token = "gallery.grid.background"
                bg = resolve_theme_color(ThemeManager.get_instance(), token)
                apply_opaque_widget_fill(container, bg)
            except Exception:
                pass
            try:
                container.setFixedHeight(scaled_px(24))
            except Exception:
                pass
            return container

    def _toggle_collapse(self, index: int | None) -> None:
        """Toggle collapsed state for series *index* (None = UNGROUPED tail)."""
        if index is None:
            try:
                self._tail_collapsed = not bool(getattr(self, "_tail_collapsed", False))
            except Exception:
                return
            try:
                self._rebuild_series()
            except Exception:
                pass
            return
        try:
            idx = int(index)
        except Exception:
            return
        try:
            cur = bool(self._collapsed.get(idx, False))
            self._collapsed[idx] = not cur
        except Exception:
            return
        # Rebuild series to reflect new collapsed state (keeps hub_names)
        try:
            self._rebuild_series()
        except Exception:
            pass

    def _clear_series_headers(self) -> None:
        for hdr in list(self._series_headers):
            try:
                self.items_layout.removeWidget(hdr)
            except Exception:
                pass
            try:
                _btn = hdr.findChild(Button)
                if _btn is not None:
                    _disconnect_btn_theme(_btn)
            except Exception:
                pass
            try:
                # Hide BEFORE dropping the parent: a still-visible widget
                # reparented to None instantly becomes a top-level window
                # (own wl_surface + xdg_toplevel + activation token on
                # Wayland) for the ms until deleteLater fires — the
                # unconsumable startup sequence behind the per-switch
                # global busy cursor. Hidden widgets never map.
                hdr.hide()
            except Exception:
                pass
            try:
                hdr.setParent(None)
                hdr.deleteLater()
            except Exception:
                pass
        self._series_headers.clear()

    def _update_host_height_for_series(self, total_rows: int) -> None:
        """Host height when series headers are present (headers + card rows)."""
        if total_rows <= 0:
            try:
                self.items_host.setMinimumHeight(1)
            except Exception:
                pass
            return
        # Each header is one row of fixed 24px; cards use the mode height.
        # Count headers vs card rows: headers already counted in total_rows.
        # Approximate: total_rows includes header rows (1 row each) + card rows.
        # For precise height, sum header heights + card rows heights + spacings.
        num_headers = len(self._series_headers)
        # total_rows = num_headers + card_grid_rows
        card_rows = total_rows - num_headers
        header_h = scaled_px(24)
        card_h = self._card_height_px()
        spacing = scaled_px(GRID_SPACING)
        margins = scaled_px(GRID_MARGIN_TOP) + scaled_px(GRID_MARGIN_BOTTOM)
        # Header rows: header_h each; card rows: card_h each; spacing between every row.
        needed = margins
        if num_headers > 0:
            needed += num_headers * header_h
        if card_rows > 0:
            needed += card_rows * card_h
        # spacings = max(0, total_rows -1) * spacing
        if total_rows > 1:
            needed += (total_rows - 1) * spacing
        try:
            self.items_host.setMinimumHeight(needed)
        except Exception:
            pass

    def refresh_card(self, item: GalleryItem) -> None:
        card = self._cards_by_path.get(str(item.path))
        if card is None:
            return
        try:
            if self._view_mode == VIEW_LIST:
                update_gallery_list_card(  # type: ignore[arg-type]
                    card, item, mode=self._resolve_mode(), translate=self._activity_translate
                )
            else:
                # translate rides the card (attached at build) — no per-update threading.
                update_gallery_card(card, item, mode=self._resolve_mode())  # type: ignore[arg-type]
        except Exception:
            pass
        self._sync_activity(card)
        # Re-apply selection tint in case accent changed.
        self.apply_selection(self._selection)

    def refresh_cards(self, items) -> None:
        """Batch card refresh: one content update per card, ONE selection sweep.

        Delivery handlers (artifact/fidelity analysis) used to call
        ``refresh_card`` per item, each re-running ``apply_selection`` over
        the whole grid — O(N^2) region updates + repaints on the UI thread
        in a single delivery, stalling the event loop (compositor busy
        cursor, dropped overlay frames) exactly when quick look shows new
        severities. Single-call behavior of ``refresh_card`` is unchanged.
        """
        try:
            items = list(items or [])
        except Exception:
            return
        if not items:
            return
        try:
            mode = self._resolve_mode()
        except Exception:
            mode = None
        for item in items:
            try:
                card = self._cards_by_path.get(str(item.path))
            except Exception:
                continue
            if card is None:
                continue
            try:
                if self._view_mode == VIEW_LIST:
                    update_gallery_list_card(  # type: ignore[arg-type]
                        card, item, mode=mode, translate=self._activity_translate
                    )
                else:
                    update_gallery_card(card, item, mode=mode)  # type: ignore[arg-type]
            except Exception:
                pass
            self._sync_activity(card)
        try:
            self.apply_selection(self._selection)
        except Exception:
            pass

    def retranslate_headers(self) -> None:
        """Re-resolve series/UNGROUPED header text + card content in place.

        Cheap chrome refresh for a live language switch: reuses the existing
        header (``_rebuild_series``'s surgical reconcile retitles headers and
        updates kept cards without hide/reparent) and card widgets, so scroll,
        focus and selection survive. On a flat (no-series) grid the header
        rebuild is skipped — ``_rebuild_series`` would tear the flat pool down
        — and only card content is refreshed.
        """
        try:
            if getattr(self, "_series", None) is not None:
                self._rebuild_series()
                return
        except Exception:
            pass
        try:
            self.refresh_cards(list(getattr(self, "_items", None) or []))
        except Exception:
            pass

    def set_card_visible(self, path: Path, visible: bool) -> None:
        card = self._cards_by_path.get(str(path))
        if card is not None:
            try:
                card.setVisible(bool(visible))
            except Exception:
                pass

    def apply_selection(self, selected: set[Path] | set[str] | None = None) -> None:
        if selected is None:
            selected = self._selection
        norm: set[str] = set()
        for p in selected or set():
            norm.add(str(p))
        self._selection = set(norm)
        accent = self._selection_accent
        try:
            accent_key = None if accent is None else (
                int(accent.red()), int(accent.green()),
                int(accent.blue()), int(accent.alpha()),
            )
        except Exception:
            accent_key = None
        for str_path, card in self._cards_by_path.items():
            want = str_path in norm
            # Idempotence stamp: repeat sweeps (thumbnail ticks, rebuild
            # tails) skip cards whose tint is already correct — otherwise
            # every sweep repaints every card (O(N²) per load cycle).
            try:
                stamp = getattr(card, "_gallery_sel_applied", None)
            except Exception:
                stamp = None
            if stamp == (want, accent_key):
                continue
            if stamp is None and not want:
                # Cold card is already visually unselected (no override ever
                # applied): stamp without painting. Otherwise the first
                # preview sweep repaints EVERY card (~26ms stall measured on
                # drag start) just to confirm the status quo.
                try:
                    card._gallery_sel_applied = (want, accent_key)  # type: ignore[attr-defined]
                except Exception:
                    pass
                continue
            try:
                apply_gallery_selection(card, want, accent=accent)  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                card._gallery_sel_applied = (want, accent_key)  # type: ignore[attr-defined]
            except Exception:
                pass

    def refresh_selection_accent(self) -> None:
        from ui.widgets.shelf.marquee_plumbing import refresh_accent

        refresh_accent(self, gallery_selection_accent())
        self.apply_selection(self._selection)

    # -- pool helpers ------------------------------------------------------

    def _acquire_card(self, item: GalleryItem):
        _mode = self._resolve_mode()
        want_list = self._view_mode == VIEW_LIST
        updater = update_gallery_list_card if want_list else update_gallery_card
        while self._pool:
            card = self._pool.pop()
            # Pool must never mix grid/list builders (different regions).
            if getattr(card, "_gallery_view_mode", VIEW_GRID) != self._view_mode:
                try:
                    card.setParent(None)
                    card.deleteLater()
                except Exception:
                    pass
                continue
            try:
                card.setParent(self.items_host)
            except Exception:
                pass
            try:
                updater(card, item, mode=_mode, translate=self._activity_translate)  # type: ignore[arg-type]
            except Exception:
                pass
            # Rebind click to current toggle handler (pool may carry old closure).
            self._rebind_card(card)
            try:
                card._gallery_view_mode = self._view_mode  # type: ignore[attr-defined]
            except Exception:
                pass
            self._ensure_card_drag(card)
            self._ensure_card_keys(card)
            self._sync_activity(card)
            return card
        if want_list:
            card = build_gallery_list_card(
                item,
                parent=self.items_host,
                on_activate=self._handle_toggle,
                on_context_menu=self._handle_context_menu,
                mode=_mode,
                translate=self._activity_translate,
            )
        else:
            card = build_gallery_card(
                item,
                parent=self.items_host,
                on_activate=self._handle_toggle,
                on_context_menu=self._handle_context_menu,
                mode=_mode,
                translate=self._activity_translate,
            )
        try:
            card._gallery_view_mode = self._view_mode  # type: ignore[attr-defined]
        except Exception:
            pass
        self._ensure_card_drag(card)
        self._ensure_card_keys(card)
        self._sync_activity(card)
        return card

    def _sync_activity(self, card) -> None:
        try:
            self._activity.sync(card)
        except RuntimeError:
            pass

    def _activity_translate(self, key: str, default: str) -> str:
        """Tab translator via the owner (controller ``_tr``; widget fallback)."""
        try:
            owner = self._gallery_widget._owner_for_triage()
            tr = getattr(owner, "_tr", None)
            return str(tr(key, default)) if callable(tr) else default
        except Exception:
            return default

    def _ungrouped_header_text(self, count: int) -> str:
        """Localized UNGROUPED tail header (``image_gallery.series.ungrouped``)."""
        try:
            return str(self._activity_translate(
                "image_gallery.series.ungrouped", "UNGROUPED · {count}"
            )).format(count=count)
        except Exception:
            return f"UNGROUPED · {count}"

    def _recycle_card(self, str_path: str) -> None:
        card = self._cards_by_path.pop(str_path, None)  # type: ignore[arg-type]
        if card is None:
            # Also handle case where path key is Path str but layout still holds widget not in map.
            return
        try:
            self.items_layout.removeWidget(card)
        except Exception:
            pass
        try:
            apply_gallery_selection(card, False)  # type: ignore[arg-type]
        except Exception:
            pass
        try:
            # Hover/menu state is per-widget; drop it before the pooled card
            # is rebound to another item (or the bar rides it to a new card).
            from tabs.image_gallery.ui.card.hover import reset_card_hover_state

            reset_card_hover_state(card)
        except Exception:
            pass
        try:
            card.hide()
        except Exception:
            pass
        if len(self._pool) < 32:
            try:
                card.setParent(self)
            except Exception:
                pass
            self._pool.append(card)
        else:
            try:
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass

    def _rebind_card(self, card) -> None:
        # Disconnect previous regionClicked/rightClicked if possible, then reconnect via helper.
        # Easiest: disconnect all and rebind via build helper's internal.
        try:
            card.regionClicked.disconnect()
        except Exception:
            pass
        try:
            card.rightClicked.disconnect()
        except Exception:
            pass
        try:
            card.clicked.disconnect()
        except Exception:
            pass
        # Re-install handlers with current callbacks. List rows route chrome
        # region clicks to actions — grid binder would activate on every id.
        if self._view_mode == VIEW_LIST:
            _bind_list_row(card, on_activate=self._handle_toggle, on_context_menu=self._handle_context_menu)
            return
        from tabs.image_gallery.ui.card import _bind_gallery_card  # local import to avoid cycle

        _bind_gallery_card(card, on_activate=self._handle_toggle, on_context_menu=self._handle_context_menu)

    def _handle_toggle(self, path: Path, additive: bool = False) -> None:
        if callable(self._on_toggle):
            try:
                self._on_toggle(path, additive)
            except TypeError:
                self._on_toggle(path)

    # -- Wave A drag source: card press origin + QDrag kickoff ---------------

    def _ensure_card_drag(self, card) -> None:
        """Install the press-drag filter on *card* (idempotent, pool-safe)."""
        try:
            if getattr(card, "_gallery_drag_installed", False):
                return
            filt = _CardPressDragFilter(card, self)
            card.installEventFilter(filt)
            card._gallery_drag_installed = True  # type: ignore[attr-defined]
        except Exception:
            pass

    def _ensure_card_keys(self, card) -> None:
        """Install the keyboard filter on *card* (idempotent, pool-safe).

        Gives every pooled card the grid navigation + activation policy
        (see ``_CardKeyFilter``). Kept separate from ``_ensure_card_drag``
        so existing drag-installed cards still gain keys after an upgrade.
        """
        try:
            if getattr(card, "_gallery_keys_installed", False):
                return
            filt = _CardKeyFilter(card, self)
            card.installEventFilter(filt)
            card._gallery_keys_installed = True  # type: ignore[attr-defined]
        except Exception:
            pass

    def note_card_press(self, path: Path, global_pos: QPoint) -> None:
        """Record a card-press origin (no selection write — arming is at drag start)."""
        try:
            self._drag_press_path = str(path)
            self._drag_press_pos = global_pos
        except Exception:
            pass

    def clear_card_press(self) -> None:
        try:
            self._drag_press_path = None
            self._drag_press_pos = None
        except Exception:
            pass

    def _drag_owner(self):
        """Triage owner for drag arming (controller, or widget when storeless)."""
        try:
            widget = getattr(self, "_gallery_widget", None)
            resolver = getattr(widget, "_owner_for_triage", None)
            if callable(resolver):
                return resolver()
        except Exception:
            pass
        return None

    def build_card_drag(self, card, global_pos: QPoint):  # type: ignore[no-untyped-def]
        """Build the QDrag for the recorded press, or None (no exec here).

        Threshold-gated; press on an unselected card arms single-card
        selection first (dispatch-only via ``selection.commit`` → controller
        ``set_selection``), press on a selected card keeps the group. Ctrl
        toggle routing is untouched (commits on click/release elsewhere).
        """
        try:
            press_path = getattr(self, "_drag_press_path", None)
            press_pos = getattr(self, "_drag_press_pos", None)
        except Exception:
            return None
        if press_path is None or press_pos is None or global_pos is None:
            return None
        if not should_start_gallery_drag(press_pos, global_pos):
            return None
        owner = self._drag_owner()
        if owner is None:
            return None
        try:
            pressed = Path(press_path)
        except Exception:
            return None
        dragged = dragged_paths_for_press(owner, pressed)
        if not dragged:
            return None
        try:
            sel = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
            sel_set = {Path(p) if not isinstance(p, Path) else p for p in sel}
        except Exception:
            sel_set = set()
        if pressed not in sel_set:
            # Unselected press → drag exactly the pressed card (arm first).
            dragged = [pressed]
            try:
                from tabs.image_gallery.use_cases import selection as _selection

                _selection.commit(owner, {pressed})
            except Exception:
                pass
        try:
            mime = build_gallery_drag_mime(dragged)
        except Exception:
            return None
        try:
            from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

            _dnd_log(
                "card drag start pressed=%s n_dragged=%d dragged=%r",
                Path(press_path).name if press_path else "?",
                len(dragged),
                [Path(p).name for p in list(dragged)[:5]],
            )
        except Exception:
            pass
        try:
            pixmap = resolve_gallery_drag_pixmap(card, owner, dragged[0])
            # Shrink to cursor size + count badge for multi-drags.
            pixmap = compose_gallery_drag_pixmap(pixmap, len(dragged))
        except Exception:
            pixmap = None
        try:
            drag = QDrag(card)
            drag.setMimeData(mime)
            if pixmap is not None and not pixmap.isNull():
                drag.setPixmap(pixmap)
                drag.setHotSpot(QPoint(0, 0))
            return drag
        except Exception:
            return None

    def maybe_start_card_drag(self, card, global_pos: QPoint) -> bool:
        """Threshold → build → ``exec(CopyAction)``. Copy only; files stay."""
        try:
            drag = self.build_card_drag(card, global_pos)
        except Exception:
            return False
        if drag is None:
            return False
        try:
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            pass
        try:
            self.clear_card_press()
        except Exception:
            pass
        return True

    def _handle_context_menu(self, path: Path | None) -> None:
        if callable(self._on_context_menu) and path is not None:
            try:
                self._on_context_menu(path)
            except Exception:
                pass

    def _handle_series_context(self, anchor, index, local_pos=None) -> None:
        """Series-header right-click → host callback.

        Host gets ``(index, anchor, paths, label, series_id, global_pos)``:
        ``series_id`` is the session-stable ``series_<n>`` of the cluster's
        members (``None`` when unknown), ``global_pos`` the popup anchor in
        screen coordinates.
        """
        if not callable(self._on_series_context_menu):
            return
        try:
            members = list((self._series or [])[int(index)])
        except Exception:
            members = []
        paths = []
        series_id = None
        for it in members:
            try:
                paths.append(it.path)
            except Exception:
                continue
            if series_id is None:
                try:
                    sid = getattr(it, "series_id", None)
                except Exception:
                    sid = None
                if sid:
                    series_id = str(sid)
        # Pass the series NAME only (the hub), not the full header chrome
        # ("SERIES 1 · … · N VARIANTS") — that repeated the grid header in
        # the flyout.
        label = ""
        try:
            idx = int(index)
            hub = self._hub_names[idx] if idx < len(self._hub_names) else None
            label = str(hub or self._series_header_labels.get(idx, "") or "")
        except Exception:
            label = ""
        global_pos = None
        try:
            if local_pos is not None:
                global_pos = anchor.mapToGlobal(local_pos)
        except Exception:
            global_pos = None
        if global_pos is None:
            try:
                from PySide6.QtGui import QCursor

                global_pos = QCursor.pos()
            except Exception:
                global_pos = None
        try:
            self._on_series_context_menu(
                int(index), anchor, tuple(paths), label, series_id, global_pos
            )
        except Exception:
            pass

    def _update_host_height(self, item_count: int) -> None:
        # Let host grow with content; scroll area will show scrollbar as needed.
        # Host height is derived from row count * stride + margins.
        if item_count <= 0:
            try:
                self.items_host.setMinimumHeight(1)
            except Exception:
                pass
            return
        rows = (item_count + self.grid_columns - 1) // self.grid_columns
        stride = self._card_height_px() + scaled_px(GRID_SPACING)
        margins = scaled_px(GRID_MARGIN_TOP) + scaled_px(GRID_MARGIN_BOTTOM)
        needed = margins + rows * self._card_height_px() + max(0, rows - 1) * scaled_px(GRID_SPACING)
        # Also ensure stride accounts for content padding already in card height.
        _ = stride  # keep for future virtualization parity
        try:
            self.items_host.setMinimumHeight(needed)
        except Exception:
            pass

    # -- helpers for marquee / external callers ----------------------------

    @property
    def grid_columns(self) -> int:
        if self._view_mode == VIEW_LIST:
            return 1
        try:
            return max(1, int(getattr(self, "_applied_columns", GRID_COLUMNS)))
        except Exception:
            return GRID_COLUMNS

    @property
    def items(self) -> list[GalleryItem]:
        return list(self._items)

    def card_for(self, path: Path | str):  # type: ignore[no-untyped-def]
        return self._cards_by_path.get(str(path))

    def set_fill_color(self, color) -> None:
        try:
            apply_opaque_widget_fill(self.items_host, color)
            apply_opaque_widget_fill(self.scroll_area.viewport(), color)
            apply_opaque_widget_fill(self.scroll_area, color)
        except Exception:
            pass

    # -- eventFilter for marquee empty-area drag ---------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # Delegate to marquee module if available.
        try:
            from tabs.image_gallery.ui import marquee as _marquee

            if _marquee.event_filter(self, watched, event):
                return True
        except Exception:
            pass
        # FM background menu: right-click on empty host opens Sort by / View.
        try:
            from PySide6.QtCore import QEvent as _QEvent
            from PySide6.QtGui import QMouseEvent as _QMouseEvent

            host = getattr(self, "items_host", None)
            if (
                host is not None
                and watched is host
                and event.type() == _QEvent.Type.MouseButtonPress
                and isinstance(event, _QMouseEvent)
                and event.button() == Qt.MouseButton.RightButton
            ):
                try:
                    pos = event.position().toPoint()
                except Exception:
                    pos = None
                try:
                    child = host.childAt(pos) if pos is not None else None
                except Exception:
                    child = None
                if child is None and callable(getattr(self, "_on_empty_context_menu", None)):
                    try:
                        global_pos = host.mapToGlobal(pos) if pos is not None else None
                    except Exception:
                        global_pos = None
                    self._on_empty_context_menu(global_pos)
                    return True
        except Exception:
            pass
        # KeyPress on the host/viewport (no card holds focus yet): the scroll
        # area would otherwise swallow arrows before the owner widget sees
        # them. Delegate to the card-grid navigation (session_picker parity,
        # ``recent/items_view.eventFilter`` → ``_handle_key_press``).
        try:
            if event.type() == QEvent.Type.KeyPress and self.handle_navigation_key(event):
                return True
        except Exception:
            pass
        return super().eventFilter(watched, event)
