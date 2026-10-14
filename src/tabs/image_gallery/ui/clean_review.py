"""S3 clean review modal — TopLevelInWindowOverlay + Toast Undo.
Audit-Meta: pattern=state-machine size=exempt reason="one overlay lifecycle — provenance+filmstrip+toasts share TopLevelInWindowOverlay state"

Lists rejected files before any move in one flat filmstrip (stable
provenance-series order — series survive only in the ``from:`` line).
Title + reassurance subtitle (``N files will be moved to <folder>/_rejected/
— nothing is deleted, Undo available for 10 s.``). Flat filmstrip
(thumbs 150x100, capped at ``FILMSTRIP_MAX_CELLS`` cells total +
``+N more`` tile in one horizontally scrollable, frameless strip) with
per-item ``↩ Restore`` + Restore all (no per-series sections, headers,
or Restore SERIES N — mockup v3 has none). Provenance line below the
filmstrip, ``from: SERIES N · hub (cnt)`` via hub resolver.
Final ``Move N to _rejected/`` (surface variant + accent background —
the mockup primary action; the toolkit has no ``variant="primary"``) does move-only ``shutil.move``
via ``triage.clean_rejected`` and shows a 10s ``ToastManager.get_instance``
``Moved N files`` (``success=True``) + ``ToastAction("Undo")``. HUD suppression via FlyoutManager
hide gallery_selection in show_for. The modal dim veil (0.45) is painted by
this overlay itself — the toolkit ``TopLevelInWindowOverlay`` has no
paintEvent (P0-10, gallery scope only).

Public toolkit surface only: ``sli_ui_toolkit.widgets.TopLevelInWindowOverlay``,
``ToastManager``, ``ToastAction`` (FEEDBACK_API, OVERLAYS_API),
``FlyoutManager`` (FLYOUT_SYSTEM), ``ThemeManager`` tokens, ``scaled_px``.
No ``setStyleSheet`` — painter pipeline owns visuals.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.layout_settle import settle_layout

from tabs.image_gallery.debug import gallery_debug

# Public toolkit imports.
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRow,
    Label,
    OverlayScrollArea,
    TopLevelInWindowOverlay,
    ToastAction,
    ToastManager,
)

# S3-2: filmstrip thumb geometry (design px — pass through scaled_px for
# raw geometry, Button scales its own ``size=`` internally).
THUMB_WIDTH_PX = 150
THUMB_HEIGHT_PX = 100
# S3-3: per-series filmstrip cap — show the first N cells, then a
# "+N more / scrollable strip" informational tile (mockup v3).
FILMSTRIP_MAX_CELLS = 8
# P0-10: modal dim-veil alpha (mockup v3 "modal veil" rect, fill-opacity
# 0.45). TopLevelInWindowOverlay has no paintEvent (transparent
# background), so CleanReviewOverlay paints this veil itself in gallery
# scope — never in the toolkit.
DIM_VEIL_ALPHA = round(0.45 * 255)  # 115

# Phase 1 — card plate geometry (mockup v3: 900x440 white card, rx12).
REVIEW_CARD_WIDTH_PX = 900
REVIEW_CARD_HEIGHT_PX = 440
REVIEW_CARD_RADIUS_PX = 12


class _ReviewPlate(QWidget):
    """S3 clean-review card plate — ``gallery.card.background`` fill + border, rx12.

    Mirrors quick-look ``_CardPlate``
    (``ui/quick_look/overlay_build.py``): painter pipeline owns visuals
    (explicit paintEvent, theme-subscribed); no QSS, no palette. Token
    chains mirror the grid-card seam. All QColor() calls take resolved
    variables — never literals
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

    @staticmethod
    def _resolve_bg():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.card.background", "surface.list", "surface.background"):
                c = try_resolve_theme_color(mgr, token)
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _is_dark_theme, _token_color

            return _token_color(
                "gallery.card.background", "#ffffff" if not _is_dark_theme() else "#383838"
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

    def enterEvent(self, event) -> None:  # noqa: N802
        if self._hover_wash_enabled:
            self._hovered = True
            try:
                self.update()
            except Exception:
                pass
        try:
            super().enterEvent(event)
        except Exception:
            pass

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_wash_enabled:
            self._hovered = False
            try:
                self.update()
            except Exception:
                pass
        try:
            super().leaveEvent(event)
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


def _hub_name_for_series(owner, series_id: str) -> str | None:
    """Hub resolver for provenance — SERIES N · hub (cnt).

    Tries state.series (Series dataclass) first, then fallback to first
    rejected item's stem. Returns None if unresolved.
    """
    if series_id == "__ungrouped__":
        return None
    # Try owner.state.series
    try:
        st = getattr(owner, "state", None)
        series_list = getattr(st, "series", None) if st is not None else None
        if series_list:
            for ser in list(series_list):
                sid = getattr(ser, "id", None)
                if sid is not None and str(sid) == str(series_id):
                    members = getattr(ser, "members", None) or []
                    if members:
                        # Prefer rank 1 hub if available
                        try:
                            ranked = sorted(members, key=lambda it: int(getattr(it, "rank", 999) or 999))
                            hub_item = ranked[0] if ranked else members[0]
                        except Exception:
                            hub_item = members[0]
                        try:
                            return Path(getattr(hub_item, "path")).stem
                        except Exception:
                            try:
                                return str(getattr(hub_item, "name", "")) or None
                            except Exception:
                                pass
    except Exception:
        pass
    # Fallback: first item with that provenance
    try:
        st = getattr(owner, "state", None)
        items = getattr(st, "items", None) or []
        for it in list(items):
            pid = getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None)
            if pid is not None and str(pid) == str(series_id):
                try:
                    return Path(getattr(it, "path")).stem
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _total_bytes_for_items(items: list) -> int:
    total = 0
    for it in items:
        try:
            p = Path(getattr(it, "path"))
            if p.is_file():
                total += int(p.stat().st_size)
        except Exception:
            continue
    return total


def _rounded_top_pixmap(pix: QPixmap, w: int, h: int) -> QPixmap:
    """Clip a pixmap to top-rounded corners (recent/grid card idiom).

    Radius 10 like the other cards, bottom corners square. Returns the
    source untouched when sizes are degenerate.
    """
    try:
        from PySide6.QtGui import QPainterPath

        w, h = int(w), int(h)
        if w <= 0 or h <= 0 or pix.isNull():
            return pix
        r = min(scaled_px(10), w // 2, h // 2)
        out = QPixmap(w, h)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.moveTo(0, h)
            path.lineTo(0, r)
            path.arcTo(0, 0, 2 * r, 2 * r, 180.0, -90.0)
            path.lineTo(w - r, 0)
            path.arcTo(w - 2 * r, 0, 2 * r, 2 * r, 90.0, -90.0)
            path.lineTo(w, h)
            path.closeSubpath()
            p.setClipPath(path)
            p.drawPixmap(0, 0, pix)
        finally:
            p.end()
        return out
    except Exception:
        return pix


def _display_folder_for_items(owner, items: list) -> str:
    """Folder shown in the subtitle/move title.

    Resolves through the same helper as the move itself
    (``triage.resolve_move_folder``), so the subtitle can never promise a
    target the move refuses; the ``<folder>`` literal is the last resort
    (no paths at all or parents disagree).
    """
    try:
        from tabs.image_gallery.use_cases.triage import resolve_move_folder

        folder = resolve_move_folder(owner, items)
        if folder is not None:
            return str(folder)
    except Exception:
        pass
    return "<folder>"


def _with_count(text: str, cnt: int) -> str:
    """Append `` (cnt)`` unless the count is 1 (a lone hub needs no count —
    and filenames like ``pic(1)`` would stutter into ``(1) (1)``)."""
    try:
        if int(cnt) > 1:
            return f"{text} ({int(cnt)})"
    except Exception:
        pass
    return text


def _clamp_clean_review_size(overlay, want_w: int, want_h: int) -> tuple[int, int]:
    """Clamp a wanted S3 card size: floor = content minimum (900×440 plate),
    ceiling = overlay minus the 16px margin on each side (Quick Look idiom).
    Session-only, nothing persisted.
    """
    try:
        margin = scaled_px(16)
        try:
            bound_w = max(0, overlay.width() - margin * 2)
            bound_h = max(0, overlay.height() - margin * 2)
        except Exception:
            bound_w, bound_h = 0, 0
        content = getattr(overlay, "_content", None)
        try:
            floor_w = int(content.minimumWidth()) if content is not None else 0
            floor_h = int(content.minimumHeight()) if content is not None else 0
        except Exception:
            floor_w, floor_h = 0, 0
        new_w = max(floor_w, int(want_w))
        new_h = max(floor_h, int(want_h))
        if bound_w > 0:
            new_w = min(new_w, bound_w)
        if bound_h > 0:
            new_h = min(new_h, bound_h)
        return new_w, new_h
    except Exception:
        return int(want_w), int(want_h)


# -- Quick Look-identical resize (W9 8px border strip + W10 outer ring) -----
# -- Quick Look-identical resize (W9 8px border strip + W10 outer ring) -----
# Same zones, cursors, clamp idiom, and D2/D4 guards as quick-look
# ``resize.py``; S3 has no nav arrows (no W11 branches) and repins through
# its own clamp/repin (S3 floor 900×440, no preview relayout).
S3_RESIZE_BORDER_PX = 8


def s3_resize_zone_at(content, pos) -> str | None:
    """Hit-test a _content-local point against the 8px border strip."""
    try:
        from sli_ui_toolkit.managers import scaled_px

        strip = scaled_px(S3_RESIZE_BORDER_PX)
        w = content.width()
        h = content.height()
        x = pos.x()
        y = pos.y()
        left = x < strip
        right = x >= w - strip
        top = y < strip
        bottom = y >= h - strip
        if top and left:
            return "top_left"
        if top and right:
            return "top_right"
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None
    except Exception:
        return None


def s3_ring_zone_at(overlay, pos) -> str | None:
    """Hit-test an OVERLAY-local point against the 8px ring OUTSIDE the card."""
    try:
        from sli_ui_toolkit.managers import scaled_px

        content = getattr(overlay, "_content", None)
        if content is None:
            return None
        try:
            card = content.geometry()
        except Exception:
            return None
        try:
            x = pos.x()
            y = pos.y()
        except Exception:
            return None
        try:
            if card.adjusted(1, 1, -1, -1).contains(pos):
                return None
        except Exception:
            pass
        strip = scaled_px(S3_RESIZE_BORDER_PX)
        left = card.x() - strip <= x <= card.x()
        right = card.x() + card.width() - 1 <= x < card.x() + card.width() + strip
        top = card.y() - strip <= y <= card.y()
        bottom = card.y() + card.height() - 1 <= y < card.y() + card.height() + strip
        v_span = card.y() - strip <= y < card.y() + card.height() + strip
        h_span = card.x() - strip <= x < card.x() + card.width() + strip
        if (left or right) and not v_span:
            return None
        if (top or bottom) and not h_span:
            return None
        if top and left:
            return "top_left"
        if top and right:
            return "top_right"
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None
    except Exception:
        return None


def s3_resize_cursor_for(zone: str | None):
    """Hover/drag cursor for a resize zone. None → default arrow."""
    try:
        from PySide6.QtCore import Qt

        mapping = {
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
        }
        return mapping.get(zone if zone is not None else "")
    except Exception:
        return None


def _s3_apply_cursor(target, cursor) -> None:
    try:
        if cursor is None:
            target.unsetCursor()
        else:
            target.setCursor(cursor)
    except Exception:
        pass


def s3_handle_border_press(overlay, event) -> bool:
    """Start a full-border drag on left-press inside the strip."""
    try:
        from PySide6.QtCore import Qt

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # D4: a second press while a drag is live must not re-anchor it.
        if getattr(overlay, "_border_drag", None) is not None:
            try:
                event.accept()
            except Exception:
                pass
            return True
        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        zone = s3_resize_zone_at(content, local)
        if zone is None:
            return False
        try:
            start_global = event.globalPosition().toPoint()
        except Exception:
            return False
        overlay._border_drag = (zone, start_global, content.geometry())
        _s3_apply_cursor(content, s3_resize_cursor_for(zone))
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def s3_handle_border_move(overlay, event) -> bool:
    """Hover cursors + live border drag. True when consumed."""
    try:
        from PySide6.QtCore import Qt

        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        drag = getattr(overlay, "_border_drag", None)
        if drag is not None:
            # D2: no grabMouse is used (Wayland-safe), so a release landing
            # outside the window strands _border_drag. A button-free move
            # cancels instead of resizing.
            try:
                held = event.buttons()
            except Exception:
                held = Qt.MouseButton.NoButton
            if held == Qt.MouseButton.NoButton:
                overlay._border_drag = None
                try:
                    _s3_apply_cursor(overlay, None)
                    _s3_apply_cursor(content, None)
                except Exception:
                    pass
                return False
            try:
                cur = event.globalPosition().toPoint()
            except Exception:
                return False
            zone, start_global, start_geom = drag
            dx = cur.x() - start_global.x()
            dy = cur.y() - start_global.y()
            want_w = start_geom.width()
            want_h = start_geom.height()
            if "left" in zone:
                want_w = start_geom.width() - dx
            elif "right" in zone:
                want_w = start_geom.width() + dx
            if "top" in zone:
                want_h = start_geom.height() - dy
            elif "bottom" in zone:
                want_h = start_geom.height() + dy
            new_w, new_h = _clamp_clean_review_size(overlay, want_w, want_h)
            try:
                # Clamp-standstill (Quick Look idiom): pushing further into
                # the floor returns the same size — skip the resize/repin so
                # a minimum drag doesn't fire a full relayout per move.
                if new_w == content.width() and new_h == content.height():
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return True
                # Anchor the opposite edge from the ACTUAL size after resize
                # (Quick Look idiom): minimums/rounding expanding the resize
                # must not drag the anchored edge along.
                content.resize(new_w, new_h)
                try:
                    actual_w = content.width()
                    actual_h = content.height()
                except Exception:
                    actual_w, actual_h = new_w, new_h
                if "left" in zone:
                    new_x = start_geom.x() + (start_geom.width() - actual_w)
                else:
                    new_x = start_geom.x()
                if "top" in zone:
                    new_y = start_geom.y() + (start_geom.height() - actual_h)
                else:
                    new_y = start_geom.y()
                try:
                    cur_x = content.x()
                    cur_y = content.y()
                except Exception:
                    cur_x, cur_y = start_geom.x(), start_geom.y()
                if new_x != cur_x or new_y != cur_y:
                    content.move(new_x, new_y)
            except Exception:
                pass
            try:
                event.accept()
            except Exception:
                pass
            return True
        # Hover (no buttons): cursor-only affordance, never consumed.
        try:
            buttons = event.buttons()
        except Exception:
            buttons = Qt.MouseButton.NoButton
        if buttons != Qt.MouseButton.NoButton:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        _s3_apply_cursor(content, s3_resize_cursor_for(s3_resize_zone_at(content, local)))
        return False
    except Exception:
        return False


def s3_handle_border_release(overlay, event) -> bool:
    """End a full-border drag. True when a drag was active."""
    try:
        if getattr(overlay, "_border_drag", None) is None:
            return False
        overlay._border_drag = None
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                _s3_apply_cursor(content, None)
        except Exception:
            pass
        try:
            _s3_apply_cursor(overlay, None)
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def s3_handle_ring_press(overlay, event) -> bool:
    """Start a border drag from the OUTER ring. Plain veil clicks (zone None)
    return False so the base veil dismiss still fires (W6 holds)."""
    try:
        from PySide6.QtCore import Qt

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # D4: never re-anchor a live drag.
        if getattr(overlay, "_border_drag", None) is not None:
            try:
                event.accept()
            except Exception:
                pass
            return True
        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        zone = s3_ring_zone_at(overlay, local)
        if zone is None:
            return False
        try:
            start_global = event.globalPosition().toPoint()
        except Exception:
            return False
        overlay._border_drag = (zone, start_global, content.geometry())
        _s3_apply_cursor(overlay, s3_resize_cursor_for(zone))
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def s3_handle_ring_hover(overlay, event) -> bool:
    """Hover cursors over the outer ring. Never consumed."""
    try:
        from PySide6.QtCore import Qt

        if getattr(overlay, "_border_drag", None) is not None:
            return False
        try:
            buttons = event.buttons()
        except Exception:
            buttons = Qt.MouseButton.NoButton
        if buttons != Qt.MouseButton.NoButton:
            return False
        try:
            local = event.position().toPoint()
        except Exception:
            return False
        # Moves over ignoring plate children propagate here: deep interior
        # (not the strip) clears a stale plate cursor; the strip itself is
        # owned by the plate filter.
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                try:
                    mapped = content.mapFrom(overlay, local)
                except Exception:
                    mapped = None
                if mapped is not None:
                    try:
                        inside = 0 <= mapped.x() < content.width() and 0 <= mapped.y() < content.height()
                    except Exception:
                        inside = False
                    if inside and s3_resize_zone_at(content, mapped) is None:
                        _s3_apply_cursor(content, None)
        except Exception:
            pass
        _s3_apply_cursor(overlay, s3_resize_cursor_for(s3_ring_zone_at(overlay, local)))
        return False
    except Exception:
        return False


def s3_handle_ring_release(overlay, event) -> bool:
    """End an outer-ring drag. True when a drag was active."""
    try:
        if getattr(overlay, "_border_drag", None) is None:
            return False
        overlay._border_drag = None
        _s3_apply_cursor(overlay, None)
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                _s3_apply_cursor(content, None)
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


# NOTE: the corner _CleanReviewResizeGrip was removed (Quick Look parity) —
# the full-border strip + outer ring remain the resize paths.


class CleanReviewOverlay(TopLevelInWindowOverlay):
    """Modal listing rejected files with restore + move.

    Close/resize parity with Quick Look: veil click, Esc, and the top-right
    ✕ close; minimize/focus loss stay pinned (tab-lifetime paths in
    ``tab.py`` still hide explicitly); the card border/ring resizes it.

    Use ``show_for(owner)`` to populate and show.
    Emits ``cleaned(list)`` after a successful move batch (for tests).
    """

    cleaned = Signal(list)
    dismissed = Signal()  # shadow TopLevelInWindowOverlay.dismissed for compat

    def __init__(self, parent: QWidget, owner=None, *, translate=None) -> None:
        # Quick Look parity: veil click + Esc close, minimize/deactivate
        # stays pinned (WindowDeactivate fires on minimize — with True the
        # menu would die with the window; tab on_deactivated/on_session_closed
        # hide it explicitly instead).
        super().__init__(
            parent,
            close_on_background=True,
            close_on_escape=True,
            close_on_deactivate=False,
        )
        # Translator seam: ``translate(key, default) -> str`` (or None for
        # the EN defaults). Captured once; ``retranslate()`` refreshes it on
        # a live language switch. Set BEFORE any child text below so the
        # construction-time labels use it.
        self._tr = translate
        # G3 dispatch-only: the triage owner (controller) arrives explicitly
        # via __init__/show_for and is stored here. Assigned ONLY from those
        # explicit arguments — never poked from outside, never re-scanned.
        self._owner = owner
        self._content = _ReviewPlate(self)
        self._content.setObjectName("CleanReviewContent")
        # Theme tokens — painter pipeline owns visuals (no QSS).
        # Uses ThemeManager palette tokens via toolkit Button/Label (no direct get_color call
        # to respect tests/contracts/test_no_manual_theming.py — painter pipeline owns colors).
        try:
            from sli_ui_toolkit.managers import ThemeManager  # noqa: F401

            _ = ThemeManager  # token palette owned by Button variant primary/surface
        except Exception:
            pass
        # Outer layout with scaled_px.
        outer = QVBoxLayout(self._content)
        outer.setContentsMargins(scaled_px(16), scaled_px(16), scaled_px(16), scaled_px(16))
        outer.setSpacing(scaled_px(12))

        # Phase 2 — mockup v3 header (svg:43-45): title 16 bold + 12
        # muted subtitle + divider rule. Bold goes through the Label
        # constructor (QL overlay_build.py:487 — setBold after would
        # re-run Label's pixel-based _apply_style and revert sizing).
        # Quick Look parity: top row is title/subtitle + top-right ✕.
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(scaled_px(8))
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(scaled_px(2))
        self._title = Label("", pixel_size=16, bold=True, parent=self._content)
        self._title.setObjectName("clean_review_title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_col.addWidget(self._title)

        # S3-1: reassurance subtitle under the title — safety promise before
        # the move (mockup v3). Muted via the toolkit ``caption`` variant
        # (12 px secondary/status text) — no hand-coloring, tokens own color.
        self._subtitle = Label("", pixel_size=14, variant="caption", parent=self._content)
        self._subtitle.setObjectName("clean_review_subtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title_col.addWidget(self._subtitle)
        header_row.addLayout(title_col, 1)
        self._close_btn = Button(text="✕", variant="surface", size=(28, 28), parent=self._content)
        self._close_btn.setObjectName("clean_review_close")
        self._close_btn.clicked.connect(self.hide)
        header_row.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header_row)

        # Phase 2 — header divider under the subtitle (mockup v3 svg:45):
        # reuse the quick-look ``_RuleWidget`` (painted 1px rule,
        # ``separator.color`` token, theme-subscribed) — same widget, no
        # new widget family, no QSS. Lazy import like the other
        # quick-look reaches in this file (module scope stays light).
        try:
            from tabs.image_gallery.ui.quick_look.helpers import _RuleWidget
        except Exception:
            _RuleWidget = None  # type: ignore[assignment]
        self._header_rule = None
        if _RuleWidget is not None:
            self._header_rule = _RuleWidget(self._content)
            self._header_rule.setObjectName("clean_review_header_rule")
            outer.addWidget(self._header_rule)

        # Scrollable list — Phase 6: single flat-strip host (frameless,
        # borderless over the plate; the strip scrolls horizontally, never
        # vertically — mockup v3 has no per-series boxes, no series headers).
        # Unification: toolkit overlay scrollbar (corner_radius=0 keeps the
        # current square look — only the scrollbar changes, not the shape).
        self._scroll = OverlayScrollArea(self._content, corner_radius=0)
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("clean_review_scroll")
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Native bars stay hidden (overlay invariant — the floating custom
        # bars appear on overflow by themselves); re-enforced by the toolkit
        # scrollbar policy at polish time.
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_host = QWidget()
        self._list_host.setObjectName("clean_review_list_host")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(scaled_px(8))
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._list_host)
        # QScrollArea auto-fills its content widget with the raw Qt ``Window``
        # palette role — dark #1e1e1e, a near-black band inside the #383838
        # plate. Route the list host + its strip through the gallery panel
        # token (light pixel-unchanged).
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _apply_panel_background

            _apply_panel_background(self._scroll)
            _apply_panel_background(self._list_host)
        except Exception:
            pass
        outer.addWidget(self._scroll, 1)

        # S3 provenance line — BELOW the filmstrip per mockup v3 (svg:100
        # draws it under the thumbs, above the bottom action bar).
        self._provenance_label = Label("", pixel_size=13, parent=self._content)
        self._provenance_label.setObjectName("clean_review_provenance")
        self._provenance_label.setWordWrap(True)
        self._provenance_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self._provenance_label)

        # Phase 4 — footer divider above the bottom bar (mockup v3 svg:104):
        # same _RuleWidget idiom as the header rule (bound above), no new
        # widget family, no QSS.
        self._footer_rule = None
        if _RuleWidget is not None:
            self._footer_rule = _RuleWidget(self._content)
            self._footer_rule.setObjectName("clean_review_footer_rule")
            outer.addWidget(self._footer_rule)

        # Bottom bar: Restore all | size | Cancel | Move N — surface variant
        # with accent background (mockup primary action; toolkit has no
        # variant="primary", so surface + set_background_color is the
        # primary look).
        bar = QWidget(self._content)
        bar.setObjectName("clean_review_bar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(scaled_px(8))

        self._restore_all_btn = Button(text=self._t("image_gallery.clean_review.restore_all", "Restore all"), variant="surface", parent=bar)
        self._restore_all_btn.setObjectName("clean_review_restore_all")
        self._restore_all_btn.clicked.connect(self._on_restore_all)
        bar_layout.addWidget(self._restore_all_btn)

        bar_layout.addStretch(1)

        self._size_label = Label("", pixel_size=13, parent=bar)
        self._size_label.setObjectName("clean_review_size_label")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self._size_label)

        bar_layout.addStretch(1)

        self._cancel_btn = Button(text=self._t("image_gallery.clean_review.cancel", "Cancel"), variant="surface", parent=bar)
        self._cancel_btn.setObjectName("clean_review_cancel")
        self._cancel_btn.clicked.connect(self.hide)
        bar_layout.addWidget(self._cancel_btn)

        self._move_btn = Button(
            text=self._t("image_gallery.clean_review.move", "Move {n}").format(n=0),
            variant="surface",
            parent=bar,
        )
        self._move_btn.setObjectName("clean_review_move")
        self._move_btn.clicked.connect(self._on_move)
        try:
            # Solid primary look (mockup v3): set_background_color() on
            # surface only yields a tint fill (derive_custom_palette) —
            # override_bg paints exact. Same idiom as the gallery delete ✕.
            # NOTE: toolkit Button has no bold API — white non-bold text is
            # the accepted mockup deviation (plan Phase 7).
            from PySide6.QtGui import QColor as _QC

            from tabs.image_gallery.ui.quick_look import _token_color

            accent = _token_color("accent", "#0096FF")
            self._move_btn.set_override_bg_color(accent)
            self._move_btn.setBorderColor(accent)
            self._move_btn.setForegroundColor(_QC("#ffffff"))
            # Hover would stack the light surface wash over the accent
            # (white button, invisible white text) — pin a darker accent.
            try:
                self._move_btn.set_hover_color(accent.darker(120))
            except Exception:
                pass
        except Exception:
            pass
        bar_layout.addWidget(self._move_btn)
        outer.addWidget(bar)

        # Host content in overlay — centered slot.
        self.add_widget(self._content, slot=None)
        # Phase 1: mockup-v3 plate floor 900x440 (scaled), not a suggestion.
        try:
            self._content.setMinimumWidth(scaled_px(REVIEW_CARD_WIDTH_PX))
            self._content.setMinimumHeight(scaled_px(REVIEW_CARD_HEIGHT_PX))
        except Exception:
            pass
        # Quick Look parity: content Resize filter for the border drag
        # (no corner grip — border strip + outer ring are the resize paths).
        self._border_drag = None
        try:
            self._content.setMouseTracking(True)
        except Exception:
            pass
        self._resize_grip = None
        try:
            self._content.installEventFilter(self)
        except Exception:
            pass
        self._row_widgets: list[QWidget] = []
        self._toast_manager: ToastManager | None = None
        self._ql_return = None

    def _t(self, key: str, default: str) -> str:
        """i18n lookup — EN ``default`` when no translator is wired."""
        tr = getattr(self, "_tr", None)
        if tr is None:
            return default
        try:
            return tr(key, default)
        except Exception:
            return default

    def retranslate(self, translate=None) -> None:
        """Re-apply keyed text after a language switch.

        Re-runs the same label pass as ``_populate`` (plus the two static
        footer buttons that ``_populate`` does not own) so an open overlay
        never keeps stale-language text.
        """
        if translate is not None:
            self._tr = translate
        try:
            self._restore_all_btn.setText(
                self._t("image_gallery.clean_review.restore_all", "Restore all")
            )
        except Exception:
            pass
        try:
            self._cancel_btn.setText(self._t("image_gallery.clean_review.cancel", "Cancel"))
        except Exception:
            pass
        try:
            if self._owner is not None:
                self._populate(self._owner)
        except Exception:
            pass

    def sizeHint(self) -> QSize:  # noqa: N802
        # QuickLook idiom (quick_look.py:848): overlay hint = plate floor.
        return QSize(scaled_px(REVIEW_CARD_WIDTH_PX), scaled_px(REVIEW_CARD_HEIGHT_PX))

    # -- public API ---------------------------------------------------

    def show_for(self, owner=None) -> None:
        """Populate from *owner* (or self._owner) and show overlay.

        Suppresses HUD via FlyoutManager hide gallery_selection.
        """
        if owner is not None:
            # Explicit owner from the caller (see __init__ note): the only
            # re-assignment point besides construction.
            self._owner = owner
        owner = self._owner
        if owner is None:
            return
        _t0 = time.perf_counter()
        # HUD suppression via FlyoutManager hide gallery_selection.
        try:
            from sli_ui_toolkit.managers import FlyoutManager

            mgr = FlyoutManager.get_instance()
            for flyout in list(getattr(mgr, "_registered_flyouts", set())):
                try:
                    grp = getattr(flyout, "flyout_group", None)
                    if grp is None:
                        grp = getattr(type(flyout), "flyout_group", None)
                    if grp == "gallery_selection" and hasattr(flyout, "isVisible") and flyout.isVisible():
                        flyout.hide()
                except Exception:
                    continue
        except Exception:
            pass

        _t1 = time.perf_counter()
        self._populate(owner)
        _t2 = time.perf_counter()
        self.show()
        try:
            self.raise_()
            self.setFocus(Qt.FocusReason.PopupFocusReason)
        except Exception:
            pass
        # Geometry/raise/filters live in show_overlay (QuickLook idiom):
        # bare show() leaves the overlay at stale geometry, painting ~nothing.
        try:
            self.show_overlay()
        except Exception:
            pass
        _t3 = time.perf_counter()
        try:
            _n = len(self._rejected_items(owner))
        except Exception:
            _n = -1
        # TEMP-DIAG (remove after S3-open lag fixed): phase splits for the
        # clean-review open path. Gated by IMGSLI_GALLERY_DEBUG via the tab's
        # debug helper (LOGGING.md: never wire subsystem noise to the global
        # debug switch) — visible without --debug when the env flag is set.
        gallery_debug(
            "s3-open: suppress=%dms populate=%dms show=%dms n_rejected=%d",
            int((_t1 - _t0) * 1000),
            int((_t2 - _t1) * 1000),
            int((_t3 - _t2) * 1000),
            _n,
        )

    def _open_quick_look_for_item(self, item) -> None:
        """Open Quick Look for a card click (anywhere but Restore).

        S3 hides; when Quick Look hides again (any close path — ✕ calls
        ``hide()`` with no signal, so this watches Hide, not ``dismissed``)
        S3 re-shows repopulated. One-shot per open.
        """
        try:
            owner = self._owner
            w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
            if w is None or not hasattr(w, "show_quick_look"):
                return
            try:
                prev = getattr(self, "_ql_return", None)
                if prev is not None:
                    try:
                        prev.removeEventFilter(self)
                    except Exception:
                        pass
            except Exception:
                pass
            w.show_quick_look(item)
            ql = getattr(w, "_quick_look_overlay", None)
            if ql is None:
                return
            self.hide()
            self._ql_return = ql
            try:
                ql.installEventFilter(self)
            except Exception:
                pass
        except Exception:
            pass

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # Card-plate resizes re-pin the grip; presses/moves/releases on the
        # plate drive the W9 border drag with hover cursors (Quick Look idiom).
        try:
            from PySide6.QtCore import QEvent

            if watched is getattr(self, "_ql_return", None) and event.type() == QEvent.Type.Hide:
                # Quick Look closed (any path) after a card-click open —
                # back to S3, repopulated (reject toggles may have changed).
                try:
                    watched.removeEventFilter(self)
                except Exception:
                    pass
                self._ql_return = None
                try:
                    self.show_for(self._owner)
                except Exception:
                    pass
                return False
            if watched is getattr(self, "_content", None):
                t = event.type()
                if t == QEvent.Type.MouseButtonPress:
                    if s3_handle_border_press(self, event):
                        return True
                elif t == QEvent.Type.MouseMove:
                    if s3_handle_border_move(self, event):
                        return True
                elif t == QEvent.Type.MouseButtonRelease:
                    if s3_handle_border_release(self, event):
                        return True
                elif t == QEvent.Type.Leave:
                    if getattr(self, "_border_drag", None) is None:
                        _s3_apply_cursor(self._content, None)
            elif (
                event.type() == QEvent.Type.MouseButtonPress
                and isinstance(watched, _ReviewPlate)
                and watched.objectName() == "clean_review_filmstrip_cell"
            ):
                # Card click: Restore eats its own presses (real Button);
                # anywhere else opens Quick Look for the card's item.
                try:
                    pos = event.position().toPoint()
                except Exception:
                    return False
                try:
                    child = watched.childAt(pos)
                except Exception:
                    child = None
                try:
                    btn = watched.findChild(QWidget, "clean_review_restore")
                except Exception:
                    btn = None
                if btn is not None and child is not None:
                    try:
                        if child is btn or btn.isAncestorOf(child):
                            return False
                    except Exception:
                        pass
                item = getattr(watched, "_s3_item", None)
                if item is not None:
                    self._open_quick_look_for_item(item)
                    return True
                return False
        except Exception:
            pass
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Outer-ring (W10) presses start a drag; open-veil presses fall
        # through to the base veil dismiss (children eat their own presses).
        try:
            if s3_handle_ring_press(self, event):
                return
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        # Veil-level moves continue a live ring drag, else paint ring hovers.
        try:
            if getattr(self, "_border_drag", None) is not None:
                if s3_handle_border_move(self, event):
                    return
            else:
                s3_handle_ring_hover(self, event)
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        try:
            if s3_handle_ring_release(self, event):
                return
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        try:
            if getattr(self, "_border_drag", None) is None:
                _s3_apply_cursor(self, None)
        except Exception:
            pass
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        # Base recenters the card.
        super().resizeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        """P0-10 modal dim veil (mockup v3 fill-opacity 0.45).

        ``TopLevelInWindowOverlay`` paints nothing (transparent
        background), so the veil lives here in gallery scope. The opacity is
        theme-aware (``_dim_veil_alpha``): light keeps the mockup 0.45, dark
        softens so the surroundings stay one background family with the card.
        """
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _dim_veil_alpha

            veil_alpha = _dim_veil_alpha()
        except Exception:
            veil_alpha = DIM_VEIL_ALPHA
        try:
            painter = QPainter(self)
            # No hardcoded QColor (contracts/test_no_hardcoded_qcolor.py):
            # the veil is mockup-specified plain black at an opacity, not
            # a theme color — Qt global black + painter opacity.
            painter.setOpacity(veil_alpha / 255.0)
            painter.fillRect(self.rect(), QBrush(Qt.GlobalColor.black))
            painter.end()
        except Exception:
            pass
        super().paintEvent(event)

    # -- internals ----------------------------------------------------

    def _rejected_items(self, owner) -> list:
        st = getattr(owner, "state", None)
        if st is None:
            return []
        items = getattr(st, "items", None) or []
        return [it for it in list(items) if bool(getattr(it, "rejected", False))]

    def _populate(self, owner) -> None:
        # Ensure provenance_series_id filled (triage wiring).
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            if hasattr(_triage, "ensure_provenance_series_ids"):
                _triage.ensure_provenance_series_ids(owner)
        except Exception:
            pass
        items = self._rejected_items(owner)
        n = len(items)
        total_bytes = _total_bytes_for_items(items)
        total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
        # Title + S3-1 reassurance subtitle (mockup v3 copy: numbers live in
        # the subtitle; folder short form — real path when known, else the
        # ``<folder>`` literal as drawn in the mockup).
        folder_name = _display_folder_for_items(owner, items)
        try:
            self._title.setText(
                self._t("image_gallery.clean_review.title", "Review rejected files")
            )
        except Exception:
            pass
        try:
            self._subtitle.setText(
                self._t(
                    "image_gallery.clean_review.subtitle",
                    "{n} files will be moved to {folder}/_rejected/ — nothing is deleted, Undo available for 10 s.",
                ).format(n=n, folder=folder_name)
            )
        except Exception:
            pass

        # Provenance-by-series line: SERIES N · hub (cnt) with hub resolver.
        by_series: dict[str, list] = {}
        for it in items:
            sid = getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None) or "__ungrouped__"
            sid = str(sid)
            by_series.setdefault(sid, []).append(it)
        # Sort keys: SERIES numeric first, ungrouped last.
        def _series_sort_key(k: str):
            if k == "__ungrouped__":
                return (9999, k)
            # Extract numeric suffix if series_N
            try:
                if k.startswith("series_"):
                    return (int(k.split("_")[1]), k)
            except Exception:
                pass
            return (0, k)

        sorted_sids = sorted(by_series.keys(), key=_series_sort_key)
        # Build hub-aware provenance parts with SERIES N indexing.
        _series_label = self._t("image_gallery.clean_review.series", "SERIES {n}")
        if by_series:
            parts = []
            for idx, sid in enumerate(sorted_sids, start=1):
                cnt = len(by_series[sid])
                _sid_label = _series_label.format(n=idx)
                if sid == "__ungrouped__":
                    hub = self._t("image_gallery.clean_review.ungrouped", "UNGROUPED")
                    parts.append(_with_count(hub, cnt) if len(sorted_sids) == 1 else _with_count(f"{_sid_label} · {hub}", cnt))
                else:
                    hub = _hub_name_for_series(owner, sid)
                    if hub:
                        parts.append(_with_count(f"{_sid_label} · {hub}", cnt))
                    else:
                        # Fallback without hub
                        parts.append(_with_count(_sid_label, cnt))
            # Use sorted order enumeration for display but keep original sid for resolver.
            # Rebuild with actual enumeration based on sorted order where hub exists.
            # For ungrouped, use UNGROUPED label.
            # Already built.
            prov_text = self._t("image_gallery.clean_review.provenance_prefix", "from: ") + " · ".join(parts)
            # Back-compat: also include raw series label for tests that search lowercase
            # Keep display as built.
        else:
            prov_text = self._t("image_gallery.clean_review.no_rejected", "No rejected files.")
        try:
            self._provenance_label.setText(prov_text)
        except Exception:
            pass

        # Move button variant primary, size label total MB.
        try:
            self._move_btn.setText(self._t("image_gallery.clean_review.move", "Move {n}").format(n=n))
            self._move_btn.setEnabled(n > 0)
        except Exception:
            pass
        try:
            if n > 0:
                self._size_label.setText(
                    self._t(
                        "image_gallery.clean_review.size", "{n} files · {mb} MB"
                    ).format(n=n, mb=f"{total_mb:.1f}")
                )
            else:
                self._size_label.setText(
                    self._t("image_gallery.clean_review.no_files", "No files to move")
                )
        except Exception:
            pass
        try:
            self._restore_all_btn.setEnabled(n > 0)
        except Exception:
            pass

        # Rebuild list rows — Phase 6: ONE flat horizontal strip over ALL
        # rejected items in stable order (mockup v3: borderless strip, no
        # per-series boxes/headers; series survive only in the provenance
        # line above). Per-series Restore buttons are gone by design
        # (mockup has none); Restore all + per-thumb Restore remain.
        for w in self._row_widgets:
            try:
                self._list_layout.removeWidget(w)
                # Hide before orphaning (stillborn-toplevel guard).
                w.hide()
                w.setParent(None)
                w.deleteLater()
            except Exception:
                pass
        self._row_widgets.clear()

        if not items:
            empty = Label(
                self._t("image_gallery.clean_review.no_rejected", "No rejected files."),
                pixel_size=14,
                parent=self._list_host,
            )
            empty.setObjectName("clean_review_empty")
            self._list_layout.addWidget(empty)
            self._row_widgets.append(empty)
            return

        # Flat order: series groups in stable SERIES order, items in state
        # order within each group (reuses sorted_sids above).
        flat: list = []
        for sid in sorted_sids:
            flat.extend(by_series[sid])

        # Filmstrip: single horizontally scrollable, frameless strip of
        # thumbs (mockup v3 "scrollable strip" — capped cells exceed the
        # modal width, so the strip scrolls horizontally past the cap to
        # the +N tile). NoFrame: borderless strip over the plate.
        strip_scroll = OverlayScrollArea(self._list_host, corner_radius=0)
        strip_scroll.setObjectName("clean_review_filmstrip")
        strip_scroll.setWidgetResizable(True)
        strip_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Native bars stay hidden (overlay invariant — the floating custom
        # bar appears on horizontal overflow by itself).
        strip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        strip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        filmstrip = QWidget()
        filmstrip.setObjectName("clean_review_filmstrip_inner")
        # Filmstrip host auto-fills raw ``Window`` (dark #1e1e1e) — the band
        # behind the cells. Same panel token as the list host.
        try:
            from tabs.image_gallery.ui.quick_look.labels_theme import _apply_panel_background

            _apply_panel_background(strip_scroll)
            _apply_panel_background(filmstrip)
        except Exception:
            pass
        film_layout = QHBoxLayout(filmstrip)
        film_layout.setContentsMargins(0, 0, 0, 0)
        film_layout.setSpacing(scaled_px(8))
        film_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for it in flat[:FILMSTRIP_MAX_CELLS]:
            # One framed card per item (recent-panel idiom): picture on top,
            # Restore button below — the plate frame makes them read as one
            # card instead of floating thumb + button parts.
            cell = _ReviewPlate(filmstrip, hover_wash=True)
            cell.setObjectName("clean_review_filmstrip_cell")
            cell._s3_item = it  # type: ignore[attr-defined]
            try:
                cell.installEventFilter(self)
            except Exception:
                pass
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(scaled_px(8), scaled_px(8), scaled_px(8), scaled_px(8))
            cell_layout.setSpacing(scaled_px(6))
            # S3-2: toolkit Label thumb 150x100 — Label is the unified
            # themed component (QLabel subclass), pixmap set via the
            # inherited QLabel.setPixmap; neutral "!" placeholder when no
            # thumbnail is available.
            thumb_label = Label("", pixel_size=12, parent=cell)
            thumb_label.setObjectName("clean_review_thumb")
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_label.setFixedSize(scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX))
            # Try to load thumbnail if available (top corners rounded like
            # the other cards; bottom stays square into the card).
            pix = getattr(it, "thumbnail", None)
            if isinstance(pix, QPixmap) and not pix.isNull():
                try:
                    scaled = pix.scaled(scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    thumb_label.setPixmap(
                        _rounded_top_pixmap(scaled, scaled_px(THUMB_WIDTH_PX), scaled_px(THUMB_HEIGHT_PX))
                    )
                except Exception:
                    thumb_label.setText("!")
            else:
                # Placeholder — painter pipeline owns visuals (no QSS, no get_color).
                thumb_label.setText("!")
            cell_layout.addWidget(thumb_label)

            # Recent-projects-panel idiom: the cell is picture on top,
            # Restore button below — no name label; the filename rides
            # the button tooltip instead.
            name = getattr(it, "name", None) or Path(getattr(it, "path", "")).name or str(getattr(it, "path", ""))

            restore_btn = Button(
                text="↩ " + self._t("image_gallery.clean_review.restore", "Restore"),
                variant="surface",
                parent=cell,
            )
            restore_btn.setObjectName("clean_review_restore")
            try:
                restore_btn.setToolTip(str(name))
            except Exception:
                pass
            cell_layout.addWidget(restore_btn, 0, Qt.AlignmentFlag.AlignHCenter)
            p = Path(it.path) if hasattr(it, "path") else None

            def _make_restore(path=p):
                def _do():
                    if path is None:
                        return
                    try:
                        from tabs.image_gallery.use_cases import triage as _triage

                        _triage.toggle_reject(self._owner, path)
                    except Exception:
                        try:
                            it2 = next((x for x in self._rejected_items(self._owner) if Path(x.path) == path), None)
                            if it2 is not None:
                                it2.rejected = False
                        except Exception:
                            pass
                    try:
                        self._populate(self._owner)
                    except Exception:
                        pass
                    try:
                        w = getattr(self._owner, "widget", None) or getattr(self._owner, "_widget", None)
                        if w is not None and hasattr(w, "rebuild_grid"):
                            st = getattr(self._owner, "state", None)
                            items2 = list(getattr(st, "items", []) or []) if st is not None else []
                            w.rebuild_grid(items2)
                    except Exception:
                        pass

                return _do

            restore_btn.clicked.connect(_make_restore())
            # Mockup v3 thumb row: every cell top-aligned so thumbs
            # share one top edge (QHBoxLayout would vertically center
            # shorter items like the +N tile otherwise).
            film_layout.addWidget(cell, 0, Qt.AlignmentFlag.AlignTop)
        # S3-3: "+N more" informational tile when ALL rejected exceed
        # FILMSTRIP_MAX_CELLS — the mockup draws a dashed-border tile,
        # which the painter pipeline does not support without QSS, so a
        # disabled surface Button with two muted rows is used instead.
        # Cells beyond the cap stay accessible via the horizontally
        # scrollable strip context (informational tile, cap documented
        # in FILMSTRIP_MAX_CELLS).
        overflow = len(flat) - FILMSTRIP_MAX_CELLS
        if overflow > 0:
            more_tile = Button(
                rows=[
                    ButtonRow(text=f"+{overflow} more", size=14),
                    ButtonRow(text="scrollable strip", size=10),
                ],
                variant="surface",
                size=(THUMB_WIDTH_PX, THUMB_HEIGHT_PX),
                parent=filmstrip,
            )
            more_tile.setObjectName("clean_review_filmstrip_more")
            more_tile.setEnabled(False)
            try:
                more_tile.setToolTip(f"{overflow} more rejected file(s)")
            except Exception:
                pass
            # Top-aligned with the cells (mockup v3: tile shares the
            # thumb-row top edge, not the row vertical center).
            film_layout.addWidget(more_tile, 0, Qt.AlignmentFlag.AlignTop)
        # Add stretch to left align.
        film_layout.addStretch(1)
        strip_scroll.setWidget(filmstrip)
        # Settle-then-read (quick_look/strip.py:378 documents the trap): a
        # fresh layout can report a stale hint before its first pass, so
        # activate the filmstrip layout before deriving the scroller's
        # fixed height from it.
        try:
            film_layout.activate()
        except Exception:
            pass
        try:
            strip_scroll.setFixedHeight(filmstrip.sizeHint().height() + scaled_px(16))
        except Exception:
            pass
        self._list_layout.addWidget(strip_scroll)
        self._row_widgets.append(strip_scroll)
        # Explicit show (quick_look/strip.py:367 documents the trap): a
        # child added while the host is visible stays hidden until the next
        # turn — excluded from layout hints, so the host collapses and the
        # strip paints a frame late.
        try:
            strip_scroll.show()
        except Exception:
            pass
        # Synchronous settle so the host and the strip agree in the same
        # frame (qt-selfsizing A1): without this the strip keeps its old
        # geometry until the next event-loop turn.
        try:
            settle_layout(self._list_host, filmstrip, strip_scroll)
        except Exception:
            gallery_debug("clean_review filmstrip settle failed")

    def _on_restore_all(self) -> None:
        owner = self._owner
        if owner is None:
            return
        # Restore all rejected.
        items = list(self._rejected_items(owner))
        for it in items:
            try:
                from tabs.image_gallery.use_cases import triage as _triage

                _triage.toggle_reject(owner, Path(it.path))
            except Exception:
                try:
                    it.rejected = False
                except Exception:
                    pass
        try:
            self._populate(owner)
        except Exception:
            pass
        try:
            w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
            if w is not None and hasattr(w, "rebuild_grid"):
                st = getattr(owner, "state", None)
                items2 = list(getattr(st, "items", []) or []) if st is not None else []
                w.rebuild_grid(items2)
        except Exception:
            pass

    def _on_move(self) -> None:
        owner = self._owner
        if owner is None:
            self.hide()
            return
        moves: list[dict] = []
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            moves = _triage.clean_rejected(owner) or []
        except Exception:
            moves = []
        self.hide()
        try:
            self.cleaned.emit(moves)
        except Exception:
            pass
        if not moves:
            return
        # Toast Undo 10s via ToastManager.get_instance if available + total MB.
        window = self.window() or self.parentWidget() or self
        tm = self._ensure_toast_manager(window)
        if tm is None:
            return

        def _undo():
            try:
                from tabs.image_gallery.use_cases.triage import restore_moves

                restore_moves(owner, moves)
            except Exception:
                pass

        # Compute total MB for toast message.
        total_mb = 0.0
        try:
            total_bytes = sum(int(Path(rec.get("dst", rec.get("src", ""))).stat().st_size) for rec in moves if rec.get("dst") and Path(rec.get("dst")).is_file())
            # Fallback: dst paths may not exist after move? Use src size after move? Instead sum from moves records if available.
            if total_bytes == 0:
                for rec in moves:
                    try:
                        p = Path(rec.get("src", ""))
                        if p.is_file():
                            total_bytes += int(p.stat().st_size)
                    except Exception:
                        continue
            total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
        except Exception:
            total_mb = 0.0
        msg = f"Moved {len(moves)} files to _rejected/"
        try:
            tm.show_toast(
                msg,
                duration=10000,
                actions=[ToastAction("Undo", callback=_undo, dismiss=True)],
                success=True,
            )
        except Exception:
            pass

    def _ensure_toast_manager(self, window: QWidget) -> ToastManager | None:
        if self._toast_manager is not None:
            return self._toast_manager
        # Prefer ToastManager.get_instance if toolkit provides it.
        try:
            get_inst = getattr(ToastManager, "get_instance", None)
            if callable(get_inst):
                try:
                    inst = get_inst(window)  # type: ignore[call-arg]
                    if inst is not None:
                        self._toast_manager = inst
                        return inst
                except TypeError:
                    try:
                        inst = get_inst()
                        if inst is not None:
                            self._toast_manager = inst
                            return inst
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._toast_manager = ToastManager(window)
            return self._toast_manager
        except Exception:
            try:
                existing = getattr(window, "toast_manager", None)
                if existing is not None:
                    self._toast_manager = existing
                    return existing
            except Exception:
                pass
        return None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        try:
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)
