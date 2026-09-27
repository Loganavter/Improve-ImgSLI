"""Gallery pool append via FakeDispatcher (Wave 3d2, plan-gallery-redux-2026-09-24).

Migrated from direct ``ctrl.state`` mutation assertions to dispatch doubles:
every pool transition asserts the dispatched ``GALLERY_*`` action type +
``scope == "gallery"`` AND the resulting slot contents via
``state/selectors.py`` (``get_item_paths``/``get_item_by_path``/``get_folder``).

Content-identity coverage (kept, now slot-backed):
distinct paths per drop -> matching pool entries; re-drop dedups; replace
wipes; folder drop rescans (append keeps folder context).

Double shape mirrors the image_compare precedent
(``test_ic_p2_hygiene.py`` ``_RecordingDispatcher``) — shared helper in
``tests/_gallery_dispatch_doubles.py``, not a second fake.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.state import selectors as gallery_selectors
from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    FakeGalleryStore,
    dispatched_kinds,
    dispatched_scopes,
    gallery_slot,
    make_gallery_context,
)


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
        self._items = []

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        self._items = list(items)

    def refresh_card(self, item) -> None:
        pass

    def set_card_visible(self, path, visible: bool) -> None:
        pass

    def set_triage(self, *a) -> None:
        pass

    def set_scanning(self, *a) -> None:
        pass

    def pick_folder_dialog(self, start_dir: str = ""):
        return None


def _make_ctrl() -> tuple[GalleryController, _WidgetStub, dict, FakeGalleryStore]:
    widget = _WidgetStub()
    context, store = make_gallery_context()
    ctrl = GalleryController(
        widget, thread_pool=QThreadPool.globalInstance(), context=context
    )
    calls: dict = {"triage": [], "thumbs": []}
    ctrl._start_triage = lambda items, **kw: calls["triage"].append(list(items))  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: calls["thumbs"].append(item.path)  # type: ignore[method-assign]
    return ctrl, widget, calls, store


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return p


def _slot_names(store: FakeGalleryStore) -> list[str]:
    return [Path(p).name for p in gallery_selectors.get_item_paths(gallery_slot(store))]


def _assert_gallery_scope(store: FakeGalleryStore) -> None:
    scopes = dispatched_scopes(store)
    assert scopes, "expected at least one gallery dispatch"
    assert all(s == GALLERY_SLOT_NAME for s in scopes), scopes


def test_file_drop_appends_to_pool(tmp_path: Path):
    ctrl, widget, calls, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a])
    assert dispatched_kinds(store) == ["GalleryPathsAppended"]
    _assert_gallery_scope(store)
    # CONTENT IDENTITY: 1 dropped file -> 1 pool entry with the matching path.
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a)]
    assert gallery_selectors.get_item_by_path(gallery_slot(store), str(a)) is not None

    ctrl.open_paths([b])
    assert dispatched_kinds(store) == ["GalleryPathsAppended"] * 2
    _assert_gallery_scope(store)
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a), str(b)]
    assert [Path(p).name for p in gallery_selectors.get_item_paths(gallery_slot(store))] == [
        "a.jpg",
        "b.jpg",
    ]
    assert _slot_names(store) == ["a.jpg", "b.jpg"]
    assert [it.path.name for it in widget._items] == ["a.jpg", "b.jpg"]
    # Triage re-runs over the merged pool (series describe the whole grid).
    assert [[it.path.name for it in batch] for batch in calls["triage"]] == [["a.jpg"], ["a.jpg", "b.jpg"]]
    # Thumbnails only for the truly-new item — no refetch flicker for old ones.
    assert [p.name for p in calls["thumbs"]] == ["a.jpg", "b.jpg"]


def test_redrop_does_not_duplicate(tmp_path: Path):
    ctrl, _, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a, b])
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a), str(b)]
    n_calls = len(store.get_dispatcher().calls)
    # Re-drop of known paths dedups: no new pool entries, no new dispatch
    # (controller skips the emit when nothing is truly new).
    ctrl.open_paths([b, a])
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a), str(b)]
    assert len(store.get_dispatcher().calls) == n_calls


def test_replace_wipes_pool(tmp_path: Path):
    ctrl, _, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a])
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a)]
    ctrl.open_paths([b], replace=True)
    # Replace wipes: pool holds only the new drop.
    assert dispatched_kinds(store)[-1] == "GalleryPoolReplaced"
    _assert_gallery_scope(store)
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(b)]


def test_append_keeps_folder_context(tmp_path: Path):
    ctrl, _, _, store = _make_ctrl()
    folder = tmp_path / "F"
    folder.mkdir()
    f1 = folder / "f1.jpg"
    f1.write_bytes(b"\x00")
    ctrl.open_folder(folder)
    assert dispatched_kinds(store)[-1] == "GalleryPoolOpened"
    _assert_gallery_scope(store)
    # Folder drop rescans: slot holds the scanned entries under the folder.
    assert gallery_selectors.get_folder(gallery_slot(store)) == str(folder)
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(f1)]

    extra = _img(tmp_path, "extra.jpg")
    ctrl.open_paths([extra])
    assert dispatched_kinds(store)[-1] == "GalleryPathsAppended"
    assert _slot_names(store) == ["f1.jpg", "extra.jpg"]
    # Appending into a folder-backed pool keeps the folder context in the slot.
    assert gallery_selectors.get_folder(gallery_slot(store)) == str(folder)


def test_append_leaves_folder_generation_untouched(tmp_path: Path):
    # Generation counters stay controller-local (plan non-goal: no gen tokens
    # in actions or the slot) — this pins the local stale-guard behavior.
    ctrl, _, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a])
    gen = ctrl._folder_gen
    ctrl.open_paths([b])
    assert ctrl._folder_gen == gen
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a), str(b)]
    ctrl.open_paths([b], replace=True)
    assert ctrl._folder_gen != gen
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(b)]
