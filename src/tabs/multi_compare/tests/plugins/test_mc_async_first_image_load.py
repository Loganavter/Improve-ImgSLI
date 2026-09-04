"""Multi Compare first-image DnD must not decode on the GUI thread (P2).

``on_images_dropped`` only does placement + imageless slot creation
synchronously; the bounded preview decodes in a ``GenericWorker`` and fills
the slot via ``replace_slot_image`` on result (IC ``ensure_async`` parity),
with full-res as the second stage. A failed load removes its pre-created
slot (sync-UX parity: the old path skipped slot creation on failure).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QImage

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.use_cases import loading as loading_use_cases
from tabs.multi_compare.use_cases import placement as placement_use_cases
from tabs.multi_compare.use_cases import preview_decode as preview_decode_use_cases


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown: list[tuple[int, str, dict]] = []
        self.updated: list[tuple[int, str, dict]] = []
        self.closed: list[int] = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _CapturingPool:
    """Holds GenericWorkers instead of running them — the test drains the
    queue explicitly, so GUI-thread work and worker work stay observable
    as separate phases."""

    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)

    def run_one(self) -> None:
        self.workers.pop(0).run()

    def run_all(self, limit: int = 20) -> None:
        for _ in range(limit):
            if not self.workers:
                return
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

    @property
    def state(self):
        return self.store.state

    def add_image_auto(self, path, image, label=""):
        return placement_use_cases.add_image_auto(self, path, image, label)

    def add_image_at(self, path, image, label, target_path, side, target_root):
        return placement_use_cases.add_image_at(
            self, path, image, label, target_path, side, target_root
        )


def _make_controller(pool):
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
    return controller, widget, mc_store, toast_manager, event_bus


def _png(tmp_path, name="img.png", size=(800, 600)):
    path = tmp_path / name
    Image.new("RGB", size, (10, 120, 200)).save(path)
    return path


def test_drop_handler_returns_fast_with_imageless_slot(tmp_path, monkeypatch):
    """No decode on the GUI thread: the drop call only places an imageless
    slot + toast and queues the worker."""
    from shared.image_processing import progressive_loader as prog_mod

    pool = _CapturingPool()
    controller, widget, mc_store, toast_manager, _ = _make_controller(pool)
    path = _png(tmp_path)

    calls: list[str] = []
    real_preview = prog_mod.load_preview_image

    def _spy_preview(path_str, **kwargs):
        calls.append(path_str)
        return real_preview(path_str, **kwargs)

    monkeypatch.setattr(prog_mod, "load_preview_image", _spy_preview)

    loading_use_cases.on_images_dropped(controller, [path], (None, True), None)

    assert len(widget.state.slots) == 1
    slot = widget.state.slots[0]
    assert slot.path == path
    assert slot.image is None  # imageless until the worker lands
    assert 0 in controller._loading_toasts  # toast armed synchronously
    assert calls == []  # nothing decoded on the GUI thread
    assert len(pool.workers) == 1  # preview worker queued


def test_preview_fills_slot_then_full_res_second_stage(tmp_path):
    """Worker preview → replace_slot_image → full-res worker → store."""
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    pool = _CapturingPool()
    controller, widget, mc_store, toast_manager, _ = _make_controller(pool)
    path = _png(tmp_path)

    loading_use_cases.on_images_dropped(controller, [path], (None, True), None)
    pool.run_one()  # preview worker lands

    slot = widget.state.slots[0]
    assert isinstance(slot.image, QImage)
    assert not slot.image.isNull()
    # Full-res second stage queued by the preview fill.
    assert len(pool.workers) >= 1

    pool.run_one()  # full-res worker lands
    pool.run_all()  # pyramid worker drains

    slot = widget.state.slots[0]
    assert isinstance(slot.image, TiledPixelStore)
    assert slot.image.is_open
    # Toast ran the full lifecycle: shown once, finished with success.
    assert len(toast_manager.shown) == 1
    assert toast_manager.updated[-1][2]["success"] is True
    assert 0 not in controller._loading_toasts


def test_preview_error_removes_slot_and_reports(tmp_path):
    """Failed decode: pre-created slot removed, toast dismissed, error toast."""
    pool = _CapturingPool()
    controller, widget, mc_store, toast_manager, event_bus = _make_controller(pool)
    missing = tmp_path / "missing.png"

    loading_use_cases.on_images_dropped(controller, [missing], (None, True), None)
    assert len(widget.state.slots) == 1
    pool.run_all()  # worker fails (no such file)

    assert widget.state.slots == []
    assert toast_manager.closed == [1]
    assert 0 not in controller._loading_toasts
    assert len(event_bus.emitted) == 1
    err_event = event_bus.emitted[0]
    err_text = str(getattr(err_event, "error", err_event))
    assert "missing.png" in err_text


def test_stale_preview_never_touches_reused_slot_id(tmp_path):
    """Late worker for a removed slot must not fill/remove a newer slot that
    recycled the id (``max+1`` allocation)."""
    pool = _CapturingPool()
    controller, widget, mc_store, toast_manager, _ = _make_controller(pool)
    path_a = _png(tmp_path, "a.png")
    path_b = _png(tmp_path, "b.png")

    loading_use_cases.on_images_dropped(controller, [path_a], (None, True), None)
    assert widget.state.slots[0].id == 0
    # User removes the still-loading slot before its worker lands.
    from tabs.multi_compare.scene import actions as mc_actions

    widget.store.dispatch(mc_actions.remove_slot(0))
    # A new drop recycles id 0.
    loading_use_cases.on_images_dropped(controller, [path_b], (None, True), None)
    assert widget.state.slots[0].id == 0
    assert widget.state.slots[0].path == path_b

    stale_preview = QImage(4, 4, QImage.Format.Format_RGBA8888)
    assert not stale_preview.isNull()
    n_dispatched = len(mc_store.dispatched)
    preview_decode_use_cases.on_preview_ready(controller, 0, path_a, (stale_preview, True))

    # Newer slot untouched: still imageless, no replace dispatched for it.
    assert widget.state.slots[0].path == path_b
    assert widget.state.slots[0].image is None
    replaces = [
        a for a in mc_store.dispatched[n_dispatched:] if type(a).__name__ == "ReplaceSlotImage"
    ]
    assert replaces == []
