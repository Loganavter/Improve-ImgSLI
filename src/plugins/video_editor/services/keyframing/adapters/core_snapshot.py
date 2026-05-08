from __future__ import annotations

from plugins.video_editor.services.keyframing.adapters.base import (
    ChannelDescriptor,
    ToolDescriptor,
    TrackDescriptor,
)
from plugins.video_editor.services.keyframing.adapters.static import (
    StaticToolAdapter,
    StaticToolBinding,
    StaticTrackBinding,
)

def build_core_snapshot_adapter() -> StaticToolAdapter:
    tool = ToolDescriptor(
        id="core.snapshot",
        tool_type="core_snapshot",
        label="Core Snapshot",
        group_id="core",
        group_label="Core",
        subclass_id="snapshot",
        subclass_label="Snapshot",
        tracks=(
            TrackDescriptor(
                id="__snapshot.viewport_state",
                label="Viewport Base",
                kind="state",
                channels=(ChannelDescriptor("value", "Value", "state", interpolate_values=False),),
                metadata={"internal": True},
            ),
            TrackDescriptor(
                id="__snapshot.settings_state",
                label="Settings State",
                kind="state",
                channels=(ChannelDescriptor("value", "Value", "state", interpolate_values=False),),
                metadata={"internal": True},
            ),
            TrackDescriptor(
                id="__snapshot.image1_path",
                label="Image 1",
                kind="source",
                channels=(ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
            ),
            TrackDescriptor(
                id="__snapshot.image2_path",
                label="Image 2",
                kind="source",
                channels=(ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
            ),
            TrackDescriptor(
                id="__snapshot.name1",
                label="Name 1",
                kind="label",
                channels=(ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
            ),
            TrackDescriptor(
                id="__snapshot.name2",
                label="Name 2",
                kind="label",
                channels=(ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
            ),
        ),
    )
    return StaticToolAdapter(
        adapter_id="core.snapshot",
        tools=(
            StaticToolBinding(
                descriptor=tool,
                tracks=(
                    StaticTrackBinding(tool.tracks[0], lambda snap: {"value": snap.viewport_state}, lambda snap, values: setattr(snap, "viewport_state", values["value"])),
                    StaticTrackBinding(tool.tracks[1], lambda snap: {"value": snap.settings_state}, lambda snap, values: setattr(snap, "settings_state", values["value"])),
                    StaticTrackBinding(tool.tracks[2], lambda snap: {"value": snap.image1_path}, lambda snap, values: setattr(snap, "image1_path", values["value"])),
                    StaticTrackBinding(tool.tracks[3], lambda snap: {"value": snap.image2_path}, lambda snap, values: setattr(snap, "image2_path", values["value"])),
                    StaticTrackBinding(tool.tracks[4], lambda snap: {"value": snap.name1}, lambda snap, values: setattr(snap, "name1", values["value"])),
                    StaticTrackBinding(tool.tracks[5], lambda snap: {"value": snap.name2}, lambda snap, values: setattr(snap, "name2", values["value"])),
                ),
            ),
        ),
    )
