from __future__ import annotations

from tabs.image_compare.video_editor.services.keyframing.adapters.base import (
    ChannelDescriptor,
    ToolDescriptor,
    TrackDescriptor,
)
from tabs.image_compare.video_editor.services.keyframing.adapters.static import (
    StaticToolAdapter,
    StaticToolBinding,
    StaticTrackBinding,
)


def _source_track(index: int) -> TrackDescriptor:
    return TrackDescriptor(
        id=f"__snapshot.source[{index}]",
        label=f"Source {index + 1}",
        kind="source",
        channels=(ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
    )


def _name_track(index: int) -> TrackDescriptor:
    return TrackDescriptor(
        id=f"__snapshot.name[{index}]",
        label=f"Name {index + 1}",
        kind="label",
        channels=(ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
    )


def _make_source_binding(track: TrackDescriptor, index: int) -> StaticTrackBinding:
    def read(snap):
        sources = snap.sources
        return {"value": sources[index] if index < len(sources) else None}

    def write(snap, values):
        current = list(snap.sources)
        while len(current) <= index:
            current.append(None)
        current[index] = values["value"]
        object.__setattr__(snap, "sources", tuple(current))

    return StaticTrackBinding(track, read, write)


def _make_name_binding(track: TrackDescriptor, index: int) -> StaticTrackBinding:
    def read(snap):
        names = snap.names
        return {"value": names[index] if index < len(names) else None}

    def write(snap, values):
        current = list(snap.names)
        while len(current) <= index:
            current.append(None)
        current[index] = values["value"]
        object.__setattr__(snap, "names", tuple(current))

    return StaticTrackBinding(track, read, write)


def build_core_snapshot_adapter(n_sources: int = 2) -> StaticToolAdapter:
    viewport_track = TrackDescriptor(
        id="__snapshot.viewport_state",
        label="Viewport Base",
        kind="state",
        channels=(ChannelDescriptor("value", "Value", "state", interpolate_values=False),),
        metadata={"internal": True},
    )
    settings_track = TrackDescriptor(
        id="__snapshot.settings_state",
        label="Settings State",
        kind="state",
        channels=(ChannelDescriptor("value", "Value", "state", interpolate_values=False),),
        metadata={"internal": True},
    )
    source_tracks = tuple(_source_track(i) for i in range(n_sources))
    name_tracks = tuple(_name_track(i) for i in range(n_sources))

    tool = ToolDescriptor(
        id="core.snapshot",
        tool_type="core_snapshot",
        label="Core Snapshot",
        group_id="core",
        group_label="Core",
        subclass_id="snapshot",
        subclass_label="Snapshot",
        tracks=(viewport_track, settings_track, *source_tracks, *name_tracks),
    )

    bindings = [
        StaticTrackBinding(
            viewport_track,
            lambda snap: {"value": snap.viewport_state},
            lambda snap, values: object.__setattr__(snap, "viewport_state", values["value"]),
        ),
        StaticTrackBinding(
            settings_track,
            lambda snap: {"value": snap.settings_state},
            lambda snap, values: object.__setattr__(snap, "settings_state", values["value"]),
        ),
    ]
    for i, track in enumerate(source_tracks):
        bindings.append(_make_source_binding(track, i))
    for i, track in enumerate(name_tracks):
        bindings.append(_make_name_binding(track, i))

    return StaticToolAdapter(
        adapter_id="core.snapshot",
        tools=(
            StaticToolBinding(
                descriptor=tool,
                tracks=tuple(bindings),
            ),
        ),
    )
