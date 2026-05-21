from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.state_management.action_base import Action
    from core.store_viewport import (
        GeometryState,
        InteractionState,
        RenderCacheState,
        RenderConfig,
        ViewState,
    )
    from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor
    from plugins.video_editor.services.keyframing.types import FrameSnapshot
else:
    Action = Any
    RenderConfig = Any
    ViewState = Any
    InteractionState = Any
    GeometryState = Any
    RenderCacheState = Any
    ChannelDescriptor = Any
    FrameSnapshot = Any

ReduceViewStateFn = Callable[[ViewState, Action], ViewState]
ReduceRenderConfigFn = Callable[[RenderConfig, Action], RenderConfig]
ReduceInteractionStateFn = Callable[[InteractionState, Action], InteractionState]
ReduceGeometryStateFn = Callable[[GeometryState, Action], GeometryState]
ReduceCacheStateFn = Callable[[RenderCacheState, Action], RenderCacheState]
PropertySnapshotReader = Callable[[FrameSnapshot], dict[str, Any]]
PropertySnapshotWriter = Callable[[FrameSnapshot, dict[str, Any]], None]
PropertySettingSerializer = Callable[[dict[str, Any]], Any]
PropertySettingDeserializer = Callable[[Any], dict[str, Any]]
ToolbarToggleHandler = Callable[[Any, bool], None]
ToolbarValueHandler = Callable[[Any, int], None]
ToolbarClickHandler = Callable[[Any], None]
ToolbarSyncHandler = Callable[[Any], None]
ToolbarSliderPressedHandler = Callable[[Any], None]
ToolbarSliderReleasedHandler = Callable[[Any], None]
FeatureCommandHandler = Callable[..., Any]
SettingsEventArgsExtractor = Callable[[Any], tuple[Any, ...]]
RenderSceneOverridesBuilder = Callable[[Any], dict[str, Any]]
PrepareWorkerViewportFn = Callable[[Any, Any], None]
ApplyPlanRuntimeOverlayFn = Callable[[Any, Any], None]
ApplyLiveRuntimeOverlayFn = Callable[[Any, Any], bool]
FeatureStateQueryHandler = Callable[..., Any]
FeatureStateCommandHandler = Callable[..., None]

@dataclass(frozen=True, slots=True)
class CanvasFeatureStateQuery:
    """Query to read feature state directly."""
    query_id: str
    handler: FeatureStateQueryHandler

@dataclass(frozen=True, slots=True)
class CanvasFeatureStateCommand:
    """Command to modify feature state directly."""
    command_id: str
    handler: FeatureStateCommandHandler

@dataclass(frozen=True, slots=True)
class CanvasFeatureProperty:
    id: str
    label: str
    kind: str
    read_snapshot: PropertySnapshotReader
    write_snapshot: PropertySnapshotWriter
    channels: tuple[ChannelDescriptor, ...] | None = None
    group_id: str | None = None
    group_label: str | None = None
    setting_key: str | None = None
    serialize_setting: PropertySettingSerializer | None = None
    deserialize_setting: PropertySettingDeserializer | None = None
    order: int = 100

BuildCanvasFeaturePropertiesFn = Callable[[], tuple[CanvasFeatureProperty, ...]]
BuildCanvasFeatureStateQueriesFn = Callable[[], tuple[CanvasFeatureStateQuery, ...]]
BuildCanvasFeatureStateCommandsFn = Callable[[], tuple[CanvasFeatureStateCommand, ...]]

@dataclass(frozen=True, slots=True)
class CanvasFeatureToolbarBinding:
    control_id: str
    on_toggled: ToolbarToggleHandler | None = None
    on_value_changed: ToolbarValueHandler | None = None
    on_right_clicked: ToolbarClickHandler | None = None
    on_middle_clicked: ToolbarClickHandler | None = None
    on_pressed: ToolbarSliderPressedHandler | None = None
    on_released: ToolbarSliderReleasedHandler | None = None
    sync_state: ToolbarSyncHandler | None = None

BuildCanvasFeatureToolbarBindingsFn = Callable[
    [], tuple[CanvasFeatureToolbarBinding, ...]
]
BuildCanvasFeatureCommandsFn = Callable[[], dict[str, FeatureCommandHandler]]

@dataclass(frozen=True, slots=True)
class CanvasFeatureCommandAlias:
    capability_id: str
    command_id: str

@dataclass(frozen=True, slots=True)
class CanvasFeatureSettingsEventBinding:
    event_type: type
    command_id: str
    extract_args: SettingsEventArgsExtractor

BuildCanvasFeatureSettingsEventsFn = Callable[
    [], tuple[CanvasFeatureSettingsEventBinding, ...]
]

@dataclass(frozen=True, slots=True)
class CanvasWidgetFeature:
    name: str
    reduce_view_state: ReduceViewStateFn
    reduce_render_config: ReduceRenderConfigFn
    reduce_interaction_state: ReduceInteractionStateFn | None = None
    reduce_geometry_state: ReduceGeometryStateFn | None = None
    reduce_cache_state: ReduceCacheStateFn | None = None
    build_properties: BuildCanvasFeaturePropertiesFn | None = None
    build_toolbar_bindings: BuildCanvasFeatureToolbarBindingsFn | None = None
    build_commands: BuildCanvasFeatureCommandsFn | None = None
    command_aliases: tuple[CanvasFeatureCommandAlias, ...] = ()
    build_settings_event_bindings: BuildCanvasFeatureSettingsEventsFn | None = None
    build_state_queries: BuildCanvasFeatureStateQueriesFn | None = None
    build_state_commands: BuildCanvasFeatureStateCommandsFn | None = None
    build_render_scene_overrides: RenderSceneOverridesBuilder | None = None
    prepare_worker_viewport: PrepareWorkerViewportFn | None = None
    apply_plan_runtime_overlay: ApplyPlanRuntimeOverlayFn | None = None
    apply_live_runtime_overlay: ApplyLiveRuntimeOverlayFn | None = None
    i18n_namespace: str | None = None
    reducer_order: int = 100
    property_order: int = 100
