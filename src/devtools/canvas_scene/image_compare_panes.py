"""Image Compare panes/divider adapter (canvas px).

Pane rects come from the render plan's content rect and the stored split
fraction (``resolve_axis_position`` is the shared primitive); the painted
divider mirrors ``divider/runtime_hooks``' suppression rules.
"""

from __future__ import annotations

from typing import Any

from .common import (
    SPACE_CANVAS_PX,
    SPACE_WIDGET_PX,
    _IC_DEFAULT_DIVIDER_THICKNESS,
    _IC_DEFAULT_DIVIDER_VISIBLE,
    _num,
    _stored_canvas_widget_state,
)


def _ic_panes(
    store: Any,
    view_state: Any,
    content: dict[str, Any] | None,
    single_preview: int,
    sources: dict[str, str],
    unavailable: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The image panes and the split line, both in canvas px."""
    if content is None:
        unavailable.append(
            {"field": "panes", "reason": "no content rect to split into panes"}
        )
        return [], None
    paths = _ic_document_paths(store)
    x, y, w, h = content["rect"]
    horizontal = bool(getattr(view_state, "is_horizontal", False))
    split = _num(getattr(view_state, "split_position_visual", 0.5), 0.5)

    if single_preview:
        sources["panes"] = "ic_render_plan.render_scene.single_image_preview"
        pane = {
            "slot": int(single_preview),
            "path": paths.get(int(single_preview)),
            "rect": [x, y, w, h],
            "space": SPACE_CANVAS_PX,
            "z": None,
            "visible": True,
            "painted": True,
            "in_composition": True,
            "reason": None,
            "rect_source": "ic_render_plan_content_rect",
        }
        return [pane], None

    from ui.canvas_infra.viewport.geometry import resolve_axis_position

    sources["panes"] = "ic_render_plan_content_rect+view_state.split_position_visual"
    if horizontal:
        line = resolve_axis_position(y, h, split)
        rects = {1: [x, y, w, line - y], 2: [x, line, w, y + h - line]}
        line_block = {"axis": "h", "pos": line}
    else:
        line = resolve_axis_position(x, w, split)
        rects = {1: [x, y, line - x, h], 2: [line, y, x + w - line, h]}
        line_block = {"axis": "v", "pos": line}
    panes = [
        {
            "slot": slot,
            "path": paths.get(slot),
            "rect": [_num(value) for value in rects[slot]],
            "space": SPACE_CANVAS_PX,
            "z": None,
            "visible": True,
            "painted": True,
            "in_composition": True,
            "reason": None,
            "rect_source": "ic_render_plan_content_rect+split_position_visual",
        }
        for slot in (1, 2)
    ]
    return panes, line_block


def _ic_document_paths(store: Any) -> dict[int, str | None]:
    """``{slot: path}`` from the session document — read, never created."""
    paths: dict[int, str | None] = {1: None, 2: None}
    if store is None:
        return paths
    try:
        document = store.get_session_state_slot("document")
    except Exception:
        return paths
    for slot, attr in ((1, "image1_path"), (2, "image2_path")):
        value = getattr(document, attr, None)
        if value:
            paths[slot] = str(value)
    return paths


def _ic_dividers(
    view_state: Any,
    single_preview: int,
    line: dict[str, Any] | None,
    sources: dict[str, str],
    unavailable: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """The painted split line, with the divider feature's own visibility rules."""
    if single_preview or line is None:
        unavailable.append(
            {
                "field": "dividers",
                "reason": (
                    "single-image preview draws no split line"
                    if single_preview
                    else "no split line without a content rect"
                ),
            }
        )
        return []
    state, materialized = _stored_canvas_widget_state(view_state, "divider")
    visible = bool(getattr(state, "visible", _IC_DEFAULT_DIVIDER_VISIBLE))
    thickness = int(getattr(state, "thickness", _IC_DEFAULT_DIVIDER_THICKNESS) or 0)
    diff_mode = str(getattr(view_state, "diff_mode", "off") or "off")
    # ``divider/runtime_hooks.build_divider_render_scene_overrides`` paints the
    # line only outside diff mode and single preview; mirror that verdict here
    # instead of reporting a line the renderer suppresses.
    painted = bool(visible and diff_mode == "off")
    sources["dividers"] = (
        "divider_widget_state+render_scene_rules"
        if materialized
        else "divider_state_defaults (state not materialized)"
    )
    return [
        {
            "axis": line["axis"],
            "pos": _num(line["pos"]),
            "space": SPACE_CANVAS_PX,
            "thickness": float(max(0, thickness)),
            # The thickness setting is a widget-px width used verbatim by the
            # divider pass (``divider/overlay_model.py:75``); reporting it as
            # canvas px would be a unit lie.
            "thickness_space": SPACE_WIDGET_PX,
            "visible": painted,
            "source": "ic_divider_feature",
            "state_materialized": materialized,
            "suppressed_by": None
            if painted
            else ("diff_mode" if visible and diff_mode != "off" else "divider_hidden"),
            # The painted line is positioned in view-transformed widget px
            # (``divider/overlay_model.py:76-82``), i.e. it moves with zoom/pan
            # while ``pos`` above stays the content-space split, in canvas px.
            "painted_position_space": SPACE_WIDGET_PX,
        }
    ]
