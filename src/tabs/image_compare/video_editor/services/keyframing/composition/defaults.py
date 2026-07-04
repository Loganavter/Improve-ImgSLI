from __future__ import annotations

from tabs.image_compare.video_editor.services.keyframing.adapters.base import KeyframeToolAdapter
from tabs.image_compare.video_editor.services.keyframing.adapters.core_snapshot import build_core_snapshot_adapter


def build_default_keyframe_adapters(
    extra_adapters: tuple[KeyframeToolAdapter, ...] = (),
) -> tuple[KeyframeToolAdapter, ...]:
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()

    tab_adapters: tuple[KeyframeToolAdapter, ...] = ()
    for tab in registry.list_tabs():
        contributed = tab.create_service("keyframe_adapters")
        if contributed:
            tab_adapters = (*tab_adapters, *tuple(contributed))

    return (
        build_core_snapshot_adapter(),
        *tab_adapters,
        *tuple(extra_adapters),
    )
