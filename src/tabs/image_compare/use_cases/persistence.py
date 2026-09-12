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
import os

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

    # Store-first: the "file names enabled" flag lives in the Store's
    # viewport render_config (SSOT) and caption texts come from
    # DocumentModel display names (editor syncs via chrome_sync) — neither
    # is snapshotted from widget state. Only the camera is captured here.
    zoom, pan_x, pan_y = read_camera_from_host(tab)
    state = ImageCompareState(
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
    # Store-first: the toolbar button and caption editors sync from the
    # Store (viewport render_config / DocumentModel display names) via
    # chrome_sync / apply_initial_state — never written from this slot.
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
        # Store-side data only (DocumentModel fields) — no widget reads;
        # crop_override is a plain tristate (None/True/False), JSON-safe.
        return [
            {
                "path": it.path,
                "display_name": it.display_name,
                "rating": it.rating,
                "crop_override": getattr(it, "crop_override", None),
            }
            for it in items
        ]

    from tabs.image_compare.session_persistence import serialize_viewport_block

    camera = {
        "zoom": float(getattr(ui_state, "zoom", 1.0) or 1.0) if ui_state else 1.0,
        "pan_x": float(getattr(ui_state, "pan_x", 0.0) or 0.0) if ui_state else 0.0,
        "pan_y": float(getattr(ui_state, "pan_y", 0.0) or 0.0) if ui_state else 0.0,
    }

    return {
        "version": 3,
        "image_list1": _items(doc.image_list1) if doc else [],
        "image_list2": _items(doc.image_list2) if doc else [],
        "current_index1": doc.current_index1 if doc else -1,
        "current_index2": doc.current_index2 if doc else -1,
        "image1_path": doc.image1_path if doc else None,
        "image2_path": doc.image2_path if doc else None,
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
            from tabs.image_compare.pipeline.cache import _pixel_key

            for path in (doc.image1_path, doc.image2_path):
                if not path:
                    continue
                try:
                    k = _pixel_key(path, None, None)
                    img = ps.pixel.get(k)  # type: ignore[attr-defined]
                    if img is not None and isinstance(img, TiledPixelStore) and img.is_open:
                        sources[path] = img
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
        rebuilt = []
        for e in entries or []:
            path = e.get("path", "") or ""
            display_name = e.get("display_name", "") or ""
            if not (isinstance(display_name, str) and display_name.strip()):
                stem = os.path.splitext(os.path.basename(path))[0] if path else ""
                display_name = stem if stem and stem.strip(" .") else "-----"
            # Tristate normalize: pre-override files lack the key (→ None/Auto).
            raw_override = e.get("crop_override", None)
            crop_override = None if raw_override is None else bool(raw_override)
            rebuilt.append(
                ImageItem(
                    path=path,
                    display_name=display_name,
                    rating=e.get("rating", 0),
                    crop_override=crop_override,
                )
            )
        return rebuilt

    doc = DocumentModel(
        image_list1=_items(data.get("image_list1")),
        image_list2=_items(data.get("image_list2")),
        current_index1=data.get("current_index1", -1),
        current_index2=data.get("current_index2", -1),
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
    # v3: the "file names enabled" flag lives in the viewport render_config
    # block and captions in DocumentModel display names. Legacy v2 keys
    # (show_file_names/edit_name_1/edit_name_2) are ignored when present.
    ui_state = ImageCompareState(
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
    is_active = session_id == tab._active_session_id or (
        active is not None and getattr(active, "id", None) == session_id
    )
    if is_active:
        apply_camera_to_host(
            tab,
            float(camera.get("zoom", 1.0) or 1.0),
            float(camera.get("pan_x", 0.0) or 0.0),
            float(camera.get("pan_y", 0.0) or 0.0),
        )
        # Toolbar re-sync after deferred restore (worker C's helper).
        # Guarded: session_persistence may not provide
        # refresh_filename_overlay_toolbar yet in this checkout.
        try:
            import importlib

            _mod = importlib.import_module("tabs.image_compare.session_persistence")
            _refresh = getattr(_mod, "refresh_filename_overlay_toolbar", None)
            if callable(_refresh):
                presenter = getattr(
                    getattr(context, "main_window", None), "presenter", None
                )
                try:
                    _refresh(store, presenter)
                except TypeError:
                    _refresh(store)
        except Exception:
            pass


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