"""Serialize / restore image_compare viewport + canvas features for projects."""

from __future__ import annotations

from typing import Any

from core.store_viewport import RenderConfig, ViewState, ViewportState
from ui.canvas_infra.scene.property_access import (
    deserialize_canvas_feature_setting,
    read_canvas_feature_property,
    serialize_canvas_feature_setting,
    write_canvas_feature_property,
)
from ui.canvas_infra.scene.registry import get_canvas_registry


def serialize_view_state(view: ViewState) -> dict[str, Any]:
    return {
        "split_position": float(view.split_position),
        "split_position_visual": float(view.split_position_visual),
        "is_horizontal": bool(view.is_horizontal),
        "diff_mode": str(view.diff_mode or "off"),
        "channel_view_mode": str(view.channel_view_mode or "RGB"),
        "optimize_interactive_movement": bool(view.optimize_interactive_movement),
        "overlay_enabled": bool(view.overlay_enabled),
        "showing_single_image_mode": int(view.showing_single_image_mode),
        "movement_speed_per_sec": float(view.movement_speed_per_sec),
    }


def restore_view_state(view: ViewState, data: dict[str, Any] | None) -> None:
    if not data:
        return
    if "split_position" in data:
        view.split_position = float(data["split_position"])
    if "split_position_visual" in data:
        view.split_position_visual = float(data["split_position_visual"])
    elif "split_position" in data:
        view.split_position_visual = float(data["split_position"])
    if "is_horizontal" in data:
        view.is_horizontal = bool(data["is_horizontal"])
    if "diff_mode" in data and data["diff_mode"] is not None:
        view.diff_mode = str(data["diff_mode"])
    if "channel_view_mode" in data and data["channel_view_mode"] is not None:
        view.channel_view_mode = str(data["channel_view_mode"])
    if "optimize_interactive_movement" in data:
        view.optimize_interactive_movement = bool(data["optimize_interactive_movement"])
    if "overlay_enabled" in data:
        view.overlay_enabled = bool(data["overlay_enabled"])
    if "showing_single_image_mode" in data:
        view.showing_single_image_mode = int(data["showing_single_image_mode"])
    if "movement_speed_per_sec" in data:
        view.movement_speed_per_sec = float(data["movement_speed_per_sec"])


def serialize_feature_settings(
    viewport: ViewportState, session_type: str = "image_compare"
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in get_canvas_registry(session_type).get_feature_properties():
        if not prop.setting_key:
            continue
        channels = read_canvas_feature_property(viewport, prop)
        out[prop.setting_key] = serialize_canvas_feature_setting(prop, channels)
    return out


def restore_feature_settings(
    viewport: ViewportState,
    data: dict[str, Any] | None,
    session_type: str = "image_compare",
) -> None:
    if not data:
        return
    by_key = {
        prop.setting_key: prop
        for prop in get_canvas_registry(session_type).get_feature_properties()
        if prop.setting_key
    }
    for key, raw in data.items():
        prop = by_key.get(key)
        if prop is None:
            continue
        channels = deserialize_canvas_feature_setting(prop, raw)
        write_canvas_feature_property(viewport, prop, channels)


def serialize_image_state_prefs(image_state: Any) -> dict[str, Any]:
    if image_state is None:
        return {}
    return {
        "auto_calculate_psnr": bool(getattr(image_state, "auto_calculate_psnr", False)),
        "auto_calculate_ssim": bool(getattr(image_state, "auto_calculate_ssim", False)),
    }


def restore_image_state_prefs(image_state: Any, data: dict[str, Any] | None) -> None:
    if image_state is None or not data:
        return
    if "auto_calculate_psnr" in data:
        image_state.auto_calculate_psnr = bool(data["auto_calculate_psnr"])
    if "auto_calculate_ssim" in data:
        image_state.auto_calculate_ssim = bool(data["auto_calculate_ssim"])


def _serialize_magnifier(view_state: ViewState) -> dict[str, Any]:
    cmd = get_canvas_registry("image_compare").get_feature_command_by_alias(
        "project.serialize_magnifier"
    )
    if cmd is None:
        return {}
    return dict(cmd(view_state) or {})


def _restore_magnifier(view_state: ViewState, data: dict[str, Any] | None) -> None:
    if not data:
        return
    cmd = get_canvas_registry("image_compare").get_feature_command_by_alias(
        "project.restore_magnifier"
    )
    if cmd is None:
        return
    cmd(view_state, data)


def serialize_viewport_block(viewport: ViewportState | None) -> dict[str, Any]:
    if viewport is None:
        return {}
    return {
        "view_state": serialize_view_state(viewport.view_state),
        "render_config": viewport.render_config.to_dict(),
        "feature_settings": serialize_feature_settings(viewport),
        "magnifier": _serialize_magnifier(viewport.view_state),
        "image_state": serialize_image_state_prefs(
            getattr(viewport.session_data, "image_state", None)
        ),
    }


def restore_viewport_block(
    viewport: ViewportState | None, data: dict[str, Any] | None
) -> None:
    if viewport is None or not data:
        return
    restore_view_state(viewport.view_state, data.get("view_state"))
    if data.get("render_config"):
        viewport.render_config = RenderConfig.from_dict(data.get("render_config"))
    # Magnifier models first so feature property writes can target active state.
    _restore_magnifier(viewport.view_state, data.get("magnifier"))
    restore_feature_settings(viewport, data.get("feature_settings"))
    restore_image_state_prefs(
        getattr(viewport.session_data, "image_state", None),
        data.get("image_state"),
    )
