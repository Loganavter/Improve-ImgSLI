"""Convert ``MultiCompareState`` into a ``CompositionPlan``.

The multi-compare workspace owns its own layout tree (``LeafNode`` /
``SplitNode`` in :mod:`tabs.multi_compare.models`); this module translates that
tree into the canvas-presentation ``CompositionNode`` family so the same
renderer can draw it for live preview and export.
"""

from __future__ import annotations

from PIL import Image
import numpy as np

from tabs.multi_compare.models import (
    LeafNode as _MCLeaf,
    MultiCompareState,
    SplitNode as _MCSplit,
    slot_ids_in_tree,
)
from ui.canvas_presentation.composition import (
    CompositionPlan,
    GroupNode,
    LayerLabel,
    LayerNode,
    SplitNode,
    compute_native_canvas_size,
)


def _slot_image_to_pil(arr: np.ndarray) -> Image.Image | None:
    if arr is None:
        return None
    if arr.ndim == 3 and arr.shape[2] == 4:
        return Image.fromarray(arr, mode="RGBA")
    if arr.ndim == 3 and arr.shape[2] == 3:
        return Image.fromarray(arr, mode="RGB").convert("RGBA")
    if arr.ndim == 2:
        return Image.fromarray(arr, mode="L").convert("RGBA")
    return None


def build_composition_plan(
    state: MultiCompareState,
    *,
    canvas_w: int | None = None,
    canvas_h: int | None = None,
    fill_rgba: tuple[int, int, int, int] | None = None,
    label_font_pt: int = 10,
    split_gap_px: int = 4,
    include_labels: bool = True,
) -> CompositionPlan | None:
    """Translate state into a CompositionPlan, or None if there is nothing to draw.

    Canvas size defaults to the smallest size that lets every leaf render at
    native image resolution (computed from the tree fractions). Pass explicit
    ``canvas_w`` / ``canvas_h`` to override.
    """
    root = state.root
    if root is None or not slot_ids_in_tree(root):
        return None
    slots_by_id = {s.id: s for s in state.slots}
    focused = state.focused_slot_id if state.is_focused else None
    composition_root = _convert_node(
        root,
        slots_by_id,
        focused_slot_id=focused,
        zoom=float(state.zoom),
        pan_x=float(state.pan_x),
        pan_y=float(state.pan_y),
        label_font_pt=label_font_pt,
        include_labels=include_labels,
        split_gap_px=split_gap_px,
    )
    if composition_root is None:
        return None
    if canvas_w is None or canvas_h is None:
        nw, nh = compute_native_canvas_size(composition_root)
        canvas_w = canvas_w or nw
        canvas_h = canvas_h or nh
    return CompositionPlan(
        root=composition_root,
        canvas_w=max(1, int(canvas_w)),
        canvas_h=max(1, int(canvas_h)),
        fill_rgba=fill_rgba,
    )


def _convert_node(
    node,
    slots_by_id: dict,
    *,
    focused_slot_id: int | None,
    zoom: float,
    pan_x: float,
    pan_y: float,
    label_font_pt: int,
    include_labels: bool,
    split_gap_px: int,
):
    if isinstance(node, _MCLeaf):
        if focused_slot_id is not None and node.slot_id != focused_slot_id:
            return None
        slot = slots_by_id.get(node.slot_id)
        if slot is None or slot.image is None:
            return None
        pil = _slot_image_to_pil(slot.image)
        if pil is None:
            return None
        label = (
            LayerLabel(text=slot.label, font_pt=label_font_pt)
            if include_labels and slot.label
            else None
        )
        return LayerNode(
            layer_id=int(slot.id),
            image=pil,
            zoom=zoom,
            pan_x=pan_x,
            pan_y=pan_y,
            label=label,
        )
    if isinstance(node, _MCSplit):
        if focused_slot_id is not None:
            for child in node.children:
                resolved = _convert_node(
                    child,
                    slots_by_id,
                    focused_slot_id=focused_slot_id,
                    zoom=zoom,
                    pan_x=pan_x,
                    pan_y=pan_y,
                    label_font_pt=label_font_pt,
                    include_labels=include_labels,
                    split_gap_px=split_gap_px,
                )
                if resolved is not None:
                    return resolved
            return None
        children = []
        weights = []
        for child, weight in zip(node.children, node.normalized_weights()):
            resolved = _convert_node(
                child,
                slots_by_id,
                focused_slot_id=focused_slot_id,
                zoom=zoom,
                pan_x=pan_x,
                pan_y=pan_y,
                label_font_pt=label_font_pt,
                include_labels=include_labels,
                split_gap_px=split_gap_px,
            )
            if resolved is None:
                continue
            children.append(resolved)
            weights.append(float(weight))
        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return SplitNode(
            direction=node.direction,
            children=tuple(children),
            weights=tuple(weights),
            gap_px=int(split_gap_px),
        )
    return None
