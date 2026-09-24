"""Gallery P2 bundle (task-fix-gallery-p2-2026-09-20).

Covers:
* sort applies to grouped series (members + cluster order) in a single
  rebuild pass (one ``set_triage``, no flat ``rebuild_grid`` first);
  flat sort still goes through one ``rebuild_grid``.
* mixed file-plus-folder drop opens the dir AND reports the dropped
  files (routes through ``open_paths``, not folder-only).
* empty-file / no-path drops surface a label note instead of silence.
* sort + mode combos opt out of drop acceptance like the filter edit.

Headless-safe: no real dialogs; ``qapp``/``qtbot`` only for widget asserts.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _item(name: str, *, rank=None, mtime=0) -> GalleryItem:
    return GalleryItem(path=Path(f"/g/{name}"), mtime_ns=mtime, rank=rank)


def _sort_self(*, items, series):
    from tabs.image_gallery.widget import ImageGalleryWidget

    calls: dict = {"triage": [], "rebuild": []}
    return (
        SimpleNamespace(
            _items=list(items),
            _series=[list(cl) for cl in series],
            _mode="fidelity",
            _source_path=None,
            # Unbound-method harness: `self` lookups resolve on the fake.
            _sort_keyfunc=ImageGalleryWidget._sort_keyfunc,
            set_triage=lambda s, m, src: calls["triage"].append((s, m, src)),
            rebuild_grid=lambda items: calls["rebuild"].append(list(items)),
        ),
        calls,
    )


# --------------------------------------------------------------------------
# grouped sort: single rebuild pass
# --------------------------------------------------------------------------


def test_grouped_sort_reorders_members_and_clusters_single_pass(qapp):
    from tabs.image_gallery.widget import ImageGalleryWidget

    items = [_item("b.png"), _item("a.png"), _item("d.png"), _item("c.png"), _item("z.png")]
    series = [[items[0], items[1]], [items[2], items[3]]]
    fake, calls = _sort_self(items=items, series=series)

    ImageGalleryWidget._on_sort_changed(fake, "Sort: Name")

    # Single rebuild pass: set_triage once, flat rebuild_grid never.
    assert len(calls["triage"]) == 1
    assert calls["rebuild"] == []
    new_series, mode, _src = calls["triage"][0]
    assert mode == "fidelity"
    # CONTENT IDENTITY: same 4 members, members sorted, clusters by first.
    assert [[it.path.name for it in cl] for cl in new_series] == [
        ["a.png", "b.png"],
        ["c.png", "d.png"],
    ]
    # _items flattened in the new order with the sorted ungrouped tail.
    assert [it.path.name for it in fake._items] == [
        "a.png", "b.png", "c.png", "d.png", "z.png",
    ]


def test_flat_sort_single_rebuild(qapp):
    from tabs.image_gallery.widget import ImageGalleryWidget

    items = [_item("b.png"), _item("a.png")]
    fake, calls = _sort_self(items=items, series=[])

    ImageGalleryWidget._on_sort_changed(fake, "Sort: Name")

    assert calls["triage"] == []
    assert len(calls["rebuild"]) == 1
    assert [it.path.name for it in calls["rebuild"][0]] == ["a.png", "b.png"]


def test_unknown_sort_label_is_noop(qapp):
    from tabs.image_gallery.widget import ImageGalleryWidget

    fake, calls = _sort_self(items=[_item("b.png")], series=[])
    ImageGalleryWidget._on_sort_changed(fake, "Sort: ???")
    assert calls == {"triage": [], "rebuild": []}


def test_sort_keyfunc_rank_orders_groups(qapp):
    from tabs.image_gallery.widget import ImageGalleryWidget

    key = ImageGalleryWidget._sort_keyfunc("sort: rank")
    assert key is not None
    lo = _item("lo.png", rank=1)
    hi = _item("hi.png", rank=9)
    assert key(lo) < key(hi)
    assert ImageGalleryWidget._sort_keyfunc("sort: ???") is None


# --------------------------------------------------------------------------
# mixed file-plus-folder drop
# --------------------------------------------------------------------------


def _mime(url_paths: list[str]):
    urls = []
    for p in url_paths:
        urls.append(
            SimpleNamespace(
                isLocalFile=lambda: True, toLocalFile=lambda p=p: p
            )
        )
    return SimpleNamespace(hasUrls=lambda: True, urls=lambda: list(urls))


def _drop_event(mime):
    calls: dict = {"accepted": 0, "ignored": 0, "accept": 0}
    return (
        SimpleNamespace(
            mimeData=lambda: mime,
            acceptProposedAction=lambda: calls.__setitem__("accepted", 1),
            ignore=lambda: calls.__setitem__("ignored", 1),
            accept=lambda: calls.__setitem__("accept", 1),
        ),
        calls,
    )


def test_mixed_file_plus_folder_routes_open_paths(qapp, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    opened: dict = {}
    ctrl = SimpleNamespace(
        open_paths=lambda ps, **kw: (opened.setdefault("paths", list(ps)), opened.update(kw)),
        open_folder=lambda f: opened.setdefault("folder", f),
    )
    owner = SimpleNamespace(_controller=ctrl)
    event, _calls = _drop_event(_mime([str(img), str(sub)]))

    dnd.drop_event(owner, event)

    # Opens the dir AND reports the files: full mixed list via open_paths.
    assert "paths" in opened
    assert "folder" not in opened
    assert {Path(p).name for p in opened["paths"]} == {"pic.png", "sub"}
    # Mixed folder+files replaces the pool (folder context wins), it must not
    # ride the file-append default.
    assert opened.get("replace") is True


def test_pure_folder_still_opens_folder(qapp, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    sub = tmp_path / "sub"
    sub.mkdir()
    opened: dict = {}
    ctrl = SimpleNamespace(
        open_paths=lambda ps: opened.setdefault("paths", list(ps)),
        open_folder=lambda f: opened.setdefault("folder", f),
    )
    owner = SimpleNamespace(_controller=ctrl)
    event, _calls = _drop_event(_mime([str(sub)]))

    dnd.drop_event(owner, event)

    assert "folder" in opened
    assert "paths" not in opened


# --------------------------------------------------------------------------
# empty / no-path feedback
# --------------------------------------------------------------------------


def test_zero_byte_drop_notes_not_opens(qapp, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    noted: list = []
    opened: list = []
    owner = SimpleNamespace(
        _controller=SimpleNamespace(open_paths=lambda ps: opened.append(ps)),
        set_folder_label=lambda p: noted.append(str(p)),
    )
    dnd.on_empty_file_dropped(owner, str(empty))
    assert opened == []
    assert len(noted) == 1
    assert "empty" in noted[0].lower()


def test_missing_path_drop_notes(qapp, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    noted: list = []
    owner = SimpleNamespace(
        _controller=None,
        set_folder_label=lambda p: noted.append(str(p)),
    )
    dnd.on_empty_file_dropped(owner, str(tmp_path / "gone.png"))
    assert len(noted) == 1


def test_no_paths_extracted_notes(qapp, monkeypatch):
    from tabs.image_gallery.ui import drag_drop as dnd

    noted: list = []
    owner = SimpleNamespace(set_folder_label=lambda p: noted.append(str(p)))
    monkeypatch.setattr(dnd, "_extract_paths", lambda mime: [])
    mime = SimpleNamespace(hasUrls=lambda: False, urls=lambda: [])
    monkeypatch.setattr(dnd, "is_acceptable_drop", lambda owner, event: True)
    event, _calls = _drop_event(mime)
    dnd.drop_event(owner, event)
    assert len(noted) == 1


# --------------------------------------------------------------------------
# sort/mode combos opt out of drops
# --------------------------------------------------------------------------


def test_sort_and_mode_combos_reject_drops(qtbot):
    from tabs.image_gallery.ui.toolbar import GalleryToolbar

    toolbar = GalleryToolbar(with_mode_combo=True)
    qtbot.addWidget(toolbar)
    assert toolbar.sort_combo.acceptDrops() is False
    assert toolbar._mode_combo is not None
    assert toolbar._mode_combo.acceptDrops() is False
