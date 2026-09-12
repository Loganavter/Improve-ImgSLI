"""Tab-local drop-hint calculator.

Given a drop QPoint and the host UI (which owns the ``image_label`` widget),
returns a slot hint (1 = left/top area, 2 = right/bottom area) used by
``ImageCompareTab.handle_drop`` to decide which image slot receives the drop.

Kept tab-owned because slot=1/2 semantics are image-pair specific — generic
``WindowEventHandler`` must not know about them.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint


def compute_drop_hint(pos: QPoint, ui, store) -> dict | None:
    image_label = getattr(ui, "image_label", None)
    if image_label is None:
        return None

    is_left = _is_in_left_area(pos, image_label, store)
    return {"is_left_area": is_left, "slot": 1 if is_left else 2}


def _is_in_left_area(pos: QPoint, image_label, store) -> bool:
    if not image_label.isVisible():
        return True

    label_rect = image_label.geometry()
    local_to_label = (
        0 <= pos.x() <= image_label.width()
        and 0 <= pos.y() <= image_label.height()
    )
    is_horizontal = store.viewport.view_state.is_horizontal

    if not is_horizontal:
        mid_x = (
            image_label.width() / 2
            if local_to_label
            else label_rect.x() + label_rect.width() / 2
        )
        return pos.x() < mid_x

    mid_y = (
        image_label.height() / 2
        if local_to_label
        else label_rect.y() + label_rect.height() / 2
    )
    return pos.y() < mid_y
