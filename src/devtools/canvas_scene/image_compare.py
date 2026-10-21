"""Image Compare canvas scene adapter (canvas px).

Reads the label's scene-graph cache and render plan without materializing
lazy state: see ``devtools.canvas_scene`` for the R1-R7 contract.
"""

from __future__ import annotations

from typing import Any

from .common import SPACE_CANVAS_PX, _num
from .image_compare_instances import _ic_magnifiers, _ic_render_layout, _ic_transform
from .image_compare_panes import _ic_dividers, _ic_panes


# ---------------------------------------------------------------------------
# Image Compare adapter (canvas px) — thin owner: assembly + canvas geometry
# ---------------------------------------------------------------------------


def _image_compare_scene(canvas: Any) -> dict[str, Any]:
    runtime_state = getattr(canvas, "runtime_state", None)
    store = _ic_store(canvas, runtime_state)
    viewport = getattr(store, "viewport", None)
    view_state = getattr(viewport, "view_state", None)
    plan = getattr(canvas, "_active_render_plan", None)
    unavailable: list[dict[str, str]] = []
    sources: dict[str, str] = {}

    canvas_block = _ic_canvas_block(plan, viewport, unavailable)
    content = _ic_content_rect(plan, canvas_block, sources, unavailable)
    single_preview = _ic_single_preview(plan, view_state)

    panes, divider_line = _ic_panes(
        store, view_state, content, single_preview, sources, unavailable
    )
    dividers = _ic_dividers(
        view_state, single_preview, divider_line, sources, unavailable
    )
    magnifiers = _ic_magnifiers(runtime_state, view_state, sources, unavailable)
    render_layout = _ic_render_layout(plan, sources, unavailable)
    transform = _ic_transform(runtime_state, canvas, sources, unavailable)

    return {
        "canvas": canvas_block,
        "panes": panes,
        "dividers": dividers,
        "magnifiers": magnifiers,
        "transform": transform,
        "render_layout": render_layout,
        "focus": None,
        "sources": sources,
        "unavailable": unavailable,
    }


def _ic_store(canvas: Any, runtime_state: Any) -> Any:
    store = getattr(runtime_state, "_store", None)
    if store is not None:
        return store
    return getattr(canvas, "store", None)


def _ic_canvas_block(
    plan: Any, viewport: Any, unavailable: list[dict[str, str]]
) -> dict[str, Any] | None:
    """Canvas size in canvas px: the render plan, else the viewport geometry."""
    width = int(getattr(plan, "canvas_w", 0) or 0) if plan is not None else 0
    height = int(getattr(plan, "canvas_h", 0) or 0) if plan is not None else 0
    if width > 0 and height > 0:
        return {
            "w": width,
            "h": height,
            "space": SPACE_CANVAS_PX,
            "source": "ic_render_plan",
        }
    geometry = getattr(viewport, "geometry_state", None)
    pix_w = int(getattr(geometry, "pixmap_width", 0) or 0)
    pix_h = int(getattr(geometry, "pixmap_height", 0) or 0)
    if pix_w > 0 and pix_h > 0:
        return {
            "w": pix_w,
            "h": pix_h,
            "space": SPACE_CANVAS_PX,
            "source": "ic_viewport_geometry",
        }
    unavailable.append(
        {
            "field": "canvas",
            "reason": "no rendered frame and no decoded image-pair size",
        }
    )
    return None


def _ic_content_rect(
    plan: Any,
    canvas_block: dict[str, Any] | None,
    sources: dict[str, str],
    unavailable: list[dict[str, str]],
) -> dict[str, Any] | None:
    """The image area inside the canvas, in canvas px."""
    if plan is not None:
        from ui.canvas_presentation.plan import resolve_plan_logical_image_rect

        x, y, w, h = resolve_plan_logical_image_rect(plan)
        sources["content_rect"] = "ic_render_plan.overlay_clip_rect"
        return {"rect": [_num(x), _num(y), _num(w), _num(h)], "space": SPACE_CANVAS_PX}
    if canvas_block is not None:
        # Without a plan the clip rect is unknown; the canvas itself is the only
        # honest content rect (the pair is drawn edge to edge, no padding).
        sources["content_rect"] = "ic_canvas_full (no render plan yet)"
        return {
            "rect": [0.0, 0.0, _num(canvas_block["w"]), _num(canvas_block["h"])],
            "space": SPACE_CANVAS_PX,
        }
    unavailable.append({"field": "content_rect", "reason": "no canvas size"})
    return None


def _ic_single_preview(plan: Any, view_state: Any) -> int:
    scene = getattr(plan, "render_scene", None) if plan is not None else None
    if scene is not None:
        try:
            return int(getattr(scene, "single_image_preview", 0) or 0)
        except Exception:
            return 0
    try:
        return int(getattr(view_state, "showing_single_image_mode", 0) or 0)
    except Exception:
        return 0
