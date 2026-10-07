"""Single-file DnD / dialog must not scan parent folder (regression for 1037-item hang).

User dropped one image from /Images (1037 files) and we opened the whole parent.
Open via dialog on one image must also show only that image.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool

from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.state import selectors as gallery_selectors
from tabs.image_gallery.tab import ImageGalleryTab
from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    dispatched_kinds,
    dispatched_scopes,
    gallery_slot,
    make_gallery_context,
)


class _WidgetStub:
    def __init__(self):
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()
        self._folder = None
        self._items = []
        self._visible = {}

    def set_folder_label(self, folder: Path) -> None:
        self._folder = folder

    def rebuild_grid(self, items: list[GalleryItem]) -> None:
        self._items = list(items)

    def refresh_card(self, item: GalleryItem) -> None:
        pass

    def set_card_visible(self, path: Path, visible: bool) -> None:
        self._visible[path] = visible

    def pick_folder_dialog(self, start_dir: str = "") -> str | None:
        return None


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a, **kw):
        for fn in self._slots:
            fn(*a, **kw)


def _make_ctrl(widget):
    """Store-backed controller: pool transitions dispatch with scope 'gallery'.

    Triage/thumbnail side-effects are stubbed (this file asserts pool
    membership, not background workers).
    """
    context, store = make_gallery_context()
    ctrl = GalleryController(
        widget, thread_pool=QThreadPool.globalInstance(), context=context
    )
    ctrl._start_triage = lambda items, **kw: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl, store


def test_open_paths_single_file_does_not_scan_parent(tmp_path: Path):
    # parent with 2 images, we drop only one
    parent = tmp_path / "Images"
    parent.mkdir()
    a = parent / "a.jpg"
    b = parent / "b.jpg"
    a.write_bytes(b"\x00")
    b.write_bytes(b"\x00")

    widget = _WidgetStub()
    ctrl, store = _make_ctrl(widget)

    ctrl.open_paths([a])

    assert dispatched_kinds(store) == ["GalleryPathsAppended"]
    assert dispatched_scopes(store) == [GALLERY_SLOT_NAME]
    # CONTENT IDENTITY: 1 dropped file -> 1 pool entry with the matching path.
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a)]
    # folder must not be the parent with 2 items scanned — it must be None (no folder context)
    # or at least not imply 2 items
    assert gallery_selectors.get_folder(gallery_slot(store)) is None
    # ensure we didn't scan b.jpg
    names = {Path(p).name for p in gallery_selectors.get_item_paths(gallery_slot(store))}
    assert "b.jpg" not in names
    assert "a.jpg" in names


def test_open_paths_multiple_files_from_same_parent(tmp_path: Path):
    parent = tmp_path / "P"
    parent.mkdir()
    a = parent / "a.png"
    b = parent / "b.png"
    c = parent / "c.txt"  # non-image, should be ignored when via open_paths filter
    a.write_bytes(b"\x00")
    b.write_bytes(b"\x00")
    c.write_text("x")

    widget = _WidgetStub()
    ctrl, store = _make_ctrl(widget)
    ctrl.open_paths([a, b, c])

    assert dispatched_kinds(store) == ["GalleryPathsAppended"]
    assert dispatched_scopes(store) == [GALLERY_SLOT_NAME]
    names = {Path(p).name for p in gallery_selectors.get_item_paths(gallery_slot(store))}
    assert names == {"a.png", "b.png"}


def test_open_folder_still_scans_all(tmp_path: Path):
    parent = tmp_path / "F"
    parent.mkdir()
    (parent / "a.jpg").write_bytes(b"\x00")
    (parent / "b.jpg").write_bytes(b"\x00")

    widget = _WidgetStub()
    ctrl, store = _make_ctrl(widget)
    ctrl.open_folder(parent)

    assert dispatched_kinds(store) == ["GalleryPoolOpened"]
    assert dispatched_scopes(store) == [GALLERY_SLOT_NAME]
    assert len(gallery_selectors.get_item_paths(gallery_slot(store))) == 2
    assert gallery_selectors.get_folder(gallery_slot(store)) == str(parent)


def test_tab_handle_drop_single_file_uses_open_paths(tmp_path: Path, qtbot):
    # STORELESS FAIL-OPEN: real Tab + Widget without a Redux store — the drop
    # takes the legacy controller path (no dispatch). Membership is asserted
    # on the local mirror only; slot-backed coverage lives in the tests above
    # plus test_gallery_pool_append.py.
    from PySide6.QtWidgets import QWidget

    from tabs.contract import TabContext

    parent = tmp_path / "Imgs"
    parent.mkdir()
    a = parent / "single.jpg"
    b = parent / "other.jpg"
    a.write_bytes(b"\x00")
    b.write_bytes(b"\x00")

    tab = ImageGalleryTab()
    host = QWidget()
    qtbot.addWidget(host)
    ctx = TabContext()
    # minimal store stub so serialize etc don't crash
    class _Store:
        def get_active_workspace_session(self):
            return None

        def get_workspace_session(self, sid):
            return None

    ctx.store = _Store()  # type: ignore[attr-defined]
    page = tab.create_page(host, ctx)
    qtbot.addWidget(page)

    assert tab.accepts_drop([a])
    # single file -> should call open_paths, not open_folder(parent) with 2 items
    ok = tab.handle_drop([a])
    assert ok is True
    # give QTimer singleShot a chance
    qtbot.wait(50)
    # controller should have only 1 item, not 2
    assert tab._controller is not None
    assert len(tab._controller.state.items) == 1
    assert tab._controller.state.items[0].path.name == "single.jpg"


def test_tab_accepts_drop_folder_and_file(tmp_path: Path):
    tab = ImageGalleryTab()
    d = tmp_path / "D"
    d.mkdir()
    f = tmp_path / "x.png"
    f.write_bytes(b"\x00")
    txt = tmp_path / "readme.txt"
    txt.write_text("hi")

    assert tab.accepts_drop([d]) is True
    assert tab.accepts_drop([f]) is True
    assert tab.accepts_drop([txt]) is False


def test_filtering_matches_filename_even_when_not_analyzed():
    from tabs.image_gallery.models import AnalysisStatus
    from tabs.image_gallery.services.filtering import filter_items

    def _item(name: str, status=AnalysisStatus.NOT_ANALYZED):
        return GalleryItem(path=Path(f"/g/{name}"), mtime_ns=1, analysis_status=status)

    items = [_item("sunset_042.jpg"), _item("city.png")]
    assert filter_items(items, "sunset") == [items[0]]
    assert filter_items(items, "CITY") == [items[1]]
    assert filter_items(items, "") == items


def test_widget_drop_single_file_uses_open_paths(tmp_path: Path, qtbot):
    # STORELESS FAIL-OPEN: real Widget + controller without a Redux store —
    # the drop takes the legacy controller path (no dispatch). Membership is
    # asserted on the local mirror only; see the slot-backed tests above.
    from PySide6.QtCore import QMimeData, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtCore import QPoint

    from tabs.contract import TabContext
    from tabs.image_gallery.widget import ImageGalleryWidget
    from tabs.image_gallery.controller import GalleryController

    parent = tmp_path / "W"
    parent.mkdir()
    a = parent / "one.png"
    b = parent / "two.png"
    a.write_bytes(b"\x00")
    b.write_bytes(b"\x00")

    ctx = TabContext()
    w = ImageGalleryWidget(None, context=ctx)
    qtbot.addWidget(w)
    w.resize(800, 600)
    w.show()
    qtbot.waitExposed(w)

    ctrl = GalleryController(w, thread_pool=QThreadPool.globalInstance(), context=ctx)
    w._controller = ctrl  # type: ignore[attr-defined]

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(a))])
    ev = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    w.dropEvent(ev)

    qtbot.wait(50)
    assert len(ctrl.state.items) == 1
    assert ctrl.state.items[0].path.name == "one.png"
    assert "two.png" not in {it.path.name for it in ctrl.state.items}


def test_widget_pick_dialog_allows_image_file(tmp_path: Path, qtbot, monkeypatch):
    from unittest.mock import MagicMock

    from PySide6.QtWidgets import QFileDialog

    from tabs.contract import TabContext
    from tabs.image_gallery.widget import ImageGalleryWidget

    ctx = TabContext()
    w = ImageGalleryWidget(None, context=ctx)
    qtbot.addWidget(w)

    # Mock QFileDialog to simulate picking an image file
    fake_file = tmp_path / "picked.jpg"
    fake_file.write_bytes(b"\x00")

    # Mock the dialog instance to return the file, not parent
    class _FakeDialog:
        def __init__(self, *a, **kw):
            pass

        def setFileMode(self, *a, **kw):
            pass

        def setOption(self, *a, **kw):
            pass

        def exec(self):
            return True

        def selectedFiles(self):
            return [str(fake_file)]

    monkeypatch.setattr("tabs.image_gallery.widget.QFileDialog", _FakeDialog)

    chosen = w.pick_folder_dialog(start_dir=str(tmp_path))
    # Must return the file itself, not its parent — controller will open_paths
    assert chosen == str(fake_file)
    assert Path(chosen).is_file()
    assert Path(chosen).suffix == ".jpg"


def test_reanalyze_bypasses_cache_and_starts_worker(tmp_path, monkeypatch):
    """Re-analyze ignores the disk cache: PENDING + worker, never instant DONE."""
    from tabs.image_gallery.models import AiAnalysisResult, AnalysisStatus
    from tabs.image_gallery.services import ai_cache
    from tabs.image_gallery.services.ai_settings_store import AiSettings

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = tmp_path / "img.png"
    path.write_bytes(b"\x00")
    ai_cache.save_analysis(
        path,
        7,
        AiAnalysisResult(
            description="old", tags=(), model="m", analyzed_at_iso="t",
            sharpness=10, noise=10, exposure=10, composition=10,
            verdict="reject", verdict_reason="old",
        ),
    )
    widget = _WidgetStub()
    ctrl, _store = _make_ctrl(widget)
    monkeypatch.setattr(
        ctrl._ai_settings_store,
        "load",
        lambda: AiSettings(enabled=True, api_key="k", model="m"),
    )
    started = []
    ctrl._pool_start = lambda worker, _=None: started.append(worker)  # type: ignore[method-assign]
    item = GalleryItem(path=path, mtime_ns=7)
    ctrl.reanalyze_item(item)
    assert item.analysis_status == AnalysisStatus.PENDING
    assert len(started) == 1
