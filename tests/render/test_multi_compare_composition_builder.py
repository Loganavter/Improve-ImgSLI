"""MultiCompareState → CompositionPlan conversion."""

from __future__ import annotations

import numpy as np

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.services.composition_builder import build_composition_plan
from ui.canvas_presentation.composition import (
    LayerNode,
    SplitNode as CompSplitNode,
    resolve_composition,
)


def _slot(slot_id: int, w: int, h: int, label: str = "") -> CompareSlot:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    return CompareSlot(id=slot_id, image=arr, label=label or f"slot{slot_id}")


def test_empty_tree_returns_none():
    state = MultiCompareState()
    assert build_composition_plan(state) is None


def test_single_leaf_maps_to_single_layer():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, 800, 600)],
    )
    plan = build_composition_plan(state)
    assert plan is not None
    assert isinstance(plan.root, LayerNode)
    assert plan.canvas_w == 800 and plan.canvas_h == 600


def test_split_with_two_leaves_maps_to_split_node():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1, 200, 200), _slot(2, 200, 200)],
    )
    plan = build_composition_plan(state)
    assert plan is not None
    assert isinstance(plan.root, CompSplitNode)
    assert plan.root.direction == "h"
    assert len(plan.root.children) == 2
    # canvas should be 400 wide so each 1/2 cell fits 200px image
    assert plan.canvas_w == 400
    assert plan.canvas_h == 200


def test_missing_slot_image_is_skipped():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1, 200, 200), CompareSlot(id=2)],
    )
    plan = build_composition_plan(state)
    # Split collapses to its single loaded child
    assert plan is not None
    assert isinstance(plan.root, LayerNode)
    assert plan.root.layer_id == 1


def test_focused_slot_isolates_single_leaf():
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1, 200, 200), _slot(2, 400, 400)],
        focused_slot_id=2,
    )
    plan = build_composition_plan(state)
    assert plan is not None
    assert isinstance(plan.root, LayerNode)
    assert plan.root.layer_id == 2
    assert plan.canvas_w == 400 and plan.canvas_h == 400


def test_zoom_pan_propagate_to_layers():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, 100, 100)],
        zoom=2.5,
        pan_x=0.1,
        pan_y=-0.2,
    )
    plan = build_composition_plan(state)
    resolved = resolve_composition(plan)
    assert resolved.layers[0].zoom == 2.5
    assert resolved.layers[0].pan_x == 0.1
    assert resolved.layers[0].pan_y == -0.2


def test_labels_included_by_default():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, 100, 100, label="image-A")],
    )
    plan = build_composition_plan(state)
    assert plan.root.label is not None
    assert plan.root.label.text == "image-A"


def test_labels_disabled_when_include_labels_false():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, 100, 100, label="image-A")],
    )
    plan = build_composition_plan(state, include_labels=False)
    assert plan.root.label is None


def test_explicit_canvas_size_overrides_native():
    state = MultiCompareState(
        root=LeafNode(slot_id=1),
        slots=[_slot(1, 800, 600)],
    )
    plan = build_composition_plan(state, canvas_w=1920, canvas_h=1080)
    assert plan.canvas_w == 1920
    assert plan.canvas_h == 1080
