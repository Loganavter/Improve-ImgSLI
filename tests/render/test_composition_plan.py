"""Composition tree resolve + native size — backend-agnostic invariants."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ui.canvas_presentation.composition import (
    CompositionPlan,
    GroupNode,
    LayerLabel,
    LayerNode,
    SplitNode,
    compute_native_canvas_size,
    resolve_composition,
)


def _img(w: int, h: int) -> Image.Image:
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def test_resolve_single_layer_uses_full_canvas():
    plan = CompositionPlan(
        root=LayerNode(layer_id=1, image=_img(100, 50)),
        canvas_w=800,
        canvas_h=600,
    )
    resolved = resolve_composition(plan)
    assert len(resolved.layers) == 1
    assert resolved.layers[0].rect == (0, 0, 800, 600)
    assert resolved.layers[0].layer_id == 1


def test_resolve_horizontal_split_covers_canvas_exactly():
    plan = CompositionPlan(
        root=SplitNode(
            direction="h",
            children=(
                LayerNode(layer_id=1, image=_img(10, 10)),
                LayerNode(layer_id=2, image=_img(10, 10)),
                LayerNode(layer_id=3, image=_img(10, 10)),
            ),
            weights=(1.0, 2.0, 1.0),
        ),
        canvas_w=1000,
        canvas_h=400,
    )
    resolved = resolve_composition(plan)
    rects = [layer.rect for layer in resolved.layers]
    assert rects[0] == (0, 0, 250, 400)
    assert rects[1] == (250, 0, 500, 400)
    assert rects[2] == (750, 0, 250, 400)
    # last child absorbs rounding so children cover canvas
    assert rects[0][0] + rects[0][2] == rects[1][0]
    assert rects[2][0] + rects[2][2] == 1000


def test_resolve_vertical_split_with_gaps():
    plan = CompositionPlan(
        root=SplitNode(
            direction="v",
            children=(
                LayerNode(layer_id=1, image=_img(10, 10)),
                LayerNode(layer_id=2, image=_img(10, 10)),
            ),
            weights=(1.0, 1.0),
            gap_px=10,
        ),
        canvas_w=300,
        canvas_h=210,
    )
    resolved = resolve_composition(plan)
    a, b = resolved.layers
    # inner = 210 - 10 = 200; each = 100
    assert a.rect == (0, 0, 300, 100)
    assert b.rect == (0, 110, 300, 100)


def test_resolve_nested_splits():
    plan = CompositionPlan(
        root=SplitNode(
            direction="h",
            children=(
                LayerNode(layer_id=1, image=_img(10, 10)),
                SplitNode(
                    direction="v",
                    children=(
                        LayerNode(layer_id=2, image=_img(10, 10)),
                        LayerNode(layer_id=3, image=_img(10, 10)),
                    ),
                    weights=(1.0, 1.0),
                ),
            ),
            weights=(1.0, 1.0),
        ),
        canvas_w=200,
        canvas_h=100,
    )
    resolved = resolve_composition(plan)
    rects = {layer.layer_id: layer.rect for layer in resolved.layers}
    assert rects[1] == (0, 0, 100, 100)
    assert rects[2] == (100, 0, 100, 50)
    assert rects[3] == (100, 50, 100, 50)


def test_resolve_group_passes_through():
    plan = CompositionPlan(
        root=GroupNode(children=(LayerNode(layer_id=1, image=_img(10, 10)),)),
        canvas_w=50,
        canvas_h=50,
    )
    resolved = resolve_composition(plan)
    assert resolved.layers[0].rect == (0, 0, 50, 50)


def test_resolve_propagates_layer_fields():
    label = LayerLabel(text="hello")
    plan = CompositionPlan(
        root=LayerNode(
            layer_id=42,
            image=_img(10, 10),
            zoom=2.0,
            pan_x=0.1,
            pan_y=-0.05,
            label=label,
        ),
        canvas_w=100,
        canvas_h=100,
    )
    layer = resolve_composition(plan).layers[0]
    assert layer.layer_id == 42
    assert layer.zoom == 2.0
    assert layer.pan_x == 0.1
    assert layer.pan_y == -0.05
    assert layer.label is label


def test_native_size_single_image_returns_image_size():
    root = LayerNode(layer_id=1, image=_img(640, 480))
    assert compute_native_canvas_size(root) == (640, 480)


def test_native_size_horizontal_split_scales_by_fraction():
    # Two equal cells, image is 100x100. Each cell gets 1/2 of width, so canvas
    # must be 200 wide for cells to fit images at native. Height stays 100.
    root = SplitNode(
        direction="h",
        children=(
            LayerNode(layer_id=1, image=_img(100, 100)),
            LayerNode(layer_id=2, image=_img(100, 100)),
        ),
        weights=(1.0, 1.0),
    )
    assert compute_native_canvas_size(root) == (200, 100)


def test_native_size_takes_worst_case_across_leaves():
    # Two cells (1/3, 2/3 split horizontally). Images: 300x100 and 600x100.
    # Left needs W * 1/3 >= 300 -> W >= 900. Right needs W * 2/3 >= 600 -> W >= 900.
    root = SplitNode(
        direction="h",
        children=(
            LayerNode(layer_id=1, image=_img(300, 100)),
            LayerNode(layer_id=2, image=_img(600, 100)),
        ),
        weights=(1.0, 2.0),
    )
    assert compute_native_canvas_size(root) == (900, 100)


def test_native_size_caps_to_max_edge():
    root = LayerNode(layer_id=1, image=_img(40000, 20000))
    w, h = compute_native_canvas_size(root, max_edge=16384)
    assert max(w, h) == 16384
    assert abs(w / h - 2.0) < 1e-3  # aspect preserved


def test_native_size_accepts_numpy_layer_image():
    arr = np.zeros((300, 500, 4), dtype=np.uint8)
    root = LayerNode(layer_id=1, image=arr)
    assert compute_native_canvas_size(root) == (500, 300)


def test_compositionplan_carries_fill_rgba():
    plan = CompositionPlan(
        root=LayerNode(layer_id=1, image=_img(10, 10)),
        canvas_w=10,
        canvas_h=10,
        fill_rgba=(20, 20, 20, 255),
    )
    resolved = resolve_composition(plan)
    assert resolved.fill_rgba == (20, 20, 20, 255)
    assert resolved.canvas_w == 10 and resolved.canvas_h == 10
