from __future__ import annotations

from typing import Any

from core.state_management.actions import InvalidateRenderCacheAction
from tabs.image_compare.canvas.registry import registry

from tabs.image_compare.canvas.features.guides.input.actions import (
    SetGuidesEnabledAction,
    SetGuidesSmoothingEnabledAction,
    SetGuidesSmoothingInterpolationMethodAction,
    SetGuidesThicknessAction,
)
from tabs.image_compare.canvas.features.guides.state.feature_state import get_guides_widget_state


def _sync_active_laser_enabled(store, enabled: bool) -> None:
    # Scrolling the thickness slider to 0 must also clear the active
    # magnifier's show_laser flag, mirroring what clicking the toggle does —
    # otherwise sync_guides_toolbar_state() sees show_laser still True and
    # forces the slider back to a minimum of 1, so it can never reach 0.
    if store is None:
        return
    cmd = registry().get_feature_command_by_alias("overlay.set_active_laser_enabled")
    if cmd is not None:
        cmd(store, bool(enabled))


def command_build_render_canvas_payload(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {
            "enabled": False,
            "thickness": 1,
            "color": (255, 255, 255, 255),
            "smoothing_enabled": False,
            "smoothing_interpolation_method": "BILINEAR",
        }
    state = get_guides_widget_state(viewport.view_state)
    color = state.color
    return {
        "enabled": bool(state.enabled),
        "thickness": int(state.thickness),
        "color": (int(color.r), int(color.g), int(color.b), int(color.a)),
        "smoothing_enabled": bool(state.smoothing_enabled),
        "smoothing_interpolation_method": str(state.smoothing_interpolation_method),
    }


def command_toggle_guides(actions, enabled: bool) -> None:
    enabled = bool(enabled)
    settings = getattr(actions, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "guides",
            "settings.toggle_visibility",
            enabled,
        )
        return
    store = getattr(actions, "store", None)
    dispatcher = getattr(store, "_dispatcher", None) if store is not None else None
    if dispatcher is not None:
        dispatcher.dispatch(SetGuidesEnabledAction(enabled), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        store.emit_state_change()
        return
    viewport = getattr(store, "viewport", None) if store is not None else None
    if viewport is None:
        return
    state = get_guides_widget_state(viewport.view_state)
    state.enabled = enabled
    store.invalidate_render_cache()
    store.emit_state_change()


def command_set_guides_thickness(actions, thickness: int) -> None:
    thickness = max(0, int(thickness))
    store = getattr(actions, "store", None)
    _sync_active_laser_enabled(store, thickness != 0)
    settings = getattr(actions, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "guides",
            "settings.set_thickness",
            thickness,
        )
        return
    dispatcher = getattr(store, "_dispatcher", None) if store is not None else None
    if dispatcher is not None:
        dispatcher.dispatch(SetGuidesThicknessAction(thickness), scope="viewport")
        dispatcher.dispatch(SetGuidesEnabledAction(thickness != 0), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        store.emit_state_change()
        return
    viewport = getattr(store, "viewport", None) if store is not None else None
    if viewport is None:
        return
    state = get_guides_widget_state(viewport.view_state)
    state.thickness = thickness
    state.enabled = thickness != 0
    store.invalidate_render_cache()
    store.emit_state_change()


def query_guides_widget_state(view_state):
    return get_guides_widget_state(view_state)


def command_viewport_toggle_guides(store, enabled: bool) -> None:
    dispatcher = getattr(store, "_dispatcher", None)
    if dispatcher is not None:
        dispatcher.dispatch(SetGuidesEnabledAction(enabled), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
    else:
        state = get_guides_widget_state(store.viewport.view_state)
        state.enabled = bool(enabled)
        store.invalidate_render_cache()


def command_viewport_set_smoothing_enabled(store, enabled: bool) -> None:
    dispatcher = getattr(store, "_dispatcher", None)
    if dispatcher is not None:
        dispatcher.dispatch(SetGuidesSmoothingEnabledAction(enabled), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
    else:
        state = get_guides_widget_state(store.viewport.view_state)
        state.smoothing_enabled = bool(enabled)
        store.invalidate_render_cache()


def command_viewport_set_smoothing_interpolation_method(store, method: str) -> None:
    dispatcher = getattr(store, "_dispatcher", None)
    if dispatcher is not None:
        dispatcher.dispatch(
            SetGuidesSmoothingInterpolationMethodAction(method), scope="viewport"
        )
    else:
        state = get_guides_widget_state(store.viewport.view_state)
        state.smoothing_interpolation_method = str(method)
    store.invalidate_render_cache()


def command_viewport_set_guides_thickness(store, thickness: int) -> None:
    thickness = max(0, int(thickness))
    _sync_active_laser_enabled(store, thickness != 0)
    dispatcher = getattr(store, "_dispatcher", None)
    if dispatcher is not None:
        dispatcher.dispatch(SetGuidesThicknessAction(thickness), scope="viewport")
        dispatcher.dispatch(SetGuidesEnabledAction(thickness != 0), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
    else:
        state = get_guides_widget_state(store.viewport.view_state)
        state.thickness = thickness
        state.enabled = thickness != 0
        store.invalidate_render_cache()


def build_guides_commands() -> dict[str, Any]:
    return {
        "query.widget_state": query_guides_widget_state,
        "query.enabled": lambda view_state: bool(
            get_guides_widget_state(view_state).enabled
        ),
        "query.thickness": lambda view_state: int(
            get_guides_widget_state(view_state).thickness
        ),
        "query.color": lambda view_state: get_guides_widget_state(view_state).color,
        "viewport.toggle_enabled": command_viewport_toggle_guides,
        "viewport.set_thickness": command_viewport_set_guides_thickness,
        "viewport.set_smoothing_enabled": command_viewport_set_smoothing_enabled,
        "viewport.set_smoothing_interpolation_method": command_viewport_set_smoothing_interpolation_method,
        "settings.toggle_visibility": lambda settings, enabled: settings.mutations.set_canvas_feature_setting(
            "guides.enabled",
            bool(enabled),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_thickness": lambda settings, thickness: settings.mutations.set_canvas_feature_setting(
            "guides.thickness",
            max(0, int(thickness)),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_color": lambda settings, color: settings.mutations.set_canvas_feature_setting(
            "guides.color",
            color,
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "render.canvas_payload": command_build_render_canvas_payload,
    }
