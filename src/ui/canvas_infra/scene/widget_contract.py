from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.state_management.action_base import Action
    from core.store_viewport import RenderConfig, ViewState
    from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor
    from plugins.video_editor.services.keyframing.types import FrameSnapshot
else:
    Action = Any
    RenderConfig = Any
    ViewState = Any
    ChannelDescriptor = Any
    FrameSnapshot = Any

ReduceViewStateFn = Callable[[ViewState, Action], ViewState]
ReduceRenderConfigFn = Callable[[RenderConfig, Action], RenderConfig]
PropertySnapshotReader = Callable[[FrameSnapshot], dict[str, Any]]
PropertySnapshotWriter = Callable[[FrameSnapshot, dict[str, Any]], None]
PropertySettingSerializer = Callable[[dict[str, Any]], Any]
PropertySettingDeserializer = Callable[[Any], dict[str, Any]]
ToolbarToggleHandler = Callable[[Any, bool], None]
ToolbarValueHandler = Callable[[Any, int], None]
ToolbarClickHandler = Callable[[Any], None]
ToolbarSyncHandler = Callable[[Any], None]
FeatureCommandHandler = Callable[..., Any]
SettingsEventArgsExtractor = Callable[[Any], tuple[Any, ...]]
RenderSceneOverridesBuilder = Callable[[Any], dict[str, Any]]

@dataclass(frozen=True, slots=True)
class CanvasFeatureProperty:
    id: str
    label: str
    kind: str
    read_snapshot: PropertySnapshotReader
    write_snapshot: PropertySnapshotWriter
    channels: tuple[ChannelDescriptor, ...] | None = None
    group_id: str = "viewport"
    group_label: str = "Viewport"
    setting_key: str | None = None
    serialize_setting: PropertySettingSerializer | None = None
    deserialize_setting: PropertySettingDeserializer | None = None
    order: int = 100

BuildCanvasFeaturePropertiesFn = Callable[[], tuple[CanvasFeatureProperty, ...]]

@dataclass(frozen=True, slots=True)
class CanvasFeatureToolbarBinding:
    control_id: str
    on_toggled: ToolbarToggleHandler | None = None
    on_value_changed: ToolbarValueHandler | None = None
    on_right_clicked: ToolbarClickHandler | None = None
    on_middle_clicked: ToolbarClickHandler | None = None
    sync_state: ToolbarSyncHandler | None = None

BuildCanvasFeatureToolbarBindingsFn = Callable[
    [], tuple[CanvasFeatureToolbarBinding, ...]
]
BuildCanvasFeatureCommandsFn = Callable[[], dict[str, FeatureCommandHandler]]

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
    build_properties: BuildCanvasFeaturePropertiesFn | None = None
    build_toolbar_bindings: BuildCanvasFeatureToolbarBindingsFn | None = None
    build_commands: BuildCanvasFeatureCommandsFn | None = None
    build_settings_event_bindings: BuildCanvasFeatureSettingsEventsFn | None = None
    build_render_scene_overrides: RenderSceneOverridesBuilder | None = None
    reducer_order: int = 100
    property_order: int = 100
