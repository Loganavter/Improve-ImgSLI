"""Session snapshot/restore + project (de)serialization for ``ImageGalleryTab``.

Split out of ``tab.py`` (G4) to keep that class down to the ``TabContract``
surface itself, mirroring the ``use_cases`` split applied to image_compare's
own ``use_cases/persistence.py``. Every function here takes the tab as its
first argument. ``serialize_session``/``deserialize_session``/
``rehydrate_session``/``duplicate_session`` are required ``TabContract``
method names, so ``tab.py`` keeps thin delegators of those exact names;
everything else here is private and only ever called from those delegators.

The ``gallery`` session slot (``GallerySlotState``) is the single source of
truth: pool membership, selection, filter, folder and triage summary.
Restore rebuilds the controller mirror from the slot WITHOUT rescanning
the disk when the slot carries pool data; a disk rescan happens only
for empty/absent/foreign slots (legacy sessions).

Slot-write mechanism mirrors
``tabs.multi_compare.use_cases.persistence.deserialize_session`` verbatim:
a direct ``store.set_session_state_slot(..., emit_scope=None)`` — no
dispatcher branch, no deferred retry. The tab never writes the slot
anywhere else (all live mutations go through
``GalleryController._emit_gallery``/``_transact_gallery``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from tabs.contract import TabContext
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.state.models import (
    GalleryItemMeta,
    GallerySlotState,
    fresh_gallery_slot_state,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

# Legacy folder-only slot (pre-Redux sessions). Read-only fallback for
# foreign/legacy restores — never written; the ``gallery`` slot above is
# the single source of truth.
_LEGACY_STATE_SLOT = "image_gallery.state"

_SERIALIZE_VERSION = 2


def _chrome_serialize(tab, session_id: str, context: TabContext) -> dict:
    state = getattr(tab, "_session_state", None)
    if state is None:
        return {}
    try:
        return state.serialize(context, session_id)
    except Exception:
        logger.debug("ImageGalleryTab chrome serialize failed", exc_info=True)
        return {}


def _chrome_deserialize(tab, session_id: str, data: dict, context: TabContext) -> None:
    state = getattr(tab, "_session_state", None)
    if state is None:
        return
    try:
        state.deserialize(data, context, session_id)
    except Exception:
        logger.debug("ImageGalleryTab chrome deserialize failed", exc_info=True)


def _apply_session_state(tab, context: TabContext, session_id: str) -> None:
    """Apply the session's toolbar chrome (unconditional; never pool-gated).

    ``SessionState.apply_from_slot`` reads the LIVE slot (QSettings fallback)
    and binds the facade to ``session_id``. The judgment domain is applied
    quietly by the widget, so a restored ``ai`` domain never fires a run.
    """
    state = getattr(tab, "_session_state", None)
    if state is None:
        return
    try:
        state.apply_from_slot(context, session_id)
    except Exception:
        logger.debug("ImageGalleryTab view-prefs restore failed", exc_info=True)


def restore_from(tab, context: TabContext, session_id: str | None) -> None:
    if session_id is None or tab._widget is None or tab._controller is None:
        return
    store = getattr(context, "store", None)
    if store is None:
        return
    try:
        slot = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=session_id)
    except Exception:
        slot = None
    if isinstance(slot, GallerySlotState) and slot.items:
        # Pool data present — rebuild the mirror from the slot, no rescan.
        # The controller resolves the slot via the *active* session, so
        # only sync when this session is the active one; otherwise the
        # slot persists untouched and activation restores it.
        try:
            active = store.get_active_workspace_session()
            active_id = getattr(active, "id", None)
        except Exception:
            active_id = None
        if active_id is not None and active_id != session_id:
            return
        try:
            tab._controller._sync_from_slot()
        except Exception:
            logger.debug("ImageGalleryTab slot restore failed", exc_info=True)
        _apply_session_state(tab, context, session_id)
        return
    # Empty / absent / foreign slot — legacy rescan path. Folder comes
    # from the (possibly empty) slot, else the legacy folder-only slot.
    folder_raw = slot.folder if isinstance(slot, GallerySlotState) else None
    if not folder_raw and isinstance(slot, dict):
        folder_raw = slot.get("folder")
    if not folder_raw:
        try:
            legacy = store.get_session_state_slot(_LEGACY_STATE_SLOT, session_id=session_id)
        except Exception:
            legacy = None
        if isinstance(legacy, dict):
            folder_raw = legacy.get("folder")
    if not folder_raw:
        # Slot-authoritative clear: the session carries no pool, so the
        # controller-local mirror + grid must not keep the previous
        # session's items (session-isolation contract).
        try:
            tab._controller.clear_to_empty()
        except Exception:
            logger.debug("ImageGalleryTab empty restore failed", exc_info=True)
        _apply_session_state(tab, context, session_id)
        return
    folder = Path(folder_raw)
    if folder.is_dir():
        try:
            tab._controller.open_folder(folder)
        except Exception:
            logger.debug("ImageGalleryTab restore failed for %s", folder, exc_info=True)
    _apply_session_state(tab, context, session_id)


def serialize_session(tab, session_id: str, context: TabContext) -> dict | None:
    store = getattr(context, "store", None)
    if store is None:
        return None
    try:
        session = store.get_workspace_session(session_id)
    except Exception:
        return None
    if session is None or getattr(session, "session_type", None) != tab.session_type:
        return None
    # No snapshot: the slot is already current (dispatch-only mutation).
    try:
        slot = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=session_id)
    except Exception:
        slot = None
    if isinstance(slot, GallerySlotState):
        snapshot = {
            "version": _SERIALIZE_VERSION,
            "folder": slot.folder,
            "filter_text": slot.filter_text,
            "selection": list(slot.selection),
            "triage_state": slot.triage_state,
            "mode": slot.mode,
            "source_path": slot.source_path,
            "items": [
                {
                    "path": it.path,
                    "mtime_ns": it.mtime_ns,
                    "status": it.status,
                    "rank": it.rank,
                }
                for it in slot.items
            ],
        }
        # Toolbar chrome is read from THIS session's slot (not the bound copy).
        snapshot.update(_chrome_serialize(tab, session_id, context))
        return snapshot
    # Foreign/legacy slot value — persist whatever folder we can find.
    # Slot-only: when slot/legacy carry no folder, fail open with
    # folder None — never reach into controller-local truth.
    folder = slot.get("folder") if isinstance(slot, dict) else None
    if folder is None:
        try:
            legacy = store.get_session_state_slot(_LEGACY_STATE_SLOT, session_id=session_id)
        except Exception:
            legacy = None
        if isinstance(legacy, dict):
            folder = legacy.get("folder")
    return {"version": 1, "folder": folder}


def deserialize_session(tab, session_id: str, data: dict, context: TabContext) -> None:
    store = getattr(context, "store", None)
    if store is None or not data:
        return
    if data.get("version", 1) >= _SERIALIZE_VERSION and data.get("items") is not None:
        items = []
        for e in data.get("items") or []:
            if not isinstance(e, dict):
                continue
            try:
                items.append(
                    GalleryItemMeta(
                        path=str(e.get("path", "")),
                        mtime_ns=int(e.get("mtime_ns", 0) or 0),
                        status=str(e.get("status", "not_loaded") or "not_loaded"),
                        rank=e.get("rank") if e.get("rank") is None else int(e.get("rank")),
                    )
                )
            except Exception:
                continue
        state = GallerySlotState(
            items=items,
            selection=[str(s) for s in (data.get("selection") or [])],
            filter_text=str(data.get("filter_text") or ""),
            folder=data.get("folder"),
            triage_state=str(data.get("triage_state") or "idle"),
            mode=data.get("mode"),
            source_path=data.get("source_path"),
        )
    else:
        # Legacy v1 (folder only): empty pool forces a rescan on restore.
        state = fresh_gallery_slot_state()
        state.folder = data.get("folder")
    try:
        store.set_session_state_slot(GALLERY_SLOT_NAME, state, session_id=session_id, emit_scope=None)
    except Exception:
        pass
    _chrome_deserialize(tab, session_id, data, context)
    # If this session is currently visible, rebuild from the slot now.
    active = None
    try:
        getter = getattr(store, "get_active_workspace_session", None)
        if callable(getter):
            active = getter()
    except Exception:
        active = None
    if session_id == tab._active_session_id or (active is not None and getattr(active, "id", None) == session_id):
        restore_from(tab, context, session_id)


def duplicate_session(tab, source_session_id: str, context: TabContext) -> dict | None:
    return serialize_session(tab, source_session_id, context)


def rehydrate_session(tab, session_id: str, context: TabContext) -> None:
    # Pool data lives in the slot — restore rebuilds from it without a
    # disk rescan; only empty/legacy slots rescan.
    restore_from(tab, context, session_id)
