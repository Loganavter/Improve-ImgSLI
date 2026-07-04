"""Image-compare payload seeder + reader for the settings dialog.

Owns the concrete `image_compare_performance` section of
`SettingsDialogData.tab_extras` / `SettingsDialogContext.tab_extras` so the
root `SettingsDialogData` DTO no longer has to carry image-compare-specific
flat fields.
"""

from __future__ import annotations

from typing import Any

SECTION_ID = "image_compare_performance"

_DEFAULTS: dict[str, Any] = {
    "optimize_magnifier_movement": True,
    "magnifier_interpolation_method": "BILINEAR",
    "optimize_laser_smoothing": False,
    "laser_interpolation_method": "BILINEAR",
    "zoom_interpolation_method": "BILINEAR",
    "magnifier_intersection_highlight_enabled": True,
    "magnifier_auto_color_new_instances": True,
    "auto_calculate_psnr": False,
    "auto_calculate_ssim": False,
    "auto_crop_black_borders": True,
}


def defaults() -> dict[str, Any]:
    return dict(_DEFAULTS)


def seed_from_store(store: object) -> dict[str, Any]:
    if store is None:
        return dict(_DEFAULTS)

    from ui.canvas_infra.scene.widget_registry import (
        get_canvas_feature_command_by_alias,
    )

    viewport = getattr(store, "viewport", None)
    settings = getattr(store, "settings", None)
    view_state = getattr(viewport, "view_state", None) if viewport is not None else None
    render_config = (
        getattr(viewport, "render_config", None) if viewport is not None else None
    )
    session_data = (
        getattr(viewport, "session_data", None) if viewport is not None else None
    )
    image_state = (
        getattr(session_data, "image_state", None) if session_data is not None else None
    )

    guides_query = get_canvas_feature_command_by_alias("guides.widget_state")
    guides_state = (
        guides_query(view_state)
        if guides_query is not None and view_state is not None
        else None
    )

    overlay_query = get_canvas_feature_command_by_alias("overlay.behavior_settings")
    magnifier_behavior = (
        overlay_query(store, {}) if overlay_query is not None else {}
    ) or {}

    payload: dict[str, Any] = dict(_DEFAULTS)
    if view_state is not None:
        payload["optimize_magnifier_movement"] = bool(
            getattr(view_state, "optimize_interactive_movement", True)
        )
    if render_config is not None:
        payload["magnifier_interpolation_method"] = getattr(
            render_config,
            "interactive_movement_interpolation_method",
            _DEFAULTS["magnifier_interpolation_method"],
        )
        payload["zoom_interpolation_method"] = getattr(
            render_config,
            "zoom_interpolation_method",
            _DEFAULTS["zoom_interpolation_method"],
        )
    if guides_state is not None:
        payload["optimize_laser_smoothing"] = bool(
            getattr(guides_state, "smoothing_enabled", False)
        )
        payload["laser_interpolation_method"] = getattr(
            guides_state,
            "smoothing_interpolation_method",
            _DEFAULTS["laser_interpolation_method"],
        )
    payload["magnifier_intersection_highlight_enabled"] = bool(
        magnifier_behavior.get(
            "intersection_highlight_enabled",
            payload["magnifier_intersection_highlight_enabled"],
        )
    )
    payload["magnifier_auto_color_new_instances"] = bool(
        magnifier_behavior.get(
            "auto_color_new_instances",
            payload["magnifier_auto_color_new_instances"],
        )
    )
    if image_state is not None:
        payload["auto_calculate_psnr"] = bool(
            getattr(image_state, "auto_calculate_psnr", False)
        )
        payload["auto_calculate_ssim"] = bool(
            getattr(image_state, "auto_calculate_ssim", False)
        )
    if settings is not None:
        payload["auto_crop_black_borders"] = bool(
            getattr(settings, "auto_crop_black_borders", True)
        )
    return payload


def read_from_dialog(dialog: object) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    def _widget_value(attr: str, default: Any) -> Any:
        widget = getattr(dialog, attr, None)
        if widget is None:
            return default
        if hasattr(widget, "currentData"):
            return widget.currentData()
        if hasattr(widget, "isChecked"):
            return widget.isChecked()
        if hasattr(widget, "value"):
            return widget.value()
        return default

    payload["optimize_magnifier_movement"] = bool(
        _widget_value(
            "optimize_movement_checkbox",
            _DEFAULTS["optimize_magnifier_movement"],
        )
    )
    payload["magnifier_interpolation_method"] = (
        _widget_value(
            "combo_mag_interp",
            _DEFAULTS["magnifier_interpolation_method"],
        )
        or _DEFAULTS["magnifier_interpolation_method"]
    )
    payload["optimize_laser_smoothing"] = bool(
        _widget_value(
            "laser_smoothing_checkbox",
            _DEFAULTS["optimize_laser_smoothing"],
        )
    )
    payload["laser_interpolation_method"] = (
        _widget_value(
            "combo_laser_interp",
            _DEFAULTS["laser_interpolation_method"],
        )
        or _DEFAULTS["laser_interpolation_method"]
    )
    payload["zoom_interpolation_method"] = (
        _widget_value(
            "combo_zoom_interp",
            _DEFAULTS["zoom_interpolation_method"],
        )
        or _DEFAULTS["zoom_interpolation_method"]
    )
    payload["magnifier_intersection_highlight_enabled"] = bool(
        _widget_value(
            "magnifier_intersection_highlight_checkbox",
            _DEFAULTS["magnifier_intersection_highlight_enabled"],
        )
    )
    payload["magnifier_auto_color_new_instances"] = bool(
        _widget_value(
            "magnifier_auto_color_checkbox",
            _DEFAULTS["magnifier_auto_color_new_instances"],
        )
    )
    payload["auto_calculate_psnr"] = bool(
        _widget_value("auto_psnr_checkbox", _DEFAULTS["auto_calculate_psnr"])
    )
    payload["auto_calculate_ssim"] = bool(
        _widget_value("auto_ssim_checkbox", _DEFAULTS["auto_calculate_ssim"])
    )
    payload["auto_crop_black_borders"] = bool(
        _widget_value("crop_checkbox", _DEFAULTS["auto_crop_black_borders"])
    )
    return payload
