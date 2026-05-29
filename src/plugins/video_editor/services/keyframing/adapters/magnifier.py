from __future__ import annotations

from typing import Any, Mapping

from plugins.video_editor.services.keyframing.adapters.base import (
    ChannelDescriptor,
    ToolDescriptor,
    TrackDescriptor,
)
from plugins.video_editor.services.keyframing.types import FrameSnapshot
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

def _store_proxy(viewport):
    return type("StoreProxy", (), {"viewport": viewport})()

def _execute_magnifier_command(store, command_id: str, *args, **kwargs):
    command = get_canvas_feature_command_by_alias(command_id)
    if command is None:
        return None
    return command(store, *args, **kwargs)

def _query_magnifier(store, query_id: str, default=None, *args, **kwargs):
    command = get_canvas_feature_command_by_alias(query_id)
    if command is None:
        return default
    result = command(store, *args, **kwargs)
    return default if result is None else result

def _iter_models(snapshot: FrameSnapshot) -> tuple[dict[str, Any], ...]:
    return tuple(
        _query_magnifier(_store_proxy(snapshot.viewport_state), "overlay.all_states", ()) or ()
    )

def _get_model(snapshot: FrameSnapshot, mag_id: str):
    for model in _iter_models(snapshot):
        if model.get("id") == mag_id:
            return model
    return None

def _magnifier_globally_enabled(snapshot: FrameSnapshot) -> bool:
    try:
        command = get_canvas_feature_command_by_alias("overlay.enabled")
        if command is None:
            return True
        return bool(command(_store_proxy(snapshot.viewport_state)))
    except Exception:
        return True

def _bool_ch(channel_id: str, label: str) -> ChannelDescriptor:
    return ChannelDescriptor(channel_id, label, "bool", interpolate_values=False)

def _scalar_ch(channel_id: str, label: str) -> ChannelDescriptor:
    return ChannelDescriptor(channel_id, label, "scalar")

def _color_ch(channel_id: str, label: str) -> ChannelDescriptor:
    return ChannelDescriptor(channel_id, label, "color", interpolate_values=False)

def _build_tool_descriptor(mag_id: str) -> ToolDescriptor:
    p = f"magnifier.{mag_id}"
    return ToolDescriptor(
        id=f"magnifier.instance.{mag_id}",
        tool_type="magnifier_instance",
        label=f"Magnifier ({mag_id})",
        group_id="magnifier",
        group_label="Magnifier",
        subclass_id=mag_id,
        subclass_label=mag_id,
        metadata={"magnifier_id": mag_id},
        tracks=(
            TrackDescriptor(
                id=f"{p}.position", label="Position", kind="vec2",
                channels=(
                    ChannelDescriptor("x", "X", "scalar"),
                    ChannelDescriptor("y", "Y", "scalar"),
                ),
            ),
            TrackDescriptor(
                id=f"{p}.size", label="Size", kind="scalar",
                channels=(_scalar_ch("value", "Value"),),
            ),
            TrackDescriptor(
                id=f"{p}.capture_size", label="Capture Size", kind="scalar",
                channels=(_scalar_ch("value", "Value"),),
            ),
            TrackDescriptor(
                id=f"{p}.internal_split", label="Internal Split", kind="scalar",
                channels=(_scalar_ch("value", "Value"),),
            ),
            TrackDescriptor(
                id=f"{p}.orientation", label="Orientation", kind="bool",
                channels=(_bool_ch("value", "Value"),),
            ),
            TrackDescriptor(
                id=f"{p}.visibility", label="Visibility", kind="mask3",
                channels=(
                    _bool_ch("left", "Left"),
                    _bool_ch("center", "Center"),
                    _bool_ch("right", "Right"),
                ),
            ),
            TrackDescriptor(
                id=f"{p}.border_color", label="Border Color", kind="color",
                channels=(
                    _color_ch("r", "R"), _color_ch("g", "G"),
                    _color_ch("b", "B"), _color_ch("a", "A"),
                ),
            ),
            TrackDescriptor(
                id=f"{p}.divider_color", label="Divider Color", kind="color",
                channels=(
                    _color_ch("r", "R"), _color_ch("g", "G"),
                    _color_ch("b", "B"), _color_ch("a", "A"),
                ),
            ),
            TrackDescriptor(
                id=f"{p}.laser_enabled", label="Laser Enabled", kind="bool",
                channels=(_bool_ch("value", "Value"),),
            ),
        ),
    )

class DynamicMagnifierAdapter:
    adapter_id = "magnifier.per_instance"

    def describe_tools(self, snapshot: FrameSnapshot | None = None) -> tuple[ToolDescriptor, ...]:
        if snapshot is None:
            return ()
        try:
            return tuple(_build_tool_descriptor(model["id"]) for model in _iter_models(snapshot))
        except Exception:
            return ()

    def read_tool_values(
        self,
        snapshot: FrameSnapshot,
        tool: ToolDescriptor,
    ) -> Mapping[str, Mapping[str, Any]]:
        mag_id = tool.metadata.get("magnifier_id", "default")
        model = _get_model(snapshot, mag_id)
        if model is None:
            return {}
        p = f"magnifier.{mag_id}"
        border = model["border_color"]
        divider = model["divider_color"]
        return {
            f"{p}.position": {"x": float(model["position"].x), "y": float(model["position"].y)},
            f"{p}.size": {"value": float(model["size_relative"])},
            f"{p}.capture_size": {"value": float(model["capture_size_relative"])},
            f"{p}.internal_split": {"value": float(model["internal_split"])},
            f"{p}.orientation": {"value": bool(model["is_horizontal"])},
            f"{p}.visibility": {
                "left": bool(model["visible_left"]),
                "center": bool(model["visible_center"]),
                "right": bool(model["visible_right"]),
            },
            f"{p}.border_color": {
                "r": int(border.r), "g": int(border.g), "b": int(border.b), "a": int(border.a),
            },
            f"{p}.divider_color": {
                "r": int(divider.r), "g": int(divider.g), "b": int(divider.b), "a": int(divider.a),
            },
            f"{p}.laser_enabled": {"value": bool(model.get("show_laser", True))},
        }

    def apply_tool_values(
        self,
        snapshot: FrameSnapshot,
        tool: ToolDescriptor,
        values_by_track_id: Mapping[str, Mapping[str, Any]],
    ) -> None:

        if not _magnifier_globally_enabled(snapshot):
            return
        mag_id = tool.metadata.get("magnifier_id", "default")
        model = _get_model(snapshot, mag_id)
        if model is None:
            return
        p = f"magnifier.{mag_id}"
        from domain.types import Color, Point

        proxy = _store_proxy(snapshot.viewport_state)
        # The per-instance "active_*" commands below operate on whatever magnifier
        # is currently active, so we temporarily switch the active instance to
        # mag_id. The active id also drives magnifier z-order (the active one
        # renders on top — see build_magnifier_layout), and apply_tool_values runs
        # once per magnifier; without restoring, the last-applied instance would
        # win and the export would layer magnifiers differently than the
        # interactive scene the user authored.
        _active_state = _query_magnifier(proxy, "overlay.active_state", None)
        saved_active_id = (
            _active_state.get("id") if isinstance(_active_state, dict) else None
        )
        _execute_magnifier_command(proxy, "overlay.set_active_instance", mag_id)
        if f"{p}.position" in values_by_track_id:
            ch = values_by_track_id[f"{p}.position"]
            _execute_magnifier_command(
                proxy,
                "overlay.move_active_position",
                Point(float(ch["x"]), float(ch["y"])),
            )
        if f"{p}.size" in values_by_track_id:
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_size",
                float(values_by_track_id[f"{p}.size"]["value"]),
            )
        if f"{p}.capture_size" in values_by_track_id:
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_capture_size",
                float(values_by_track_id[f"{p}.capture_size"]["value"]),
            )
        if f"{p}.internal_split" in values_by_track_id:
            _execute_magnifier_command(
                proxy,
                "overlay.set_internal_split",
                float(values_by_track_id[f"{p}.internal_split"]["value"]),
            )
        if f"{p}.orientation" in values_by_track_id:
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_orientation",
                bool(values_by_track_id[f"{p}.orientation"]["value"]),
            )
        if f"{p}.visibility" in values_by_track_id:
            ch = values_by_track_id[f"{p}.visibility"]
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_visibility_parts",
                left=bool(ch["left"]) if "left" in ch else None,
                center=bool(ch["center"]) if "center" in ch else None,
                right=bool(ch["right"]) if "right" in ch else None,
            )
        if f"{p}.border_color" in values_by_track_id:
            ch = values_by_track_id[f"{p}.border_color"]
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_border_color",
                Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
            )
        if f"{p}.divider_color" in values_by_track_id:
            ch = values_by_track_id[f"{p}.divider_color"]
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_divider_color",
                Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
            )
        if f"{p}.laser_enabled" in values_by_track_id:
            _execute_magnifier_command(
                proxy,
                "overlay.set_active_laser_enabled",
                bool(values_by_track_id[f"{p}.laser_enabled"]["value"]),
            )
        if saved_active_id != mag_id:
            _execute_magnifier_command(
                proxy, "overlay.set_active_instance", saved_active_id
            )
