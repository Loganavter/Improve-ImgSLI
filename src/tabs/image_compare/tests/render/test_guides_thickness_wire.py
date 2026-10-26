"""Behaviour: the guides *thickness* control reaches the painted laser width.

Owner report (2026-10-26): "толщина лазеров у лупы всегда либо ноль, либо
единица" -- the magnifier guide lines ("laser") never thickened. Cause was a
severed wire, not a scale mapping: the toolbar value travelled all the way to
``runtime_state._guides_thickness`` (``set_guides_params``) and no renderer
read it. ``resolve_guide_spans`` painted
``ctx.resolved_style.annotation_line_stroke_px`` -- the theme stroke -- so
every value 1..10 produced the same hairline.

Pinned here (both live and export, which share ``resolve_guide_spans``):

1. the guide-set tuple carries a thickness and the resolver paints
   ``max(style_px, thickness)`` canvas px -- the value IS the width, in the
   same unit the magnifier divider takes from its toolbar
   (``divider_thickness_px`` straight into the layout, no theme multiplier),
   with the theme stroke as the FLOOR (thickness 1 reproduces the pre-fix
   look exactly). A multiplier (``thickness * style_px``, PR #696) made
   thickness 10 a fat band instead of a 10 px line (owner report
   2026-10-26);
2. a legacy 5-tuple (no thickness slot) falls back to
   ``runtime_state._guides_thickness`` instead of silently painting 1x;
3. the live producer (``apply_guides_object``) and the export producer
   (``apply_magnifier_plan_overlay``) both put the thickness into the set;
4. the pass hands the resolved width -- not the raw style -- to the guides
   uniform (``DiskItem.extra[3]``, the value ``pack_guides`` packs as
   ``lineWidthPx``).

Red before the #696 fix: every assertion below failed (the guide set had 5
slots and the width was the style px alone). Red before the width-unit fix
(2026-10-26, `thickness * style_px`): the pinned ``10.0`` widths failed --
thickness 10 painted ``20.0`` with the fixture stroke (a fat band on a real,
large canvas). The structural half of the same contract lives in
``tests/contracts/test_guides_thickness_wire.py`` (root tests may not
deep-import tab internals).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

STYLE_PX = 2.0


def _ctx(style_px: float = STYLE_PX):
    return SimpleNamespace(
        width=100,
        height=100,
        canvas_width=100,
        canvas_height=100,
        canvas_offset_x=0.0,
        canvas_offset_y=0.0,
        zoom_level=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        resolved_style=SimpleNamespace(
            annotation_line_stroke_px=style_px,
            annotation_ring_stroke_px=style_px,
        ),
        scene_frame=SimpleNamespace(feature_payloads={}, single_image_preview=0),
        feature_overlay=SimpleNamespace(capture_circles=()),
        widget=None,
    )


def _guide_set(thickness: int | None = 1):
    """One guide set as produced by the live/export applicators."""
    base = (
        QPointF(10.0, 20.0),  # capture center
        5.0,  # capture radius
        (QPointF(70.0, 80.0),),  # target centers
        (4.0,),  # target radii
        QColor(255, 0, 0, 255),
    )
    if thickness is None:
        return base  # legacy 5-tuple shape
    return base + (thickness,)


def _widget(thickness: int | None = 1, *, runtime_thickness: int | None = None):
    state = SimpleNamespace(_guide_sets=[_guide_set(thickness)], _capture_circles=[])
    if runtime_thickness is not None:
        state._guides_thickness = runtime_thickness
    return SimpleNamespace(runtime_state=state)


def _resolve(widget, ctx=None):
    from tabs.image_compare.canvas.features.guides.overlay_model import (
        resolve_guide_spans,
    )

    ctx = ctx or _ctx()
    ctx.widget = widget
    return resolve_guide_spans(ctx, widget)


def test_thickness_is_a_width_in_px_not_a_stroke_multiplier():
    (thin,) = _resolve(_widget(1))
    (thick,) = _resolve(_widget(10))
    # thickness 1 == today's look (theme stroke, the floor)
    assert thin.line_width == pytest.approx(STYLE_PX)
    # thickness 10 is a ten-px line -- the divider/toolbar convention -- and
    # NOT 10 x the theme stroke (a fat band, the #696 regression).
    assert thick.line_width == pytest.approx(10.0)
    assert thick.line_width != pytest.approx(STYLE_PX * 10.0)


def test_width_is_bounded_by_the_control_not_by_the_theme_stroke():
    """Same thickness, different theme stroke: a width, never a multiplier."""
    # A thick theme stroke (large canvas): it is the floor below the control
    # value, but the control value never scales with it.
    (floor,) = _resolve(_widget(1), _ctx(style_px=8.0))
    assert floor.line_width == pytest.approx(8.0)  # floor, not 8 x 1
    (ten_thick_theme,) = _resolve(_widget(10), _ctx(style_px=8.0))
    assert ten_thick_theme.line_width == pytest.approx(10.0)  # not 80
    # ... and at the same control value a bigger stroke cannot change the
    # result: this is the discriminator against the old `style_px * t` rule.
    (a,) = _resolve(_widget(10), _ctx(style_px=2.0))
    (b,) = _resolve(_widget(10), _ctx(style_px=8.0))
    assert a.line_width == pytest.approx(b.line_width)


def test_thickness_below_one_keeps_the_theme_floor():
    (zero,) = _resolve(_widget(0))
    assert zero.line_width == pytest.approx(STYLE_PX)


def test_legacy_five_tuple_falls_back_to_runtime_thickness():
    (span,) = _resolve(_widget(None, runtime_thickness=4))
    assert span.line_width == pytest.approx(4.0)


def test_pass_packs_the_resolved_width_into_the_uniform_input():
    from tabs.image_compare.canvas.features.guides.passes import _semantic_resolver

    thin = _semantic_resolver(_widget(1))(_ctx())
    thick = _semantic_resolver(_widget(10))(_ctx())
    (thin_item,) = thin
    (thick_item,) = thick
    # extra[3] is what pack_guides writes as lineWidthPx.
    assert float(thin_item.extra[3]) == pytest.approx(STYLE_PX)
    assert float(thick_item.extra[3]) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Producers: live scene applicator + export plan applicator
# ---------------------------------------------------------------------------


def _live_canvas():
    calls = []
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _guide_sets=[],
            _show_guides=False,
            _laser_color=QColor(),
            _guides_thickness=0,
            _request_update=lambda: None,
        ),
        set_guides_params=lambda visible, color, thickness: calls.append(
            ("set_guides_params", bool(visible), int(thickness))
        ),
        _request_update=lambda: None,
    )
    return canvas, calls


def test_live_applicator_puts_thickness_into_the_guide_set():
    from domain.types import Color
    from tabs.image_compare.canvas.features.guides.feature import (
        apply_guides_object,
    )
    from tabs.image_compare.canvas.features.guides.scene.objects import (
        GuidesSceneObject,
    )
    from ui.canvas_infra.scene.context import CanvasSceneApplyContext
    from ui.canvas_infra.scene.models import CanvasSceneGraph

    guides_object = GuidesSceneObject(
        id="mag:guides",
        kind="guides",
        visible=True,
        z_index=10,
        source_center=QPointF(10.0, 20.0),
        target_centers=(QPointF(70.0, 80.0),),
        source_radius=5.0,
        target_radii=(4.0,),
        color=Color(255, 0, 0, 255),
        thickness=7,
    )
    canvas, calls = _live_canvas()
    apply_guides_object(
        CanvasSceneGraph(objects=(guides_object,)),
        CanvasSceneApplyContext(
            canvas=canvas, geometry_state=None, use_quick_overlay=True
        ),
    )
    (guide_set,) = canvas.runtime_state._guide_sets
    assert len(guide_set) == 6, "guide set must carry the thickness slot"
    assert int(guide_set[5]) == 7
    assert calls == [("set_guides_params", True, 7)]
    # ... and the resolver turns that slot into a real width.
    (span,) = _resolve(
        SimpleNamespace(
            runtime_state=SimpleNamespace(
                _guide_sets=list(canvas.runtime_state._guide_sets)
            )
        )
    )
    assert span.line_width == pytest.approx(7.0)


def test_export_applicator_puts_plan_thickness_into_the_guide_set():
    from ui.canvas_presentation.plan import (
        GuideSet,
        OverlayLayout,
        OverlaySlot,
    )
    from tabs.image_compare.canvas.features.magnifier.render.plan_overlay import (
        apply_magnifier_plan_overlay,
    )

    slot = OverlaySlot(
        center=QPointF(50.0, 50.0),
        radius=10.0,
        uv_rect=(0.0, 0.0, 1.0, 1.0),
        uv_rect2=(0.0, 0.0, 1.0, 1.0),
        source=0,
        is_combined=False,
        internal_split=0.5,
        horizontal=True,
        divider_visible=False,
        divider_color=(0.0, 0.0, 0.0, 1.0),
        divider_thickness_uv=0.0,
        border_color=QColor(255, 255, 255, 255),
        border_width=2.0,
    )
    layout = OverlayLayout(
        slots=(slot,),
        capture_circles=(),
        guide_sets=(
            GuideSet(
                capture_center=QPointF(40.0, 40.0),
                capture_radius=10.0,
                target_centers=(QPointF(80.0, 80.0),),
                target_radii=(5.0,),
                color=QColor(255, 0, 0, 255),
            ),
        ),
        capture_center=QPointF(40.0, 40.0),
        capture_radius=10.0,
    )
    plan = SimpleNamespace(
        overlay_layout=layout,
        canvas_w=100,
        canvas_h=100,
        guides_thickness=9,
        capture_visible=True,
        capture_radius=10.0,
        render_scene=SimpleNamespace(overlay_clip_rect=None),
    )
    state = SimpleNamespace(
        _inner_content_rect_px=(0, 0, 100, 100),
        _content_rect_px=(0, 0, 100, 100),
        _content_sr=1.0,
        _capture_circles=[],
        _guide_sets=[],
    )
    canvas = SimpleNamespace(
        runtime_state=state,
        set_overlay_coords=lambda *args, **kwargs: None,
        set_feature_overlay_gpu_params=lambda *args, **kwargs: None,
    )
    apply_magnifier_plan_overlay(canvas, plan)

    (guide_set,) = state._guide_sets
    assert len(guide_set) == 6, "export guide set must carry the thickness slot"
    assert int(guide_set[5]) == 9
    (span,) = _resolve(
        SimpleNamespace(
            runtime_state=SimpleNamespace(_guide_sets=list(state._guide_sets))
        )
    )
    assert span.line_width == pytest.approx(9.0)
