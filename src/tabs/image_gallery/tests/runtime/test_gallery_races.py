"""Gallery async races: folder-switch drops, scan cancel/cap, filter debounce.

Regression for task-fix-gallery-races-2026-09-20:
- late triage/artifact/thumbnail results from a previous folder are dropped
- folder scan honors count cap + cooperative cancellation
- filter keystrokes debounce; stale brief-disk matches never resurrect
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import folder_scanner


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a, **kw):
        for fn in self._slots:
            fn(*a, **kw)


class _WidgetStub:
    def __init__(self):
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()
        self._visible: dict = {}
        self._items = []

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        self._items = list(items)

    def refresh_card(self, item) -> None:
        pass

    def set_card_visible(self, path, visible: bool) -> None:
        self._visible[path] = visible

    def set_triage(self, *a) -> None:
        pass

    def set_scanning(self, *a) -> None:
        pass

    def pick_folder_dialog(self, start_dir: str = ""):
        return None


def _make_ctrl() -> tuple[GalleryController, _WidgetStub]:
    widget = _WidgetStub()
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=None)
    # Silence real background triage/thumbnails: this test drives handlers directly.
    ctrl._start_triage = lambda items: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl, widget


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return p


def test_folder_switch_drops_stale_triage(tmp_path: Path):
    ctrl, _ = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a])
    stale_gen = ctrl._folder_gen
    ctrl.open_paths([b])
    assert ctrl._folder_gen != stale_gen

    # Late triage result from folder A arrives after the switch.
    ctrl._on_triage_ready((["series-from-A"], None, None), stale_gen)
    assert ctrl.state.series == []
    assert [it.path for it in ctrl.state.items] == [b]


def test_folder_switch_drops_stale_artifacts_and_thumbnails(tmp_path: Path):
    ctrl, _ = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a])
    stale_gen = ctrl._folder_gen
    item_a = ctrl.state.items[0]
    ctrl.open_paths([b])

    # Stale artifact catalog must not touch the new folder's items.
    ctrl._on_artifacts_ready({str(item_a.path): {"x": 1}}, stale_gen)
    assert ctrl.state.items[0].metrics.get("artifacts") is None

    # Stale thumbnail must not resolve against the new folder either.
    ctrl._on_thumbnail_ready(item_a.path, None, stale_gen)
    assert all(it.path != item_a.path for it in ctrl.state.items)


def test_scan_cancel_and_cap(tmp_path: Path):
    folder = tmp_path / "F"
    folder.mkdir()
    for i in range(5):
        (folder / f"img{i:02d}.jpg").write_bytes(b"\x00")

    assert folder_scanner.scan_folder(folder, cancel=lambda: True) == []
    capped = folder_scanner.scan_folder(folder, limit=2)
    assert len(capped) == 2
    full = folder_scanner.scan_folder(folder)
    assert len(full) == 5


def test_filter_debounce_and_stale_brief_drop(tmp_path: Path):
    ctrl, widget = _make_ctrl()
    a = _img(tmp_path, "apple.jpg")
    b = _img(tmp_path, "banana.jpg")
    ctrl.open_paths([a, b])

    # Rapid keystrokes coalesce to the last query only.
    ctrl.set_filter_text("apple")
    ctrl.set_filter_text("banana")
    ctrl.apply_pending_filter()
    assert ctrl.state.filter_text == "banana"
    assert widget._visible[a] is False
    assert widget._visible[b] is True

    # A slow brief worker for the old query must not resurrect "apple".
    ctrl._on_brief_filter_ready({a}, filter_gen=ctrl._filter_gen - 1, folder_gen=ctrl._folder_gen)
    assert widget._visible[a] is False
