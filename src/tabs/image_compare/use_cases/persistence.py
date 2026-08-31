"""Session snapshot/restore, camera sync, serialize/deserialize/rehydrate
for ``ImageCompareTab`` -- split out to keep that class down to the
``TabContract`` surface itself, mirroring the ``use_cases`` split applied to
``_session_controller.py``. Every function here takes the tab as its first
argument. ``serialize_session``/``deserialize_session``/``rehydrate_session``
are required ``TabContract`` method names, so ``tab.py`` keeps thin
delegators of those exact names; everything else here is private and only
ever called from those delegators.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer

from tabs.contract import TabContext

logger = logging.getLogger("ImproveImgSLI")

_STATE_SLOT = "image_compare.state"


def _resolve_image_compare_sessions(context: TabContext):
    main_window = context.main_window
    if main_window is None:
        return None
    controller = getattr(main_window, "main_controller", None)
    if controller is None:
        presenter = getattr(main_window, "presenter", None)
        controller = getattr(presenter, "main_controller", None)
    if controller is None:
        return None
    return getattr(controller, "sessions", None)


def canvas_host(tab):
    widget = tab._widget
    if widget is None:
        return None
    return getattr(widget, "image_label", None)


def read_camera_from_host(tab) -> tuple[float, float, float]:
    from ui.canvas_infra.viewport import get_pan_offset_x, get_pan_offset_y, get_zoom_level

    host = canvas_host(tab)
    if host is None:
        return 1.0, 0.0, 0.0
    try:
        return (
            float(get_zoom_level(host)),
            float(get_pan_offset_x(host)),
            float(get_pan_offset_y(host)),
        )
    except Exception:
        return 1.0, 0.0, 0.0


def apply_camera_to_host(tab, zoom: float, pan_x: float, pan_y: float) -> None:
    from ui.canvas_infra.viewport import set_pan_offsets, set_zoom_level

    host = canvas_host(tab)
    if host is None:
        return
    try:
        set_zoom_level(host, zoom)
        set_pan_offsets(host, pan_x, pan_y)
    except Exception:
        logger.exception("Failed to apply camera to image_compare canvas host")


def snapshot_into(tab, context: TabContext, session_id: str | None) -> None:
    if session_id is None or tab._widget is None:
        return
    store = getattr(context, "store", None)
    if store is None or not hasattr(store, "set_session_state_slot"):
        return
    from tabs.image_compare.models import ImageCompareState

    widget = tab._widget
    zoom, pan_x, pan_y = read_camera_from_host(tab)
    state = ImageCompareState(
        show_file_names=bool(getattr(getattr(widget, "btn_file_names", None), "isChecked", lambda: False)()),
        edit_name_1=getattr(getattr(widget, "edit_name1", None), "text", lambda: "")(),
        edit_name_2=getattr(getattr(widget, "edit_name2", None), "text", lambda: "")(),
        zoom=zoom,
        pan_x=pan_x,
        pan_y=pan_y,
    )
    try:
        store.set_session_state_slot(
            _STATE_SLOT, state, session_id=session_id, emit_scope=None,
        )
    except Exception:
        pass


def restore_from(tab, context: TabContext, session_id: str | None) -> None:
    if session_id is None or tab._widget is None:
        return
    store = getattr(context, "store", None)
    if store is None or not hasattr(store, "ensure_session_state_slot"):
        return
    from tabs.image_compare.models import ImageCompareState

    try:
        state = store.ensure_session_state_slot(
            _STATE_SLOT, session_id=session_id, factory=ImageCompareState,
        )
    except Exception:
        return
    if state is None:
        return
    widget = tab._widget
    btn = getattr(widget, "btn_file_names", None)
    if btn is not None and hasattr(btn, "setChecked"):
        btn.setChecked(bool(state.show_file_names))
    for attr, value in (("edit_name1", state.edit_name_1), ("edit_name2", state.edit_name_2)):
        edit = getattr(widget, attr, None)
        if edit is not None and hasattr(edit, "setText"):
            edit.setText(value or "")
    apply_camera_to_host(
        tab,
        float(getattr(state, "zoom", 1.0) or 1.0),
        float(getattr(state, "pan_x", 0.0) or 0.0),
        float(getattr(state, "pan_y", 0.0) or 0.0),
    )


def serialize_session(tab, session_id: str, context: TabContext) -> dict | None:
    store = getattr(context, "store", None)
    if store is None:
        return None
    session = store.get_workspace_session(session_id)
    if session is None or session.session_type != tab.session_type:
        return None
    # Sync camera from the live host when serializing the active session.
    if session_id == tab._active_session_id:
        snapshot_into(tab, context, session_id)
        session = store.get_workspace_session(session_id) or session

    doc = session.document
    ui_state = session.state_slots.get(_STATE_SLOT)

    def _items(items):
        return [
            {"path": it.path, "display_name": it.display_name, "rating": it.rating}
            for it in items
        ]

    from tabs.image_compare.session_persistence import serialize_viewport_block

    camera = {
        "zoom": float(getattr(ui_state, "zoom", 1.0) or 1.0) if ui_state else 1.0,
        "pan_x": float(getattr(ui_state, "pan_x", 0.0) or 0.0) if ui_state else 0.0,
        "pan_y": float(getattr(ui_state, "pan_y", 0.0) or 0.0) if ui_state else 0.0,
    }

    return {
        "version": 2,
        "image_list1": _items(doc.image_list1) if doc else [],
        "image_list2": _items(doc.image_list2) if doc else [],
        "current_index1": doc.current_index1 if doc else -1,
        "current_index2": doc.current_index2 if doc else -1,
        "image1_path": doc.image1_path if doc else None,
        "image2_path": doc.image2_path if doc else None,
        "show_file_names": bool(ui_state.show_file_names) if ui_state else False,
        "edit_name_1": ui_state.edit_name_1 if ui_state else "",
        "edit_name_2": ui_state.edit_name_2 if ui_state else "",
        "camera": camera,
        "viewport": serialize_viewport_block(getattr(session, "viewport", None)),
    }


def collect_pixel_cache_sources(tab, session_id: str, context: TabContext) -> dict:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    store = getattr(context, "store", None)
    if store is None:
        return {}
    session = store.get_workspace_session(session_id)
    if session is None or session.session_type != tab.session_type:
        return {}
    doc = session.document
    if doc is None:
        return {}

    sources: dict = {}
    # Phase 3: PipelineCache is single source — peek via session store pipeline
    try:
        ps = store.get_session_state_slot("pipeline")  # type: ignore[union-attr]
        if ps is not None:
            import os

            from tabs.image_compare.pipeline.cache import _pixel_key

            for path in (doc.image1_path, doc.image2_path):
                if not path:
                    continue
                try:
                    k = _pixel_key(path, None, None)
                    img = ps.pixel.get(k)  # type: ignore[attr-defined]
                    if img is not None and isinstance(img, TiledPixelStore) and img.is_open:
                        sources[path] = img
                        continue
                    # fallback scan by path prefix
                    norm = os.path.normpath(path)
                    for kk, vv in ps.pixel.items():  # type: ignore[attr-defined]
                        if kk[0] == norm and isinstance(vv, TiledPixelStore) and vv.is_open:
                            sources[path] = vv
                            break
                except Exception:
                    continue
    except Exception:
        pass
    return sources


def deserialize_session(tab, session_id: str, data: dict, context: TabContext) -> None:
    store = getattr(context, "store", None)
    if store is None or not data:
        return
    session = store.get_workspace_session(session_id)
    if session is None:
        return
    from tabs.image_compare.state.document import DocumentModel, ImageItem
    from tabs.image_compare.models import ImageCompareState
    from tabs.image_compare.session_persistence import restore_viewport_block

    def _items(entries):
        # `image=None` — pixel data is not persisted, only the source
        # path; the existing load pipeline decodes it from disk lazily,
        # the same way `ImageSessionState.loaded_image*_paths` already
        # tracks history without holding pixels.
        return [
            ImageItem(
                path=e.get("path", ""),
                display_name=e.get("display_name", ""),
                rating=e.get("rating", 0),
            )
            for e in entries or []
        ]

    doc = DocumentModel(
        image_list1=_items(data.get("image_list1")),
        image_list2=_items(data.get("image_list2")),
        current_index1=data.get("current_index1", -1),
        current_index2=data.get("current_index2", -1),
        image1_path=data.get("image1_path"),
        image2_path=data.get("image2_path"),
    )
    camera = data.get("camera") or {}
    # Replace direct session.document assignment with slot API (AST-safe).
    # Use batch to coalesce document + viewport writes atomically when
    # dispatcher is bound; defer via QTimer.singleShot if dispatcher not yet
    # bound (dispatcher.py:118), fallback via setattr for fake stores.
    def _write_document():
        try:
            store.set_session_state_slot(
                "document", doc, session_id=session_id, emit_scope="document"
            )
        except Exception:
            try:
                setattr(session, "document", doc)
            except Exception:
                pass

    dispatcher = getattr(store, "get_dispatcher", lambda: None)()
    ui_state = ImageCompareState(
        show_file_names=bool(data.get("show_file_names", False)),
        edit_name_1=data.get("edit_name_1", ""),
        edit_name_2=data.get("edit_name_2", ""),
        zoom=float(camera.get("zoom", 1.0) or 1.0),
        pan_x=float(camera.get("pan_x", 0.0) or 0.0),
        pan_y=float(camera.get("pan_y", 0.0) or 0.0),
    )
    viewport_data = data.get("viewport")
    viewport = getattr(session, "viewport", None)
    if dispatcher is not None:
        try:
            with store.batch_changes():
                store.set_session_state_slot(
                    "document", doc, session_id=session_id, emit_scope="document"
                )
                store.set_session_state_slot(
                    _STATE_SLOT, ui_state, session_id=session_id, emit_scope=None
                )
                restore_viewport_block(viewport, viewport_data, store)
        except Exception:
            logger.error("Failed to deserialize document/viewport via batch", exc_info=True)
            _write_document()
            try:
                store.set_session_state_slot(
                    _STATE_SLOT, ui_state, session_id=session_id, emit_scope=None
                )
            except Exception:
                pass
            restore_viewport_block(viewport, viewport_data, store)
    else:
        # No dispatcher yet – early bootstrap: write slot directly and defer
        # a retry once dispatcher is wired; also handle fake stores where
        # dispatcher never appears (immediate write is the final state).
        _write_document()
        try:
            store.set_session_state_slot(
                _STATE_SLOT, ui_state, session_id=session_id, emit_scope=None
            )
        except Exception:
            pass
        restore_viewport_block(viewport, viewport_data, store)
        try:
            QTimer.singleShot(
                0,
                lambda: store.set_session_state_slot(
                    "document", doc, session_id=session_id, emit_scope="document"
                ),
            )
        except Exception:
            pass
    # If this session is currently shown, push camera onto the host now.
    active = None
    try:
        getter = getattr(store, "get_active_workspace_session", None)
        if callable(getter):
            active = getter()
    except Exception:
        active = None
    if session_id == tab._active_session_id or (
        active is not None and getattr(active, "id", None) == session_id
    ):
        apply_camera_to_host(
            tab,
            float(camera.get("zoom", 1.0) or 1.0),
            float(camera.get("pan_x", 0.0) or 0.0),
            float(camera.get("pan_y", 0.0) or 0.0),
        )


def rehydrate_session(tab, session_id: str, context: TabContext) -> None:
    """Lazy rehydrate — only ensure current slots, don't preload history.

    Old code decoded every path in image_list1/2 (history) via
    load_images_from_paths, which for 100 files meant 200 full decodes on
    project open. PipelineCache is demand-driven: history ImageItems keep
    only path/display_name, pixels are loaded on first browse via
    set_current_image → pipeline.ensure. This makes open O(1).
    """
    store = getattr(context, "store", None)
    if store is None:
        return
    session = store.get_workspace_session(session_id)
    if session is None or session.session_type != tab.session_type:
        return
    doc = session.document
    if doc is None:
        return

    if not doc.image_list1 and not doc.image_list2:
        return

    sessions = _resolve_image_compare_sessions(context)
    if sessions is None:
        return

    # Demand-driven: only the current index matters for initial display.
    # The canvas/ metrics will call pipeline.ensure on first set_current_image.
    # History stays as path-only ImageItems until the user browses to them.
    with store.using_workspace_session(session_id):
        # Ensure the document's current_index is valid, but don't force a
        # decode of every history entry. set_current_image will use
        # PipelineCache (single-flight, memo) for the current path only.
        for slot in (1, 2):
            lst = doc.image_list1 if slot == 1 else doc.image_list2
            idx = doc.current_index1 if slot == 1 else doc.current_index2
            if lst and 0 <= idx < len(lst):
                try:
                    sessions.set_current_image(slot, force_refresh=False, emit_signal=False)
                except Exception:
                    pass
        # One coalesced emit for the initial view (was 2× load_images_from_paths
        # with 3–5 dispatches each).
        try:
            store.emit_state_change("document")
        except Exception:
            pass