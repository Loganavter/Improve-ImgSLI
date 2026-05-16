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
    CanvasWidgetFeature,
)

from .actions import (
    SetDividerColorAction,
    SetDividerThicknessAction,
    SetDividerVisibleAction,
)
from .commands import build_divider_commands
from .properties import build_divider_properties
from .runtime_hooks import build_divider_render_scene_overrides
from .settings_bindings import build_divider_settings_event_bindings
from .state import get_divider_widget_state, replace_divider_widget_state
from .toolbar import build_divider_toolbar_bindings

def reduce_divider_view_state(view_state: ViewState, action: Action) -> ViewState:
    from dataclasses import replace

    if isinstance(action, SetSplitPositionAction):
        return replace(view_state, split_position=max(0.0, min(1.0, action.position)))
    if isinstance(action, SetSplitPositionVisualAction):
        return replace(view_state, split_position_visual=max(0.0, min(1.0, action.position)))
    if isinstance(action, ToggleOrientationAction):
        return replace(view_state, is_horizontal=action.is_horizontal)
    if isinstance(action, SetDividerVisibleAction):
        state = get_divider_widget_state(view_state).clone()
        state.visible = bool(action.visible)
        return replace_divider_widget_state(view_state, state)
    if isinstance(action, SetDividerColorAction):
        state = get_divider_widget_state(view_state).clone()
        state.color = action.color
        return replace_divider_widget_state(view_state, state)
    if isinstance(action, SetDividerThicknessAction):
        state = get_divider_widget_state(view_state).clone()
        state.thickness = max(0, int(action.thickness))
        return replace_divider_widget_state(view_state, state)
    return view_state

def reduce_divider_render_config(config: RenderConfig, action: Action) -> RenderConfig:
    del action
    return config

DIVIDER_COMMAND_ALIASES = (
    CanvasFeatureCommandAlias("splitter.begin_drag", "interaction.begin_split_drag"),
    CanvasFeatureCommandAlias("splitter.update_drag", "interaction.update_split_drag"),
    CanvasFeatureCommandAlias("splitter.end_drag", "interaction.end_split_drag"),
    CanvasFeatureCommandAlias("splitter.sync_split_position", "interaction.sync_split_position"),
    CanvasFeatureCommandAlias("splitter.overlay_style", "runtime.overlay_style"),
    CanvasFeatureCommandAlias("splitter.export_overlay", "export.overlay"),
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
        build_render_scene_overrides=build_divider_render_scene_overrides,
        i18n_namespace="ui.tooltips",
        reducer_order=10,
        property_order=10,
    )

WIDGET_FEATURE = build_widget_feature()
