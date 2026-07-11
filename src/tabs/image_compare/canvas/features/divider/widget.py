from __future__ import annotations

from core.state_management.action_base import Action
from core.state_management.viewport_actions import (
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    ToggleOrientationAction,
)
from core.store_viewport import RenderConfig, ViewState
from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasFeatureStateCommand,
    CanvasFeatureStateQuery,
    CanvasWidgetFeature,
)

from tabs.image_compare.canvas.features.divider.input.actions import (
    SetDividerColorAction,
    SetDividerThicknessAction,
    SetDividerVisibleAction,
)
from tabs.image_compare.canvas.features.divider.commands.registry import build_divider_commands
from tabs.image_compare.canvas.features.divider.input.gestures import build_divider_gesture_bindings
from tabs.image_compare.canvas.features.divider.properties import build_divider_properties
from tabs.image_compare.canvas.features.divider.runtime_hooks import build_divider_render_scene_overrides
from tabs.image_compare.canvas.features.divider.settings_bindings import build_divider_settings_event_bindings
from tabs.image_compare.canvas.features.divider.state.feature_state import DividerWidgetState, replace_divider_widget_state
from tabs.image_compare.canvas.features.divider.toolbar.bindings import build_divider_toolbar_bindings


def _clone_divider_widget_state(view_state: ViewState) -> DividerWidgetState:
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("divider")
    if isinstance(state, DividerWidgetState):
        return state.clone()
    return DividerWidgetState()


def reduce_divider_view_state(view_state: ViewState, action: Action) -> ViewState:
    from dataclasses import replace

    if isinstance(action, SetSplitPositionAction):
        return replace(view_state, split_position=max(0.0, min(1.0, action.position)))
    if isinstance(action, SetSplitPositionVisualAction):
        return replace(
            view_state, split_position_visual=max(0.0, min(1.0, action.position))
        )
    if isinstance(action, ToggleOrientationAction):
        return replace(view_state, is_horizontal=action.is_horizontal)
    if isinstance(action, SetDividerVisibleAction):
        state = _clone_divider_widget_state(view_state)
        state.visible = bool(action.visible)
        return replace_divider_widget_state(view_state, state)
    if isinstance(action, SetDividerColorAction):
        state = _clone_divider_widget_state(view_state)
        state.color = action.color
        return replace_divider_widget_state(view_state, state)
    if isinstance(action, SetDividerThicknessAction):
        state = _clone_divider_widget_state(view_state)
        state.thickness = max(0, int(action.thickness))
        return replace_divider_widget_state(view_state, state)
    return view_state


def reduce_divider_render_config(config: RenderConfig, action: Action) -> RenderConfig:
    del action
    return config


def build_divider_state_queries():
    """Build state queries for direct feature state access."""
    from tabs.image_compare.canvas.features.divider.commands.registry import query_divider_widget_state

    return (
        CanvasFeatureStateQuery(
            query_id="widget_state", handler=query_divider_widget_state
        ),
    )


def build_divider_state_commands():
    """Build state commands for direct feature state modification."""
    from tabs.image_compare.canvas.features.divider.commands.registry import (
        command_begin_split_drag,
        command_end_split_drag,
        command_sync_split_position,
        command_update_split_drag,
        command_viewport_set_divider_thickness,
        command_viewport_toggle_divider_visibility,
    )

    return (
        CanvasFeatureStateCommand(
            command_id="toggle_visibility",
            handler=command_viewport_toggle_divider_visibility,
        ),
        CanvasFeatureStateCommand(
            command_id="set_thickness", handler=command_viewport_set_divider_thickness
        ),
        CanvasFeatureStateCommand(
            command_id="begin_drag", handler=command_begin_split_drag
        ),
        CanvasFeatureStateCommand(
            command_id="end_drag", handler=command_end_split_drag
        ),
        CanvasFeatureStateCommand(
            command_id="update_drag", handler=command_update_split_drag
        ),
        CanvasFeatureStateCommand(
            command_id="sync_position", handler=command_sync_split_position
        ),
    )


DIVIDER_COMMAND_ALIASES = (
    CanvasFeatureCommandAlias("splitter.begin_drag", "interaction.begin_split_drag"),
    CanvasFeatureCommandAlias("splitter.update_drag", "interaction.update_split_drag"),
    CanvasFeatureCommandAlias("splitter.end_drag", "interaction.end_split_drag"),
    CanvasFeatureCommandAlias(
        "splitter.sync_split_position", "interaction.sync_split_position"
    ),
    CanvasFeatureCommandAlias("splitter.overlay_style", "runtime.overlay_style"),
    CanvasFeatureCommandAlias("splitter.export_overlay", "export.overlay"),
    CanvasFeatureCommandAlias(
        "splitter.layout_requirement", "render.layout_requirement"
    ),
    CanvasFeatureCommandAlias("splitter.set_thickness", "viewport.set_thickness"),
)


def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="divider",
        reduce_view_state=reduce_divider_view_state,
        reduce_render_config=reduce_divider_render_config,
        build_properties=build_divider_properties,
        build_toolbar_bindings=build_divider_toolbar_bindings,
        build_commands=build_divider_commands,
        command_aliases=DIVIDER_COMMAND_ALIASES,
        build_settings_event_bindings=build_divider_settings_event_bindings,
        build_gesture_bindings=build_divider_gesture_bindings,
        build_state_queries=build_divider_state_queries,
        build_state_commands=build_divider_state_commands,
        build_render_scene_overrides=build_divider_render_scene_overrides,
        i18n_namespace="ui.tooltips",
        reducer_order=10,
        property_order=10,
    )


WIDGET_FEATURE = build_widget_feature()
