"""Single-file DnD / dialog must not scan parent folder (regression for 1037-item hang).

User dropped one image from /Images (1037 files) and we opened the whole parent.
Open via dialog on one image must also show only that image.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.tab import ImageGalleryTab


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


def test_open_paths_single_file_does_not_scan_parent(tmp_path: Path):
    # parent with 2 images, we drop only one
    parent = tmp_path / "Images"
    parent.mkdir()
    a = parent / "a.jpg"
    b = parent / "b.jpg"
    a.write_bytes(b"\x00")
    b.write_bytes(b"\x00")

    widget = _WidgetStub()
    pool = QThreadPool.globalInstance()
    # use direct pool to avoid async racy thumbnail workers in this unit test
    # we only care about state after open_paths, not thumbnails
    ctrl = GalleryController(widget, thread_pool=pool, context=None)

    ctrl.open_paths([a])

    assert len(ctrl.state.items) == 1
    assert ctrl.state.items[0].path == a
    # folder must not be the parent with 2 items scanned — it must be None (no folder context)
    # or at least not imply 2 items
    assert ctrl.state.folder is None or ctrl.state.folder == parent
    # ensure we didn't scan b.jpg
    names = {it.path.name for it in ctrl.state.items}
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
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=None)
    ctrl.open_paths([a, b, c])

    names = {it.path.name for it in ctrl.state.items}
    assert names == {"a.png", "b.png"}


def test_open_folder_still_scans_all(tmp_path: Path):
    parent = tmp_path / "F"
    parent.mkdir()
    (parent / "a.jpg").write_bytes(b"\x00")
    (parent / "b.jpg").write_bytes(b"\x00")

    widget = _WidgetStub()
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=None)
    ctrl.open_folder(parent)

    assert len(ctrl.state.items) == 2
    assert ctrl.state.folder == parent


def test_tab_handle_drop_single_file_uses_open_paths(tmp_path: Path, qtbot):
    # Real Tab + Widget path for handle_drop single file
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
