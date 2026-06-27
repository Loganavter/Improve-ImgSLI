"""Multi-compare keeps state, canvas-px layout, and framebuffer projection separate."""

import numpy as np

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.scene.passes.dividers import DividersOverlaySource
from tabs.multi_compare.scene.projection import build_render_context
from tabs.multi_compare.services.composition_builder import (
    DEFAULT_SPLIT_GAP_PX,
    build_composition_plan,
)
from ui.canvas_presentation.composition import resolve_composition


def _image(w=100, h=80):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _state(*, weights=(1.0, 1.0), focused_slot_id=None):
    return MultiCompareState(
        slots=[
            CompareSlot(id=1, label="one", image=_image()),
            CompareSlot(id=2, label="two", image=_image()),
        ],
        root=SplitNode("h", [LeafNode(1), LeafNode(2)], list(weights)),
        focused_slot_id=focused_slot_id,
    )


def test_multi_compare_layers_are_resolved_in_canvas_px_before_sr_projection():
    state = _state(weights=(1.0, 3.0))
    plan = build_composition_plan(
        state,
        canvas_w=404,
        canvas_h=200,
        include_labels=False,
    )
    composition = resolve_composition(plan)

    assert [layer.rect for layer in composition.layers] == [
        (0, 0, 100, 200),
        (104, 0, 300, 200),
    ]

    ctx = build_render_context(
        composition=composition,
        framebuffer_size=(202.0, 100.0),
        clip_matrix=(1.0,) * 16,
        available_slot_ids={1, 2},
    )

    assert ctx.scale == 0.5
    assert ctx.offset == (0.0, 0.0)
    assert [layer.rect for layer in composition.layers] == [
        (0, 0, 100, 200),
        (104, 0, 300, 200),
    ]
    assert [projected.rect_fb for projected in ctx.projected_layers] == [
        (0.0, 0.0, 50.0, 100.0),
        (52.0, 0.0, 150.0, 100.0),
    ]


def test_multi_compare_dividers_read_redux_tree_not_flattened_layers():
    state = _state(weights=(1.0, 3.0))
    composition = resolve_composition(
        build_composition_plan(
            state,
            canvas_w=404,
            canvas_h=200,
            include_labels=False,
        )
    )

    rects = DividersOverlaySource().projected_divider_rects(
        composition=composition,
        state=state,
        scale=0.5,
        offset=(0.0, 0.0),
    )

    assert len(rects) == 1
    assert rects[0].x() == 50.0
    assert rects[0].width() == DividersOverlaySource.MIN_THICKNESS_FB
    assert rects[0].height() == 100.0

    state_with_changed_redux_tree = _state(weights=(3.0, 1.0))
    shifted = DividersOverlaySource().projected_divider_rects(
        composition=composition,
        state=state_with_changed_redux_tree,
        scale=0.5,
        offset=(0.0, 0.0),
    )

    assert shifted[0].x() == 150.0


def test_multi_compare_dividers_are_suppressed_in_focused_redux_state():
    focused = _state(focused_slot_id=1)
    composition = resolve_composition(
        build_composition_plan(
            focused,
            canvas_w=404,
            canvas_h=200,
            include_labels=False,
        )
    )

    rects = DividersOverlaySource().projected_divider_rects(
        composition=composition,
        state=focused,
        scale=1.0,
        offset=(0.0, 0.0),
    )

    assert rects == ()


def test_multi_compare_divider_gap_constant_is_canvas_px_not_framebuffer_px():
    state = _state()
    composition = resolve_composition(
        build_composition_plan(
            state,
            canvas_w=204,
            canvas_h=100,
            include_labels=False,
        )
    )

    rects = DividersOverlaySource().projected_divider_rects(
        composition=composition,
        state=state,
        scale=3.0,
        offset=(0.0, 0.0),
    )

    assert DEFAULT_SPLIT_GAP_PX == 4
    assert rects[0].width() == 12.0
