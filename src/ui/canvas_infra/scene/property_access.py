from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.store_viewport import ViewportState
from domain.qt_adapters import color_to_hex, hex_to_color

from .widget_contract import CanvasFeatureProperty
from .widget_registry import get_canvas_feature_properties

if TYPE_CHECKING:
    from plugins.video_editor.services.keyframing.types import FrameSnapshot

_log = logging.getLogger("ImproveImgSLI.canvas.properties")

def get_canvas_feature_property_by_id(property_id: str) -> CanvasFeatureProperty | None:
    for item in get_canvas_feature_properties():
        if item.id == property_id:
            return item
    return None

def get_canvas_feature_property_by_setting_key(setting_key: str) -> CanvasFeatureProperty | None:
    for item in get_canvas_feature_properties():
        if item.setting_key == setting_key:
            return item
    return None

def _snapshot(viewport_state: ViewportState) -> FrameSnapshot:
    from plugins.video_editor.services.keyframing.types import FrameSnapshot

    return FrameSnapshot(
        timestamp=0.0,
        viewport_state=viewport_state,
        settings_state=None,
        image1_path=None,
        image2_path=None,
        name1=None,
        name2=None,
    )

def read_canvas_feature_property(
    viewport_state: ViewportState,
    prop: CanvasFeatureProperty,
) -> dict[str, Any]:
    return dict(prop.read_snapshot(_snapshot(viewport_state)))

def write_canvas_feature_property(
    viewport_state: ViewportState,
    prop: CanvasFeatureProperty,
    channels: dict[str, Any],
) -> None:
    prop.write_snapshot(_snapshot(viewport_state), dict(channels))

def serialize_canvas_feature_setting(
    prop: CanvasFeatureProperty,
    channels: dict[str, Any],
) -> Any:
    if prop.serialize_setting is not None:
        return prop.serialize_setting(dict(channels))
    if prop.kind == "color":
        return color_to_hex(channels_to_color(channels))
    if prop.kind in {"bool", "scalar", "enum"}:
        return channels["value"]
    if prop.kind == "vec2":
        return {"x": channels["x"], "y": channels["y"]}
    if prop.kind == "mask3":
        return {
            "left": bool(channels["left"]),
            "center": bool(channels["center"]),
            "right": bool(channels["right"]),
        }
    raise ValueError(f"Unsupported property kind for persistence: {prop.kind}")

def deserialize_canvas_feature_setting(
    prop: CanvasFeatureProperty,
    raw_value: Any,
) -> dict[str, Any]:
    if prop.deserialize_setting is not None:
        return prop.deserialize_setting(raw_value)
    if prop.kind == "color":
        if hasattr(raw_value, "r") and hasattr(raw_value, "g") and hasattr(raw_value, "b") and hasattr(raw_value, "a"):
            return {
                "r": int(raw_value.r),
                "g": int(raw_value.g),
                "b": int(raw_value.b),
                "a": int(raw_value.a),
            }
        color = hex_to_color(str(raw_value))
        return {"r": color.r, "g": color.g, "b": color.b, "a": color.a}
    if prop.kind == "bool":
        if isinstance(raw_value, str):
            return {"value": raw_value.lower() in ("true", "1", "yes")}
        return {"value": bool(raw_value)}
    if prop.kind == "scalar":
        return {"value": float(raw_value)}
    if prop.kind == "enum":
        return {"value": raw_value}
    if prop.kind == "vec2":
        return {"x": float(raw_value["x"]), "y": float(raw_value["y"])}
    if prop.kind == "mask3":
        return {
            "left": bool(raw_value["left"]),
            "center": bool(raw_value["center"]),
            "right": bool(raw_value["right"]),
        }
    raise ValueError(f"Unsupported property kind for persistence: {prop.kind}")

def channels_to_color(channels: dict[str, Any]):
    from domain.types import Color

    return Color(
        int(channels["r"]),
        int(channels["g"]),
        int(channels["b"]),
        int(channels["a"]),
    )

def read_canvas_feature_color_by_setting_key(
    viewport_state: ViewportState,
    setting_key: str,
):
    prop = get_canvas_feature_property_by_setting_key(setting_key)
    if prop is None:
        available_keys = tuple(
            item.setting_key
            for item in get_canvas_feature_properties()
            if item.setting_key is not None
        )
        _log.error(
            "Unknown canvas feature color setting key '%s'. Available keys: %s",
            setting_key,
            available_keys,
        )
        raise KeyError(f"Unknown canvas feature setting key: {setting_key}")
    return channels_to_color(read_canvas_feature_property(viewport_state, prop))

def read_canvas_feature_setting_by_key(
    viewport_state: ViewportState,
    setting_key: str,
):
    prop = get_canvas_feature_property_by_setting_key(setting_key)
    if prop is None:
        available_keys = tuple(
            item.setting_key
            for item in get_canvas_feature_properties()
            if item.setting_key is not None
        )
        _log.error(
            "Unknown canvas feature setting key '%s'. Available keys: %s",
            setting_key,
            available_keys,
        )
        raise KeyError(f"Unknown canvas feature setting key: {setting_key}")
    channels = read_canvas_feature_property(viewport_state, prop)
    if prop.kind == "color":
        return channels_to_color(channels)
    if prop.kind in {"bool", "scalar", "enum"}:
        return channels["value"]
    if prop.kind == "vec2":
        return {"x": float(channels["x"]), "y": float(channels["y"])}
    if prop.kind == "mask3":
        return {
            "left": bool(channels["left"]),
            "center": bool(channels["center"]),
            "right": bool(channels["right"]),
        }
    raise ValueError(f"Unsupported property kind for readback: {prop.kind}")
