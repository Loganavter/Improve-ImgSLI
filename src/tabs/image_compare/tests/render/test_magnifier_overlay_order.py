"""Active magnifier slots render last so the focused overlay is drawn on top.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md §GL passes / stacking.
"""

from __future__ import annotations
from types import SimpleNamespace

from domain.types import Color, Point
from tabs.image_compare.canvas.features.magnifier.geometry.layout_plan import build_magnifier_layout
from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel

def test_active_magnifier_slots_render_last(monkeypatch):
    import tabs.image_compare.canvas.features.magnifier.geometry.layout_plan as layout_plan

    active = MagnifierModel(
        id="active",
        position=Point(0.35, 0.5),
        border_color=Color(255, 80, 80, 255),
        visible_left=True,
        visible_center=False,
        visible_right=False,
    )
    other = MagnifierModel(
        id="other",
        position=Point(0.65, 0.5),
        border_color=Color(80, 160, 255, 255),
        visible_left=True,
        visible_center=False,
        visible_right=False,
    )

    monkeypatch.setattr(layout_plan, "iter_magnifier_models", lambda view, render: [active, other])
    monkeypatch.setattr(layout_plan, "active_magnifier_id", lambda view: "active")
    monkeypatch.setattr(
        layout_plan,
        "read_canvas_feature_color_by_setting_key",
        lambda session_type, viewport, key: Color(255, 50, 100, 230),
    )
    monkeypatch.setattr(
        layout_plan,
        "active_or_default_border_color",
        lambda view: Color(255, 255, 255, 248),
    )

    view_state = SimpleNamespace(
        diff_mode="off",
        channel_view_mode="RGB",
        canvas_widget_state={},
    )
    render_config = SimpleNamespace(interpolation_method="BILINEAR")
    viewport = SimpleNamespace(view_state=view_state, render_config=render_config)

    layout = build_magnifier_layout(
        viewport,
        width=100,
        height=100,
        canvas_width=100,
        canvas_height=100,
        divider_thickness_px=2,
    )

    assert layout is not None
    assert len(layout.slots) == 2
    assert layout.slots[0].border_color.getRgb() == (
        other.border_color.r,
        other.border_color.g,
        other.border_color.b,
        other.border_color.a,
    )
    assert layout.slots[1].border_color.getRgb() == (
        active.border_color.r,
        active.border_color.g,
        active.border_color.b,
        active.border_color.a,
    )
