"""Slot placement (auto-target insertion, removal, view reset) for ``MultiCompareWidget``.

Split out of ``widget.py`` to keep that class down to composition/wiring --
mirrors the ``drag_drop``/loading/export use_cases splits. Every function
here takes the widget as its first argument and reads/writes its instance
state directly.
"""

from __future__ import annotations

from pathlib import Path

from tabs.multi_compare.scene import actions


def add_image_auto(
    widget,
    path: Path,
    label: str = "",
    *,
    leaf_entries=None,
) -> int | None:
    """Append an image by splitting the largest leaf along its longer axis.

    B1: path-only — the slot is created imageless; callers kick the async
    preview fill (``preview_decode.load_preview_async``) after dispatch.
    """
    if len(widget.state.slots) >= widget.state.max_slots:
        return None
    if widget.state.root is None:
        target_path, side, target_root = None, None, True
    else:
        target_path, side = pick_auto_target(widget, leaf_entries=leaf_entries)
        target_root = False
    before = len(widget.state.slots)
    widget.store.dispatch(
        actions.add_slot(
            path=path,
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
    label: str,
    target_path: tuple[int, ...] | None,
    side: str | None,
    target_root: bool,
    *,
    leaf_entries=None,
) -> int | None:
    if len(widget.state.slots) >= widget.state.max_slots:
        return None

    if (
        not target_root
        and (target_path is None or side is None)
        and widget.state.root is not None
    ):
        target_path, side = pick_auto_target(widget, leaf_entries=leaf_entries)
    before = len(widget.state.slots)
    widget.store.dispatch(
        actions.add_slot(
            path=path,
            label=label or path.stem,
            target_path=target_path,
            side=side,
            target_root=target_root or widget.state.root is None,
        )
    )
    return widget.state.slots[-1].id if len(widget.state.slots) > before else None


def pick_largest_leaf_target(leaf_entries) -> tuple[tuple[int, ...], str]:
    """Pure auto-placement core: largest leaf by area, split along longer axis.

    Takes explicit leaf geometry ``[(leaf, rect, path), ...]`` (rects expose
    ``width()``/``height()``) instead of reading the live canvas, so the
    verdict is a pure function of its input. Empty input falls back
    deterministically to ``((), "right")``. Ties resolve to the first
    maximal entry (``max`` stability) — deterministic for a given order.
    """
    if not leaf_entries:
        return (), "right"
    _leaf, rect, path = max(
        leaf_entries, key=lambda e: e[1].width() * e[1].height()
    )
    side = "right" if rect.width() >= rect.height() else "bottom"
    return tuple(path), side


def anchor_slot_for_path(root, path: tuple[int, ...] | None) -> int | None:
    """Pure anchor resolution: slot_id of the first leaf under ``path``.

    Tree data in, slot id out — no canvas reads. ``None`` when the subtree
    is missing/empty (callers treat it as "no anchor", e.g. DropQueue
    slot key ``0``).
    """
    if path is None:
        return None
    from tabs.multi_compare.models import leaves, node_at_path

    node = node_at_path(root, path)
    if node is None:
        return None
    first = leaves(node)
    return first[0].slot_id if first else None


def pick_auto_target(widget, leaf_entries=None) -> tuple[tuple[int, ...], str]:
    """Pick the existing leaf with the largest rect; split along its longer axis.

    Thin impure shell over :func:`pick_largest_leaf_target`: the only
    canvas read in this module. Pass ``leaf_entries`` explicitly (geometry
    data, e.g. from ``hit_projection`` pure core) to skip the live-canvas
    read — same verdict, deterministic fallback ``((), "right")``.
    """
    if leaf_entries is None:
        leaf_entries = widget.canvas._leaf_paths_and_rects()
    return pick_largest_leaf_target(leaf_entries)


def remove_slot(widget, slot_id: int) -> None:
    widget.store.dispatch(actions.remove_slot(slot_id))


def reset_view(widget) -> None:
    widget.store.dispatch(actions.reset_view())
