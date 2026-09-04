"""Convert ``MultiCompareState`` into a ``CompositionPlan``.

The multi-compare workspace owns its own layout tree (``LeafNode`` /
``SplitNode`` in :mod:`tabs.multi_compare.models`); this module translates that
tree into the canvas-presentation ``CompositionNode`` family so the same
renderer can draw it for live preview and export.
"""

from __future__ import annotations

import logging

from tabs.multi_compare.models import LeafNode as _MCLeaf
from tabs.multi_compare.models import (
    MultiCompareState,
)
from tabs.multi_compare.models import SplitNode as _MCSplit
from tabs.multi_compare.models import (
    slot_ids_in_tree,
)
from ui.canvas_presentation.composition import (
    CompositionPlan,
    LayerLabel,
    LayerNode,
    SplitNode,
    compute_native_canvas_size,
)

DEFAULT_SPLIT_GAP_PX = 4
DEFAULT_LABEL_FONT_PX = 10

logger = logging.getLogger("ImproveImgSLI")


def _describe_node(node) -> str:
    if isinstance(node, LayerNode):
        return f"Layer(id={node.layer_id})"
    if isinstance(node, SplitNode):
        kids = ", ".join(_describe_node(c) for c in node.children)
        return f"Split(dir={node.direction}, gap_px={node.gap_px}, weights={node.weights}, children=[{kids}])"
    return f"Group(children=[{', '.join(_describe_node(c) for c in getattr(node, 'children', ()))}])"


def build_composition_plan(
    state: MultiCompareState,
    *,
    canvas_w: int | None = None,
    canvas_h: int | None = None,
    fill_rgba: tuple[int, int, int, int] | None = None,
    label_font_pt: int = DEFAULT_LABEL_FONT_PX,
    split_gap_px: int | None = None,
    include_labels: bool = True,
    sources: dict[int, object] | None = None,
) -> CompositionPlan | None:
    """Translate state into a CompositionPlan, or None if there is nothing to draw.

    Canvas size defaults to the smallest size that lets every leaf render at
    native image resolution (computed from the tree fractions). Pass explicit
    ``canvas_w`` / ``canvas_h`` to override.

    ``split_gap_px`` (the actual layout space reserved between sibling
    images, consumed by ``resolve_composition``'s ``_walk``) defaults to
    ``state.divider_settings.thickness`` (0 if ``visible`` is ``False``)
    when not given -- previously every caller left this at the hardcoded
    ``DEFAULT_SPLIT_GAP_PX``, so the divider-width toolbar control only
    ever resized ``GridDividersPass``'s own (underlay) quad while the
    neighboring images' rects kept reserving the same fixed 4px
    regardless -- widening the divider setting had no visible effect (the
    extra width was hidden under the images, which are drawn on top and
    abut their neighbor's fixed gap), and narrowing it below 4px was too
    small a difference to notice. Only a divider *color* change was ever
    visibly wired all the way through, which read as "thickness doesn't
    update until you touch color" (docs/dev/KNOWN_BUGS.md
    same-slot-swap SSIM follow-up investigation's divider side-quest).

    Imageless-leaf policy (A4 decision, fixed -- do not drift): leaves
    whose slot has no image yet (``slot is None or sources has no entry``)
    are *skipped*, never rendered as placeholder layers. Rationale: a
    placeholder would need invented geometry (native-size computation
    reads real image extents) and would leak into the export canon --
    live and export share one ``CompositionPlan``, so a live-only
    placeholder desyncs export parity. The never-presented hole stays
    covered one layer up instead: the canvas chrome's startup
    placeholder (``ui/chrome.py``) owns the empty-canvas surface, same
    posture as image_compare's canvas-only overlay. An all-imageless
    tree therefore yields ``None`` (clear-color canvas under the chrome
    placeholder); session-restore ordering that leaves every leaf
    imageless is B1/P6 territory and must not be papered over here.
    """
    root = state.root
    if root is None or not slot_ids_in_tree(root):
        return None
    slots_by_id = {s.id: s for s in state.slots}
    # B1: pixels live in the session cache, resolved by the caller into
    # ``sources`` (slot_id -> TiledPixelStore | QImage). ``None`` (e.g. a
    # headless caller without a cache) reads every leaf as imageless.
    sources_by_id = dict(sources) if sources else {}
    focused = state.focused_slot_id if state.is_focused else None
    if split_gap_px is None:
        # ``thickness`` alone isn't enough: setting the toolbar width to 0
        # keeps the last nonzero value in ``thickness`` (so re-enabling
        # remembers it, see widget.py's _on_divider_width_changed) and just
        # flips ``visible`` off instead -- collapse the reserved gap to 0
        # too in that case, or images stay pulled apart by the old
        # thickness with nothing drawn in the space to explain why.
        ds = state.divider_settings
        split_gap_px = max(0, int(ds.thickness)) if ds.visible else 0
    composition_root = _convert_node(
        root,
        slots_by_id,
        sources_by_id,
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
        divider_settings=state.divider_settings,
        label_settings=state.label_settings,
    )


def _convert_node(
    node,
    slots_by_id: dict,
    sources_by_id: dict,
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
        image = sources_by_id.get(node.slot_id)
        if slot is None or image is None:
            # Imageless-leaf policy: documented skip (see
            # build_composition_plan's docstring) -- no placeholder layer,
            # no drift. A partially-loaded split collapses onto its loaded
            # children; an all-imageless tree yields plan None.
            return None

        label = (
            LayerLabel(text=slot.label, font_pt=label_font_pt)
            if include_labels and slot.label
            else None
        )
        return LayerNode(
            layer_id=int(slot.id),
            image=image,
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
                    sources_by_id,
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
                sources_by_id,
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