from __future__ import annotations

from domain.types import Rect
from .context import CanvasSceneBuildContext
from .models import (
    CanvasSceneGraph,
)
from .pipeline import get_scene_overlay_builders, get_scene_primary_builders
from .registry import get_canvas_registry

def _session_type(store) -> str | None:
    session = store.get_active_workspace_session()
    return session.session_type if session is not None else None

def _resolve_active_object_id(view, session_type: str | None) -> str | None:
    for feature in get_canvas_registry(session_type).get_scene_features():
        resolver = getattr(feature, "resolve_active_object_id", None)
        if resolver is None:
            continue
        object_id = resolver(view)
        if object_id is not None:
            return object_id
    return None

def _sync_scene_geometry(
    scene: CanvasSceneGraph, geometry_state, session_type: str | None
) -> None:
    for feature in get_canvas_registry(session_type).get_scene_features():
        sync_geometry = getattr(feature, "sync_geometry", None)
        if sync_geometry is None:
            continue
        sync_geometry(scene, geometry_state)

def _resolve_bounds(store, image_label, label_width: int, label_height: int) -> Rect:
    state = getattr(image_label, "runtime_state", None) if image_label is not None else None

    inner_rect = getattr(state, "_inner_content_rect_px", None) if state is not None else None
    if inner_rect:
        x, y, w, h = inner_rect
        if int(w) > 0 and int(h) > 0:
            return Rect(int(x), int(y), int(w), int(h))
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

def _session_has_content(store) -> bool:
    from tabs.registry import get_shared_tab_registry

    result = get_shared_tab_registry().create_service("session_has_content", store)
    return bool(result)

def _document_names_pair(store) -> bool:
    """True when the document still names BOTH sides of a pair.

    A slot replace dispatches ``ClearImageSlotDataAction`` (and an emptied
    first-file transaction clears both slots) BEFORE the new tier lands, so the
    frame where ``image_state.imageN`` is momentarily ``None`` still has both
    document paths. That is the discriminator between "a transiently empty
    frame" and "the user really has no (pair) content": a one-sided document is
    the user's content, not a replace in flight, and its overlays may go.
    """
    try:
        document = store.get_session_state_slot("document")
    except Exception:
        document = getattr(store, "document", None)
    if document is None:
        return False
    return bool(
        getattr(document, "image1_path", None) and getattr(document, "image2_path", None)
    )

def _previous_scene(image_label):
    state = getattr(image_label, "runtime_state", None) if image_label is not None else None
    if state is None:
        return None
    return getattr(state, "_canvas_scene_graph", None)

def _hold_previous_scene(store, image_label):
    """The last resolved frame, when this frame is only transiently empty.

    An empty graph drops every declared-visible overlay (loupe, capture ring)
    from both the scene AND the hit-test. Ownership rule: an overlay that is
    declared visible may only be killed by the user, so a frame we cannot
    resolve (slot being replaced, pixmap invalidated mid-swap) repeats the
    previous one byte-identically — geometry included. Returns ``None`` when
    there is nothing to hold or the session genuinely has no content.
    """
    if not _document_names_pair(store):
        return None
    previous = _previous_scene(image_label)
    if previous is None or not getattr(previous, "objects", ()):
        return None
    return previous

def build_canvas_scene(store, image_label=None, label_width: int | None = None, label_height: int | None = None) -> CanvasSceneGraph:
    viewport = store.viewport
    view = viewport.view_state
    session_type = _session_type(store)

    pix_w = int(getattr(viewport.geometry_state, "pixmap_width", 0) or 0)
    pix_h = int(getattr(viewport.geometry_state, "pixmap_height", 0) or 0)
    active_object_id = _resolve_active_object_id(view, session_type)
    if not _session_has_content(store):
        # A slot replace zeroes the side's image_state before the new tier
        # lands (use_cases/slot.py: ClearImageSlotDataAction). Rebuilding the
        # scene over that frame used to answer with an EMPTY graph, which
        # removed a declared-visible magnifier from the scene graph and its
        # hit-test for one frame (measured live 2026-10-27:
        # magnifiers[0].visible == True with circles == []). Keep the previous
        # frame while the document still names content.
        held = _hold_previous_scene(store, image_label)
        if held is not None:
            return held
        return CanvasSceneGraph(bounds=Rect(), objects=(), active_object_id=active_object_id)

    if label_width is None:
        label_width = int(getattr(image_label, "width", lambda: 0)() or 0) if image_label is not None else 0
    if label_height is None:
        label_height = int(getattr(image_label, "height", lambda: 0)() or 0) if image_label is not None else 0

    bounds = _resolve_bounds(store, image_label, label_width, label_height)
    if pix_w <= 0 or pix_h <= 0:
        # Transient geometry invalidation (image swap, session restore, a
        # clear-then-reload frame) must not delete a declared-visible overlay:
        # an empty graph drops the loupe/capture ring from the scene AND from
        # the hit-test for those frames. Fall back to the frame we last
        # resolved -- the content rect / display rect already carries it -- and
        # only a genuinely unknowable frame (empty bounds) stays empty. An
        # overlay that is declared visible may only be killed by the user.
        pix_w, pix_h = int(bounds.w), int(bounds.h)
    if pix_w <= 0 or pix_h <= 0:
        # Same ownership rule as the no-content branch above: a frame we
        # cannot resolve repeats the previous one instead of deleting a
        # declared-visible overlay.
        held = _hold_previous_scene(store, image_label)
        if held is not None:
            return held
        return CanvasSceneGraph(bounds=Rect(), objects=(), active_object_id=active_object_id)
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
            for builder in get_scene_primary_builders(session_type)
            for obj in builder(context)
        ),
        active_object_id=active_object_id,
    )
    overlay_objects = tuple(
        obj
        for builder in get_scene_overlay_builders(session_type)
        for obj in builder(scene, context)
    )
    if overlay_objects:
        scene = CanvasSceneGraph(
            bounds=scene.bounds,
            objects=tuple((*scene.objects, *overlay_objects)),
            active_object_id=scene.active_object_id,
        )

    _sync_scene_geometry(scene, viewport.geometry_state, session_type)
    return scene
