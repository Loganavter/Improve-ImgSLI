"""Triage must not tear down a good view on every new image.

Regression for the load-cycle jump: appending one image hid the grouped
grid behind the S1 scanning state and then rebuilt every card from scratch
even when clustering changed nothing — groups vanished, cards piled flat,
groups reappeared.

Pinned here:
- identical re-``set_triage`` (same ordered membership, same objects,
  same mode/source) skips the grid rebuild (stats still sync);
- changed membership still rebuilds (single transition, no pile);
- ``open_paths`` append runs background triage (toolbar spinner only,
  grid stays), replace covers as before;
- ``set_background_scanning`` never switches the content stack.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i) for i, n in enumerate(names)]


def _grouped_widget(qtbot, items: list[GalleryItem]) -> ImageGalleryWidget:
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    w.rebuild_grid(items)
    a, b, c, d = items
    w.set_triage([[a, b], [c, d]], "camera", None)
    assert w._grid_view._series is not None
    assert len(w._grid_view._series_headers) == 2  # SERIES x2, all grouped
    return w


def test_identical_retriage_skips_rebuild(qtbot) -> None:
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    calls: list = []
    orig = w._grid_view.set_series
    try:
        w._grid_view.set_series = lambda *a, **k: (calls.append((a, k)), orig(*a, **k))  # type: ignore[method-assign]
        w.set_triage([[items[0], items[1]], [items[2], items[3]]], "camera", None)
    finally:
        w._grid_view.set_series = orig  # type: ignore[method-assign]
    assert calls == []
    # View intact: same headers, same cards, stats synced.
    assert len(w._grid_view._series_headers) == 2
    for it in items:
        assert w._grid_view.card_for(it.path) is not None


def test_changed_retriage_rebuilds_once(qtbot) -> None:
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    calls: list = []
    orig = w._grid_view.set_series
    try:
        w._grid_view.set_series = lambda *a, **k: (calls.append((a, k)), orig(*a, **k))  # type: ignore[method-assign]
        # New grouping: everything in one cluster.
        w.set_triage([items], "camera", None)
    finally:
        w._grid_view.set_series = orig  # type: ignore[method-assign]
    assert len(calls) == 1
    assert len(w._grid_view._series) == 1


def test_background_scanning_keeps_grid_visible(qtbot) -> None:
    items = _items("a.png", "b.png", "c.png", "d.png")
    w = _grouped_widget(qtbot, items)
    from PySide6.QtWidgets import QStackedWidget

    assert isinstance(w._content_stack, QStackedWidget)
    assert w._content_stack.currentWidget() is w._grid_view
    w.set_background_scanning(0, len(items))
    assert w._content_stack.currentWidget() is w._grid_view
    assert w._grid_view._series is not None


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)


class _ScanStub:
    def __init__(self):
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()
        self.cover_calls: list = []
        self.background_calls: list = []
        self.triage_calls: list = []
        self.rebuild_calls: list = []
        self._items = []
        self._grid_view = None

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        self.rebuild_calls.append([str(it.path) for it in items])
        self._items = list(items)

    def refresh_card(self, item) -> None:
        pass

    def set_triage(self, *a) -> None:
        self.triage_calls.append(a)

    def set_scanning(self, *a) -> None:
        self.cover_calls.append(a)

    def set_background_scanning(self, *a) -> None:
        self.background_calls.append(a)

    def pick_folder_dialog(self, start_dir: str = ""):
        return None


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return p


def _make_ctrl(widget):
    from tabs.image_gallery.tests._gallery_dispatch_doubles import make_gallery_context

    context, _store = make_gallery_context()
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=context)
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl


def test_append_triage_runs_in_background(tmp_path, qtbot) -> None:
    """First drop covers (nothing to preserve); appends stay background."""
    widget = _ScanStub()
    ctrl = _make_ctrl(widget)
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")
    ctrl.open_paths([a])
    assert widget.cover_calls == [(0, 1)]
    assert widget.background_calls == []
    ctrl.open_paths([b])
    assert widget.cover_calls == [(0, 1)]
    assert widget.background_calls == [(0, 2)]


def test_replace_triage_covers_grid(tmp_path, qtbot) -> None:
    widget = _ScanStub()
    ctrl = _make_ctrl(widget)
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")
    ctrl.open_paths([a])
    ctrl.open_paths([b], replace=True)
    assert widget.cover_calls == [(0, 1), (0, 1)]
    assert widget.background_calls == []


def _make_ctrl_no_triage(widget):
    """Controller with _start_triage recorded, never run (routing asserts)."""
    from types import SimpleNamespace

    from tabs.image_gallery.tests._gallery_dispatch_doubles import make_gallery_context

    context, _store = make_gallery_context()
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=context)
    calls: list = []
    ctrl._start_triage = lambda items, **kw: calls.append((list(items), kw))  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl, calls


def test_redrop_into_grouped_view_is_full_noop(tmp_path, qtbot) -> None:
    """Re-drop of known files into a grouped view: no rebuild, no triage."""
    from types import SimpleNamespace

    widget = _ScanStub()
    ctrl, triage_calls = _make_ctrl_no_triage(widget)
    a = _img(tmp_path, "a.jpg")
    ctrl.open_paths([a])
    assert len(widget.rebuild_calls) == 1
    assert [kw.get("cover_grid") for _, kw in triage_calls] == [True]
    # Series view is live now (grouped paint, e.g. after triage delivery).
    widget._grid_view = SimpleNamespace(_series=[[a]])
    ctrl.open_paths([a])
    assert len(widget.rebuild_calls) == 1
    assert len(triage_calls) == 1


def test_redrop_into_flat_view_retriages_without_rebuild(tmp_path, qtbot) -> None:
    """Re-drop into a never-grouped view: no rebuild, background triage."""
    widget = _ScanStub()
    ctrl, triage_calls = _make_ctrl_no_triage(widget)
    a = _img(tmp_path, "a.jpg")
    ctrl.open_paths([a])
    assert len(widget.rebuild_calls) == 1
    # Still flat (triage never delivered): re-drop regroups in background.
    widget._grid_view = SimpleNamespace(_series=None)
    ctrl.open_paths([a])
    assert len(widget.rebuild_calls) == 1
    assert [(len(items), kw.get("cover_grid")) for items, kw in triage_calls] == [
        (1, True),
        (1, False),
    ]
