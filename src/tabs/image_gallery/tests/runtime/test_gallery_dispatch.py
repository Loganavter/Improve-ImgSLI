"""Gallery dispatch coverage (Wave 3d2, plan-gallery-redux-2026-09-24).

Every pool/selection/filter/thumbnail/triage transition asserts the dispatched
``GALLERY_*`` action type + ``scope == "gallery"`` AND the resulting slot
contents via ``state/selectors.py`` — counts alone are not correctness.

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
from tabs.image_gallery.use_cases import selection as selection_uc


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


def _make_ctrl() -> tuple[GalleryController, _WidgetStub, FakeGalleryStore]:
    widget = _WidgetStub()
    context, store = make_gallery_context()
    ctrl = GalleryController(
        widget, thread_pool=QThreadPool.globalInstance(), context=context
    )
    ctrl._start_triage = lambda items: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl, widget, store


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return p


def _assert_gallery_scope(store: FakeGalleryStore) -> None:
    scopes = dispatched_scopes(store)
    assert scopes, "expected at least one gallery dispatch"
    assert all(s == GALLERY_SLOT_NAME for s in scopes), scopes


def test_folder_drop_rescans_into_slot(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    folder = tmp_path / "F"
    folder.mkdir()
    f1 = folder / "f1.jpg"
    f1.write_bytes(b"\x00")

    ctrl.open_folder(folder)

    assert dispatched_kinds(store) == ["GalleryPoolOpened"]
    _assert_gallery_scope(store)
    slot = gallery_slot(store)
    assert gallery_selectors.get_folder(slot) == str(folder)
    assert gallery_selectors.get_item_paths(slot) == [str(f1)]


def test_file_drop_appends_with_matching_paths(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")

    ctrl.open_paths([a])
    ctrl.open_paths([b])

    assert dispatched_kinds(store) == ["GalleryPathsAppended"] * 2
    _assert_gallery_scope(store)
    # CONTENT IDENTITY: 2 distinct dropped paths -> 2 pool entries, same paths.
    assert gallery_selectors.get_item_paths(gallery_slot(store)) == [str(a), str(b)]
    for p in (a, b):
        assert gallery_selectors.get_item_by_path(gallery_slot(store), str(p)) is not None


def test_selection_dispatch_sets_slot_selection(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")
    ctrl.open_paths([a, b])

    ctrl.set_selection([b, a])

    assert dispatched_kinds(store)[-1] == "GallerySelectionSet"
    _assert_gallery_scope(store)
    slot = gallery_slot(store)
    assert gallery_selectors.get_selection(slot) == [str(b), str(a)]
    assert {it.path for it in gallery_selectors.get_selected_items(slot)} == {
        str(a),
        str(b),
    }
    # Re-selection of the current slot value skips the dispatch (changed-guard).
    n_calls = len(store.get_dispatcher().calls)
    ctrl.set_selection([b, a])
    assert len(store.get_dispatcher().calls) == n_calls


def test_selection_use_case_dispatches_gallery_scope(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    ctrl.open_paths([a])

    selection_uc.commit(ctrl, [a])

    assert dispatched_kinds(store)[-1] == "GallerySelectionSet"
    _assert_gallery_scope(store)
    assert gallery_selectors.get_selection(gallery_slot(store)) == [str(a)]


def test_filter_dispatch_sets_slot_filter_text(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    ctrl.open_paths([a])

    ctrl.set_filter_text("cat")
    ctrl.apply_pending_filter()

    assert dispatched_kinds(store)[-1] == "GalleryFilterSet"
    _assert_gallery_scope(store)
    assert gallery_selectors.get_filter_text(gallery_slot(store)) == "cat"


def test_thumbnails_coalesce_to_one_action(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")
    ctrl.open_paths([a, b])
    n_calls = len(store.get_dispatcher().calls)

    # Completions landing in one turn -> ONE GalleryThumbnailsReady action
    # (same path twice: last status wins, first-seen order kept). The batch
    # is driven directly: without a Qt event loop each _queue_thumb_ready
    # flushes synchronously, which cannot observe turn-coalescing.
    ctrl._pending_thumb_ready.extend(
        [(str(a), "loaded"), (str(b), "error"), (str(b), "loaded")]
    )
    ctrl.flush_pending_thumbnails()

    new_calls = store.get_dispatcher().calls[n_calls:]
    assert [type(action).__name__ for action, _ in new_calls] == [
        "GalleryThumbnailsReady"
    ]
    assert all(scope == GALLERY_SLOT_NAME for _, scope in new_calls)
    slot = gallery_slot(store)
    assert gallery_selectors.get_item_by_path(slot, str(a)).status == "loaded"  # type: ignore[union-attr]
    assert gallery_selectors.get_item_by_path(slot, str(b)).status == "loaded"  # type: ignore[union-attr]


def test_triage_finished_dispatch_sets_summary_and_ranks(tmp_path: Path):
    ctrl, _, store = _make_ctrl()
    a = _img(tmp_path, "a.jpg")
    b = _img(tmp_path, "b.jpg")
    ctrl.open_paths([a, b])
    # Rank lands on the local mirror first (rich local state, not pool
    # membership); the dispatch carries it into the slot.
    ctrl.state.items[0].rank = 1
    ctrl.state.items[1].rank = 2

    assert ctrl._emit_triage_finished("done") is True

    assert dispatched_kinds(store)[-1] == "GalleryTriageFinished"
    _assert_gallery_scope(store)
    slot = gallery_slot(store)
    summary = gallery_selectors.get_triage_summary(slot)
    assert summary["triage_state"] == "done"
    assert summary["ranked"] == 2
    assert gallery_selectors.get_item_by_path(slot, str(a)).rank == 1  # type: ignore[union-attr]
    assert gallery_selectors.get_item_by_path(slot, str(b)).rank == 2  # type: ignore[union-attr]
