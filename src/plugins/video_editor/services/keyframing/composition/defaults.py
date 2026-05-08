from __future__ import annotations

from plugins.video_editor.services.keyframing.adapters.base import KeyframeToolAdapter
from plugins.video_editor.services.keyframing.adapters.core_snapshot import build_core_snapshot_adapter
from plugins.video_editor.services.keyframing.adapters.viewport_base import build_viewport_base_adapter

def build_default_keyframe_adapters(
    extra_adapters: tuple[KeyframeToolAdapter, ...] = (),
) -> tuple[KeyframeToolAdapter, ...]:
    return (
        build_core_snapshot_adapter(),
        build_viewport_base_adapter(),
        *tuple(extra_adapters),
    )
