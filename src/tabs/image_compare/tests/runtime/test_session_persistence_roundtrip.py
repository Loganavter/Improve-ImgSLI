"""image_compare's viewport-block and magnifier project persistence."""

from __future__ import annotations

import json

import pytest

from core.store_viewport import RenderConfig, ViewState, ViewportState
from tabs.image_compare.session_persistence import (
    restore_viewport_block,
    serialize_viewport_block,
)


def test_render_config_and_viewport_block_roundtrip():
    from tabs.image_compare.state.models import ImageSessionState
    from core.store_viewport import SessionData

    vp = ViewportState(
        render_config=RenderConfig(font_size_percent=140, jpeg_quality=88),
        view_state=ViewState(
            split_position=0.33,
            is_horizontal=True,
            diff_mode="highlight",
            channel_view_mode="R",
            overlay_enabled=True,
            showing_single_image_mode=1,
            movement_speed_per_sec=3.5,
        ),
        session_data=SessionData(
            image_state=ImageSessionState(
                auto_calculate_psnr=True, auto_calculate_ssim=True
            )
        ),
    )
    blob = serialize_viewport_block(vp)
    assert blob["view_state"]["diff_mode"] == "highlight"
    assert blob["render_config"]["font_size_percent"] == 140
    assert blob["image_state"]["auto_calculate_psnr"] is True

    other = ViewportState(
        session_data=SessionData(image_state=ImageSessionState())
    )
    restore_viewport_block(other, blob)
    assert other.view_state.split_position == pytest.approx(0.33)
    assert other.view_state.is_horizontal is True
    assert other.view_state.diff_mode == "highlight"
    assert other.render_config.font_size_percent == 140
    assert other.session_data.image_state.auto_calculate_ssim is True


def test_magnifier_models_roundtrip_in_viewport_block():
    from tabs.image_compare.canvas.features.magnifier.state.feature_state import (
        get_magnifier_widget_state,
    )
    from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel
    from tabs.image_compare.canvas.features.magnifier.persistence import (
        restore_magnifier_from_project,
        serialize_magnifier_for_project,
    )
    from domain.types import Color, Point

    vp = ViewportState()
    state = get_magnifier_widget_state(vp.view_state)
    state.enabled = True
    model = MagnifierModel(
        id="mag-1",
        position=Point(0.25, 0.75),
        size_relative=0.3,
        border_color=Color(1, 2, 3, 4),
        is_horizontal=True,
    )
    state.models[model.id] = model
    state.active_id = model.id

    blob = serialize_magnifier_for_project(vp.view_state)
    assert blob["enabled"] is True
    assert blob["models"][0]["id"] == "mag-1"
    json.dumps(blob)

    other = ViewportState()
    restore_magnifier_from_project(other.view_state, blob)
    restored = get_magnifier_widget_state(other.view_state)
    assert restored.enabled is True
    assert restored.active_id == "mag-1"
    assert "mag-1" in restored.models
    assert restored.models["mag-1"].position.x == pytest.approx(0.25)
    assert restored.models["mag-1"].border_color.r == 1
