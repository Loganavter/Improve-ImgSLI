"""Multi-compare keeps state, canvas-px layout, and framebuffer projection separate."""

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
from tabs.multi_compare.tests.pixel_fixtures import slot_image
from ui.canvas_presentation.composition import resolve_composition


def _image(w=100, h=80):
    return slot_image(w, h)


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


def test_multi_compare_dividers_read_resolved_composition_gaps():
    """Divider geometry is baked into ``ResolvedComposition.gaps`` at
    plan-build time — the overlay source takes no ``state`` argument at all,
    so live and offscreen-export rendering (which never populates a widget
    ``state``) see identical divider geometry."""
    composition = resolve_composition(
        build_composition_plan(
            _state(weights=(1.0, 3.0)),
            canvas_w=404,
            canvas_h=200,
            include_labels=False,
        )
    )

    rects = DividersOverlaySource().projected_divider_rects(
        composition=composition,
        scale=0.5,
        offset=(0.0, 0.0),
        framebuffer_size=(202.0, 100.0),
    )

    assert len(rects) == 1
    assert rects[0].x() == 50.5
    assert rects[0].width() == DividersOverlaySource.MIN_THICKNESS_FB
    assert rects[0].height() == 100.0

    other_composition = resolve_composition(
        build_composition_plan(
            _state(weights=(3.0, 1.0)),
            canvas_w=404,
            canvas_h=200,
            include_labels=False,
        )
    )
    shifted = DividersOverlaySource().projected_divider_rects(
        composition=other_composition,
        scale=0.5,
        offset=(0.0, 0.0),
        framebuffer_size=(202.0, 100.0),
    )

    assert shifted[0].x() == 150.5


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
        scale=1.0,
        offset=(0.0, 0.0),
        framebuffer_size=(404.0, 200.0),
    )

    assert rects == ()


def test_multi_compare_divider_gap_thickness_is_du_relative_to_framebuffer_short_edge():
    """Divider thickness is a "du" value (design units against a 1000px
    reference short edge, same convention as image_compare's
    guides_stroke_du) — it scales with the render target's framebuffer
    size, not with the composition's fixed native canvas size, so preview
    and export stay visually WYSIWYG. See DividersOverlaySource._project_gap."""
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
        scale=3.0,
        offset=(0.0, 0.0),
        framebuffer_size=(612.0, 300.0),
    )

    assert DEFAULT_SPLIT_GAP_PX == 4
    # thickness_du (4) * short_edge_fb (300) / 1000 reference = 1.2
    assert rects[0].width() == 1.2
