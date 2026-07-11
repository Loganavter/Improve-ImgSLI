from __future__ import annotations

from tabs.image_compare.plugins.video_editor.services.keyframing.types import KeyframeToolAdapter
from tabs.image_compare.plugins.video_editor.services.keyframing.adapters.core_snapshot import build_core_snapshot_adapter
from tabs.image_compare.plugins.video_editor.services.keyframing.adapters.magnifier import DynamicMagnifierAdapter
from tabs.image_compare.plugins.video_editor.services.keyframing.adapters.viewport_base import build_viewport_base_adapter

def build_default_keyframe_adapters(
    extra_adapters: tuple[KeyframeToolAdapter, ...] = (),
) -> tuple[KeyframeToolAdapter, ...]:
    return (
        build_core_snapshot_adapter(),
        build_viewport_base_adapter(),
        DynamicMagnifierAdapter(),
        *tuple(extra_adapters),
    )
