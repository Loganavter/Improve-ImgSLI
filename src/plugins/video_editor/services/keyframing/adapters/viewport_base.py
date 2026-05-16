from __future__ import annotations

from typing import Any, Callable

from core.store_viewport import ViewportState
from domain.types import Color, Point
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
from plugins.video_editor.services.keyframing.types import FrameSnapshot
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_properties

class _ViewportProxy:
    def __init__(self, viewport: ViewportState):
        self.viewport = viewport

def _resolve_read(viewport: ViewportState, parts: list[str]) -> Any:
    obj = viewport
    for part in parts:
        obj = getattr(obj, part)
    return obj

def _resolve_write(viewport: ViewportState, attr_path: str, value: Any) -> None:
    parts = attr_path.split(".")
    obj = viewport
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)

def _make_snapshot_accessor(
    attr: str,
    kind: str,
    write_attrs: list[str] | None,
) -> tuple[
    Callable[[FrameSnapshot], dict[str, Any]],
    Callable[[FrameSnapshot, dict[str, Any]], None],
]:
    read_parts = attr.split(".")
    all_write = write_attrs or [attr]

    if kind == "scalar":
        def reader(snap: FrameSnapshot) -> dict[str, Any]:
            return {"value": float(_resolve_read(snap.viewport_state, read_parts))}

        def writer(snap: FrameSnapshot, ch: dict[str, Any]) -> None:
            value = float(ch["value"])
            for attr_name in all_write:
                _resolve_write(snap.viewport_state, attr_name, value)
    elif kind == "bool":
        def reader(snap: FrameSnapshot) -> dict[str, Any]:
            return {"value": bool(_resolve_read(snap.viewport_state, read_parts))}

        def writer(snap: FrameSnapshot, ch: dict[str, Any]) -> None:
            value = bool(ch["value"])
            for attr_name in all_write:
                _resolve_write(snap.viewport_state, attr_name, value)
    elif kind == "enum":
        def reader(snap: FrameSnapshot) -> dict[str, Any]:
            return {"value": _resolve_read(snap.viewport_state, read_parts)}

        def writer(snap: FrameSnapshot, ch: dict[str, Any]) -> None:
            value = ch["value"]
            for attr_name in all_write:
                _resolve_write(snap.viewport_state, attr_name, value)
    elif kind == "color":
        def reader(snap: FrameSnapshot) -> dict[str, Any]:
            color = _resolve_read(snap.viewport_state, read_parts)
            return {"r": int(color.r), "g": int(color.g), "b": int(color.b), "a": int(color.a)}

        def writer(snap: FrameSnapshot, ch: dict[str, Any]) -> None:
            value = Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"]))
            for attr_name in all_write:
                _resolve_write(snap.viewport_state, attr_name, value)
    elif kind == "vec2":
        def reader(snap: FrameSnapshot) -> dict[str, Any]:
            point = _resolve_read(snap.viewport_state, read_parts)
            return {"x": float(point.x), "y": float(point.y)}

        def writer(snap: FrameSnapshot, ch: dict[str, Any]) -> None:
            value = Point(float(ch["x"]), float(ch["y"]))
            for attr_name in all_write:
                _resolve_write(snap.viewport_state, attr_name, value)
    else:
        raise ValueError(f"Unsupported viewport track kind '{kind}' for attr '{attr}'")

    return reader, writer

def _read_interaction_session(snapshot: FrameSnapshot) -> dict[str, Any]:
    viewport = snapshot.viewport_state
    return {"value": str(int(getattr(viewport.interaction_state, "interaction_session_id", 0)))}

def _write_interaction_session(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    viewport = snapshot.viewport_state
    try:
        viewport.interaction_state.interaction_session_id = int(channels["value"])
    except (TypeError, ValueError):
        viewport.interaction_state.interaction_session_id = 0

def _track_descriptor(
    track_id: str,
    label: str,
    kind: str,
    *,
    channels: tuple[ChannelDescriptor, ...] | None = None,
) -> TrackDescriptor:
    defaults = {
        "scalar": (ChannelDescriptor("value", "Value", "scalar"),),
        "bool": (ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
        "enum": (ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
        "vec2": (
            ChannelDescriptor("x", "X", "scalar"),
            ChannelDescriptor("y", "Y", "scalar"),
        ),
        "color": (
            ChannelDescriptor("r", "R", "color", interpolate_values=False),
            ChannelDescriptor("g", "G", "color", interpolate_values=False),
            ChannelDescriptor("b", "B", "color", interpolate_values=False),
            ChannelDescriptor("a", "A", "color", interpolate_values=False),
        ),
        "mask3": (
            ChannelDescriptor("left", "Left", "bool", interpolate_values=False),
            ChannelDescriptor("center", "Center", "bool", interpolate_values=False),
            ChannelDescriptor("right", "Right", "bool", interpolate_values=False),
        ),
    }
    return TrackDescriptor(id=track_id, label=label, kind=kind, channels=channels or defaults[kind])

def _binding(
    descriptor: TrackDescriptor,
    *,
    attr: str | None = None,
    write_attrs: list[str] | None = None,
    reader: Callable[[FrameSnapshot], dict[str, Any]] | None = None,
    writer: Callable[[FrameSnapshot, dict[str, Any]], None] | None = None,
) -> StaticTrackBinding:
    if reader is None or writer is None:
        if attr is None:
            raise ValueError(f"Track '{descriptor.id}' requires attr or explicit reader/writer")
        reader, writer = _make_snapshot_accessor(attr, descriptor.kind, write_attrs)
    return StaticTrackBinding(descriptor=descriptor, reader=reader, writer=writer)

def build_viewport_base_adapter() -> StaticToolAdapter:
    feature_properties = tuple(get_canvas_feature_properties())
    property_descriptors = tuple(
        _track_descriptor(
            item.id,
            item.label,
            item.kind,
            channels=item.channels,
        )
        for item in feature_properties
    )
    property_bindings = tuple(
        StaticTrackBinding(
            descriptor=descriptor,
            reader=item.read_snapshot,
            writer=item.write_snapshot,
        )
        for item, descriptor in zip(feature_properties, property_descriptors)
    )

    descriptor = ToolDescriptor(
        id="viewport.base",
        tool_type="viewport",
        label="Viewport",
        group_id="viewport",
        group_label="Viewport",
        subclass_id="base",
        subclass_label="Base",
        tracks=(
            _track_descriptor("comparison.diff_mode", "Diff Mode", "enum"),
            _track_descriptor("comparison.channel_view_mode", "Channel View", "enum"),
            _track_descriptor("view.interpolation_method", "Interpolation", "enum"),
            *property_descriptors,
            _track_descriptor("text.visible", "Visible", "bool"),
            _track_descriptor("text.font_size", "Font Size %", "scalar"),
            _track_descriptor("text.font_weight", "Font Weight", "scalar"),
            _track_descriptor("text.alpha", "Alpha %", "scalar"),
            _track_descriptor("text.color", "Color", "color"),
            _track_descriptor("text.bg_color", "Background Color", "color"),
            _track_descriptor("text.bg_visible", "Background", "bool"),
            _track_descriptor("text.placement", "Placement", "enum"),
            _track_descriptor("__input.interaction_session", "Interaction Session", "enum"),
        ),
    )

    tracks = descriptor.tracks
    comparison_diff_mode = tracks[0]
    comparison_channel_mode = tracks[1]
    view_interpolation = tracks[2]
    post_property_offset = 3 + len(property_descriptors)
    text_visible = tracks[post_property_offset + 0]
    text_font_size = tracks[post_property_offset + 1]
    text_font_weight = tracks[post_property_offset + 2]
    text_alpha = tracks[post_property_offset + 3]
    text_color = tracks[post_property_offset + 4]
    text_bg_color = tracks[post_property_offset + 5]
    text_bg_visible = tracks[post_property_offset + 6]
    text_placement = tracks[post_property_offset + 7]
    interaction_session = tracks[post_property_offset + 8]
    return StaticToolAdapter(
        adapter_id="viewport.base",
        tools=(
            StaticToolBinding(
                descriptor=descriptor,
                tracks=(
                    _binding(comparison_diff_mode, attr="view_state.diff_mode"),
                    _binding(comparison_channel_mode, attr="view_state.channel_view_mode"),
                    _binding(view_interpolation, attr="render_config.interpolation_method", write_attrs=["render_config.interpolation_method"]),
                    *property_bindings,
                    _binding(text_visible, attr="render_config.include_file_names_in_saved"),
                    _binding(text_font_size, attr="render_config.font_size_percent"),
                    _binding(text_font_weight, attr="render_config.font_weight"),
                    _binding(text_alpha, attr="render_config.text_alpha_percent"),
                    _binding(text_color, attr="render_config.file_name_color"),
                    _binding(text_bg_color, attr="render_config.file_name_bg_color"),
                    _binding(text_bg_visible, attr="render_config.draw_text_background"),
                    _binding(text_placement, attr="render_config.text_placement_mode"),
                    _binding(interaction_session, reader=_read_interaction_session, writer=_write_interaction_session),
                ),
            ),
        ),
    )
