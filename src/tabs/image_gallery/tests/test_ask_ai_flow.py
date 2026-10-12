"""A4 — Ask AI controller flow: async dispatch, cache, generation guard.

Storeless controller doubles (``context=None``), a synchronous fake pool, and
an injected transport (``ask_router.call_sync`` monkeypatched) keep this
headless and network-free. Advisory-only is asserted: rank / best / selection
are untouched by an ask.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from tabs.image_gallery import controller as _ctrl_module
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import ask_router
from tabs.image_gallery.services.ai_settings_store import AiSettings
from tabs.image_gallery.services.ask_context import AskScope


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Sig:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a, **kw):
        for fn in list(self._slots):
            fn(*a, **kw)


class _WidgetStub:
    def __init__(self):
        self.folder_pick_requested = _Sig()
        self.analyze_requested = _Sig()
        self.filter_text_changed = _Sig()
        self.visible_range_changed = _Sig()
        self.opened = []
        self.results = []
        self.errors = []
        self.busy = 0

    def visible_paths(self):
        return []

    def installEventFilter(self, filt):
        pass

    def refresh_card(self, item):
        pass

    def refresh_cards(self, items):
        pass

    def reset_session_view(self):
        pass

    def open_ask_ai(self, anchor, scope, *, default_prompt="Summary", texts=None):
        self.opened.append((anchor, scope, default_prompt))

    def show_ask_ai_busy(self):
        self.busy += 1

    def show_ask_ai_result(self, result, model="", links=None):
        self.results.append(result)

    def show_ask_ai_error(self, message):
        self.errors.append(str(message))


class _Worker:
    def __init__(self, fn, *args, **kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = SimpleNamespace(
            result=_Sig(), finished=_Sig(), error=_Sig()
        )


class _SyncPool:
    def start(self, worker, *a):
        try:
            out = worker.fn(*worker.args, **worker.kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            worker.signals.error.emit((type(exc), exc, None))
            return
        worker.signals.result.emit(out)


class _Store:
    def __init__(self, settings):
        self._settings = settings

    def load(self):
        return self._settings


def _make(monkeypatch, *, settings=None):
    monkeypatch.setattr(_ctrl_module, "GenericWorker", _Worker)
    widget = _WidgetStub()
    ctrl = GalleryController(widget, thread_pool=_SyncPool(), context=None)
    ctrl._ai_settings_store = _Store(
        settings or AiSettings(enabled=True, base_url="http://x", api_key="k", model="m")
    )
    return ctrl, widget


def _install_transport(monkeypatch, reply="Answer.", record=None):
    def fake(base_url, api_key, payload):
        if record is not None:
            record.append(payload)
        return {"choices": [{"message": {"content": reply}}]}

    monkeypatch.setattr(ask_router, "call_sync", fake)


def _item(tmp_path: Path, name="a.png") -> GalleryItem:
    p = tmp_path / name
    p.write_bytes(b"not really an image")
    return GalleryItem(path=p, mtime_ns=1, metrics={"sharpness": 200.0})


def _scope(*items, label="Selection"):
    return AskScope(kind="selection", paths=tuple(it.path for it in items), label=label)


def test_ask_runs_worker_and_shows_result(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    record = []
    _install_transport(monkeypatch, "Looks clean.", record)
    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}

    ctrl.ask_ai_question(_scope(it), "Summary")

    assert len(record) == 1
    assert widget.results and widget.results[-1].text == "Looks clean."
    assert widget.busy == 1


def test_answer_aliases_are_mapped_back_to_filenames(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    _install_transport(monkeypatch, "img_1 looks softer.")
    it = _item(tmp_path, "Archivist Soft.png")
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}

    ctrl.ask_ai_question(_scope(it), "Summary")

    assert widget.results[-1].text == "Archivist Soft.png looks softer."


def test_second_identical_ask_is_served_from_cache(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    record = []
    _install_transport(monkeypatch, "Cached answer.", record)
    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}
    scope = _scope(it)

    ctrl.ask_ai_question(scope, "Summary")
    ctrl.ask_ai_question(scope, "Summary")

    assert len(record) == 1  # second call never hit the transport
    assert widget.results[-1].cached is True
    assert widget.results[-1].text == "Cached answer."


def test_late_answer_dropped_after_folder_switch(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    _install_transport(monkeypatch)
    stale_gen = ctrl._folder_gen
    ctrl._next_folder_gen()

    late = ask_router.AskResult(text="late", backend="text")
    ctrl._on_ask_ai_ready(late, "key-1", stale_gen)

    assert widget.results == []
    assert "key-1" not in ctrl._ask_cache


def test_routing_question_degrades_without_transport_or_cache(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    record = []
    _install_transport(monkeypatch, record=record)
    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}

    ctrl.ask_ai_question(_scope(it), "prioritize this series")

    assert record == []  # Jev stub never reaches the wire
    assert widget.errors and "routing" in widget.errors[-1].lower()
    assert ctrl._ask_cache == {}


def test_not_configured_shows_error_and_no_transport(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(
        monkeypatch, settings=AiSettings(enabled=False, base_url="", api_key="", model="")
    )
    record = []
    _install_transport(monkeypatch, record=record)
    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}

    ctrl.ask_ai_question(_scope(it), "Summary")

    assert record == []
    assert widget.errors


def test_ask_never_mutates_rank_best_or_selection(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    _install_transport(monkeypatch, "Advisory text.")
    it = _item(tmp_path)
    it.rank = 3
    it.is_best = False
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}
    selection_before = set(ctrl.state.selected_paths)

    ctrl.ask_ai_question(_scope(it), "Summary")

    assert it.rank == 3
    assert it.is_best is False
    assert ctrl.state.selected_paths == selection_before


def test_open_ask_ai_resolves_selection_scope(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}

    ctrl.open_ask_ai("selection", None, it.path)

    assert widget.opened
    _anchor, scope, _default = widget.opened[-1]
    assert scope.kind == "selection"
    assert scope.paths == (it.path,)
    # No generic "Selection" scope line in the flyout (ask_context still
    # derives "Selection" for the model when the label is empty).
    assert scope.label == ""

    # A card ask keeps the filename as its scope line.
    ctrl.open_ask_ai("card", None, it.path)
    _anchor, scope_card, _default = widget.opened[-1]
    assert scope_card.label == it.path.name


def test_open_ask_ai_for_series_uses_series_scope(monkeypatch, tmp_path, qapp):
    ctrl, widget = _make(monkeypatch)
    a = _item(tmp_path, "1.png")
    b = _item(tmp_path, "2.png")

    ctrl.open_ask_ai_for_series(0, None, (a.path, b.path), "My Series")

    _anchor, scope, _default = widget.opened[-1]
    assert scope.kind == "series"
    # No series name on the surface (the anchor header already labels it).
    assert scope.label == ""
    assert set(scope.paths) == {a.path, b.path}
