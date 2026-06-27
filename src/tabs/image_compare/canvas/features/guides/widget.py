from __future__ import annotations

from core.state_management.action_base import Action
from core.store_viewport import RenderConfig, ViewState
from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasFeatureStateCommand,
    CanvasFeatureStateQuery,
    CanvasWidgetFeature,
)

from .actions import (
    SetGuidesColorAction,
    SetGuidesEnabledAction,
    SetGuidesSmoothingEnabledAction,
    SetGuidesSmoothingInterpolationMethodAction,
    SetGuidesThicknessAction,
)
from .commands import build_guides_commands
from .properties import build_guides_properties
from .runtime_hooks import build_guides_render_scene_overrides
from .settings_bindings import build_guides_settings_event_bindings
from .state import GuidesWidgetState, replace_guides_widget_state
from .toolbar import build_guides_toolbar_bindings


def _clone_guides_widget_state(view_state: ViewState) -> GuidesWidgetState:
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("guides")
    if isinstance(state, GuidesWidgetState):
        return state.clone()
    return GuidesWidgetState()


def reduce_guides_view_state(view_state: ViewState, action: Action) -> ViewState:
    if isinstance(action, SetGuidesEnabledAction):
        state = _clone_guides_widget_state(view_state)
        state.enabled = bool(action.enabled)
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesThicknessAction):
        state = _clone_guides_widget_state(view_state)
        state.thickness = max(0, int(action.thickness))
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesColorAction):
        state = _clone_guides_widget_state(view_state)
        state.color = action.color
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesSmoothingEnabledAction):
        state = _clone_guides_widget_state(view_state)
        state.smoothing_enabled = bool(action.enabled)
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesSmoothingInterpolationMethodAction):
        state = _clone_guides_widget_state(view_state)
        state.smoothing_interpolation_method = str(action.method)
        return replace_guides_widget_state(view_state, state)
    return view_state


def reduce_guides_render_config(config: RenderConfig, action: Action) -> RenderConfig:
    del action
    return config


def build_guides_state_queries():
    """Build state queries for direct feature state access."""
    from .commands import query_guides_widget_state

    return (
        CanvasFeatureStateQuery(
            query_id="widget_state", handler=query_guides_widget_state
        ),
    )


def build_guides_state_commands():
    """Build state commands for direct feature state modification."""
    from .commands import (
        command_set_guides_thickness,
        command_toggle_guides,
        command_viewport_set_smoothing_enabled,
        command_viewport_set_smoothing_interpolation_method,
        command_viewport_toggle_guides,
    )

    return (
        CanvasFeatureStateCommand(
            command_id="toggle_enabled", handler=command_toggle_guides
        ),
        CanvasFeatureStateCommand(
            command_id="set_thickness", handler=command_set_guides_thickness
        ),
        CanvasFeatureStateCommand(
            command_id="toggle_enabled_viewport", handler=command_viewport_toggle_guides
        ),
        CanvasFeatureStateCommand(
            command_id="set_smoothing_enabled",
            handler=command_viewport_set_smoothing_enabled,
        ),
        CanvasFeatureStateCommand(
            command_id="set_smoothing_method",
            handler=command_viewport_set_smoothing_interpolation_method,
        ),
    )


GUIDES_COMMAND_ALIASES = (
    CanvasFeatureCommandAlias("guides.widget_state", "query.widget_state"),
    CanvasFeatureCommandAlias("guides.enabled", "query.enabled"),
    CanvasFeatureCommandAlias("guides.thickness", "query.thickness"),
    CanvasFeatureCommandAlias("guides.color", "query.color"),
    CanvasFeatureCommandAlias("guides.toggle_enabled", "viewport.toggle_enabled"),
    CanvasFeatureCommandAlias("guides.set_thickness", "viewport.set_thickness"),
    CanvasFeatureCommandAlias(
        "guides.set_smoothing_enabled", "viewport.set_smoothing_enabled"
    ),
    CanvasFeatureCommandAlias(
        "guides.set_smoothing_interpolation_method",
        "viewport.set_smoothing_interpolation_method",
    ),
    CanvasFeatureCommandAlias("guides.settings.set_color", "settings.set_color"),
    CanvasFeatureCommandAlias(
        "guides.settings.toggle_visibility", "settings.toggle_visibility"
    ),
    CanvasFeatureCommandAlias(
        "guides.settings.set_thickness", "settings.set_thickness"
    ),
)


def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="guides",
        reduce_view_state=reduce_guides_view_state,
        reduce_render_config=reduce_guides_render_config,
        build_properties=build_guides_properties,
        build_toolbar_bindings=build_guides_toolbar_bindings,
        build_commands=build_guides_commands,
        command_aliases=GUIDES_COMMAND_ALIASES,
        build_settings_event_bindings=build_guides_settings_event_bindings,
        build_state_queries=build_guides_state_queries,
        build_state_commands=build_guides_state_commands,
        build_render_scene_overrides=build_guides_render_scene_overrides,
        i18n_namespace="ui.tooltips",
        reducer_order=20,
        property_order=20,
    )


WIDGET_FEATURE = build_widget_feature()
