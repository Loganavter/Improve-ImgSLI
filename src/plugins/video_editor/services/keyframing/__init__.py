from __future__ import annotations

from importlib import import_module

__all__ = [
    "ChannelDescriptor",
    "FrameSnapshot",
    "KeyframeAdapterRegistry",
    "KeyframeToolAdapter",
    "KeyframedRecording",
    "KeyframeTrack",
    "KeyframingValidationError",
    "StaticToolAdapter",
    "StaticToolBinding",
    "StaticTrackBinding",
    "ToolDescriptor",
    "TrackDescriptor",
]

_EXPORTS = {
    "FrameSnapshot": ("plugins.video_editor.services.keyframing.types", "FrameSnapshot"),
    "KeyframedRecording": ("plugins.video_editor.services.keyframing.recording", "KeyframedRecording"),
    "KeyframeTrack": ("plugins.video_editor.services.keyframing.recording", "KeyframeTrack"),
    "KeyframingValidationError": ("plugins.video_editor.services.keyframing.engine.errors", "KeyframingValidationError"),
    "ChannelDescriptor": ("plugins.video_editor.services.keyframing.adapters.base", "ChannelDescriptor"),
    "KeyframeToolAdapter": ("plugins.video_editor.services.keyframing.adapters.base", "KeyframeToolAdapter"),
    "ToolDescriptor": ("plugins.video_editor.services.keyframing.adapters.base", "ToolDescriptor"),
    "TrackDescriptor": ("plugins.video_editor.services.keyframing.adapters.base", "TrackDescriptor"),
    "StaticToolAdapter": ("plugins.video_editor.services.keyframing.adapters.static", "StaticToolAdapter"),
    "StaticToolBinding": ("plugins.video_editor.services.keyframing.adapters.static", "StaticToolBinding"),
    "StaticTrackBinding": ("plugins.video_editor.services.keyframing.adapters.static", "StaticTrackBinding"),
    "KeyframeAdapterRegistry": ("plugins.video_editor.services.keyframing.composition.registry", "KeyframeAdapterRegistry"),
}

def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
