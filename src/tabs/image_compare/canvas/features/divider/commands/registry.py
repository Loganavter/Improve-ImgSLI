from __future__ import annotations

from typing import Any

from core.state_management.actions import (
    InvalidateRenderCacheAction,
    SetDraggingSplitLineAction,
)
from core.state_management.viewport_actions import (
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
)
from domain.qt_adapters import color_to_qcolor
from domain.types import Color
from shared.rendering import FeatureLayoutRequirement, NormalizedBounds
from ui.canvas_infra.viewport.geometry import resolve_axis_position

from tabs.image_compare.canvas.features.divider.input.actions import SetDividerThicknessAction, SetDividerVisibleAction
from tabs.image_compare.canvas.features.divider.input.events import (
    SettingsSetDividerThicknessEvent,
    SettingsToggleDividerVisibilityEvent,
)
from tabs.image_compare.canvas.features.divider.state.feature_state import get_divider_widget_state


def dispatch_viewport_action(actions, action) -> bool:
    store = getattr(actions, "store", None)
    dispatcher = getattr(store, "_dispatcher", None) if store is not None else None
    if dispatcher is None:
        return False
    dispatcher.dispatch(action, scope="viewport")
    return True


def emit_interaction_update(actions) -> None:
    store = getattr(actions, "store", None)
    if store is not None and hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change("interaction")


def command_toggle_divider_visibility(actions, visible: bool) -> None:
    if actions.controller.event_bus is not None:
        actions.controller.event_bus.emit(
            SettingsToggleDividerVisibilityEvent(bool(visible))
        )
        return
    settings = getattr(actions.controller, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "divider",
            "settings.toggle_visibility",
            bool(visible),
        )


def command_set_divider_thickness(actions, thickness: int) -> None:
    thickness = max(0, int(thickness))
    visible = thickness > 0
    if actions.controller.event_bus is not None:
        actions.controller.event_bus.emit(SettingsToggleDividerVisibilityEvent(visible))
        actions.controller.event_bus.emit(SettingsSetDividerThicknessEvent(thickness))
        actions.controller.update_requested.emit()
        return
    settings = getattr(actions.controller, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "divider",
            "settings.set_thickness",
            thickness,
        )
        return
    actions.controller.update_requested.emit()


def command_build_export_overlay(
    store,
    *,
    scale_x: float,
    scale_y: float,
    content_offset_x: float,
    content_offset_y: float,
    content_width: float,
    content_height: float,
) -> dict[str, Any]:
    del scale_x, scale_y
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "thickness": 0}
    view = viewport.view_state
    divider_state = get_divider_widget_state(view)
    is_horizontal = bool(view.is_horizontal)
    thickness = int(divider_state.thickness)
    split_pos = int(
        round(
            resolve_axis_position(
                content_offset_y, content_height, view.split_position_visual
            )
            if is_horizontal
            else resolve_axis_position(
                content_offset_x, content_width, view.split_position_visual
            )
        )
    )
    return {
        "visible": bool(
            divider_state.visible and str(view.diff_mode or "off") == "off"
        ),
        "split_pos": split_pos,
        "is_horizontal": is_horizontal,
        "color": color_to_qcolor(divider_state.color),
        "thickness": thickness,
    }


def command_build_render_canvas_payload(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "color": (255, 255, 255, 255), "thickness": 0}
    divider_state = get_divider_widget_state(viewport.view_state)
    color = divider_state.color
    return {
        "visible": bool(divider_state.visible),
        "color": (int(color.r), int(color.g), int(color.b), int(color.a)),
        "thickness": int(divider_state.thickness),
    }


def command_build_layout_requirement(store, *, drawing_width: int, drawing_height: int):
    del store, drawing_width, drawing_height
    return FeatureLayoutRequirement(
        feature_id="divider",
        bounds=NormalizedBounds.unit(),
    )


def command_build_runtime_overlay_style(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "color": color_to_qcolor(Color()), "thickness": 0}
    divider_state = get_divider_widget_state(viewport.view_state)
    return {
        "visible": bool(divider_state.visible),
        "color": color_to_qcolor(divider_state.color),
        "thickness": int(divider_state.thickness),
    }


def command_begin_split_drag(actions) -> None:
    if dispatch_viewport_action(actions, SetDraggingSplitLineAction(True)):
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.interaction_state.is_dragging_split_line = True
    emit_interaction_update(actions)


def command_end_split_drag(actions) -> None:
    if dispatch_viewport_action(actions, SetDraggingSplitLineAction(False)):
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.interaction_state.is_dragging_split_line = False
    emit_interaction_update(actions)


def command_update_split_drag(actions, position: float) -> None:
    clamped = max(0.0, min(1.0, float(position)))
    if dispatch_viewport_action(actions, SetSplitPositionAction(clamped)):
        viewport = getattr(getattr(actions, "store", None), "viewport", None)
        interaction = (
            getattr(viewport, "interaction_state", None)
            if viewport is not None
            else None
        )
        if bool(getattr(interaction, "is_dragging_split_line", False)):
            dispatch_viewport_action(actions, SetSplitPositionVisualAction(clamped))
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.view_state.split_position = clamped
    if viewport.interaction_state.is_dragging_split_line:
        viewport.view_state.split_position_visual = clamped
    emit_interaction_update(actions)


def command_sync_split_position(actions, position: float) -> None:
    clamped = max(0.0, min(1.0, float(position)))
    dispatched = dispatch_viewport_action(actions, SetSplitPositionAction(clamped))
    dispatched = (
        dispatch_viewport_action(actions, SetSplitPositionVisualAction(clamped))
        or dispatched
    )
    if dispatched:
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.view_state.split_position = clamped
    viewport.view_state.split_position_visual = clamped
    emit_interaction_update(actions)


def query_divider_widget_state(view_state):
    return get_divider_widget_state(view_state)


def command_viewport_set_divider_thickness(store, thickness: int) -> None:
    thickness = max(0, min(10, int(thickness)))
    dispatcher = getattr(store, "_dispatcher", None)
    if dispatcher is not None:
        dispatcher.dispatch(SetDividerVisibleAction(thickness > 0), scope="viewport")
        dispatcher.dispatch(SetDividerThicknessAction(thickness), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
    else:
        state = get_divider_widget_state(store.viewport.view_state)
        state.visible = thickness > 0
        state.thickness = thickness
        store.invalidate_render_cache()
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()


def command_viewport_toggle_divider_visibility(store, visible: bool) -> None:
    visible = bool(visible)
    dispatcher = getattr(store, "_dispatcher", None)
    if dispatcher is not None:
        dispatcher.dispatch(SetDividerVisibleAction(visible), scope="viewport")
        dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
    else:
        state = get_divider_widget_state(store.viewport.view_state)
        state.visible = visible
        store.invalidate_render_cache()
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()


def build_divider_commands() -> dict[str, Any]:
    return {
        "query.widget_state": query_divider_widget_state,
        "viewport.toggle_visibility": command_viewport_toggle_divider_visibility,
        "viewport.set_thickness": command_viewport_set_divider_thickness,
        "interaction.begin_split_drag": command_begin_split_drag,
        "interaction.update_split_drag": command_update_split_drag,
        "interaction.end_split_drag": command_end_split_drag,
        "interaction.sync_split_position": command_sync_split_position,
        "settings.toggle_visibility": lambda settings, visible: settings.mutations.set_canvas_feature_setting(
            "divider.visible",
            bool(visible),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_color": lambda settings, color: settings.mutations.set_canvas_feature_setting(
            "divider.color",
            color,
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_thickness": lambda settings, thickness: settings.mutations.set_canvas_feature_setting(
            "divider.thickness",
            max(0, min(20, int(thickness))),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "render.layout_requirement": command_build_layout_requirement,
        "export.overlay": command_build_export_overlay,
        "render.canvas_payload": command_build_render_canvas_payload,
        "runtime.overlay_style": command_build_runtime_overlay_style,
    }
