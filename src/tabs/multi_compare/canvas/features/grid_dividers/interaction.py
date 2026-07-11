"""Grid-divider drag interaction helpers.

Weight-redistribution math lives here, operating purely on the canvas widget
``handler`` — mirrors ``image_compare``'s ``divider/interaction.py`` pattern.
Unlike ``image_compare``'s single two-way ``split_position``, multi_compare's
N-way grid tracks per-divider ``(split_path, idx, weights)`` state, so the
drag session data is carried on ``handler._divider_drag`` rather than in the
store's ``interaction_state`` (see the D1 gesture-mapping note in
``MULTI_COMPARE_QRHI_REFACTOR.md`` for why this diverges from image_compare's
store-resident convention).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from tabs.multi_compare.scene import actions


def begin_divider_drag(handler, local_pos: QPointF) -> None:
    div = handler._divider_at(local_pos)
    if div is None:
        return
    split_path, idx, _drect, direction, weights = div
    handler._divider_drag = (split_path, idx, direction, weights)
    handler._divider_start_cursor = local_pos
    handler.setCursor(
        Qt.CursorShape.SplitHCursor if direction == "h" else Qt.CursorShape.SplitVCursor
    )


def update_divider_drag(handler, local_pos: QPointF) -> None:
    if handler._divider_drag is None:
        return
    split_path, idx, direction, start_weights = handler._divider_drag
    ws = list(start_weights)
    delta_px = (
        local_pos.x() - handler._divider_start_cursor.x()
        if direction == "h"
        else local_pos.y() - handler._divider_start_cursor.y()
    )
    container_size_px = handler._split_container_size_at(split_path, direction)
    if container_size_px <= 0:
        return
    total_pair = ws[idx] + ws[idx + 1]
    total_weights = sum(ws) or 1.0
    weight_delta = delta_px / container_size_px * total_weights
    new_left = ws[idx] + weight_delta
    new_right = ws[idx + 1] - weight_delta
    min_w = handler._min_pane_weight(
        split_path, direction, container_size_px, total_weights
    )

    max_w = total_pair - min_w
    if max_w < min_w:
        new_left = new_right = total_pair / 2.0
    else:
        new_left = max(min_w, min(max_w, new_left))
        new_right = total_pair - new_left
    ws[idx] = new_left
    ws[idx + 1] = new_right
    handler._do_dispatch(actions.set_split_weights(split_path, ws))


def end_divider_drag(handler) -> None:
    handler._divider_drag = None
    handler.setCursor(Qt.CursorShape.ArrowCursor)
