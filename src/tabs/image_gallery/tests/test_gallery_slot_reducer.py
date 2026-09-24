"""Gallery slot reducer unit tests — Wave 1 (plan-gallery-redux-2026-09-24).

Covers the frozen W1 interface: pool replace / append+dedup / remove /
selection / filter / thumbnails-ready / triage-finished, reducer purity
(no in-place mutation, new instances via ``dataclasses.replace``), unknown
action identity, None-state init, and the undoable allowlist (progress +
view actions OUT of ``_UNDOABLE_TYPES``).

Headless: pure reducer + dataclasses only, no Qt widgets.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.state_management.dispatcher import _UNDOABLE_TYPES
from core.state_management.gallery_actions import (
    GalleryFilterSet,
    GalleryItemsRemoved,
    GalleryPathsAppended,
    GalleryPoolOpened,
    GalleryPoolReplaced,
    GallerySelectionSet,
    GalleryThumbnailsReady,
    GalleryTriageFinished,
)
from tabs.image_gallery.state.models import (
    GallerySlotState,
    fresh_gallery_slot_state,
)
from tabs.image_gallery.state.reducer import GallerySlotReducer
from tabs.image_gallery.state.selectors import (
    get_filter_text,
    get_folder,
    get_item_by_path,
    get_item_paths,
    get_selected_items,
    get_selection,
    get_triage_summary,
)


def _entries(*paths: str) -> list[tuple[str, int]]:
    return [(p, 1000 + i) for i, p in enumerate(paths)]


def test_pool_opened_replaces_wholesale() -> None:
    state = fresh_gallery_slot_state()
    opened = GallerySlotReducer.reduce(
        state, GalleryPoolOpened(folder="/pics", entries=_entries("/pics/a.png", "/pics/b.png"))
    )
    assert opened is not state
    assert get_item_paths(opened) == ["/pics/a.png", "/pics/b.png"]
    assert get_folder(opened) == "/pics"
    assert get_selection(opened) == []
    assert state.items == []  # input untouched


def test_pool_replaced_wipes_previous_pool() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(),
        GalleryPoolOpened(folder="/pics", entries=_entries("/pics/a.png", "/pics/b.png")),
    )
    replaced = GallerySlotReducer.reduce(
        state, GalleryPoolReplaced(folder=None, entries=_entries("/other/c.png"))
    )
    assert get_item_paths(replaced) == ["/other/c.png"]
    assert get_folder(replaced) is None


def test_paths_appended_dedups() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(),
        GalleryPoolOpened(folder="/pics", entries=_entries("/pics/a.png")),
    )
    appended = GallerySlotReducer.reduce(
        state,
        GalleryPathsAppended(entries=_entries("/pics/a.png", "/pics/b.png", "/pics/b.png")),
    )
    assert get_item_paths(appended) == ["/pics/a.png", "/pics/b.png"]
    # re-drop of only-known paths is a no-op (identical state, no emit)
    assert GallerySlotReducer.reduce(appended, GalleryPathsAppended(entries=_entries("/pics/a.png"))) is appended
    assert GallerySlotReducer.reduce(appended, GalleryPathsAppended(entries=[])) is appended


def test_items_removed_prunes_pool_and_selection() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(),
        GalleryPoolOpened(entries=_entries("/a.png", "/b.png", "/c.png")),
    )
    state = GallerySlotReducer.reduce(state, GallerySelectionSet(selected_ids=["/a.png", "/b.png"]))
    removed = GallerySlotReducer.reduce(state, GalleryItemsRemoved(paths=["/b.png"]))
    assert get_item_paths(removed) == ["/a.png", "/c.png"]
    assert get_selection(removed) == ["/a.png"]
    # removing unknown paths is a no-op
    assert GallerySlotReducer.reduce(removed, GalleryItemsRemoved(paths=["/nope.png"])) is removed
    assert GallerySlotReducer.reduce(removed, GalleryItemsRemoved(paths=[])) is removed


def test_selection_set_wholesale_and_dedup() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(), GalleryPoolOpened(entries=_entries("/a.png", "/b.png"))
    )
    selected = GallerySlotReducer.reduce(
        state, GallerySelectionSet(selected_ids=["/b.png", "/a.png", "/b.png"])
    )
    assert get_selection(selected) == ["/b.png", "/a.png"]
    # selected items resolve in pool order, selection order is kept on the ids
    assert [it.path for it in get_selected_items(selected)] == ["/a.png", "/b.png"]
    # same selection again is a no-op
    assert (
        GallerySlotReducer.reduce(selected, GallerySelectionSet(selected_ids=["/b.png", "/a.png"]))
        is selected
    )
    cleared = GallerySlotReducer.reduce(selected, GallerySelectionSet(selected_ids=[]))
    assert get_selection(cleared) == []


def test_filter_set() -> None:
    state = fresh_gallery_slot_state()
    filtered = GallerySlotReducer.reduce(state, GalleryFilterSet(filter_text="cat"))
    assert get_filter_text(filtered) == "cat"
    assert GallerySlotReducer.reduce(filtered, GalleryFilterSet(filter_text="cat")) is filtered


def test_thumbnails_ready_updates_status() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(), GalleryPoolOpened(entries=_entries("/a.png", "/b.png"))
    )
    ready = GallerySlotReducer.reduce(
        state, GalleryThumbnailsReady(ready=[("/a.png", "loaded")])
    )
    assert ready is not state
    item = get_item_by_path(ready, "/a.png")
    assert item is not None and item.status == "loaded"
    assert get_item_by_path(ready, "/b.png").status == "not_loaded"  # type: ignore[union-attr]
    # unknown paths and identical statuses are no-ops
    assert GallerySlotReducer.reduce(ready, GalleryThumbnailsReady(ready=[("/zz.png", "loaded")])) is ready
    assert GallerySlotReducer.reduce(ready, GalleryThumbnailsReady(ready=[("/a.png", "loaded")])) is ready
    assert GallerySlotReducer.reduce(ready, GalleryThumbnailsReady(ready=[])) is ready


def test_triage_finished_sets_summary_and_ranks() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(), GalleryPoolOpened(entries=_entries("/a.png", "/b.png"))
    )
    done = GallerySlotReducer.reduce(
        state,
        GalleryTriageFinished(
            triage_state="done", mode="fidelity", source_path="/a.png",
            ranks={"/a.png": 1, "/b.png": 2},
        ),
    )
    assert get_triage_summary(done) == {
        "triage_state": "done",
        "mode": "fidelity",
        "source_path": "/a.png",
        "ranked": 2,
    }
    assert get_item_by_path(done, "/a.png").rank == 1  # type: ignore[union-attr]
    assert get_item_by_path(done, "/b.png").rank == 2  # type: ignore[union-attr]
    # identical re-delivery is a no-op
    assert (
        GallerySlotReducer.reduce(
            done,
            GalleryTriageFinished(
                triage_state="done", mode="fidelity", source_path="/a.png",
                ranks={"/a.png": 1, "/b.png": 2},
            ),
        )
        is done
    )


def test_purity_no_mutation() -> None:
    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(), GalleryPoolOpened(entries=_entries("/a.png"))
    )
    snapshot_items = list(state.items)
    snapshot_first = state.items[0]
    before = (state.items[0].status, state.items[0].rank, list(state.selection))
    ready = GallerySlotReducer.reduce(state, GalleryThumbnailsReady(ready=[("/a.png", "loaded")]))
    ranked = GallerySlotReducer.reduce(
        ready, GalleryTriageFinished(triage_state="done", ranks={"/a.png": 1})
    )
    # inputs unchanged: same list object contents, same item instances, same scalars
    assert state.items == snapshot_items
    assert state.items[0] is snapshot_first
    assert (state.items[0].status, state.items[0].rank, state.selection) == (before[0], before[1], before[2])
    assert ready.items[0] is not snapshot_first
    assert ranked.items[0] is not ready.items[0]
    assert isinstance(ranked, GallerySlotState)


def test_none_state_initializes_default() -> None:
    state = GallerySlotReducer.reduce(
        None, GalleryPathsAppended(entries=_entries("/a.png"))
    )
    assert isinstance(state, GallerySlotState)
    assert get_item_paths(state) == ["/a.png"]
    # unknown actions pass None-state through as a fresh default
    fresh = GallerySlotReducer.reduce(None, GalleryFilterSet(filter_text="x"))
    assert isinstance(fresh, GallerySlotState)
    assert get_filter_text(fresh) == "x"


def test_unknown_action_returns_identical_state() -> None:
    from core.state_management.actions import SetSplitPositionAction

    state = GallerySlotReducer.reduce(
        fresh_gallery_slot_state(), GalleryPoolOpened(entries=_entries("/a.png"))
    )
    assert GallerySlotReducer.reduce(state, SetSplitPositionAction(0.5)) is state


def test_undoable_types_membership_and_triage_only() -> None:
    for action_type in (
        "GALLERY_POOL_OPENED",
        "GALLERY_PATHS_APPENDED",
        "GALLERY_POOL_REPLACED",
        "GALLERY_ITEMS_REMOVED",
        "GALLERY_TRIAGE_FINISHED",
    ):
        assert action_type in _UNDOABLE_TYPES, action_type
    for action_type in (
        "GALLERY_SELECTION_SET",
        "GALLERY_FILTER_SET",
        "GALLERY_THUMBNAILS_READY",
    ):
        assert action_type not in _UNDOABLE_TYPES, action_type


def test_registration_shape() -> None:
    from core.state_management import slot_reducers as _slots

    from tabs.image_gallery.bootstrap_reducers import register_gallery_reducers
    from tabs.image_gallery.state.reducer import GallerySlotReducer as _Reducer

    register_gallery_reducers()
    assert _slots._SLOT_REDUCERS.get("gallery") is _Reducer.reduce
