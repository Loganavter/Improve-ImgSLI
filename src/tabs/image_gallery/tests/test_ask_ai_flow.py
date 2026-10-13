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
        self.grow_up = []
        self.toggles = []
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

    def open_ask_ai(self, anchor, scope, *, default_prompt="Summary", texts=None, grow_up=False, show_images_toggle=True):
        self.opened.append((anchor, scope, default_prompt))
        self.grow_up.append(bool(grow_up))
        self.toggles.append(bool(show_images_toggle))

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


def test_open_ask_ai_region_opens_upward_with_region_scope(monkeypatch, tmp_path, qapp):
    """A Quick Look region selection opens the flyout upward with a region scope."""
    ctrl, widget = _make(monkeypatch)
    it = _item(tmp_path)
    ctrl.state.items = [it]

    ctrl.open_ask_ai_region(it.path, (0.1, 0.1, 0.5, 0.5), anchor=object())

    assert widget.opened, "region ask should open the flyout"
    _anchor, scope, _prompt = widget.opened[-1]
    assert scope.kind == "region"
    assert tuple(scope.box) == (0.1, 0.1, 0.5, 0.5)
    assert str(scope.paths[0]) == str(it.path)
    assert widget.grow_up[-1] is True


def test_open_ask_ai_region_dismisses_band_on_flyout_hide(monkeypatch, tmp_path, qapp):
    """The held selection clears only when the region flyout closes.

    Falsification: pre-change no slot is wired to ``flyout.hidden``.
    """
    from types import SimpleNamespace

    from PySide6.QtCore import QObject, Signal

    class _Flyout(QObject):
        hidden = Signal()

    ctrl, widget = _make(monkeypatch)
    flyout = _Flyout()
    widget._ensure_ask_ai_flyout = lambda: flyout
    dismissed: list[bool] = []
    band = SimpleNamespace(dismiss_selection=lambda: dismissed.append(True))

    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.open_ask_ai_region(it.path, (0.1, 0.1, 0.5, 0.5), anchor=band)

    assert widget.opened, "region ask should open the flyout"
    assert dismissed == [], "band must stay visible while the flyout is open"
    flyout.hidden.emit()
    assert dismissed == [True]
    flyout.hidden.emit()
    assert dismissed == [True], "dismiss slot is one-shot"


def test_open_ask_ai_region_hides_images_toggle(monkeypatch, tmp_path, qapp):
    """Region scope always sends the images: the toggle is not offered.

    Falsification: pre-change the flag is never threaded (stub default).
    """
    from types import SimpleNamespace

    from PySide6.QtCore import QObject, Signal

    class _Flyout(QObject):
        hidden = Signal()

    ctrl, widget = _make(monkeypatch)
    flyout = _Flyout()
    widget._ensure_ask_ai_flyout = lambda: flyout
    dismissed: list[bool] = []
    band = SimpleNamespace(
        dismiss_selection=lambda: dismissed.append(True), selection_id=7
    )

    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.open_ask_ai_region(it.path, (0.1, 0.1, 0.5, 0.5), anchor=band)

    assert widget.opened, "region ask should open the flyout"
    assert widget.toggles[-1] is False
    flyout.hidden.emit()
    assert dismissed == [True], "matching generation still dismisses"


def test_region_dismiss_slot_skips_superseded_selection(monkeypatch, tmp_path, qapp):
    """A newer marquee supersedes the armed dismissal (one-gesture reselect).

    The close ending the old flyout session must not wipe the selection the
    dismissing press-drag just started.

    Falsification: pre-change the hidden slot dismisses unconditionally.
    """
    from PySide6.QtCore import QObject, QRect, Signal
    from PySide6.QtWidgets import QWidget

    from tabs.image_gallery.ui.quick_look.region import RegionBand

    class _Flyout(QObject):
        hidden = Signal()

    ctrl, widget = _make(monkeypatch)
    flyout = _Flyout()
    widget._ensure_ask_ai_flyout = lambda: flyout

    host = QWidget()
    band = RegionBand(host)
    band.setGeometry(0, 0, 200, 200)
    band.set_band(QRect(10, 10, 50, 40))
    band.show()
    gen = band.begin_selection()

    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.open_ask_ai_region(it.path, (0.1, 0.1, 0.5, 0.5), anchor=band)

    # A newer marquee starts before the old flyout session closes.
    band.set_band(QRect(60, 60, 40, 40))
    band.show()
    band.begin_selection()
    assert band.selection_id == gen + 1
    flyout.hidden.emit()
    assert not band.isHidden(), "superseded dismissal must spare the new selection"

    # A clean close of the current session still dismisses.
    ctrl.open_ask_ai_region(it.path, (0.2, 0.2, 0.6, 0.6), anchor=band)
    flyout.hidden.emit()
    assert band.isHidden()


def test_region_ask_sends_crop_and_region_prompt(monkeypatch, tmp_path, qapp):
    """Region asks force vision, use the region prompt and append the crop."""
    ctrl, widget = _make(monkeypatch)
    record = []
    _install_transport(monkeypatch, '{"answer": "ok", "confidence": "high"}', record)
    it = _item(tmp_path)
    ctrl.state.items = [it]
    ctrl.state.selected_paths = {it.path}

    from tabs.image_gallery.services import vlm as _vlm

    monkeypatch.setattr(_vlm, "encode_region", lambda path, box: ("png", "QUJD"))
    scope = AskScope(kind="region", paths=(it.path,), box=(0.1, 0.1, 0.5, 0.5))

    ctrl.ask_ai_question(scope, "What is wrong?")

    assert len(record) == 1, "region ask must reach the transport"
    messages = record[0]["messages"]
    from tabs.image_gallery.services.ask_prompt import (
        ASK_REGION_SYSTEM_PROMPT,
        ASK_SYSTEM_PROMPT,
    )

    system_text = messages[0]["content"][0]["text"]
    assert system_text == ASK_REGION_SYSTEM_PROMPT
    assert system_text != ASK_SYSTEM_PROMPT

    user_content = messages[-1]["content"]
    assert any(
        c.get("type") == "image_url" for c in user_content
    )
    assert any("SELECTED REGION" in str(c.get("text", "")) for c in user_content)
    # Full downscaled image + the region crop.
    assert sum(1 for c in user_content if c.get("type") == "image_url") >= 2
