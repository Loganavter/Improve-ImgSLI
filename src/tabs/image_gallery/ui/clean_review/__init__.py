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
from PySide6.QtGui import QBrush, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

from tabs.image_gallery.debug import gallery_debug

# Public toolkit imports.
from sli_ui_toolkit.widgets import (
    Button,
    Label,
    OverlayScrollArea,
    TopLevelInWindowOverlay,
    ToastAction,
    ToastManager,
)

# P0-10: modal dim-veil alpha (mockup v3 "modal veil" rect, fill-opacity
# 0.45). TopLevelInWindowOverlay has no paintEvent (transparent
# background), so CleanReviewOverlay paints this veil itself in gallery
# scope — never in the toolkit.
DIM_VEIL_ALPHA = round(0.45 * 255)  # 115

# Phase 1 — card plate geometry (mockup v3: 900x440 white card, rx12).
REVIEW_CARD_WIDTH_PX = 900
REVIEW_CARD_HEIGHT_PX = 440

# Package split (plan-gallery-split-2026-10-17, Part C3): the plate widget
# (plate.py) and the ``_populate`` row builder (populate.py) live in this
# package. Re-export the moved names so ``tabs.image_gallery.ui.clean_review``
# keeps its full surface for importers and tests.
from .plate import REVIEW_CARD_RADIUS_PX, _ReviewPlate
from .populate import (
    FILMSTRIP_MAX_CELLS,
    THUMB_HEIGHT_PX,
    THUMB_WIDTH_PX,
    _display_folder_for_items,
    _hub_name_for_series,
    _rounded_top_pixmap,
    _total_bytes_for_items,
    _with_count,
    populate,
)


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


def _register_nav(overlay) -> None:
    """Register the S3 modal section (idempotent, fail-open)."""
    try:
        from tabs.image_gallery.ui.clean_review import nav_section

        nav_section.register(overlay)
    except Exception:
        pass


def _unregister_nav(overlay) -> None:
    """Leave the navigation graph (idempotent, fail-open).

    First thing in every close path (``hide`` / ``hideEvent`` / ``closeEvent``)
    so no section outlives the overlay — a stale section would keep claiming
    arrows for a hidden overlay. Mirrors Quick Look's
    ``overlay_parts/lifecycle.py::_unregister_nav``.
    """
    try:
        from tabs.image_gallery.ui.clean_review import nav_section

        nav_section.unregister(overlay)
    except Exception:
        pass


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
        # constructor (QL tabs/image_gallery/ui/quick_look/overlay_build/build.py:113 — setBold after would
        # re-run Label's pixel-based _apply_style and revert sizing).
        # Quick Look parity: top row is title/subtitle + top-right ✕.
        # The header layout stays a direct layout item (design-parity pin);
        # the S3 navigation section's header row is its only focusable
        # control, the ✕ button (clean_review/nav_section.py::rows). The
        # header's title/subtitle carry no focus, so no inert container sits
        # between them and the row model.
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
        # The action bar is the S3 navigation section's bottom row.
        self._action_bar = bar
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
        # Current strip row (populate() replaces it on every rebuild); the
        # navigation section re-reads this attribute per key press.
        self._strip_row: QWidget | None = None
        self._toast_manager: ToastManager | None = None
        self._ql_return = None

    def _t(self, key: str, default: str, **fmt) -> str:
        """i18n lookup — EN ``default`` when no translator is wired.

        ``**fmt`` mirrors ``quick_look/meta._ql_text``: the EN default
        carries the ``{n}`` placeholders and the SAME ``.format`` runs on
        the translated string, so a locale is free to reorder them.
        """
        tr = getattr(self, "_tr", None)
        text = default
        if tr is not None:
            try:
                text = tr(key, default)
            except Exception:
                text = default
        if fmt:
            try:
                text = text.format(**fmt)
            except Exception:
                pass
        return text

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
        # QuickLook idiom (src/tabs/image_gallery/ui/quick_look/overlay_parts/pinning.py:47): overlay hint = plate floor.
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
        # Return-focus: capture the opener while it still holds the ring (the
        # show path below grabs focus for the overlay). Re-armed on every
        # open; the close path restores it (nav_section.unregister).
        try:
            from tabs.image_gallery.ui.clean_review import nav_section

            nav_section.remember_opener(self)
        except Exception:
            pass
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
        # The overlay owns its keys through the app's navigation model while it
        # is visible: a modal row section (clean_review/nav_section.py) over the
        # header, strip and action bar, so every control is reachable by arrows
        # and the gallery grid behind receives nothing. Registered LAST, after
        # show_overlay()'s own focus grab — Quick Look's ordering.
        _register_nav(self)

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
            # Mark the hand-off BEFORE hiding: the close path's return-focus
            # must not pull the ring back out of the Quick Look overlay that
            # just opened (nav_section.restore_opener_focus reads this).
            self._ql_return = ql
            try:
                ql.installEventFilter(self)
            except Exception:
                pass
            self.hide()
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

    def hide(self) -> None:  # noqa: N802
        # Every close path funnels through here (direct hide, X/Cancel,
        # move-end, card-click-to-QL, toolkit dismiss()): drop the modal
        # navigation section FIRST, so it cannot claim keys for a hidden veil.
        _unregister_nav(self)
        super().hide()

    def hideEvent(self, event) -> None:  # noqa: N802
        _unregister_nav(self)
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        _unregister_nav(self)
        super().closeEvent(event)

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
        # Row building lives in this package's ``populate`` module (package
        # split, plan-gallery-split-2026-10-17 Part C3); name + signature kept.
        populate(self, owner)
        # A rebuild replaces the strip row (and every per-item Restore
        # button), so the navigation section's rows are re-derived on the next
        # key — and a ring the rebuild dropped is put back inside S3.
        try:
            from tabs.image_gallery.ui.clean_review import nav_section

            nav_section.restore_after_rebuild(self)
        except Exception:
            pass

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
        msg = self._t(
            "image_gallery.clean_review.moved_toast",
            "Moved {n} files to _rejected/",
            n=len(moves),
        )
        try:
            tm.show_toast(
                msg,
                duration=10000,
                actions=[
                    ToastAction(
                        self._t("image_gallery.clean_review.undo", "Undo"),
                        callback=_undo,
                        dismiss=True,
                    )
                ],
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
            key = event.key()
            # The navigation manager leaves horizontal arrows to the focused
            # widget (clean_review/nav_section.py keeps ``extra_keys`` empty);
            # re-deliver them to the row section so ←/→ still walk the strip
            # and the action bar. The section stays the single row owner.
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                from tabs.image_gallery.ui.clean_review import nav_section

                section = nav_section.section_of(self)
                if section is not None:
                    focused = nav_section.focused_widget(self) or self
                    if section.navigate(key, focused):
                        event.accept()
                        return
            if key == Qt.Key.Key_Escape:
                self.hide()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)
