"""Project-file serialize/restore for magnifier widget state.

Lives inside the magnifier feature package so shared/tab code can call it
only through capability aliases (see ``project.serialize_magnifier`` /
``project.restore_magnifier``).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from domain.types import Color, Point
from tabs.image_compare.canvas.features.magnifier.state.feature_state import (
    MagnifierWidgetState,
    get_magnifier_widget_state,
)
from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel


def _color_to_dict(color: Color | None) -> dict[str, int] | None:
    if color is None:
        return None
    return {"r": int(color.r), "g": int(color.g), "b": int(color.b), "a": int(color.a)}


def _color_from_dict(value: Any, default: Color | None = None) -> Color | None:
    if value is None:
        return default
    if isinstance(value, Color):
        return value
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        a = int(value[3]) if len(value) > 3 else 255
        return Color(int(value[0]), int(value[1]), int(value[2]), a)
    if isinstance(value, dict):
        return Color(
            int(value.get("r", 255)),
            int(value.get("g", 255)),
            int(value.get("b", 255)),
            int(value.get("a", 255)),
        )
    return default


def _point_to_dict(point: Point | None) -> dict[str, float] | None:
    if point is None:
        return None
    return {"x": float(point.x), "y": float(point.y)}


def _point_from_dict(value: Any, default: Point | None = None) -> Point | None:
    if value is None:
        return default
    if isinstance(value, Point):
        return value
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return Point(float(value[0]), float(value[1]))
    if isinstance(value, dict):
        return Point(float(value.get("x", 0.0)), float(value.get("y", 0.0)))
    return default


def serialize_magnifier_model(model: MagnifierModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "visible": bool(model.visible),
        "position": _point_to_dict(model.position),
        "size_relative": float(model.size_relative),
        "capture_size_relative": float(model.capture_size_relative),
        "border_color": _color_to_dict(model.border_color),
        "divider_color": _color_to_dict(model.divider_color),
        "capture_color": _color_to_dict(model.capture_color),
        "guides_color": _color_to_dict(model.guides_color),
        "offset_relative": _point_to_dict(model.offset_relative),
        "spacing_relative": float(model.spacing_relative),
        "is_horizontal": bool(model.is_horizontal),
        "internal_split": float(model.internal_split),
        "divider_visible": bool(model.divider_visible),
        "divider_thickness": int(model.divider_thickness),
        "border_thickness": int(getattr(model, "border_thickness", 2)),
        "visible_left": bool(model.visible_left),
        "visible_center": bool(model.visible_center),
        "visible_right": bool(model.visible_right),
        "freeze": bool(model.freeze),
        "frozen_position": _point_to_dict(model.frozen_position),
        "show_capture_area": bool(getattr(model, "show_capture_area", True)),
        "show_laser": bool(getattr(model, "show_laser", True)),
        "interpolation_method": str(getattr(model, "interpolation_method", "BILINEAR")),
    }


def deserialize_magnifier_model(data: dict[str, Any]) -> MagnifierModel:
    return MagnifierModel(
        id=str(data.get("id") or ""),
        visible=bool(data.get("visible", True)),
        position=_point_from_dict(data.get("position"), Point(0.5, 0.5)) or Point(0.5, 0.5),
        size_relative=float(data.get("size_relative", 0.2)),
        capture_size_relative=float(data.get("capture_size_relative", 0.1)),
        border_color=_color_from_dict(
            data.get("border_color"), Color(255, 255, 255, 230)
        )
        or Color(255, 255, 255, 230),
        divider_color=_color_from_dict(
            data.get("divider_color"), Color(255, 255, 255, 230)
        )
        or Color(255, 255, 255, 230),
        capture_color=_color_from_dict(data.get("capture_color")),
        guides_color=_color_from_dict(data.get("guides_color")),
        offset_relative=_point_from_dict(data.get("offset_relative"), Point(0.0, 0.0))
        or Point(0.0, 0.0),
        spacing_relative=float(data.get("spacing_relative", 0.05)),
        is_horizontal=bool(data.get("is_horizontal", False)),
        internal_split=float(data.get("internal_split", 0.5)),
        divider_visible=bool(data.get("divider_visible", True)),
        divider_thickness=int(data.get("divider_thickness", 2)),
        border_thickness=int(data.get("border_thickness", 2)),
        visible_left=bool(data.get("visible_left", True)),
        visible_center=bool(data.get("visible_center", True)),
        visible_right=bool(data.get("visible_right", True)),
        freeze=bool(data.get("freeze", False)),
        frozen_position=_point_from_dict(data.get("frozen_position")),
        show_capture_area=bool(data.get("show_capture_area", True)),
        show_laser=bool(data.get("show_laser", True)),
        interpolation_method=str(data.get("interpolation_method", "BILINEAR")),
    )


def serialize_magnifier_for_project(view_state) -> dict[str, Any]:
    state = get_magnifier_widget_state(view_state)
    return {
        "enabled": bool(state.enabled),
        "active_id": state.active_id,
        "default_size_relative": float(state.default_size_relative),
        "default_capture_size_relative": float(state.default_capture_size_relative),
        "default_divider_visible": bool(state.default_divider_visible),
        "default_divider_thickness": int(state.default_divider_thickness),
        "default_divider_color": _color_to_dict(state.default_divider_color),
        "default_border_color": _color_to_dict(state.default_border_color),
        "intersection_highlight_enabled": bool(state.intersection_highlight_enabled),
        "auto_color_new_instances": bool(state.auto_color_new_instances),
        "models": [serialize_magnifier_model(m) for m in state.models.values()],
    }


def restore_magnifier_from_project(view_state, data: dict[str, Any] | None) -> None:
    if not data:
        return
    models: OrderedDict[str, MagnifierModel] = OrderedDict()
    for entry in data.get("models") or []:
        if not isinstance(entry, dict):
            continue
        model = deserialize_magnifier_model(entry)
        if not model.id:
            continue
        models[model.id] = model
    state = MagnifierWidgetState(
        enabled=bool(data.get("enabled", False)),
        active_id=data.get("active_id"),
        default_size_relative=float(data.get("default_size_relative", 0.2)),
        default_capture_size_relative=float(
            data.get("default_capture_size_relative", 0.1)
        ),
        default_divider_visible=bool(data.get("default_divider_visible", True)),
        default_divider_thickness=int(data.get("default_divider_thickness", 2)),
        default_divider_color=_color_from_dict(
            data.get("default_divider_color"), Color(255, 255, 255, 230)
        )
        or Color(255, 255, 255, 230),
        default_border_color=_color_from_dict(
            data.get("default_border_color"), Color(255, 255, 255, 248)
        )
        or Color(255, 255, 255, 248),
        intersection_highlight_enabled=bool(
            data.get("intersection_highlight_enabled", True)
        ),
        auto_color_new_instances=bool(data.get("auto_color_new_instances", True)),
        models=models,
    )
    if getattr(view_state, "canvas_widget_state", None) is None:
        view_state.canvas_widget_state = {}
    view_state.canvas_widget_state["magnifier"] = state
