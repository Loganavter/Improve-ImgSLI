"""Multi Compare drop wait-cursor regression (P7).

The Wayland drag source shows busy/waiting until Qt's
``wl_data_offer.finish()`` fires, which happens after ``dropEvent``
returns. So the drop handler must accept FIRST on a cheap verdict
(suffix-only, no resolve/dispatch/stat/emit) and defer everything else
past the return — mirroring image_compare's hide→accept→``singleShot``
shape (``window_event_handler.py:186-192,241``).

Covered headless with fakes (live cursor check stays manual — see below):

- accept precedes resolve/dispatch/emit on the canvas path, and the full
  chain (drop → emit → controller → worker start) only starts workers
  after accept;
- ignored drops never accept and schedule nothing;
- internal-drag echo stays synchronous and byte-identical (Move action,
  ``apply_internal_drop`` untouched).

Live verification (for a human, Wayland+Mutter):
``IMGSLI_MC_DEBUG=1`` → single-file DnD onto the canvas → no busy cursor;
log shows ``drop external accept-first`` with ``accept_ms`` < 1 frame
(~16ms) and ``drop → finish`` ms-scale.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QPoint, Qt

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.ui import drag_drop
from tabs.multi_compare.ui.canvas_widget import INTERNAL_SLOT_MIME
from tabs.multi_compare.use_cases import placement as placement_use_cases


def _pump(qapp, rounds: int = 10) -> None:
    for _ in range(rounds):
        qapp.processEvents()


def _png(tmp_path, name="img.png"):
    path = tmp_path / name
    Image.new("RGB", (800, 600), (10, 120, 200)).save(path)
    return path


def _url(path):
    return SimpleNamespace(toLocalFile=lambda: str(path))


def _external_mime(urls):
    return SimpleNamespace(
        hasUrls=lambda: bool(urls),
        hasFormat=lambda fmt: False,
        urls=lambda: list(urls),
    )


def _recording_event(mime, *, pos=None):
    calls: list[str] = []
    pos = pos if pos is not None else QPoint(10, 10)
    return (
        SimpleNamespace(
            position=lambda: SimpleNamespace(toPoint=lambda: pos),
            mimeData=lambda: mime,
            acceptProposedAction=lambda: calls.append("accept"),
            setDropAction=lambda action: calls.append(("drop_action", action)),
            accept=lambda: calls.append("accept"),
            ignore=lambda: calls.append("ignore"),
        ),
        calls,
    )


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown: list = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, *a, **k):
        pass

    def close_toast(self, *a, **k):
        pass


class _CapturingPool:
    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)


class _FakeMcStore:
    """Dispatch-only mutation through the real pure reducer (STORE invariants)."""

    def __init__(self):
        self.state = MultiCompareState()
        self.dispatched: list = []

    def dispatch(self, action):
        self.dispatched.append(action)
        self.state = mc_reduce(self.state, action)


class _FakeWidget:
    """Canvas-path widget: Qt-like signal that synchronously delivers
    (like a direct connection), so the full drop → controller chain is
    observable without a real event loop for delivery."""

    def __init__(self, mc_store, controller_holder: dict):
        self.store = mc_store
        self._holder = controller_holder
        self.resolve_calls: list = []
        self.emitted: list = []
        self.canvas = SimpleNamespace(
            mapFrom=lambda w, p: p,
            compute_drop_target=self._compute,
            request_view_update=lambda: None,
            _leaf_paths_and_rects=lambda: [],
        )
        self._pending_duplicate_source = None
        self._pending_paste_paths = None

        def _connect(cb):
            self._holder["cb"] = cb

        self.images_dropped = SimpleNamespace(
            connect=_connect, emit=self._emit
        )
        self.add_requested = SimpleNamespace(connect=lambda *_: None)
        self.save_requested = SimpleNamespace(connect=lambda *_: None)
        self.quick_save_requested = SimpleNamespace(connect=lambda *_: None)
        self.settings_requested = SimpleNamespace(connect=lambda *_: None)
        self.help_requested = SimpleNamespace(connect=lambda *_: None)
        self.divider_color_picker_requested = SimpleNamespace(
            connect=lambda *_: None
        )

    @property
    def state(self):
        return self.store.state

    def _compute(self, pos, include_center=False):
        self.resolve_calls.append(pos)
        return (None, None, True, None)  # empty canvas: whole widget is zone

    def _emit(self, paths, target, side):
        self.emitted.append((list(paths), target, side))
        cb = self._holder.get("cb")
        if cb is not None:
            cb(list(paths), target, side)

    def add_image_auto(self, path, image, label=""):
        return placement_use_cases.add_image_auto(self, path, image, label)

    def add_image_at(self, path, image, label, target_path, side, target_root):
        return placement_use_cases.add_image_at(
            self, path, image, label, target_path, side, target_root
        )


def _make_chain(pool):
    holder: dict = {}
    mc_store = _FakeMcStore()
    widget = _FakeWidget(mc_store, holder)
    toast_manager = _FakeToastManager()
    context = SimpleNamespace(
        main_window=SimpleNamespace(toast_manager=toast_manager),
        thread_pool=pool,
        event_bus=SimpleNamespace(
            emit=lambda e: None, subscribe=lambda *a, **k: None
        ),
    )
    store = SimpleNamespace(settings=SimpleNamespace(auto_crop_black_borders=False))
    controller = MultiCompareController(widget, store=store, context=context)
    return controller, widget, mc_store, toast_manager


def test_drop_accepts_before_any_gui_work(qapp, tmp_path):
    """accept() lands inside dropEvent; resolve/dispatch/emit only after."""
    pool = _CapturingPool()
    _, widget, mc_store, _ = _make_chain(pool)
    path = _png(tmp_path)
    event, calls = _recording_event(_external_mime([_url(path)]))

    drag_drop.drop_event(widget, event)

    assert calls == ["accept"]  # returned past accept with nothing else done
    assert widget.resolve_calls == []
    assert mc_store.dispatched == []
    assert widget.emitted == []
    assert pool.workers == []

    _pump(qapp)

    assert len(widget.resolve_calls) == 1  # deferred resolve ran
    assert any(
        type(a).__name__ == "SetDragState" for a in mc_store.dispatched
    )
    assert len(widget.emitted) == 1  # deferred emit ran
    assert [p for (ps, _, _) in widget.emitted for p in ps] == [path]
    assert len(pool.workers) == 1  # preview worker queued, never decoded inline


def test_drop_ignored_schedules_nothing(qapp, tmp_path):
    """Non-image drop: ignore(), no accept, nothing deferred."""
    pool = _CapturingPool()
    _, widget, mc_store, _ = _make_chain(pool)
    event, calls = _recording_event(
        _external_mime([_url(tmp_path / "notes.txt")])
    )

    drag_drop.drop_event(widget, event)

    assert calls == ["ignore"]
    _pump(qapp)
    assert widget.resolve_calls == []
    assert mc_store.dispatched == []
    assert widget.emitted == []
    assert pool.workers == []


def test_internal_drop_stays_synchronous(qapp):
    """Internal Move echo byte-identical: sync accept + move dispatch."""

    mc_store = _FakeMcStore()
    holder: dict = {}
    widget = _FakeWidget(mc_store, holder)
    # Two slots so the move has somewhere to go: anchor != source.
    placement_use_cases.add_image_auto(widget, Path("a.png"), None, "a")
    placement_use_cases.add_image_auto(widget, Path("b.png"), None, "b")
    n_before = len(mc_store.dispatched)
    mime = SimpleNamespace(
        hasUrls=lambda: False,
        hasFormat=lambda fmt: fmt == INTERNAL_SLOT_MIME,
        urls=lambda: [],
        data=lambda fmt: b"0",
    )
    event, calls = _recording_event(mime)

    drag_drop.drop_event(widget, event)

    assert calls == ["accept"]  # Move echo preserved, synchronously
    # move/swap dispatch happened inline (apply_internal_drop untouched)
    assert len(mc_store.dispatched) > n_before
    _pump(qapp)  # no deferred external work may appear
    assert widget.emitted == []
    assert widget.resolve_calls != []  # internal resolve stays synchronous


def test_tab_handle_drop_returns_before_slot(qapp, tmp_path):
    """Chrome path: handle_drop validates synchronously, loads past accept."""
    from tabs.multi_compare.tab import MultiCompareTab

    pool = _CapturingPool()
    controller, widget, _, toast_manager = _make_chain(pool)
    tab = MultiCompareTab()
    tab._widget = widget
    tab._controller = controller
    path = _png(tmp_path)

    tab.handle_drop([path], hint=None)

    assert widget.state.slots == []  # nothing before the window accept
    _pump(qapp)
    assert len(widget.state.slots) == 1
    assert widget.state.slots[0].path == path
    assert widget.state.slots[0].image is None  # imageless until worker lands
    assert len(toast_manager.shown) == 1
    assert len(pool.workers) == 1


def test_copy_action_forced_on_external_enter(qapp, tmp_path):
    """Enter still forces Copy (regression anchor for the accept bytes)."""
    mc_store = _FakeMcStore()
    widget = _FakeWidget(mc_store, {})
    path = _png(tmp_path)
    event, calls = _recording_event(_external_mime([_url(path)]))
    widget._dnd_gen = 0

    drag_drop.drag_enter_event(widget, event)
    _pump(qapp)

    assert ("drop_action", Qt.DropAction.CopyAction) in calls
    assert "accept" in calls
