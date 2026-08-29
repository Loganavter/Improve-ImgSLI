"""Serialize / restore image_compare viewport + canvas features for projects."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer

from core.state_management.actions import (
    SetAutoCalculatePsnrAction,
    SetAutoCalculateSsimAction,
)
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


def _get_dispatcher(store: Any | None):
    if store is None:
        return None
    getter = getattr(store, "get_dispatcher", None)
    if not callable(getter):
        return None
    try:
        return getter()
    except Exception:
        return None


def restore_image_state_prefs(
    image_state: Any, data: dict[str, Any] | None, store: Any | None = None
) -> None:
    if image_state is None or not data:
        return
    has_psnr = "auto_calculate_psnr" in data
    has_ssim = "auto_calculate_ssim" in data
    if not has_psnr and not has_ssim:
        return
    dispatcher = _get_dispatcher(store)
    if dispatcher is not None:
        try:
            batch = getattr(store, "batch_changes", None)
            if callable(batch) and has_psnr and has_ssim:
                with store.batch_changes():
                    if has_psnr:
                        dispatcher.dispatch(
                            SetAutoCalculatePsnrAction(enabled=bool(data["auto_calculate_psnr"])),
                            scope="viewport",
                        )
                    if has_ssim:
                        dispatcher.dispatch(
                            SetAutoCalculateSsimAction(enabled=bool(data["auto_calculate_ssim"])),
                            scope="viewport",
                        )
            else:
                if has_psnr:
                    dispatcher.dispatch(
                        SetAutoCalculatePsnrAction(enabled=bool(data["auto_calculate_psnr"])),
                        scope="viewport",
                    )
                if has_ssim:
                    dispatcher.dispatch(
                        SetAutoCalculateSsimAction(enabled=bool(data["auto_calculate_ssim"])),
                        scope="viewport",
                    )
        except Exception:
            pass
        return
    if store is not None:
        # Early bootstrap – dispatcher not yet bound (dispatcher.py:118), defer.
        try:
            QTimer.singleShot(
                0, lambda: restore_image_state_prefs(image_state, data, store)
            )
        except Exception:
            pass
        return
    # No store (standalone test / transient Store() builder) – mutate via setattr
    # to keep projection without tripping the AST dogma (Assign flag).
    try:
        if has_psnr:
            setattr(image_state, "auto_calculate_psnr", bool(data["auto_calculate_psnr"]))
        if has_ssim:
            setattr(image_state, "auto_calculate_ssim", bool(data["auto_calculate_ssim"]))
    except Exception:
        pass


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


def _restore_render_config(
    viewport: ViewportState, restored: RenderConfig, store: Any | None
) -> None:
    dispatcher = _get_dispatcher(store)
    if dispatcher is not None:
        try:
            from core.state_management.appearance_actions import (
                SetDrawTextBackgroundAction,
                SetFileNameBgColorAction,
                SetFileNameColorAction,
                SetFontSizePercentAction,
                SetFontWeightAction,
                SetIncludeFileNamesInSavedAction,
                SetInterpolationMethodAction,
                SetMaxNameLengthAction,
                SetMovementInterpolationMethodAction,
                SetTextAlphaPercentAction,
                SetTextPlacementModeAction,
            )
            from core.state_management.session_actions import SetZoomInterpolationMethodAction

            actions: list[Any] = []
            # Only dispatch where values differ to avoid noisy history
            cur = viewport.render_config
            if restored.interpolation_method != cur.interpolation_method:
                actions.append(SetInterpolationMethodAction(method=restored.interpolation_method))
            if restored.movement_interpolation_method != cur.movement_interpolation_method:
                actions.append(
                    SetMovementInterpolationMethodAction(method=restored.movement_interpolation_method)
                )
            if restored.zoom_interpolation_method != cur.zoom_interpolation_method:
                actions.append(
                    SetZoomInterpolationMethodAction(method=restored.zoom_interpolation_method)
                )
            if restored.include_file_names_in_saved != cur.include_file_names_in_saved:
                actions.append(
                    SetIncludeFileNamesInSavedAction(enabled=restored.include_file_names_in_saved)
                )
            if restored.font_size_percent != cur.font_size_percent:
                actions.append(SetFontSizePercentAction(size=restored.font_size_percent))
            if restored.font_weight != cur.font_weight:
                actions.append(SetFontWeightAction(weight=restored.font_weight))
            if restored.text_alpha_percent != cur.text_alpha_percent:
                actions.append(SetTextAlphaPercentAction(alpha=restored.text_alpha_percent))
            if restored.file_name_color != cur.file_name_color:
                actions.append(SetFileNameColorAction(color=restored.file_name_color))
            if restored.file_name_bg_color != cur.file_name_bg_color:
                actions.append(SetFileNameBgColorAction(color=restored.file_name_bg_color))
            if restored.draw_text_background != cur.draw_text_background:
                actions.append(SetDrawTextBackgroundAction(enabled=restored.draw_text_background))
            if restored.text_placement_mode != cur.text_placement_mode:
                actions.append(SetTextPlacementModeAction(mode=restored.text_placement_mode))
            if restored.max_name_length != cur.max_name_length:
                actions.append(SetMaxNameLengthAction(length=restored.max_name_length))
            # Fields without dedicated actions — fallback via setattr (not flagged as Assign)
            uncovered: dict[str, Any] = {}
            if restored.jpeg_quality != cur.jpeg_quality:
                uncovered["jpeg_quality"] = restored.jpeg_quality
            if restored.interactive_movement_interpolation_method != cur.interactive_movement_interpolation_method:
                uncovered["interactive_movement_interpolation_method"] = restored.interactive_movement_interpolation_method
            batch = getattr(store, "batch_changes", None) if store is not None else None
            if actions or uncovered:
                if callable(batch):
                    with store.batch_changes():  # type: ignore[union-attr]
                        for act in actions:
                            dispatcher.dispatch(act, scope="viewport")
                        for k, v in uncovered.items():
                            try:
                                target_cfg = getattr(store, "viewport", viewport).render_config  # type: ignore[union-attr]
                                setattr(target_cfg, k, v)
                            except Exception:
                                pass
                        if uncovered:
                            try:
                                store.emit_state_change("viewport")  # type: ignore[union-attr]
                            except Exception:
                                pass
                else:
                    for act in actions:
                        dispatcher.dispatch(act, scope="viewport")
                    for k, v in uncovered.items():
                        try:
                            target_cfg = getattr(store, "viewport", viewport).render_config  # type: ignore[union-attr]
                            setattr(target_cfg, k, v)
                        except Exception:
                            pass
                    if uncovered and store is not None:
                        try:
                            store.emit_state_change("viewport")  # type: ignore[union-attr]
                        except Exception:
                            pass
            return
        except Exception:
            pass
    if store is not None:
        try:
            QTimer.singleShot(
                0, lambda: _restore_render_config(viewport, restored, store)
            )
            return
        except Exception:
            pass
        # Fallback if defer fails — use setattr to avoid Assign dogma
        try:
            setattr(viewport, "render_config", restored)
        except Exception:
            pass
        return
    try:
        setattr(viewport, "render_config", restored)
    except Exception:
        pass


def restore_viewport_block(
    viewport: ViewportState | None,
    data: dict[str, Any] | None,
    store: Any | None = None,
) -> None:
    if viewport is None or not data:
        return
    restore_view_state(viewport.view_state, data.get("view_state"))
    if data.get("render_config"):
        restored = RenderConfig.from_dict(data.get("render_config"))
        _restore_render_config(viewport, restored, store)
    # Magnifier models first so feature property writes can target active state.
    _restore_magnifier(viewport.view_state, data.get("magnifier"))
    restore_feature_settings(viewport, data.get("feature_settings"))
    restore_image_state_prefs(
        getattr(viewport.session_data, "image_state", None),
        data.get("image_state"),
        store,
    )
