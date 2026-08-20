"""Slot placement (auto-target insertion, removal, view reset) for ``MultiCompareWidget``.

Split out of ``widget.py`` to keep that class down to composition/wiring --
mirrors the ``drag_drop``/loading/export use_cases splits. Every function
here takes the widget as its first argument and reads/writes its instance
state directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tabs.multi_compare.scene import actions

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore


def add_image_auto(
    widget, path: Path, image: "TiledPixelStore", label: str = ""
) -> int | None:
    """Append an image by splitting the largest leaf along its longer axis."""
    if len(widget.state.slots) >= widget.state.max_slots:
        return None
    if widget.state.root is None:
        target_path, side, target_root = None, None, True
    else:
        target_path, side = pick_auto_target(widget)
        target_root = False
    before = len(widget.state.slots)
    widget.store.dispatch(
        actions.add_slot(
            path=path,
            image=image,
            label=label or path.stem,
            target_path=target_path,
            side=side,
            target_root=target_root,
        )
    )
    return widget.state.slots[-1].id if len(widget.state.slots) > before else None


def add_image_at(
    widget,
    path: Path,
    image: "TiledPixelStore",
    label: str,
    target_path: tuple[int, ...] | None,
    side: str | None,
    target_root: bool,
) -> int | None:
    if len(widget.state.slots) >= widget.state.max_slots:
        return None

    if (
        not target_root
        and (target_path is None or side is None)
        and widget.state.root is not None
    ):
        target_path, side = pick_auto_target(widget)
    before = len(widget.state.slots)
    widget.store.dispatch(
        actions.add_slot(
            path=path,
            image=image,
            label=label or path.stem,
            target_path=target_path,
            side=side,
            target_root=target_root or widget.state.root is None,
        )
    )
    return widget.state.slots[-1].id if len(widget.state.slots) > before else None


def pick_auto_target(widget) -> tuple[tuple[int, ...], str]:
    """Pick the existing leaf with the largest rect; split along its longer axis."""
    entries = widget.canvas._leaf_paths_and_rects()
    if not entries:
        return (), "right"
    leaf, rect, path = max(entries, key=lambda e: e[1].width() * e[1].height())
    side = "right" if rect.width() >= rect.height() else "bottom"
    return path, side


def remove_slot(widget, slot_id: int) -> None:
    widget.store.dispatch(actions.remove_slot(slot_id))


def reset_view(widget) -> None:
    widget.store.dispatch(actions.reset_view())
