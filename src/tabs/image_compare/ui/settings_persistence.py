from __future__ import annotations

from typing import Callable

from tabs.image_compare.canvas.registry import registry


def query_image_compare_metrics_settings(store) -> tuple[bool, bool]:
    image_state = store.viewport.session_data.image_state
    if image_state is None:
        return False, False
    return bool(image_state.auto_calculate_psnr), bool(image_state.auto_calculate_ssim)


def load_image_compare_feature_settings(store, get_setting: Callable) -> None:
    render = store.viewport.render_config

    image_state = store.viewport.session_data.image_state
    if image_state is not None:
        image_state.auto_calculate_psnr = get_setting("auto_calculate_psnr", False, bool)
        image_state.auto_calculate_ssim = get_setting("auto_calculate_ssim", False, bool)

    optimize_movement = get_setting("optimize_magnifier_movement", True, bool)
    _execute_alias("overlay.settings.set_optimize_movement", store, optimize_movement)

    magnifier_movement_interp = get_setting(
        "magnifier_movement_interpolation_method",
        None,
        str,
    )
    laser_smoothing_interp = None

    if magnifier_movement_interp is None:
        movement_interp = get_setting("movement_interpolation_method", "BILINEAR", str)
        magnifier_movement_interp = movement_interp
        laser_smoothing_interp = movement_interp

    _execute_alias(
        "overlay.settings.set_movement_interpolation",
        store,
        magnifier_movement_interp,
    )
    _execute_alias(
        "guides.set_smoothing_interpolation_method",
        store,
        laser_smoothing_interp or "BILINEAR",
    )
    render.movement_interpolation_method = magnifier_movement_interp

    _execute_alias("overlay.settings_initialize", store, get_setting)


def save_image_compare_feature_settings(store, save_setting: Callable) -> None:
    render = store.viewport.render_config
    view = store.viewport.view_state

    image_state = store.viewport.session_data.image_state
    save_setting(
        "auto_calculate_psnr",
        image_state.auto_calculate_psnr if image_state is not None else False,
    )
    save_setting(
        "auto_calculate_ssim",
        image_state.auto_calculate_ssim if image_state is not None else False,
    )

    _execute_alias("overlay.settings.persist", store, save_setting)
    save_setting("optimize_magnifier_movement", view.optimize_interactive_movement)
    save_setting(
        "magnifier_movement_interpolation_method",
        render.interactive_movement_interpolation_method,
    )
    save_setting("movement_interpolation_method", render.movement_interpolation_method)


def _execute_alias(alias: str, *args):
    command = registry().get_feature_command_by_alias(alias)
    if command is None:
        return None
    return command(*args)
