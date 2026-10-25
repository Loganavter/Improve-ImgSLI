"""IC tab P2 hygiene bundle (task-fix-ic-tab-p2-2026-09-20).

Covers:
* rating/rename route via dispatcher (``SetImageListAction`` scope
  ``"document"``) — items replaced, never mutated in place; changed-guard
  dispatches nothing on identical values; fail-open legacy path (no
  dispatcher) still mutates + raw-emits.
* ``get_current_display_name`` is a pure read; pinning is explicit via
  ``remember_current_display_name`` (write moved out of the getter).
* ``SessionDataReducer`` with ``render_cache=None`` logs and still reduces
  the image state instead of dropping image actions.
* context-menu ``execute`` is fail-closed on unresolvable slot/list refs.
* ``open_image_dialog`` pins ``sessions`` across the 100ms dialog defer.
* toolbar ``connections``: every ``.connect`` routes via ``_track``
  (pairing test) and ``disconnect_signals`` drops exactly those.

Headless-safe: no real dialogs/widgets; ``qapp`` fixture is a safety net.
"""

from __future__ import annotations

import ast
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.state_management.actions import SetImageSessionImageAction
from core.state_management.document_actions import SetImageListAction
from tabs.image_compare.services.playlist_components.metadata import (
    PlaylistMetadataController,
)
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.reducer import DocumentReducer
from tabs.image_compare.state.reducers import SessionDataReducer
from tabs.image_compare.ui.context_menu import ImageCompareContextMenuProvider
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget
from core.log_names import APP_LOGGER_NAME


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------


class _Session:
    def __init__(self, session_id: str, *, document=None):
        self.id = session_id
        self.session_type = "image_compare"
        self.document = document
        self.viewport = None
        self.state_slots: dict = {}


class _RecordingDispatcher:
    """Fake dispatcher applying the real DocumentReducer (no Qt needed)."""

    def __init__(self, store):
        self._store = store
        self.calls: list = []

    def dispatch(self, action, scope: str = "viewport") -> None:
        session = self._store.get_workspace_session(self._store._active_id)
        self.calls.append((action, scope))
        if scope == "document" and session is not None:
            session.document = DocumentReducer.reduce(session.document, action)
            self._store.emit_state_change(scope)


class _Store:
    def __init__(self, sessions: dict | None = None, *, with_dispatcher: bool = False):
        self._sessions = sessions or {}
        self._active_id = next(iter(self._sessions), "s1")
        self.emitted: list = []
        self._dispatcher = _RecordingDispatcher(self) if with_dispatcher else None

    def get_workspace_session(self, session_id):
        return self._sessions.get(session_id)

    def get_session_state_slot(self, slot, *, session_id=None, default=None):
        session = self._sessions.get(session_id or self._active_id)
        if session is None:
            return default
        if slot == "document":
            return session.document
        return session.state_slots.get(slot, default)

    def get_dispatcher(self):
        return self._dispatcher

    def batch_changes(self):
        return nullcontext()

    def emit_state_change(self, scope: str = "") -> None:
        self.emitted.append(scope)

    @property
    def state_changed(self):
        store = self

        class _Sig:
            def emit(self, scope=""):
                store.emitted.append(scope)

        return _Sig()


def _doc() -> DocumentModel:
    return DocumentModel(
        image_list1=[
            ImageItem(path="/a/b.png", display_name="b", rating=2),
            ImageItem(path="/a/c.png", display_name="c", rating=0),
        ],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )


def _metadata(document, *, with_dispatcher: bool):
    session = _Session("s1", document=document)
    store = _Store({"s1": session}, with_dispatcher=with_dispatcher)
    return PlaylistMetadataController(store, None), store, session


# --------------------------------------------------------------------------
# rating / rename via dispatcher
# --------------------------------------------------------------------------


def test_set_rating_dispatches_replace_not_mutate(qapp):
    meta, store, session = _metadata(_doc(), with_dispatcher=True)
    old_item = session.document.image_list1[0]
    old_list = session.document.image_list1

    meta.set_rating(1, 0, 5)

    assert len(store._dispatcher.calls) == 1
    action, scope = store._dispatcher.calls[0]
    assert isinstance(action, SetImageListAction)
    assert scope == "document"
    # CONTENT IDENTITY: same paths/order, only the rating changed ...
    assert [i.path for i in session.document.image_list1] == ["/a/b.png", "/a/c.png"]
    assert session.document.image_list1[0].rating == 5
    # ... via replace, never in-place: old objects untouched.
    assert old_item.rating == 2
    assert session.document.image_list1 is not old_list
    assert session.document.image_list1[0] is not old_item


def test_set_rating_changed_guard_dispatches_nothing(qapp):
    meta, store, session = _metadata(_doc(), with_dispatcher=True)
    meta.set_rating(1, 0, 2)
    assert store._dispatcher.calls == []


def test_set_rating_out_of_range_is_noop(qapp):
    meta, store, session = _metadata(_doc(), with_dispatcher=True)
    meta.set_rating(1, 9, 5)
    assert store._dispatcher.calls == []
    assert [i.rating for i in session.document.image_list1] == [2, 0]


def test_rating_fail_open_without_dispatcher(qapp):
    meta, store, session = _metadata(_doc(), with_dispatcher=False)
    meta.increment_rating(1, 1)
    assert session.document.image_list1[1].rating == 1
    assert "document" in store.emitted


def test_rename_dispatches_and_pins_display_name(qapp, monkeypatch):
    from PySide6.QtCore import QTimer

    monkeypatch.setattr(QTimer, "singleShot", lambda *a, **k: None)
    meta, store, session = _metadata(_doc(), with_dispatcher=True)
    old_item = session.document.image_list1[0]

    meta.rename_image_at_index(1, 0, "renamed")

    assert len(store._dispatcher.calls) == 1
    assert session.document.image_list1[0].display_name == "renamed"
    assert old_item.display_name == "b"
    assert session.document._last_display_name1 == "renamed"


def test_rename_changed_guard_schedules_nothing(qapp, monkeypatch):
    from PySide6.QtCore import QTimer

    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda *a: scheduled.append(a))
    meta, store, session = _metadata(_doc(), with_dispatcher=True)
    meta.rename_image_at_index(1, 0, "b")
    assert store._dispatcher.calls == []
    assert scheduled == []


def test_on_edit_name_changed_dispatches(qapp):
    meta, store, session = _metadata(_doc(), with_dispatcher=True)
    meta.on_edit_name_changed(1, "  new-name  ")
    assert len(store._dispatcher.calls) == 1
    assert session.document.image_list1[0].display_name == "new-name"


# --------------------------------------------------------------------------
# pure getter + explicit pin
# --------------------------------------------------------------------------


def test_get_current_display_name_is_pure_read():
    doc = _doc()
    assert doc.get_current_display_name(1) == "b"
    assert doc._last_display_name1 == ""
    assert doc.get_current_display_name(1) == "b"
    assert doc._last_display_name1 == ""


def test_remember_pins_and_fallback_survives_clear():
    doc = _doc()
    assert doc.remember_current_display_name(1) == "b"
    assert doc._last_display_name1 == "b"
    doc.image_list1 = []
    doc.current_index1 = -1
    assert doc.get_current_display_name(1) == "b"
    assert doc.get_active_display_name(1) == ""


# --------------------------------------------------------------------------
# SessionDataReducer: log + reduce when render_cache is None
# --------------------------------------------------------------------------


def test_session_data_reducer_reduces_image_without_render_cache(caplog):
    from core.store_viewport import SessionData
    from tabs.image_compare.state.models import ImageSessionState

    import logging

    reducer = SessionDataReducer()
    data = SessionData(image_state=ImageSessionState(), render_cache=None)
    with caplog.at_level(logging.WARNING, logger=f"{APP_LOGGER_NAME}.session_data"):
        out = reducer.reduce(data, SetImageSessionImageAction(slot=1, image=object()))
    assert out is not data
    assert out.image_state.image1 is not None
    assert out.render_cache is None
    assert any("render_cache is None" in r.message for r in caplog.records)


def test_session_data_reducer_noop_stays_identical(caplog):
    from core.state_management.actions import SetLanguageAction
    from core.store_viewport import SessionData
    from tabs.image_compare.state.models import ImageSessionState

    reducer = SessionDataReducer()
    data = SessionData(image_state=ImageSessionState(), render_cache=None)
    out = reducer.reduce(data, SetLanguageAction(language="en"))
    assert out is data


# --------------------------------------------------------------------------
# context menu fail-closed
# --------------------------------------------------------------------------


def _menu_request(kind, ref_id):
    from PySide6.QtCore import QPoint

    return ContextMenuRequest(
        source_widget=object(),
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="image_compare",
        target=ContextMenuTarget(kind=kind, id=ref_id, payload={}),
    )


def test_execute_unresolvable_slot_is_not_handled(qapp):
    session = _Session("s1", document=_doc())
    store = _Store({"s1": session}, with_dispatcher=True)
    provider = ImageCompareContextMenuProvider(
        canvas=object(), store=store, flyout=None
    )
    req = _menu_request("image_compare_slot", 99)
    assert provider.execute("image_compare.copy_path", req, 99) is False


def test_execute_unresolvable_list_ref_is_not_handled(qapp):
    session = _Session("s1", document=_doc())
    store = _Store({"s1": session}, with_dispatcher=True)
    provider = ImageCompareContextMenuProvider(
        canvas=object(), store=store, flyout=None
    )
    req = _menu_request("image_compare_list_item", None)
    assert provider.execute("image_compare.remove_list_item", req, None) is False


# --------------------------------------------------------------------------
# open_image_dialog pins sessions across the defer
# --------------------------------------------------------------------------


def test_open_image_dialog_pins_sessions(qapp, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog

    from tabs.image_compare.presenters.toolbar import actions as toolbar_actions

    captured: dict = {}
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda *a, **k: (["/x/a.png"], "")
    )
    monkeypatch.setattr(
        QTimer, "singleShot", lambda delay, fn: captured.setdefault("fn", fn)
    )

    pinned = SimpleNamespace(
        loads=[],
        load_images_from_paths=lambda paths, slot: pinned.loads.append((paths, slot)),
    )
    replaced = SimpleNamespace(
        loads=[],
        load_images_from_paths=lambda paths, slot: replaced.loads.append((paths, slot)),
    )
    main_controller = SimpleNamespace(sessions=pinned)
    presenter = SimpleNamespace(
        store=SimpleNamespace(
            settings=SimpleNamespace(export_default_dir="", current_language="en")
        ),
        main_window_app=None,
        main_controller=main_controller,
        _first_dialog_load_pending=True,
    )

    toolbar_actions.open_image_dialog(presenter, 1)
    # Session rebound before the deferred lambda fires ...
    main_controller.sessions = replaced
    captured["fn"]()

    assert pinned.loads == [(["/x/a.png"], 1)]
    assert replaced.loads == []


# --------------------------------------------------------------------------
# toolbar connections pairing + disconnect mirror
# --------------------------------------------------------------------------


def test_toolbar_connections_all_route_via_track():
    path = (
        Path(__file__).resolve().parents[2]
        / "presenters"
        / "toolbar"
        / "connections.py"
    )
    tree = ast.parse(path.read_text())
    offenders: list = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self):
            self._func: list = []

        def visit_FunctionDef(self, node):
            self._func.append(node.name)
            self.generic_visit(node)
            self._func.pop()

        def visit_Attribute(self, node):
            if node.attr == "connect" and self._func != ["_track"]:
                offenders.append((self._func[-1] if self._func else "?", node.lineno))
            self.generic_visit(node)

    _Visitor().visit(tree)
    assert offenders == [], f"bare .connect() outside _track: {offenders}"


def test_disconnect_signals_drops_tracked(qapp):
    from PySide6.QtCore import QObject, Signal

    from tabs.image_compare.presenters.toolbar import connections as conns

    class _Emitter(QObject):
        fired = Signal()

    emitter = _Emitter()
    calls: list = []
    presenter = SimpleNamespace()
    conns._track(presenter, emitter.fired, lambda: calls.append(1))
    assert len(getattr(presenter, "_ic_toolbar_conns")) == 1
    emitter.fired.emit()
    assert calls == [1]

    dropped = conns.disconnect_signals(presenter)
    assert dropped == 1
    emitter.fired.emit()
    assert calls == [1]
    # Idempotent: second call is a no-op.
    assert conns.disconnect_signals(presenter) == 0
