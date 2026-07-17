"""Divider hit-test and pane-weight floors for multi-compare grid dividers."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect

DIVIDER_GRAB_PX = 8
MIN_PANE_FRACTION = 0.15
MIN_PANE_PIXELS = 100
MAX_CELL_ASPECT = 5.0


def divider_at(
    handler, pos: QPointF
) -> tuple[tuple[int, ...], int, QRect, str, list[float]] | None:
    """Return ``(split_path, divider_idx, divider_rect, direction, weights)``.

    ``split_path`` is the chain of child indices from the root tree node to
    the SplitNode that owns this divider. Used to drive ``SetSplitWeights``
    dispatches independent of any specific SplitNode identity (the tree is
    immutable from the store's perspective).
    """
    grab = DIVIDER_GRAB_PX
    for split, split_path, idx, drect in handler._drop_gaps():
        expanded = drect.adjusted(-grab, -grab, grab, grab)
        if expanded.contains(pos.toPoint()):
            return split_path, idx, drect, split.direction, list(split.weights)
    return None


def split_container_size_at(
    handler, split_path: tuple[int, ...], direction: str
) -> int:
    """Width / height of the SplitNode container at ``split_path``."""
    rect = handler._node_rect_at_path(split_path)
    if rect is None:
        return 0
    return rect.width() if direction == "h" else rect.height()


def min_pane_weight(
    handler,
    split_path: tuple[int, ...],
    direction: str,
    container_size_px: int,
    total_weights: float,
) -> float:
    """Translate the readability floors into a weight value."""
    rect = handler._node_rect_at_path(split_path)
    perp_size_px = 0
    if rect is not None:
        perp_size_px = rect.height() if direction == "h" else rect.width()
    floor_px = MIN_PANE_PIXELS
    if perp_size_px > 0:
        floor_px = max(floor_px, int(perp_size_px / MAX_CELL_ASPECT))
    floor_px = min(floor_px, container_size_px // 2)
    frac_from_pct = MIN_PANE_FRACTION
    frac_from_px = floor_px / container_size_px if container_size_px > 0 else 0.0
    return max(frac_from_pct, frac_from_px) * total_weights
