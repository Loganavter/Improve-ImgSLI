"""Fixed card and panel geometry for the Session Picker recent shelf.

Helpers return real device px: every constant is scaled through ``scaled_px``
before it leaves this module, so callers can compare the results against live
widget geometry (viewport sizes, scroll offsets) at any UI scale factor.
"""

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import overlay_scrollbar_max_inset

GRID_CARD_W = 168
GRID_CARD_H = 128
LIST_CARD_H = 52
PANEL_RADIUS = 12.0

# Breathing room between the scroll host edges and the card grid.
ITEMS_MARGIN = 8
# Vertical breathing room above the first row and below the last row — bigger
# than the horizontal margin so cards never press against the shelf content's
# top/bottom boundaries.
ITEMS_MARGIN_TOP = 16
ITEMS_MARGIN_BOTTOM = 16
# Static estimate of the overlay scrollbar's footprint, used only where no
# live OverlayScrollArea is available to ask directly (grid column count,
# marquee hit-testing). Read from the toolkit's single source of truth — the
# bar's maximum width plus its overlay margin — instead of hardcoding a
# number. The actual on-screen list-card right inset is computed at layout
# time from ``OverlayScrollArea.overlay_scrollbar_inset()`` (see
# ``RecentItemsView._place_live_cards``), so it collapses to 0 when the bar
# isn't shown instead of always reserving this much space.
ITEMS_MARGIN_RIGHT = overlay_scrollbar_max_inset()
ITEMS_SPACING = 12

# Empty-state DnD zone height matches one grid-row viewport.
EMPTY_DROP_ZONE_H = ITEMS_MARGIN_TOP + ITEMS_MARGIN_BOTTOM + GRID_CARD_H

# Scroll viewport grows with content up to this many *card* rows (grid or
# list, whichever mode is active); beyond that height the area stays fixed and
# scrolling kicks in.
VISIBLE_ROWS_MAX = 2

# Extra rows kept alive above/below the visible scroll window.
VIRTUAL_ROW_BUFFER = 1

# Button ``content_padding`` (left, top, right, bottom) — insets icon/text only.
# Keep vertical insets modest: they apply to *every* region, and the text
# strip already sits near the bottom of the card.
GRID_CONTENT_PADDING = (12.0, 6.0, 12.0, 8.0)
LIST_CONTENT_PADDING = (12.0, 6.0, 12.0, 6.0)

# VerticalSplit weights: icon shelf above, title/meta strip below.
# Text weight must leave room for title + relative + optional marquee type.
GRID_ICON_WEIGHT = 1.85
GRID_TEXT_WEIGHT = 1.5


def grid_columns_for_width(available_width: int) -> int:
    """How many fixed-width grid cards fit in ``available_width`` (scroll viewport)."""
    inner = max(0, int(available_width) - ITEMS_MARGIN - ITEMS_MARGIN_RIGHT)
    stride = GRID_CARD_W + ITEMS_SPACING
    if stride <= 0:
        return 1
    # n cards: n*W + (n-1)*gap <= inner  →  n <= (inner + gap) / (W + gap)
    return max(1, (inner + ITEMS_SPACING) // stride)


def grid_row_count(item_count: int, columns: int) -> int:
    cols = max(1, int(columns))
    if item_count <= 0:
        return 0
    return (int(item_count) + cols - 1) // cols


def row_stride(card_h: int) -> int:
    """Real-px vertical distance from the top of one row to the next.

    Card height and spacing are scaled separately so the stride matches the
    actual on-screen card placement at every UI scale factor.
    """
    return scaled_px(card_h) + scaled_px(ITEMS_SPACING)


def content_height_for_rows(rows: int, *, card_h: int) -> int:
    """Real-px unclamped height for ``rows`` of cards at logical ``card_h``.

    Margins, card height, and spacing are each scaled individually, matching
    ``row_stride`` and the per-card geometry in ``RecentItemsView._place_live_cards``.
    """
    rows = max(0, int(rows))
    if rows <= 0:
        return 0
    return (
        scaled_px(ITEMS_MARGIN_TOP)
        + scaled_px(ITEMS_MARGIN_BOTTOM)
        + rows * scaled_px(card_h)
        + max(0, rows - 1) * scaled_px(ITEMS_SPACING)
    )


def scroll_viewport_height(
    *, content_rows: int, card_h: int, max_height: int | None = None
) -> int:
    """Real-px viewport height: shrink to content, cap at ``max_height`` when
    the host can bound it (the available window space below the create-cards),
    else the fixed ``VISIBLE_ROWS_MAX``-row fallback for pre-layout builds.
    ``card_h`` is the logical (unscaled) card height of the active mode; the
    cap never drops below a single full scaled row so cards are never clipped
    by the fallback at scale factors above 1.0.

    ``max_height`` semantics:
    - ``None`` or ``0`` — no usable signal yet (pre-layout estimate failed or
      bare panel): the fixed ``VISIBLE_ROWS_MAX`` fallback applies.
    - ``> 0`` — cap at that space, never below one full scaled row.
    - ``< 0`` — the host *has* measured the space and there is no room for
      even one row (the shelf sits beyond the visible area): cap at exactly
      one scaled row so the shelf never grows past what can ever be seen.
    """
    needed = content_height_for_rows(content_rows, card_h=card_h)
    if needed <= 0:
        return content_height_for_rows(1, card_h=card_h)
    one_row = content_height_for_rows(1, card_h=card_h)
    if max_height is not None and int(max_height) > 0:
        cap = max(int(max_height), one_row)
    elif max_height is not None and int(max_height) < 0:
        cap = one_row
    else:
        cap = content_height_for_rows(VISIBLE_ROWS_MAX, card_h=card_h)
    return min(needed, cap)


def visible_row_window(
    scroll_y: int,
    viewport_h: int,
    *,
    row_stride_px: int,
    total_rows: int,
    buffer: int = VIRTUAL_ROW_BUFFER,
) -> tuple[int, int]:
    """Inclusive ``(first_row, last_row)`` for the scroll window plus buffer.

    ``scroll_y`` is the content offset (scrollbar value). Rows are measured
    below the top ``ITEMS_MARGIN_TOP``. Returns ``(0, -1)`` when there are no rows.
    """
    total = max(0, int(total_rows))
    if total <= 0:
        return 0, -1
    stride = max(1, int(row_stride_px))
    buf = max(0, int(buffer))
    top_inset = scaled_px(ITEMS_MARGIN_TOP)
    # Y range of the viewport in content coordinates, relative to card origin.
    y0 = max(0, int(scroll_y) - top_inset)
    y1 = max(y0, int(scroll_y) + max(0, int(viewport_h)) - top_inset)
    first = y0 // stride
    # A row that starts at y is visible until y + card_h; approximate with stride.
    last = max(first, (y1 - 1) // stride)
    first = max(0, first - buf)
    last = min(total - 1, last + buf)
    return int(first), int(last)