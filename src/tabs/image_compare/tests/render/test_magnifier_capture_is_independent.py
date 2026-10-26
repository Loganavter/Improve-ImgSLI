"""The loupe's two controls are independent: size moves the disk, capture moves
the sampled area.

Owner decisions 2026-10-26, in order:
1. "смена интерполяции не видна" → the loupe was magnifying the unify result
   instead of the side's own pixels (fixed in 844ddfe0b).
2. "изменение размера луп изменяет размер области определения" → an invariant
   magnification had derived the capture radius from the drawn disk, so the size
   slider chased the pink ring. This file pins the opposite: the capture radius
   depends on `capture_size_relative` ONLY.

Red-before: on the invariant revision, changing `size_relative` changed
`capture_circles[0].radius` (assertion 1 fails), so the test names the behaviour
rather than the implementation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.types import Color, Point
from tabs.image_compare.canvas.features.magnifier.geometry.capture import (
    resolve_magnifier_capture_radius,
)
from tabs.image_compare.canvas.features.magnifier.geometry.layout_plan import (
    build_magnifier_layout,
)
from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel

W, H = 1400, 1000


def _layout(monkeypatch, *, size_rel=0.4, capture_rel=0.1, display_scale=0.4836):
    import tabs.image_compare.canvas.features.magnifier.geometry.layout_plan as layout_plan

    model = MagnifierModel(
        id="default",
        position=Point(0.5, 0.5),
        border_color=Color(255, 255, 255, 255),
        size_relative=size_rel,
        capture_size_relative=capture_rel,
        visible_left=True,
        visible_center=False,
        visible_right=True,
    )
    monkeypatch.setattr(layout_plan, "iter_magnifier_models", lambda v, r: [model])
    monkeypatch.setattr(layout_plan, "active_magnifier_id", lambda v: "default")
    monkeypatch.setattr(
        layout_plan,
        "read_canvas_feature_color_by_setting_key",
        lambda s, v, k: Color(255, 50, 100, 230),
    )
    monkeypatch.setattr(
        layout_plan, "active_or_default_border_color", lambda v: Color(255, 255, 255, 248)
    )
    vp = SimpleNamespace(
        view_state=SimpleNamespace(
            diff_mode="off", channel_view_mode="RGB", canvas_widget_state={}
        ),
        render_config=SimpleNamespace(interpolation_method="NEAREST"),
    )
    return build_magnifier_layout(
        vp,
        width=W,
        height=H,
        canvas_width=W,
        canvas_height=H,
        divider_thickness_px=2,
        display_scale=display_scale,
    )


@pytest.mark.parametrize("size_rel", [0.2, 0.4, 0.56, 0.8])
def test_the_size_slider_does_not_move_the_capture_ring(monkeypatch, size_rel):
    layout = _layout(monkeypatch, size_rel=size_rel)
    baseline = _layout(monkeypatch, size_rel=0.4)
    assert layout.capture_circles[0].radius == pytest.approx(
        baseline.capture_circles[0].radius, rel=1e-9
    ), "the sampled area must not follow the loupe size"
    # ...while the drawn disk DOES follow it, proportionally
    assert layout.slots[0].radius == pytest.approx(
        baseline.slots[0].radius * (size_rel / 0.4), rel=1e-9
    )


@pytest.mark.parametrize("capture_rel, factor", [(0.1, 1.0), (0.05, 0.5), (0.2, 2.0)])
def test_the_capture_slider_scales_the_sampled_area(monkeypatch, capture_rel, factor):
    baseline = _layout(monkeypatch, capture_rel=0.1).capture_circles[0].radius
    layout = _layout(monkeypatch, capture_rel=capture_rel)
    assert layout.capture_circles[0].radius == pytest.approx(baseline * factor, rel=1e-9)


def test_capture_ring_and_uv_rect_are_one_measurement(monkeypatch):
    layout = _layout(monkeypatch)
    ring = 2.0 * layout.capture_circles[0].radius
    sampled = (layout.slots[0].uv_rect[2] - layout.slots[0].uv_rect[0]) * W
    assert sampled == pytest.approx(ring, rel=1e-6)


def test_the_magnification_is_reported_not_enforced():
    """The ratio is derived from whatever the two sliders say; it is the number a
    reader (and the scene JSON) can report, not a constraint on the geometry."""
    radius, magnification = resolve_magnifier_capture_radius(
        size_relative=0.4, capture_size_relative=0.1, pix_w=W, pix_h=H, display_scale=0.4836
    )
    assert radius == pytest.approx(0.1 * H / 2, rel=1e-9)
    assert magnification > 1.0
    # a smaller capture area is a longer loupe, at the SAME drawn size
    tiny, tiny_mag = resolve_magnifier_capture_radius(
        size_relative=0.4, capture_size_relative=0.05, pix_w=W, pix_h=H, display_scale=0.4836
    )
    assert tiny == pytest.approx(radius / 2, rel=1e-9)
    assert tiny_mag == pytest.approx(magnification * 2, rel=1e-9)
