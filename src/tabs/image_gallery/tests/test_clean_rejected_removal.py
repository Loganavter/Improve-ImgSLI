"""Regression: clean_rejected removes the moved cards; Undo re-inserts them.

Bug (plan-gallery-fixes-2026-10-14, CLEAN): ``clean_rejected`` rewrote
``it.path`` into ``_rejected/`` and KEPT the item in ``state.items``, then
emitted ``GalleryItemsRemoved(old)`` + ``GalleryPathsAppended(new)`` — so
the moved cards stayed gallery members and ``_refresh_owner_grid``
re-rendered them (the reported "cards stay in the gallery").

Fix mirrors the working sibling ``remove_paths_from_grid``: drop the moved
items from ``state.items``, prune selection/series clusters, emit ONLY the
removal (the ``_rejected/`` locations are not gallery members), refresh the
grid once — and stash the removed item objects on the move records so Undo
re-inserts them (files + cards).

Runs headless (no Qt widgets).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    dispatched_kinds,
    gallery_slot,
    make_gallery_context,
)
from tabs.image_gallery.use_cases import triage as _triage


def _drop_file(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (10, 20, 30)).save(path)


class _RebuildRecorder:
    """Minimal widget double: records every ``rebuild_grid`` list."""

    def __init__(self) -> None:
        self.calls: list[list] = []
        self.refreshed: list = []

    def rebuild_grid(self, items) -> None:
        self.calls.append(list(items))

    def refresh_card(self, item) -> None:
        self.refreshed.append(item)

    def _refresh_action_states(self) -> None:
        pass


def _make_owner(tmp_path: Path, names: list[str], *, with_store: bool = False):
    items = []
    for name in names:
        p = tmp_path / name
        _drop_file(p)
        items.append(
            SimpleNamespace(
                rejected=True,
                triage_rejected=True,
                path=str(p),
                name=name,
                thumbnail=None,
            )
        )
    recorder = _RebuildRecorder()
    state = SimpleNamespace(
        items=items,
        folder=str(tmp_path),
        selected_paths=set(),
        selected_order=[],
    )
    owner = SimpleNamespace(state=state, widget=recorder)
    store = None
    if with_store:
        context, store = make_gallery_context()
        owner.context = context
    return owner, recorder, store


def test_clean_rejected_removes_moved_cards(tmp_path: Path) -> None:
    """After the move the cards are gone from the pool and the rebuild list."""
    owner, recorder, _ = _make_owner(tmp_path, ["a.png", "b.png"])

    moves = _triage.clean_rejected(owner)

    assert len(moves) == 2
    # Files landed in _rejected/, originals gone.
    for name in ("a.png", "b.png"):
        assert (tmp_path / "_rejected" / name).is_file()
        assert not (tmp_path / name).exists()
    # Cards dropped from the local pool — nothing points into _rejected/.
    assert owner.state.items == []
    # And the grid rebuild never saw the moved locations.
    assert recorder.calls
    assert recorder.calls[-1] == []


def test_clean_rejected_emits_only_removal(tmp_path: Path) -> None:
    """The slot sees one GalleryItemsRemoved — no re-append of _rejected/."""
    from core.state_management.gallery_actions import GalleryPoolOpened

    owner, _recorder, store = _make_owner(tmp_path, ["a.png", "b.png"], with_store=True)
    originals = [str(it.path) for it in owner.state.items]
    # Seed the slot pool with the originals (mirrors a loaded session).
    store.transact(
        [GalleryPoolOpened(folder=str(tmp_path), entries=[(p, 0) for p in originals])]
    )
    store.get_dispatcher().calls.clear()

    moves = _triage.clean_rejected(owner)

    assert len(moves) == 2
    assert dispatched_kinds(store) == ["GalleryItemsRemoved"]
    assert [it.path for it in gallery_slot(store).items] == []
    # The removed paths were the originals, never the _rejected/ targets.
    (action, _scope) = store.get_dispatcher().calls[0]
    assert sorted(action.paths) == sorted(originals)


def test_clean_rejected_prunes_selection(tmp_path: Path) -> None:
    owner, _recorder, _ = _make_owner(tmp_path, ["a.png", "b.png", "c.png"])
    owner.state.items[0].rejected = False
    owner.state.items[0].triage_rejected = False
    a = str(owner.state.items[0].path)
    b = str(owner.state.items[1].path)
    owner.state.selected_paths = {a, b}
    owner.state.selected_order = [a, b]

    _triage.clean_rejected(owner)

    assert owner.state.selected_paths == {a}
    assert owner.state.selected_order == [a]


def test_restore_moves_reinserts_cards(tmp_path: Path) -> None:
    """Undo brings the files AND the cards back."""
    owner, recorder, _ = _make_owner(tmp_path, ["a.png", "b.png"])
    original = [str(it.path) for it in owner.state.items]
    moved_items = list(owner.state.items)

    moves = _triage.clean_rejected(owner)
    assert owner.state.items == []

    restored = _triage.restore_moves(owner, moves)

    assert restored == 2
    assert [str(it.path) for it in owner.state.items] == original
    # Same item objects (identity) — cards restored, not rebuilt from scratch.
    assert owner.state.items == moved_items
    for name in ("a.png", "b.png"):
        assert (tmp_path / name).is_file()
    assert recorder.calls[-1] == moved_items
