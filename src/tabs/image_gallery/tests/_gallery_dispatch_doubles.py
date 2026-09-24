"""Shared FakeDispatcher doubles for gallery Redux tests (Wave 3d2).

Mirrors the ``image_compare`` precedent
(``src/tabs/image_compare/tests/runtime/test_ic_p2_hygiene.py``:
``_RecordingDispatcher`` + ``_Store``) — do not invent a second fake shape.
The double applies the real ``GallerySlotReducer`` so tests assert dispatched
action types/scopes AND resulting slot contents via ``state/selectors.py``.

Scope for every gallery emit is ``"gallery"`` (``GALLERY_SLOT_NAME``); the
slot key is ``"gallery"``.
"""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.state.models import fresh_gallery_slot_state
from tabs.image_gallery.state.reducer import GallerySlotReducer


class FakeGallerySession:
    """Minimal workspace session carrying the ``gallery`` slot value."""

    def __init__(self, session_id: str = "s1"):
        self.id = session_id
        self.session_type = "image_gallery"
        self.state_slots: dict[str, Any] = {
            GALLERY_SLOT_NAME: fresh_gallery_slot_state()
        }


class FakeGalleryDispatcher:
    """Fake dispatcher applying the real GallerySlotReducer (no Qt needed).

    Records ``(action, scope)`` per dispatch; only ``scope == "gallery"``
    mutates the slot (other scopes are recorded but ignored, mirroring the
    ``_RecordingDispatcher`` document-scope guard in the precedent).
    """

    def __init__(self, store: FakeGalleryStore):
        self._store = store
        self.calls: list[tuple[Any, str]] = []

    def dispatch(self, action: Any, scope: str = "viewport") -> None:
        self.calls.append((action, scope))
        if scope != GALLERY_SLOT_NAME:
            return
        session = self._store.get_workspace_session(self._store._active_id)
        if session is None:
            return
        current = session.state_slots.get(
            GALLERY_SLOT_NAME, fresh_gallery_slot_state()
        )
        session.state_slots[GALLERY_SLOT_NAME] = GallerySlotReducer.reduce(
            current, action
        )
        self._store.emit_state_change(scope)


class FakeGalleryStore:
    """Minimal store stub behind ``context.store`` for controller tests."""

    def __init__(self, session_id: str = "s1"):
        self._sessions = {session_id: FakeGallerySession(session_id)}
        self._active_id = session_id
        self._dispatcher = FakeGalleryDispatcher(self)
        self.emitted: list[str] = []
        self._change_listeners: list = []

    def get_workspace_session(self, session_id: str | None):
        return self._sessions.get(session_id or self._active_id)

    def get_active_workspace_session(self):
        return self._sessions.get(self._active_id)

    def get_session_state_slot(
        self, slot: str, *, session_id: str | None = None, default: Any = None
    ):
        session = self._sessions.get(session_id or self._active_id)
        if session is None:
            return default
        return session.state_slots.get(slot, default)

    def get_dispatcher(self) -> FakeGalleryDispatcher:
        return self._dispatcher

    def transact(self, actions: list, *, scope: str = GALLERY_SLOT_NAME) -> None:
        for action in actions or []:
            self._dispatcher.dispatch(action, scope=scope)

    def batch_changes(self):
        return nullcontext()

    def on_change(self, cb) -> None:
        self._change_listeners.append(cb)

    def emit_state_change(self, scope: str = "") -> None:
        self.emitted.append(scope)
        for cb in list(self._change_listeners):
            try:
                cb(scope)
            except Exception:
                pass


def make_gallery_context(session_id: str = "s1") -> tuple[Any, FakeGalleryStore]:
    """Return ``(context, store)`` wiring a controller to a fake Redux store."""
    store = FakeGalleryStore(session_id)
    return SimpleNamespace(store=store), store


def gallery_slot(store: FakeGalleryStore):
    """Read the ``gallery`` slot value for membership assertions via selectors."""
    return store.get_session_state_slot(GALLERY_SLOT_NAME)


def dispatched_kinds(store: FakeGalleryStore) -> list[str]:
    return [type(action).__name__ for action, _scope in store.get_dispatcher().calls]


def dispatched_scopes(store: FakeGalleryStore) -> list[str]:
    return [scope for _action, scope in store.get_dispatcher().calls]


__all__ = [
    "FakeGalleryDispatcher",
    "FakeGallerySession",
    "FakeGalleryStore",
    "dispatched_kinds",
    "dispatched_scopes",
    "gallery_slot",
    "make_gallery_context",
]
