"""Quick look card resize — border/ring zones + the shared size clamp.

Bodies moved verbatim from ``ui/quick_look/resize.py`` (plan-gallery-split-
2026-10-17, Part C2). 8px inner border strip + outer ring hit-testing, the
session-only size clamp both drag paths share, and the card re-layout entry
``reposition_grip`` (the hook every resize path already runs).

Plain functions taking the overlay as their first argument
(``CODE_PATTERNS.md`` "thin owner + use_cases module"). Function names and
signatures are unchanged; the package ``__init__`` re-exports every name.
"""

from __future__ import annotations

# Kill-switch: False = fixed card, no user resize drags (nav arrows keep
# walking). Flip to True to restore border/ring resizing with no other
# changes (tests cover both states via the drag helpers).
QL_RESIZABLE = True


def reposition_grip(overlay) -> None:
    """Card re-layout entry invoked on every resize path (W-B; keeps the
    historical name so all ``quick_look.py`` hooks stay untouched).

    The W8 corner grip is gone (border W9 + ring W10 are the resize paths),
    so there is nothing to pin — the function ends with the card re-layout
    (preview-with-aspect rescale + footer reflow). It is already invoked on
    every resize path by ``quick_look.py`` (``_content`` Resize filter +
    overlay ``resizeEvent``), so the re-layout rides all resizes with no
    new hooks.
    """
    try:
        content = getattr(overlay, "_content", None)
        grip = getattr(overlay, "_resize_grip", None)
        if content is not None and grip is not None:
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
        from .relayout import _relayout_on_card_resize

        _relayout_on_card_resize(overlay)
    except Exception:
        pass


def clamp_card_size(overlay, want_w: int, want_h: int) -> tuple[int, int]:
    """Clamp a wanted card size to the session-only resize bounds (W8/W9).

    Floor: the 1040×680 card (mockup was 1040×620; +60 for the third artifact row). Ceiling: the overlay (parent/window)
    minus the 16px margin on each side. Shared by the border and ring drags
    so both handles agree exactly.
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
        new_h = max(scaled_px(680), int(want_h))
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
# reposition idiom. No QSS: hover affordance is cursor-only (no corner grip).
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
