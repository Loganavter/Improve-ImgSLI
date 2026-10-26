"""Image Compare instance/render-layout adapter (canvas px).

R1 lives here: instances come from the stored widget state (all of them,
hidden included) while geometry comes from the scene-graph cache; a hidden
instance gets no geometry, because the render layout does not paint it.
"""

from __future__ import annotations

from typing import Any

from .common import (
    SPACE_CANVAS_PX,
    SPACE_RELATIVE,
    SPACE_WIDGET_PX,
    _num,
    _point_or_none,
    _stored_canvas_widget_state,
)


def _ic_magnifiers(
    runtime_state: Any,
    view_state: Any,
    sources: dict[str, str],
    unavailable: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Every instance — hidden ones included (R1/R6/R7)."""
    state, materialized = _stored_canvas_widget_state(view_state, "magnifier")
    models = getattr(state, "models", None) if state is not None else None
    active_id = getattr(state, "active_id", None) if state is not None else None
    if not models:
        sources["magnifiers"] = (
            "magnifier_widget_state (no instances)"
            if materialized
            else "magnifier_state_absent (no instances)"
        )
        return []

    objects = _scene_graph_magnifier_objects(runtime_state)
    sources["magnifier_state"] = "magnifier_widget_state"
    sources["magnifier_geometry"] = (
        "scene_graph (visible instances)" if objects else "unavailable"
    )
    by_id = {str(key): value for key, value in models.items()}
    rows: list[dict[str, Any]] = []
    for magnifier_id in sorted(by_id):
        model = by_id[magnifier_id]
        visible = bool(getattr(model, "visible", False))
        scene_object = objects.get(magnifier_id)
        row: dict[str, Any] = {
            "id": magnifier_id,
            "kind": "magnifier",
            "visible": visible,
            "active": magnifier_id == str(active_id),
            "state_source": "magnifier_widget_state",
            "geometry_source": None,
            "space": None,
            "z_index": None,
            "capture": None,
            "circles": [],
            "is_combined": None,
            "model": _magnifier_model_block(model),
            "geometry_unavailable_reason": None,
        }
        if not visible:
            # R1: the render layout filters ``model.visible``, so a hidden
            # instance has no canvas geometry in the render path. The scene
            # graph may still carry last-built numbers; reporting them as
            # geometry would claim a loupe that is not on screen.
            row["geometry_unavailable_reason"] = (
                "hidden instance: not painted by the render layout, "
                "no canvas geometry in the render path"
            )
        elif scene_object is None:
            row["geometry_unavailable_reason"] = (
                "no scene-graph object for this instance (no magnifier rebuild yet)"
            )
            unavailable.append(
                {
                    "field": f"magnifiers[{magnifier_id}].geometry",
                    "reason": "the scene-graph cache holds no object for it",
                }
            )
        else:
            row["geometry_source"] = "scene_graph"
            row["space"] = SPACE_WIDGET_PX  # scene graph space, see _SCENE_SPACE_NOTE
            row["z_index"] = int(getattr(scene_object, "z_index", 0) or 0)
            row["is_combined"] = bool(getattr(scene_object, "is_combined", False))
            row["capture"] = _capture_block(scene_object)
            row["circles"] = _circle_rows(scene_object)
        rows.append(row)
    return sorted(rows, key=lambda row: row["id"])


def _scene_graph_magnifier_objects(runtime_state: Any) -> dict[str, Any]:
    """``{instance id: MagnifierSceneObject}`` from the cached scene graph."""
    graph = getattr(runtime_state, "_canvas_scene_graph", None)
    objects = getattr(graph, "objects", None) or ()
    found: dict[str, Any] = {}
    for obj in objects:
        if getattr(obj, "kind", None) != "magnifier":
            continue
        object_id = getattr(obj, "id", None)
        if object_id is None:
            continue
        found[str(object_id)] = obj
    return found


#: The scene graph authors magnifier geometry in WIDGET px (its ``pix_w/pix_h``
#: context), while ``render_layout`` is in CANVAS px. Reporting the scene values
#: as ``canvas_px`` made one quantity arrive in two scales: measured 2026-10-27,
#: the same capture ring read 24.2 (scene) vs 115 (plan) with no way for a caller
#: to know why. Every field now names its own space; the conversion is
#: ``divider by transform.projection.scale``.
_SCENE_SPACE_NOTE = (
    "scene graph space (widget px); divide by transform.projection.scale for "
    "canvas_px — render_layout.* is already canvas_px"
)


def _capture_block(scene_object: Any) -> dict[str, Any] | None:
    center = getattr(scene_object, "capture_center", None)
    if center is None:
        return None
    return {
        "center": [_num(getattr(center, "x", 0.0)), _num(getattr(center, "y", 0.0))],
        "radius": _num(getattr(scene_object, "capture_radius", 0.0)),
        "space": SPACE_WIDGET_PX,
        "space_note": _SCENE_SPACE_NOTE,
        "source": "scene_graph",
    }


def _circle_rows(scene_object: Any) -> list[dict[str, Any]]:
    """One row per drawn circle; the role belongs to the circle (R7)."""
    rows = []
    for circle in getattr(scene_object, "circles", ()) or ():
        center = getattr(circle, "center", None)
        rows.append(
            {
                "role": str(getattr(circle, "role", "")),
                "center": [
                    _num(getattr(center, "x", 0.0)),
                    _num(getattr(center, "y", 0.0)),
                ],
                "radius": _num(getattr(circle, "radius", 0.0)),
                "visible": bool(getattr(circle, "visible", True)),
                "space": SPACE_WIDGET_PX,
                "space_note": _SCENE_SPACE_NOTE,
                "source": "scene_graph",
            }
        )
    return rows


def _magnifier_model_block(model: Any) -> dict[str, Any]:
    """The instance's model fields (state, not geometry) — no invented zoom (R7)."""
    position = getattr(model, "position", None)
    offset = getattr(model, "offset_relative", None)
    return {
        "source": "magnifier_widget_state",
        "position_relative": [
            _num(getattr(position, "x", 0.0)),
            _num(getattr(position, "y", 0.0)),
        ],
        "space": SPACE_RELATIVE,
        "size_relative": _num(getattr(model, "size_relative", 0.0)),
        "capture_size_relative": _num(getattr(model, "capture_size_relative", 0.0)),
        "offset_relative": [
            _num(getattr(offset, "x", 0.0)),
            _num(getattr(offset, "y", 0.0)),
        ],
        "spacing_relative": _num(getattr(model, "spacing_relative", 0.0)),
        "internal_split": _num(getattr(model, "internal_split", 0.5), 0.5),
        "is_horizontal": bool(getattr(model, "is_horizontal", False)),
        "visible_left": bool(getattr(model, "visible_left", True)),
        "visible_center": bool(getattr(model, "visible_center", True)),
        "visible_right": bool(getattr(model, "visible_right", True)),
        "show_capture_area": bool(getattr(model, "show_capture_area", True)),
        "freeze": bool(getattr(model, "freeze", False)),
        "divider_visible": bool(getattr(model, "divider_visible", True)),
        "divider_thickness": int(getattr(model, "divider_thickness", 0) or 0),
    }


def _ic_render_layout(
    plan: Any,
    sources: dict[str, str],
    unavailable: list[dict[str, str]],
) -> dict[str, Any]:
    """The *painted* overlay summary (R1): aggregated, never re-mapped per id.

    ``OverlayLayout`` carries no instance ids, so mapping its slots back onto
    instances would be a reconstruction, not a read. It is reported as the
    aggregate it is; per-instance geometry comes from the scene graph above.
    """
    layout = getattr(plan, "overlay_layout", None) if plan is not None else None
    if layout is None:
        sources["render_layout"] = "unavailable"
        unavailable.append(
            {
                "field": "render_layout",
                "reason": "no visible magnifier overlay in the last render plan",
            }
        )
        return {"available": False, "source": "ic_overlay_layout"}
    sources["render_layout"] = "ic_overlay_layout"
    centers = [
        [_num(getattr(point, "x", 0.0)), _num(getattr(point, "y", 0.0))]
        for point in (getattr(layout, "overlay_centers", None) or ())
    ]
    return {
        "available": True,
        "source": "ic_overlay_layout",
        "space": SPACE_CANVAS_PX,
        "space_note": (
            "OverlayLayout is authored in canvas px on the live path "
            "(build_magnifier_layout runs with render_scale=1.0)"
        ),
        "slot_count": len(getattr(layout, "slots", ()) or ()),
        "slot_meaning": "one slot per drawn circle, not per instance",
        "capture_center": _point_or_none(getattr(layout, "capture_center", None)),
        "capture_radius": _num(getattr(layout, "capture_radius", 0.0)),
        "overlay_centers": centers,
        "overlay_radius": _num(getattr(layout, "overlay_radius", 0.0)),
        "per_instance_mapping": "unavailable",
    }


def _ic_transform(
    runtime_state: Any,
    canvas: Any,
    sources: dict[str, str],
    unavailable: list[dict[str, str]],
) -> dict[str, Any]:
    """Camera + canvas→widget projection, read without materializing state (R2)."""
    zoom_state = getattr(runtime_state, "_zoom_viewport_state", None)
    if zoom_state is not None:
        zoom = _num(getattr(zoom_state, "zoom_level", 1.0), 1.0)
        pan = [
            _num(getattr(zoom_state, "pan_offset_x", 0.0)),
            _num(getattr(zoom_state, "pan_offset_y", 0.0)),
        ]
        materialized = True
        sources["transform"] = "runtime_state._zoom_viewport_state"
    else:
        # ``ensure_zoom_viewport_state`` would create and copy the state into
        # the widget; a read only reads what is already there.
        zoom = _num(getattr(canvas, "zoom_level", 1.0), 1.0)
        pan = [
            _num(getattr(canvas, "pan_offset_x", 0.0)),
            _num(getattr(canvas, "pan_offset_y", 0.0)),
        ]
        materialized = False
        sources["transform"] = "widget_zoom_attributes_or_defaults"

    projection = None
    content_rect = getattr(runtime_state, "_content_rect_px", None)
    scale = getattr(runtime_state, "_content_sr", None)
    if content_rect and scale is not None:
        projection = {
            "scale": _num(scale, 1.0),
            "offset": [_num(content_rect[0]), _num(content_rect[1])],
            "from_space": SPACE_CANVAS_PX,
            "space": SPACE_WIDGET_PX,
            "source": "ic_runtime_content_geometry",
        }
        sources["projection"] = "ic_runtime_content_geometry"
    else:
        sources["projection"] = "unavailable"
        unavailable.append(
            {
                "field": "transform.projection",
                "reason": "the canvas has not placed content yet (no content rect/scale)",
            }
        )
    return {
        "source": sources["transform"],
        "input_space": SPACE_CANVAS_PX,
        "output_space": SPACE_CANVAS_PX,
        "camera": {
            "zoom": zoom,
            "pan": pan,
            "space": SPACE_RELATIVE,
            "state_materialized": materialized,
        },
        "projection": projection,
    }


# ---------------------------------------------------------------------------
