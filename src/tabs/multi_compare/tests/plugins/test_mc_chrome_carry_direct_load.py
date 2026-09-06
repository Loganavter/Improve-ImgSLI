"""Multi Compare chrome/carry/paste drops load directly like IC (P3A).

``tab.handle_drop``, the ``begin_pending_image_insert`` service and
``controller.begin_paste_placement`` must NOT arm ``begin_pending_paste``
(highlight + click-to-place + ``Esc`` cancel). Instead they auto-place
through the P2 async path (``load_external_paths`` → ``on_images_dropped``
→ ``load_preview_async``): imageless slot + loading toast synchronously,
preview worker queued, no armed pending state.

P7: ``tab.handle_drop`` additionally defers that direct load one tick past
the window ``acceptProposedAction`` (no slot/toast/stat before accept), so
these tests pump the event loop after the call.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QImage

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.tab import MultiCompareTab
from tabs.multi_compare.use_cases import placement as placement_use_cases


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown: list = []
        self.updated: list = []
        self.closed: list = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _CapturingPool:
    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)

    def run_one(self) -> None:
        self.workers.pop(0).run()


class _FakeMcStore:
    """Dispatch-only mutation through the real pure reducer (STORE invariants)."""

    def __init__(self):
        self.state = MultiCompareState()
        self.dispatched: list = []

    def dispatch(self, action):
        self.dispatched.append(action)
        self.state = mc_reduce(self.state, action)


class _FakeWidget:
    def __init__(self, mc_store):
        self.store = mc_store
        self.canvas = SimpleNamespace(request_view_update=lambda: None)
        self.images_dropped = SimpleNamespace(connect=lambda *_: None)
        self.add_requested = SimpleNamespace(connect=lambda *_: None)
        self.save_requested = SimpleNamespace(connect=lambda *_: None)
        self.quick_save_requested = SimpleNamespace(connect=lambda *_: None)
        self.settings_requested = SimpleNamespace(connect=lambda *_: None)
        self.help_requested = SimpleNamespace(connect=lambda *_: None)
        self.divider_color_picker_requested = SimpleNamespace(connect=lambda *_: None)
        # Pending-placement fields the real widget owns; P3A must leave them clear.
        self._pending_paste_paths = None
        self._pending_duplicate_source = None

    @property
    def state(self):
        return self.store.state

    def add_image_auto(self, path, label=""):
        return placement_use_cases.add_image_auto(self, path, label)

    def add_image_at(self, path, label, target_path, side, target_root):
        return placement_use_cases.add_image_at(
            self, path, label, target_path, side, target_root
        )


def _make_tab(pool):
    mc_store = _FakeMcStore()
    widget = _FakeWidget(mc_store)
    toast_manager = _FakeToastManager()
    emitted: list = []
    event_bus = SimpleNamespace(
        emitted=emitted,
        emit=lambda e: emitted.append(e),
        subscribe=lambda *a, **k: None,
    )
    context = SimpleNamespace(
        main_window=SimpleNamespace(toast_manager=toast_manager),
        thread_pool=pool,
        event_bus=event_bus,
    )
    store = SimpleNamespace(settings=SimpleNamespace(auto_crop_black_borders=False))
    controller = MultiCompareController(widget, store=store, context=context)
    tab = MultiCompareTab()
    tab._widget = widget
    tab._controller = controller
    return tab, controller, widget, mc_store, toast_manager, pool


def _pump(qapp, rounds: int = 5) -> None:
    """Flush QTimer.singleShot(0) chains (P7 deferred loads)."""
    for _ in range(rounds):
        qapp.processEvents()


def _png(tmp_path, name="img.png", size=(800, 600)):
    path = tmp_path / name
    Image.new("RGB", size, (10, 120, 200)).save(path)
    return path


def _assert_direct_loaded(tab_bundle, path, *, workers=1):
    _, controller, widget, _, toast_manager, pool = tab_bundle
    assert len(widget.state.slots) == 1
    slot = widget.state.slots[0]
    assert slot.path == path
    from tabs.multi_compare.pipeline.cache import resolve_slot_source

    assert resolve_slot_source(controller.pixel_cache, slot) is None  # imageless until the worker lands
    assert len(toast_manager.shown) == 1  # IC-like loading feedback, no click needed
    assert len(pool.workers) == workers  # preview worker queued, nothing decoded inline
    # No armed pending state: nothing for Esc/click to cancel.
    assert widget._pending_paste_paths is None
    assert widget._pending_duplicate_source is None
    from tabs.multi_compare.ui import drag_drop as _drag_drop

    assert _drag_drop.has_pending_placement(widget) is False


def test_handle_drop_loads_directly_without_arming(qapp, tmp_path):
    """Window-chrome route_drop → tab.handle_drop: slot + worker, no pending.

    P7: the load is deferred one tick past the window accept (busy-cursor
    fix), so the call itself only validates + schedules; pump to observe
    the P3A direct-load shape (slot + toast + worker, nothing armed)."""
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    tab, _, widget, _, _, _ = bundle
    path = _png(tmp_path)

    tab.handle_drop([path], hint={"slot": 2})

    assert widget.state.slots == []  # nothing synchronous before accept
    _pump(qapp)
    _assert_direct_loaded(bundle, path)


def test_handle_drop_ignores_non_images(tmp_path):
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    tab, _, widget, _, toast_manager, _ = bundle

    tab.handle_drop([tmp_path / "notes.txt"], hint=None)

    assert widget.state.slots == []
    assert toast_manager.shown == []
    assert widget._pending_paste_paths is None


def test_begin_pending_image_insert_service_loads_directly(tmp_path):
    """Carry route: service loads, no begin_pending_paste arming."""
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    tab, _, _, _, _, _ = bundle
    path = _png(tmp_path)

    started = tab.create_service("begin_pending_image_insert", [path])

    assert started is True
    _assert_direct_loaded(bundle, path)
    # Worker still lands through the P2 path (preview tier).
    pool.run_one()
    from tabs.multi_compare.pipeline.cache import resolve_slot_source as _resolve

    assert isinstance(_resolve(bundle[1].pixel_cache, bundle[2].state.slots[0]), QImage)


def test_begin_pending_image_insert_rejects_non_images(tmp_path):
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    tab, _, widget, _, _, _ = bundle

    assert tab.create_service("begin_pending_image_insert", [tmp_path / "x.txt"]) is False
    assert tab.create_service("begin_pending_image_insert", None) is False
    assert widget.state.slots == []
    assert widget._pending_paste_paths is None


def test_begin_paste_placement_loads_directly(tmp_path):
    """Clipboard paste entry: immediate load, no cursor-tracked highlight."""
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    _, controller, _, _, _, _ = bundle
    path = _png(tmp_path)

    controller.begin_paste_placement([path])

    _assert_direct_loaded(bundle, path)


def test_chrome_drop_chains_multiple_files(qapp, tmp_path):
    """Each file gets its own slot + toast + worker (adjacent chaining)."""
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    tab, _, widget, _, toast_manager, _ = bundle
    paths = [_png(tmp_path, f"{c}.png") for c in "abc"]

    tab.handle_drop(paths, hint=None)

    _pump(qapp)
    assert [s.path for s in widget.state.slots] == paths
    from tabs.multi_compare.pipeline.cache import resolve_slot_source as _resolve2

    assert all(
        _resolve2(bundle[1].pixel_cache, s) is None for s in widget.state.slots
    )
    assert len(toast_manager.shown) == 3
    assert len(pool.workers) == 3
    assert widget._pending_paste_paths is None


def test_missing_file_skipped_without_slot(qapp, tmp_path):
    """is_file filter (begin_pending_paste parity): no slot, no worker."""
    pool = _CapturingPool()
    bundle = _make_tab(pool)
    tab, _, widget, _, toast_manager, _ = bundle

    tab.handle_drop([tmp_path / "gone.png"], hint=None)

    _pump(qapp)
    assert widget.state.slots == []
    assert toast_manager.shown == []
    assert pool.workers == []
