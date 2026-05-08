from __future__ import annotations

from domain.types import Rect
from .context import CanvasSceneBuildContext
from .feature_registry import get_canvas_scene_features
from .models import (
    CanvasSceneGraph,
)
from .pipeline import SCENE_OVERLAY_BUILDERS, SCENE_PRIMARY_BUILDERS

def _resolve_active_object_id(view) -> str | None:
    for feature in get_canvas_scene_features():
        resolver = getattr(feature, "resolve_active_object_id", None)
        if resolver is None:
            continue
        object_id = resolver(view)
        if object_id is not None:
            return object_id
    return None

def _sync_scene_geometry(scene: CanvasSceneGraph, geometry_state) -> None:
    for feature in get_canvas_scene_features():
        sync_geometry = getattr(feature, "sync_geometry", None)
        if sync_geometry is None:
            continue
        sync_geometry(scene, geometry_state)

def _resolve_bounds(store, image_label, label_width: int, label_height: int) -> Rect:
    state = getattr(image_label, "runtime_state", None) if image_label is not None else None
    content_rect = getattr(state, "_content_rect_px", None) if state is not None else None
    if content_rect:
        x, y, w, h = content_rect
        if int(w) > 0 and int(h) > 0:
            return Rect(int(x), int(y), int(w), int(h))

    rect = store.viewport.geometry_state.image_display_rect_on_label
    if rect.w > 0 and rect.h > 0:
        return Rect(int(rect.x), int(rect.y), int(rect.w), int(rect.h))

    pix_w = int(getattr(store.viewport.geometry_state, "pixmap_width", 0) or 0)
    pix_h = int(getattr(store.viewport.geometry_state, "pixmap_height", 0) or 0)
    if pix_w > 0 and pix_h > 0 and label_width > 0 and label_height > 0:
        return Rect(
            int((label_width - pix_w) // 2),
            int((label_height - pix_h) // 2),
            pix_w,
            pix_h,
        )
    return Rect()

def build_canvas_scene(store, image_label=None, label_width: int | None = None, label_height: int | None = None) -> CanvasSceneGraph:
    viewport = store.viewport
    view = viewport.view_state
    image_state = viewport.session_data.image_state

    pix_w = int(getattr(viewport.geometry_state, "pixmap_width", 0) or 0)
    pix_h = int(getattr(viewport.geometry_state, "pixmap_height", 0) or 0)
    active_object_id = _resolve_active_object_id(view)
    if pix_w <= 0 or pix_h <= 0 or not image_state.image1:
        return CanvasSceneGraph(bounds=Rect(), objects=(), active_object_id=active_object_id)

    if label_width is None:
        label_width = int(getattr(image_label, "width", lambda: 0)() or 0) if image_label is not None else 0
    if label_height is None:
        label_height = int(getattr(image_label, "height", lambda: 0)() or 0) if image_label is not None else 0

    bounds = _resolve_bounds(store, image_label, label_width, label_height)
    context = CanvasSceneBuildContext(
        store=store,
        image_label=image_label,
        bounds=bounds,
        label_width=label_width,
        label_height=label_height,
        pix_w=pix_w,
        pix_h=pix_h,
    )

    scene = CanvasSceneGraph(
        bounds=bounds,
        objects=tuple(
            obj
            for builder in SCENE_PRIMARY_BUILDERS
            for obj in builder(context)
        ),
        active_object_id=active_object_id,
    )
    overlay_objects = tuple(
        obj
        for builder in SCENE_OVERLAY_BUILDERS
        for obj in builder(scene, context)
    )
    if overlay_objects:
        scene = CanvasSceneGraph(
            bounds=scene.bounds,
            objects=tuple((*scene.objects, *overlay_objects)),
            active_object_id=scene.active_object_id,
        )

    _sync_scene_geometry(scene, viewport.geometry_state)
    return scene
