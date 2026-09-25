"""Quick look prev/next nav — plain functions (no owner state).

Overlay-child circles pinned half-outside the card edges (W4 item 6, W10);
arrow presses walk the series, never start a drag (W11). Extracted verbatim
from ``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint


def reposition_nav_buttons(overlay) -> None:
    """Pin prev/next circles half-outside the card edges (W4 item 6, W10).

    W10: the circles are overlay children (siblings above the card plate),
    positioned in OVERLAY coords — each center sits on the card's left/right
    edge, vertically centered on the preview band. W4..W9 parented them to
    the card plate, whose parent-rect clipping erased the outside half
    (offscreen overlay grab: outside-half pixel was pure veil). Called from
    ``resizeEvent`` and after ``_populate`` (best effort before first show).
    """
    try:
        content = getattr(overlay, "_content", None)
        host = getattr(overlay, "_preview_host", None)
        prev = getattr(overlay, "_prev_btn", None)
        nxt = getattr(overlay, "_next_btn", None)
        if content is None or host is None or prev is None or nxt is None:
            return
        try:
            card = content.geometry()
        except Exception:
            return
        try:
            host_pos = host.mapTo(overlay, QPoint(0, 0))
        except Exception:
            return
        cy = host_pos.y() + host.height() // 2
        for btn, left_edge in ((prev, True), (nxt, False)):
            try:
                bw = btn.width() or btn.sizeHint().width()
                bh = btn.height() or btn.sizeHint().height()
            except Exception:
                continue
            x = card.x() - bw // 2 if left_edge else card.x() + card.width() - bw // 2
            btn.move(x, cy - bh // 2)
            try:
                btn.raise_()
            except Exception:
                pass
    except Exception:
        pass


# W11: nav arrows (overlay children sitting in the ring zone) must NEVER
# start a drag. A press/drag starting inside either arrow rect walks the
# series and consumes the event — the arrow rects are excluded from ring +
# plate drag hit-testing at the handler level (the pure zone functions
# ``resize_zone_at`` / ``ring_zone_at`` stay arrow-agnostic so their unit
# geometry is unchanged). This covers the fall-through production case:
# enabled buttons consume presses as widgets, but DISABLED buttons (single
# item) let presses through to the overlay/plate handlers, where the outer
# half of the circle sits inside the ring band. Hover over an arrow shows
# the plain arrow cursor, never a resize cursor.


def nav_button_at(overlay, overlay_pos):
    """Overlay-local hit-test against the prev/next circles (W11).

    Returns the hit button or None. Geometry is overlay-local (W10: the
    circles are overlay children), so plate callers must map content-local
    points via ``content.mapTo(overlay, local)`` first.
    """
    try:
        for btn in (getattr(overlay, "_prev_btn", None), getattr(overlay, "_next_btn", None)):
            try:
                if btn is not None and btn.geometry().contains(overlay_pos):
                    return btn
            except Exception:
                continue
    except Exception:
        pass
    return None


def _walk_for_nav_button(overlay, btn) -> None:
    """Walk the series for a nav-arrow press (W11). Prev → −1, next → +1."""
    try:
        overlay._walk(-1 if btn is getattr(overlay, "_prev_btn", None) else 1)
    except Exception:
        pass
