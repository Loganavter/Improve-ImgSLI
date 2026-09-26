"""Quick look card resize — plain functions (no owner state).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one card-resize concern: grip/border/ring share one clamp + repin idiom"

Corner grip pin, session-only clamp (floor 1040x620), 8px inner border
strip + outer ring drags, card re-layout entry (``_relayout_on_card_resize``).
Extracted verbatim from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.quick_look.nav import _walk_for_nav_button, nav_button_at
from tabs.image_gallery.ui.quick_look.preview import _rescale_preview_to_host


def reposition_grip(overlay) -> None:
    """Pin the drag-resize grip to the card's bottom-right corner (W8).

    Absolute child of the card plate (same idiom as
    ``reposition_nav_buttons`` / ``reposition_source_inset``). Runs from the
    overlay's ``_content`` Resize filter, ``resizeEvent``, and the grip's
    own drag handler.

    W-B: ends with the card re-layout (preview-with-aspect rescale + footer
    reflow). This function is the one resize entry point that lives in this
    module AND is already invoked on every resize path by ``quick_look.py``
    (``_content`` Resize filter + overlay ``resizeEvent``, both out of W-B
    scope), so the re-layout rides all resizes with no new hooks and no
    out-of-scope edits.
    """
    try:
        content = getattr(overlay, "_content", None)
        grip = getattr(overlay, "_resize_grip", None)
        if content is None or grip is None:
            return
        grip.move(
            max(0, content.width() - grip.width()),
            max(0, content.height() - grip.height()),
        )
        try:
            grip.raise_()
        except Exception:
            pass
    except Exception:
        pass
    try:
        _relayout_on_card_resize(overlay)
    except Exception:
        pass


def clamp_card_size(overlay, want_w: int, want_h: int) -> tuple[int, int]:
    """Clamp a wanted card size to the session-only resize bounds (W8/W9).

    Floor: the S4 mockup 1040×620 card. Ceiling: the overlay (parent/window)
    minus the 16px margin on each side. Shared by the corner grip drag and
    the full-border drag so both handles agree exactly.
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        margin = scaled_px(16)
        try:
            bound_w = max(0, overlay.width() - margin * 2)
            bound_h = max(0, overlay.height() - margin * 2)
        except Exception:
            bound_w, bound_h = 0, 0
        new_w = max(scaled_px(1040), int(want_w))
        new_h = max(scaled_px(620), int(want_h))
        if bound_w > 0:
            new_w = min(new_w, bound_w)
        if bound_h > 0:
            new_h = min(new_h, bound_h)
        return new_w, new_h
    except Exception:
        return int(want_w), int(want_h)


# W9: full-border resize — an 8px hit strip along the WHOLE card border
# (4 edges + 4 corners, 8 drag directions). Zones are hit-tested from the
# overlay's _content eventFilter (quick_look.py) and reuse the W8 clamp +
# reposition idiom. No QSS: hover affordance is cursor-only, and the
# painted _ResizeGrip stays as the SE corner's visual affordance.
RESIZE_BORDER_PX = 8


def resize_zone_at(content, pos) -> str | None:
    """Hit-test a _content-local point against the 8px border strip (W9).

    Returns one of ``left`` / ``right`` / ``top`` / ``bottom`` /
    ``top_left`` / ``top_right`` / ``bottom_left`` / ``bottom_right``,
    or None when the point is outside the strip (interior).
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        strip = scaled_px(RESIZE_BORDER_PX)
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


def resize_cursor_for(zone: str | None):
    """Hover/drag cursor for a resize zone (W9). None → default arrow."""
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


def _distribute_column_floors(overlay) -> None:
    """Pin left/right minimums from the LIVE card width (65/35 split).

    QBoxLayout hands all undistributed extra space to a single side, so
    stretch factors alone cannot hold mockup proportions AND share growth:
    the column ended stranded at ~496px after shrink-back (clipped preview).
    Instead the floors consume the width exactly — left (preview priority)
    takes 65% of the extra, right 35% — leaving no remainder to misdeal.
    Floors derive from the card width only (never from grown children), so
    nothing ratchets: shrink restores 640/296.
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        content = getattr(overlay, "_content", None)
        host = getattr(overlay, "_preview_host", None)
        if content is None or host is None:
            return
        left = host.parentWidget()
        scroll = content.findChild(QWidget, "quicklook_right_scroll")
        if left is None or scroll is None:
            return
        outer = content.layout()
        mid = left.parentWidget().layout()
        try:
            om = outer.contentsMargins()
            mm = mid.contentsMargins()
            avail = (
                content.width()
                - om.left() - om.right()
                - mm.left() - mm.right()
                - mid.spacing()
            )
        except Exception:
            avail = content.width() - scaled_px(40)
        base_l, base_r = scaled_px(640), scaled_px(296)
        extra = max(0, int(avail) - base_l - base_r)
        left_extra = int(round(extra * 0.65))
        left.setMinimumWidth(base_l + left_extra)
        scroll.setMinimumWidth(base_r + (extra - left_extra))
    except Exception:
        pass


def relayout_report_rows(overlay) -> None:
    """Lay metric + artifact rows flat in the right column, uniformly spaced.

    Rows (tracked in ``overlay._metric_rows`` / ``overlay._artifact_rows``)
    become direct ``right_lay`` children with stretch 0, in visual order,
    with one stretch-1 spacer between every consecutive pair — metrics rows,
    then artifact rows, inserted right before the series divider. Rows pin
    at sizeHint; ALL surplus splits evenly among the N equal spacers at
    every height (gap = surplus/N, collapsing to the 4px spacing floor
    when short). The series/strip/brief blocks below stay pinned after the
    last row. Called after every metrics/artifacts rebuild (either order);
    never raises.
    """
    try:
        lay = getattr(overlay, "_right_lay", None)
        host = getattr(overlay, "_report_host", None)
        anchor = getattr(overlay, "_div_series", None)
        if lay is None or host is None or anchor is None:
            return
        rows = list(getattr(overlay, "_metric_rows", [])) + list(getattr(overlay, "_artifact_rows", []))
        # Detach previous pass: tracked rows plus any spacers this function
        # inserted (this layout owns no other spacers, so sweep them all).
        for row in rows:
            try:
                lay.removeWidget(row)
            except Exception:
                pass
        for i in range(lay.count() - 1, -1, -1):
            try:
                it = lay.itemAt(i)
            except Exception:
                continue
            if it is not None and it.widget() is None and it.spacerItem() is not None:
                try:
                    lay.removeItem(it)
                except Exception:
                    pass
        try:
            idx = lay.indexOf(anchor)
        except Exception:
            idx = -1
        if idx < 0:
            return
        for n, row in enumerate(rows):
            try:
                if row.parent() is not host:
                    row.setParent(host)
            except Exception:
                pass
            try:
                lay.insertWidget(idx, row, 0)
            except Exception:
                continue
            idx += 1
            if n < len(rows) - 1:
                try:
                    lay.insertStretch(idx, 1)
                except Exception:
                    pass
                idx += 1
    except Exception:
        pass


def _repin_after_card_resize(overlay) -> None:
    """Re-run the absolute-child pin hooks after a card resize step.

    W-B: the card re-layout (preview-with-aspect rescale + footer reflow)
    rides along via ``reposition_grip`` (called below), so the drag paths
    (grip / border / ring) and the overlay Resize paths all re-layout
    through this one entry.
    """
    try:
        overlay._reposition_source_inset()
    except Exception:
        pass
    try:
        reposition_grip(overlay)
    except Exception:
        pass


def _reflow_footer(overlay) -> None:
    """Reflow the bottom action bar after a card resize (W-B).

    Export-window idiom: action buttons keep their natural widths on the
    left, the trailing stretch pins them there. The layout does the reflow
    itself; this hook only refreshes bar geometry so a resize can never
    strand the bar mid-layout. The bar hint is gone (no hint re-pin).
    Never hides or closes anything.
    """
    try:
        bar = None
        try:
            content = getattr(overlay, "_content", None)
            if content is not None:
                bar = content.findChild(QWidget, "quicklook_bottom_bar")
        except Exception:
            bar = None
        if bar is None:
            return
        try:
            bar.updateGeometry()
        except Exception:
            pass
    except Exception:
        pass


def _relayout_on_card_resize(overlay) -> None:
    """Card re-layout entry for every resize step (W-B).

    Preview stretches with aspect, footer reflows. Called from
    ``reposition_grip`` (the in-scope hook every resize path already runs);
    also reachable directly. No close paths, no size-policy changes (W8
    min-only stays: minimum 1040×620, no maximum).
    """
    _distribute_column_floors(overlay)
    _rescale_preview_to_host(overlay)
    _reflow_footer(overlay)


def _resize_dbg():
    """Debug helper pair (IMGSLI_GALLERY_DEBUG=1): [gallery-debug] ql-resize
    traces for edge press/drag/hover diagnosis. Returns (enabled, dbg)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _enabled

        if _enabled():
            return True, _dbg
    except Exception:
        pass
    return False, None


def _resize_trace_on() -> bool:
    """Full firehose (IMGSLI_QL_RESIZE_TRACE=1): log EVERYObserved move with
    receiver + effective cursor, no change-gating. For when the filtered
    ql-resize logs hide the picture (steady states and child-swallowed
    events are silent there by design)."""
    try:
        from shared.debug_flags import env_flag as _env_flag

        return bool(_env_flag("IMGSLI_QL_RESIZE_TRACE"))
    except Exception:
        return False


def _effective_cursor_name(widget) -> str:
    """Effective (inherited) cursor shape name for a widget."""
    try:
        if widget is None:
            return "none"
        cur = widget.cursor()
        shape = cur.shape() if hasattr(cur, "shape") else cur
        return str(shape).split(".")[-1]
    except Exception:
        return "?"


def trace_move(overlay, where: str, pos, receiver=None) -> None:
    """One firehose line per observed mouse move (trace mode only)."""
    try:
        if not _resize_trace_on():
            return
        from tabs.image_gallery.debug import gallery_debug as _dbg

        try:
            recv_name = (
                f"{type(receiver).__name__}:{receiver.objectName()}"
                if receiver is not None
                else "veil"
            )
        except Exception:
            recv_name = "?"
        try:
            eff = _effective_cursor_name(receiver if receiver is not None else overlay)
        except Exception:
            eff = "?"
        try:
            drag = getattr(overlay, "_border_drag", None)
            drag_s = drag[0] if drag is not None else "-"
        except Exception:
            drag_s = "?"
        _dbg(
            "ql-resize trace %s pos=(%d,%d) receiver=%s cursor=%s drag=%s",
            where,
            pos.x(),
            pos.y(),
            recv_name,
            eff,
            drag_s,
        )
    except Exception:
        pass


def _cursor_name(cursor) -> str:
    """Human-readable cursor shape (ArrowCursor for None)."""
    if cursor is None:
        return "arrow"
    try:
        shape = cursor.shape() if hasattr(cursor, "shape") else cursor
        return str(shape).split(".")[-1]
    except Exception:
        return "?"


def apply_resize_cursor(overlay, target, slot: str, cursor) -> None:
    """Set/unset a resize cursor, logging the ACTUAL change (ql-resize).

    ``slot`` is ``plate`` (``_content``) or ``overlay``. Logs only on change
    (per slot), so plain hovers don't spam — you see exactly when the visible
    cursor flips and on which widget. No-op overhead when the debug flag is
    unset (one env check).
    """
    _dbg_on, _dbg = _resize_dbg()
    try:
        if not _dbg_on:
            if cursor is None:
                try:
                    target.unsetCursor()
                except Exception:
                    pass
            else:
                try:
                    target.setCursor(cursor)
                except Exception:
                    pass
            return
        want = _cursor_name(cursor)
        try:
            state = getattr(overlay, "_dbg_cursor_state", None)
            if not isinstance(state, dict):
                state = {}
                overlay._dbg_cursor_state = state
            prev = state.get(slot)
        except Exception:
            state, prev = None, None
        try:
            if cursor is None:
                target.unsetCursor()
            else:
                target.setCursor(cursor)
        except Exception:
            pass
        if want != prev:
            try:
                if isinstance(state, dict):
                    state[slot] = want
            except Exception:
                pass
            try:
                _dbg("ql-resize cursor %s -> %s", slot, want)
            except Exception:
                pass
    except Exception:
        pass


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
            _dbg("ql-resize drag start zone=%s (inner strip)", zone)
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
                        _dbg("ql-resize drag cancel (no buttons held)")
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
                # Anchor the opposite edge: left/top drags move the card
                # so the edge under the cursor tracks it (right/bottom
                # drags keep the W8 top-left anchor).
                new_x = start_geom.x() + (start_geom.width() - new_w) if "left" in zone else start_geom.x()
                new_y = start_geom.y() + (start_geom.height() - new_h) if "top" in zone else start_geom.y()
                if new_x != start_geom.x() or new_y != start_geom.y():
                    content.move(new_x, new_y)
                content.resize(new_w, new_h)
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
            _dbg("ql-resize drag end zone=%s", zone)
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


def ring_zone_at(overlay, pos) -> str | None:
    """Hit-test an OVERLAY-local point against the 8px ring OUTSIDE the card.

    W10: the W9 strip lives on the card plate (inner edge only) — the 8px
    band on the veil around the card grabbed nothing. This mirrors
    ``resize_zone_at`` for that outer band: returns the same 8 zone names
    when ``pos`` is outside the card but within ``RESIZE_BORDER_PX`` of it,
    else None (deep interior, card children, and open veil all return None —
    a plain veil click must never start a drag, W6).

    The 1px boundary frame belongs to BOTH sides: the plate strip claims
    content-0 and the ring claims the card edge row/column too. The two
    handlers never fire for the same event (delivery is exclusive), so this
    overlap only removes the single-row cliff where receiver, owner, and
    cursor slot all switched at once (a press still starts exactly one drag).
    """
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
        # Deep interior belongs to the W9 plate filter, never to the ring —
        # but the 1px boundary frame is claimed here too (see docstring).
        try:
            if card.adjusted(1, 1, -1, -1).contains(pos):
                return None
        except Exception:
            pass
        strip = scaled_px(RESIZE_BORDER_PX)
        left = card.x() - strip <= x <= card.x()
        right = card.x() + card.width() - 1 <= x < card.x() + card.width() + strip
        top = card.y() - strip <= y <= card.y()
        bottom = card.y() + card.height() - 1 <= y < card.y() + card.height() + strip
        # Ring bands only run alongside the card (corners are strip×strip
        # squares); anything beyond is open veil.
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
            _dbg("ql-resize drag start zone=%s (outer ring)", zone)
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
            _dbg("ql-resize drag end zone=%s (outer ring)", zone)
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
