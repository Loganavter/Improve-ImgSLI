from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QTimer

from core.state_management.actions import (
    SetAutoCalculatePsnrAction,
    SetAutoCalculateSsimAction,
)
from tabs.image_compare.canvas.registry import registry


def query_image_compare_metrics_settings(store) -> tuple[bool, bool]:
    image_state = store.viewport.session_data.image_state
    if image_state is None:
        return False, False
    return bool(image_state.auto_calculate_psnr), bool(image_state.auto_calculate_ssim)


def _deferred_auto_calculate(store, psnr_val: bool, ssim_val: bool) -> None:
    dispatcher = getattr(store, "get_dispatcher", lambda: None)()
    if dispatcher is not None:
        try:
            with store.batch_changes():
                dispatcher.dispatch(
                    SetAutoCalculatePsnrAction(enabled=psnr_val), scope="viewport"
                )
                dispatcher.dispatch(
                    SetAutoCalculateSsimAction(enabled=ssim_val), scope="viewport"
                )
        except Exception:
            pass
        return
    # Still no dispatcher – retry once more (early bootstrap race).
    try:
        QTimer.singleShot(
            0, lambda: _deferred_auto_calculate(store, psnr_val, ssim_val)
        )
    except Exception:
        pass


def load_image_compare_feature_settings(store, get_setting: Callable) -> None:
    render = store.viewport.render_config

    image_state = store.viewport.session_data.image_state
    if image_state is not None:
        psnr_val = bool(get_setting("auto_calculate_psnr", False, bool))
        ssim_val = bool(get_setting("auto_calculate_ssim", False, bool))
        dispatcher = getattr(store, "get_dispatcher", lambda: None)()
        if dispatcher is not None:
            try:
                with store.batch_changes():
                    dispatcher.dispatch(
                        SetAutoCalculatePsnrAction(enabled=psnr_val), scope="viewport"
                    )
                    dispatcher.dispatch(
                        SetAutoCalculateSsimAction(enabled=ssim_val), scope="viewport"
                    )
            except Exception:
                pass
        else:
            # Early bootstrap before dispatcher is wired (dispatcher.py:118) – defer.
            # Keep immediate setattr for fake stores / tests where no dispatcher
            # ever appears, so the value is still observable without a dispatch.
            try:
                setattr(image_state, "auto_calculate_psnr", psnr_val)
                setattr(image_state, "auto_calculate_ssim", ssim_val)
            except Exception:
                pass
            try:
                QTimer.singleShot(
                    0, lambda: _deferred_auto_calculate(store, psnr_val, ssim_val)
                )
            except Exception:
                pass

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
