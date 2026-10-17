"""Quick look card resize — border/ring press/move/release handlers.
Audit-Meta: pattern=thin-owner-target size=exempt reason="one card-resize concern: border/ring share one clamp + repin idiom"

Bodies moved verbatim from ``ui/quick_look/resize.py`` (plan-gallery-split-
2026-10-17, Part C2). Plain functions taking the overlay as their first
argument (``CODE_PATTERNS.md`` "thin owner + use_cases module"); function
names and signatures are unchanged.

Inner ``_content`` border strip (W9) and outer overlay ring (W10) drags share
the ``_border_drag`` tuple + ``clamp_card_size`` + cursor idiom, so inner and
outer drags agree exactly.
"""

from __future__ import annotations

from tabs.image_gallery.ui.quick_look.nav import _walk_for_nav_button, nav_button_at

from .cursors import (
    _override_cursor_name,
    _resize_dbg,
    _resize_trace_on,
    apply_resize_cursor,
)
from .relayout import _repin_after_card_resize
from .zones import (
    QL_RESIZABLE,
    clamp_card_size,
    resize_cursor_for,
    resize_zone_at,
    ring_zone_at,
)


def handle_border_press(overlay, event) -> bool:
    """Start a full-border drag on left-press inside the strip (W9).

    W11: presses inside either nav-arrow rect walk the series and are
    consumed (never a drag). Returns True when the press was consumed
    (caller must accept it).
    """
    _dbg_on, _dbg = _resize_dbg()
    try:
        from PySide6.QtCore import Qt

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # D4: a second press while a drag is live must not silently re-anchor
        # it (multi-touch / accidental re-press jump). Swallow, keep the
        # first drag; its own release still ends it.
        if getattr(overlay, "_border_drag", None) is not None:
            if _dbg_on:
                try:
                    _dbg("ql-resize press ignored (drag already live)")
                except Exception:
                    pass
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
        try:
            nav_hit = nav_button_at(overlay, content.mapTo(overlay, local))
        except Exception:
            nav_hit = None
        if nav_hit is not None:
            if _dbg_on:
                _dbg(
                    "ql-resize plate press WALK nav=%s content-local=(%d,%d)",
                    nav_hit,
                    local.x(),
                    local.y(),
                )
            _walk_for_nav_button(overlay, nav_hit)
            try:
                event.accept()
            except Exception:
                pass
            return True
        if not QL_RESIZABLE:
            # Fixed card: no border drags (nav handled above).
            return False
        zone = resize_zone_at(content, local)
        if _dbg_on:
            _dbg(
                "ql-resize plate press zone=%s content-local=(%d,%d) card=%dx%d",
                zone,
                local.x(),
                local.y(),
                content.width(),
                content.height(),
            )
        if zone is None:
            return False
        try:
            start_global = event.globalPosition().toPoint()
        except Exception:
            return False
        overlay._border_drag = (zone, start_global, content.geometry())
        if _dbg_on:
            _dbg("ql-resize drag start zone=%s (inner strip) override=%s", zone, _override_cursor_name())
        cursor = resize_cursor_for(zone)
        apply_resize_cursor(overlay, content, "plate", cursor)
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def handle_border_move(overlay, event) -> bool:
    """Hover cursors + live border drag (W9). True when consumed."""
    try:
        from PySide6.QtCore import Qt

        content = getattr(overlay, "_content", None)
        if content is None:
            return False
        drag = getattr(overlay, "_border_drag", None)
        if drag is not None:
            # D2: no grabMouse is used (Wayland-safe), so a release landing
            # outside the window strands _border_drag. A button-free move
            # means the press is gone — cancel instead of resizing, or every
            # later free hover would move the card.
            try:
                held = event.buttons()
            except Exception:
                held = Qt.MouseButton.NoButton
            if held == Qt.MouseButton.NoButton:
                _dbg_on, _dbg = _resize_dbg()
                if _dbg_on:
                    try:
                        _dbg("ql-resize drag cancel (no buttons held) override=%s", _override_cursor_name())
                    except Exception:
                        pass
                overlay._border_drag = None
                try:
                    apply_resize_cursor(overlay, overlay, "overlay", None)
                    apply_resize_cursor(overlay, content, "plate", None)
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
            new_w, new_h = clamp_card_size(overlay, want_w, want_h)
            try:
                # Clamp-standstill: pushing further into the floor keeps
                # returning the same size — resizing to it again would only
                # fire resizeEvent → full relayout (Smooth preview rescale +
                # footer reflow + bar geometry) per mouse-move with zero
                # visual change, stalling the drag exactly at the minimum.
                cur_w = content.width()
                cur_h = content.height()
                if new_w == cur_w and new_h == cur_h:
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return True
                # Anchor the opposite edge: left/top drags move the card
                # so the edge under the cursor tracks it (right/bottom
                # drags keep the W8 top-left anchor). The move is computed
                # from the ACTUAL size after resize (not the requested
                # one): if minimums/rounding expanded the resize, the
                # opposite edge still lands on start_right/start_bottom
                # instead of drifting with the expansion.
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
                try:
                    if _resize_trace_on():
                        from tabs.image_gallery.debug import gallery_debug as _dbg2

                        try:
                            end_g = content.geometry()
                            end_right = end_g.x() + end_g.width()
                        except Exception:
                            end_right = "?"
                        _dbg2(
                            "ql-resize drag zone=%s start_right=%d want=%dx%d req=%dx%d actual=%dx%d end_right=%s",
                            zone,
                            start_geom.x() + start_geom.width(),
                            want_w,
                            want_h,
                            new_w,
                            new_h,
                            actual_w,
                            actual_h,
                            end_right,
                        )
                except Exception:
                    pass
            except Exception:
                pass
            _repin_after_card_resize(overlay)
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
        # W11: arrow rects never show a resize cursor (plain arrow instead).
        try:
            if nav_button_at(overlay, content.mapTo(overlay, local)) is not None:
                apply_resize_cursor(overlay, content, "plate", None)
                return False
        except Exception:
            pass
        cursor = resize_cursor_for(resize_zone_at(content, local))
        apply_resize_cursor(overlay, content, "plate", cursor)
        try:
            _dbg_on, _dbg = _resize_dbg()
            if _dbg_on:
                zone_name = resize_zone_at(content, local)
                last = getattr(overlay, "_dbg_resize_hover", None)
                if zone_name != last:
                    overlay._dbg_resize_hover = zone_name
                    _dbg(
                        "ql-resize hover inner zone=%s content-local=(%d,%d)",
                        zone_name,
                        local.x(),
                        local.y(),
                    )
        except Exception:
            pass
        return False
    except Exception:
        return False


def handle_border_release(overlay, event) -> bool:
    """End a full-border drag (W9). True when a drag was active."""
    _dbg_on, _dbg = _resize_dbg()
    try:
        drag = getattr(overlay, "_border_drag", None)
        if drag is None:
            return False
        if _dbg_on:
            try:
                zone = drag[0]
            except Exception:
                zone = "?"
            _dbg("ql-resize drag end zone=%s override=%s", zone, _override_cursor_name())
        overlay._border_drag = None
        _repin_after_card_resize(overlay)
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                apply_resize_cursor(overlay, content, "plate", None)
        except Exception:
            pass
        # D3: an outer-ring drag can end over the card (plate path), leaving
        # the overlay cursor stale. Clearing both slots is safe: during an
        # inner drag the overlay slot is untouched (arrow), so this is a no-op
        # there and a real clear here.
        try:
            apply_resize_cursor(overlay, overlay, "overlay", None)
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def handle_ring_press(overlay, event) -> bool:
    """Start a border drag from the OUTER ring (W10). True when consumed.

    Shares the ``_border_drag`` tuple + ``clamp_card_size`` + cursor idiom
    with the W9 plate handlers, so inner and outer drags agree exactly.
    Plain veil clicks (``ring_zone_at`` None) return False — W6 holds.
    W11: presses inside either nav-arrow rect walk the series and are
    consumed (arrows never start a drag).
    """
    _dbg_on, _dbg = _resize_dbg()
    try:
        from PySide6.QtCore import Qt

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # D4: see handle_border_press — never re-anchor a live drag.
        if getattr(overlay, "_border_drag", None) is not None:
            if _dbg_on:
                try:
                    _dbg("ql-resize press ignored (drag already live)")
                except Exception:
                    pass
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
        try:
            receiver = overlay.childAt(local)
            receiver_name = (
                f"{type(receiver).__name__}:{receiver.objectName()}"
                if receiver is not None
                else "veil"
            )
        except Exception:
            receiver_name = "?"
        nav_hit = nav_button_at(overlay, local)
        if nav_hit is not None:
            if _dbg_on:
                _dbg(
                    "ql-resize veil press WALK nav=%s overlay-local=(%d,%d) receiver=%s",
                    nav_hit,
                    local.x(),
                    local.y(),
                    receiver_name,
                )
            _walk_for_nav_button(overlay, nav_hit)
            try:
                event.accept()
            except Exception:
                pass
            return True
        if not QL_RESIZABLE:
            # Fixed card: no ring drags (nav handled above) — plain veil
            # clicks fall through to the overlay dismiss.
            return False
        zone = ring_zone_at(overlay, local)
        if _dbg_on:
            _dbg(
                "ql-resize veil press zone=%s overlay-local=(%d,%d) receiver=%s",
                zone,
                local.x(),
                local.y(),
                receiver_name,
            )
        if zone is None:
            return False
        try:
            start_global = event.globalPosition().toPoint()
        except Exception:
            return False
        overlay._border_drag = (zone, start_global, content.geometry())
        if _dbg_on:
            _dbg("ql-resize drag start zone=%s (outer ring) override=%s", zone, _override_cursor_name())
        cursor = resize_cursor_for(zone)
        apply_resize_cursor(overlay, overlay, "overlay", cursor)
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False


def handle_ring_hover(overlay, event) -> bool:
    """Hover cursors over the outer ring (W10). Never consumed.

    Overlay-level moves carry overlay-local positions, so the W9 plate
    hover (content-local) cannot serve here. Cursor-only affordance, no QSS.
    """
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
        # W11: arrow rects never show a resize cursor (plain arrow instead).
        try:
            if nav_button_at(overlay, local) is not None:
                apply_resize_cursor(overlay, overlay, "overlay", None)
                return False
        except Exception:
            pass
        # D1: moves over ignoring plate children (labels, scroll areas)
        # propagate here. Deep interior (not the strip the plate owns) must
        # clear a stale plate cursor, or a resize arrow leaks over content.
        # The strip itself is left alone — the plate filter owns it.
        try:
            content = getattr(overlay, "_content", None)
            if content is not None and getattr(overlay, "_border_drag", None) is None:
                try:
                    mapped = content.mapFrom(overlay, local)
                except Exception:
                    mapped = None
                if mapped is not None:
                    try:
                        inside = 0 <= mapped.x() < content.width() and 0 <= mapped.y() < content.height()
                    except Exception:
                        inside = False
                    if inside and resize_zone_at(content, mapped) is None:
                        apply_resize_cursor(overlay, content, "plate", None)
        except Exception:
            pass
        cursor = resize_cursor_for(ring_zone_at(overlay, local))
        apply_resize_cursor(overlay, overlay, "overlay", cursor)
        try:
            _dbg_on, _dbg = _resize_dbg()
            if _dbg_on:
                zone_name = ring_zone_at(overlay, local)
                last = getattr(overlay, "_dbg_resize_hover", None)
                if zone_name != last:
                    overlay._dbg_resize_hover = zone_name
                    try:
                        receiver = overlay.childAt(local)
                        receiver_name = (
                            f"{type(receiver).__name__}:{receiver.objectName()}"
                            if receiver is not None
                            else "veil"
                        )
                    except Exception:
                        receiver_name = "?"
                    _dbg(
                        "ql-resize hover outer zone=%s overlay-local=(%d,%d) receiver=%s",
                        zone_name,
                        local.x(),
                        local.y(),
                        receiver_name,
                    )
        except Exception:
            pass
        return False
    except Exception:
        return False


def handle_ring_release(overlay, event) -> bool:
    """End an outer-ring drag (W10). True when a drag was active."""
    _dbg_on, _dbg = _resize_dbg()
    try:
        if getattr(overlay, "_border_drag", None) is None:
            return False
        if _dbg_on:
            try:
                zone = getattr(overlay, "_border_drag")[0]
            except Exception:
                zone = "?"
            _dbg("ql-resize drag end zone=%s (outer ring) override=%s", zone, _override_cursor_name())
        overlay._border_drag = None
        _repin_after_card_resize(overlay)
        apply_resize_cursor(overlay, overlay, "overlay", None)
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                apply_resize_cursor(overlay, content, "plate", None)
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass
        return True
    except Exception:
        return False
