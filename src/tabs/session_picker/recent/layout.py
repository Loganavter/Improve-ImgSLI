"""Fixed card and panel geometry for the Session Picker recent shelf."""

GRID_CARD_W = 168
GRID_CARD_H = 128
LIST_CARD_H = 52
PANEL_RADIUS = 12.0

# Breathing room between the scroll host edges and the card grid.
ITEMS_MARGIN = 8
# Extra right inset so cards clear the overlay scrollbar inside the scroll area
# (OverlayScrollArea vertical bar is ~10px; keep a small gap beside it).
ITEMS_MARGIN_RIGHT = 22
ITEMS_SPACING = 12

# Empty-state DnD zone height matches one grid-row viewport.
EMPTY_DROP_ZONE_H = ITEMS_MARGIN * 2 + GRID_CARD_H

# Scroll viewport grows with content up to this many *grid* card rows; beyond
# that height the area stays fixed and scrolling kicks in.
VISIBLE_ROWS_MAX = 2

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


def content_height_for_rows(rows: int, *, card_h: int) -> int:
    """Unclamped height for ``rows`` of cards at ``card_h`` plus item margins."""
    rows = max(0, int(rows))
    if rows <= 0:
        return 0
    return (
        ITEMS_MARGIN * 2
        + rows * int(card_h)
        + max(0, rows - 1) * ITEMS_SPACING
    )


def scroll_viewport_height(*, content_rows: int, card_h: int) -> int:
    """Viewport height: shrink to content, cap at ``VISIBLE_ROWS_MAX`` grid rows."""
    needed = content_height_for_rows(content_rows, card_h=card_h)
    max_h = content_height_for_rows(VISIBLE_ROWS_MAX, card_h=GRID_CARD_H)
    if needed <= 0:
        return content_height_for_rows(1, card_h=GRID_CARD_H)
    return min(needed, max_h)
