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
    "FrameSnapshot": ("tabs.image_compare.plugins.video_editor.services.keyframing.types", "FrameSnapshot"),
    "KeyframedRecording": ("tabs.image_compare.plugins.video_editor.services.keyframing.recording", "KeyframedRecording"),
    "KeyframeTrack": ("tabs.image_compare.plugins.video_editor.services.keyframing.recording", "KeyframeTrack"),
    "KeyframingValidationError": ("tabs.image_compare.plugins.video_editor.services.keyframing.engine.errors", "KeyframingValidationError"),
    "ChannelDescriptor": ("shared.keyframing.adapters_base", "ChannelDescriptor"),
    "KeyframeToolAdapter": ("tabs.image_compare.plugins.video_editor.services.keyframing.types", "KeyframeToolAdapter"),
    "ToolDescriptor": ("shared.keyframing.adapters_base", "ToolDescriptor"),
    "TrackDescriptor": ("shared.keyframing.adapters_base", "TrackDescriptor"),
    "StaticToolAdapter": ("tabs.image_compare.plugins.video_editor.services.keyframing.adapters.static", "StaticToolAdapter"),
    "StaticToolBinding": ("tabs.image_compare.plugins.video_editor.services.keyframing.adapters.static", "StaticToolBinding"),
    "StaticTrackBinding": ("tabs.image_compare.plugins.video_editor.services.keyframing.adapters.static", "StaticTrackBinding"),
    "KeyframeAdapterRegistry": ("tabs.image_compare.plugins.video_editor.services.keyframing.composition.registry", "KeyframeAdapterRegistry"),
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
