"""Drop-zone hit testing for multi-compare canvas."""

from __future__ import annotations

from PySide6.QtCore import QPoint


def compute_drop_target(
    widget, pos: QPoint, *, include_center: bool = False
) -> tuple[tuple[int, ...] | None, str | None, bool, int | None]:
    """Return (target_path, side, target_root, swap_slot_id).

    target_root=True when tree is empty (whole widget is the drop zone).
    When include_center=True, the central half of a leaf maps to side="center";
    in that case swap_slot_id holds the leaf's slot id (for internal drag swap).
    All zones are relative to the target leaf, never to the whole grid or an
    enclosing split.
    """
    if widget.state.root is None:
        return None, None, True, None
    leaf_entries = widget._leaf_paths_and_rects()
    if not leaf_entries:
        return None, None, True, None

    gap_target = widget._drop_target_for_gap(pos)
    if gap_target is not None:
        return gap_target

    target_leaf = None
    target_rect = None
    target_path: tuple[int, ...] = ()
    for leaf, rect, path in leaf_entries:
        if rect.contains(pos):
            target_leaf = leaf
            target_rect = rect
            target_path = path
            break
    if target_leaf is None:
        best_d2 = None
        for leaf, rect, path in leaf_entries:
            dx = max(rect.x() - pos.x(), 0, pos.x() - (rect.x() + rect.width() - 1))
            dy = max(
                rect.y() - pos.y(), 0, pos.y() - (rect.y() + rect.height() - 1)
            )
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                target_leaf = leaf
                target_rect = rect
                target_path = path
        if target_leaf is None:
            return None, None, False, None

    u = (pos.x() - target_rect.x()) / max(target_rect.width(), 1)
    v = (pos.y() - target_rect.y()) / max(target_rect.height(), 1)
    if include_center and 0.25 <= u <= 0.75 and 0.25 <= v <= 0.75:
        return target_path, "center", False, target_leaf.slot_id

    distances = {"left": u, "right": 1 - u, "top": v, "bottom": 1 - v}
    side = min(distances, key=lambda k: distances[k])
    return target_path, side, False, None


def drop_target_for_gap(
    widget, pos: QPoint
) -> tuple[tuple[int, ...], str, bool, None] | None:
    """Resolve the dedicated zones inside an actual split gap.

    A vertical gap is split by height: the top quarter inserts above the
    whole split, the bottom quarter below it, and the middle half inserts
    between the adjacent children. Horizontal gaps use the symmetric
    left/middle/right behavior.
    """
    for split, split_path, divider_index, divider_rect in widget._drop_gaps():
        if not divider_rect.contains(pos):
            continue

        adjacent_path = split_path + (divider_index + 1,)
        if split.direction == "h":
            fraction = (pos.y() - divider_rect.y()) / max(divider_rect.height(), 1)
            if fraction < 0.25:
                return split_path, "top", False, None
            if fraction >= 0.75:
                return split_path, "bottom", False, None
            return adjacent_path, "left", False, None

        fraction = (pos.x() - divider_rect.x()) / max(divider_rect.width(), 1)
        if fraction < 0.25:
            return split_path, "left", False, None
        if fraction >= 0.75:
            return split_path, "right", False, None
        return adjacent_path, "top", False, None
    return None
