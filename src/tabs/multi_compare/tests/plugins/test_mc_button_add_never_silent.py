"""Multi Compare toolbar "Add images" must never silently lose files (P8).

Dialog confirm with >=1 valid file → slot + preview/error-toast, never a
silent 0 slots. Losing step was ``use_cases.dialog_add.load_single_auto``
(formerly in ``loading.py``):
``sid is None → return`` (grid full / reducer grew nothing) dropped
dialog-confirmed files with no slot, no toast, no bus event, while DnD of
the same file worked. Companion drift fixed alongside: the button entry
was the only one without extension/``is_file`` validation (DnD filters in
``drop_event``, chrome/carry in ``load_external_paths``) and crashed with
a bare ``AttributeError`` on ``str`` input (``path.stem``) — invisible
inside the Qt slot.

Covers the bug-a1 guard too: a corrupt drop/add must surface an
error-toast, never vanish silently.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QImage

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.use_cases import placement as placement_use_cases
from tabs.multi_compare.use_cases import preview_decode as preview_decode_use_cases


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
    """Holds GenericWorkers instead of running them — GUI-thread work and
    worker work stay observable as separate phases."""

    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)

    def run_all(self, limit: int = 30) -> None:
        for _ in range(limit):
            if not self.workers:
                return
            self.workers.pop(0).run()


class _FakeMcStore:
    """Dispatch-only mutation through the real pure reducer (STORE invariants)."""

    def __init__(self, state=None):
        self.state = state or MultiCompareState()
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


def _make_controller(pool, state=None):
    mc_store = _FakeMcStore(state)
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


def _err_text(event) -> str:
    return str(getattr(event, "error", event))


def test_dialog_add_valid_file_creates_slot_and_fills_preview(tmp_path):
    """Happy path: dialog confirm → imageless slot + toast + worker now,
    image tier once the worker lands, no error bus traffic."""
    pool = _CapturingPool()
    controller, widget, _, toast_manager, event_bus = _make_controller(pool)
    path = _png(tmp_path)

    created = controller.load_images([path])

    assert created == 1
    assert len(widget.state.slots) == 1
    slot = widget.state.slots[0]
    assert slot.path == path
    assert slot.image is None  # imageless until the worker lands
    assert len(toast_manager.shown) == 1
    assert len(pool.workers) == 1

    pool.run_all()

    assert widget.state.slots[0].image is not None
    assert event_bus.emitted == []


def test_dialog_add_full_grid_reports_single_error(tmp_path):
    """The P8 losing step: grid full must surface one error-toast via the
    bus — never a silent 0 slots."""
    pool = _CapturingPool()
    full_state = MultiCompareState(max_slots=1)
    controller, widget, _, toast_manager, event_bus = _make_controller(pool, full_state)
    first = _png(tmp_path, "first.png")
    widget.store.dispatch(
        mc_actions.add_slot(
            path=first, image=None, label="first",
            target_path=None, side=None, target_root=True,
        )
    )
    assert len(widget.state.slots) == 1
    second = _png(tmp_path, "second.png")

    created = controller.load_images([second, _png(tmp_path, "third.png")])

    assert created == 0
    assert len(widget.state.slots) == 1  # nothing added
    assert pool.workers == []  # nothing queued
    assert toast_manager.shown == []  # no slot → no loading toast
    assert len(event_bus.emitted) == 1  # single grid-full report, not per-file
    assert "second.png" in _err_text(event_bus.emitted[0])


def test_dialog_add_corrupt_file_reports_error_toast(tmp_path):
    """bug-a1 guard on the button entry: corrupt file → error-toast on the
    bus and no lingering slot, never a silent vanish."""
    pool = _CapturingPool()
    controller, widget, _, _, event_bus = _make_controller(pool)
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not an image at all\x00\x01\x02")

    created = controller.load_images([corrupt])
    assert created == 1  # slot staged synchronously like the drop path
    assert len(widget.state.slots) == 1
    pool.run_all()

    assert widget.state.slots == []
    assert len(event_bus.emitted) == 1
    assert "corrupt.png" in _err_text(event_bus.emitted[0])


def test_dialog_add_accepts_str_paths(tmp_path):
    """QFileDialog yields ``str``; the entry must not ``AttributeError`` on
    ``path.stem`` inside the Qt slot (stderr-only, user sees nothing)."""
    pool = _CapturingPool()
    controller, widget, _, _, event_bus = _make_controller(pool)
    path = _png(tmp_path)

    created = controller.load_images([str(path)])

    assert created == 1
    assert [s.path for s in widget.state.slots] == [path]
    pool.run_all()
    assert widget.state.slots[0].image is not None
    assert event_bus.emitted == []


def test_dialog_add_skips_non_images_without_slot(tmp_path):
    """Dialog 'All files' picks and vanished files: skipped like the
    DnD/chrome/carry entries skip them — no slot, no worker, no crash."""
    pool = _CapturingPool()
    controller, widget, _, toast_manager, event_bus = _make_controller(pool)
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")

    created = controller.load_images([notes, tmp_path / "gone.png"])

    assert created == 0
    assert widget.state.slots == []
    assert pool.workers == []
    assert toast_manager.shown == []
    assert event_bus.emitted == []


def test_stale_guard_tolerates_textual_path_variants(tmp_path):
    """Slot-ownership guards compare normalized paths: a ``str``-vs-``Path``
    (or ``./``) variant of the same file must fill, not dismiss-and-orphan
    (imageless slot forever, toast dismissed, no error)."""
    pool = _CapturingPool()
    controller, widget, _, _, event_bus = _make_controller(pool)
    path = _png(tmp_path)

    # Legacy/other-entries slots may hold a str path while the worker
    # reports a Path (strict ``==`` differs) — the guard must still match.
    sid = widget.add_image_auto(str(path), None, "img")
    assert sid is not None
    assert widget.state.slots[0].path != path  # strict == really differs
    preview = QImage(4, 4, QImage.Format.Format_RGBA8888)
    assert not preview.isNull()
    preview_decode_use_cases.on_preview_ready(controller, sid, path, (preview, True))

    assert widget.state.slots[0].image is not None
    assert event_bus.emitted == []
