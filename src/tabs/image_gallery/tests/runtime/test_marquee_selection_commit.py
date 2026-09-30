"""Marquee selection commit must reach the ``gallery`` slot (bug 1 regression).

User report: a card that was ever in selection mode stays selected forever —
clear it, and it comes back on the next repaint. Root cause: G2 removed the
``view._owner`` back-poke, but the marquee plumbing still resolved the owner
through it, so ``_commit`` never dispatched to the slot; any stale slot
selection was re-rendered on every store emit.

This pins the fix: ``marquee_select._commit`` resolves the controller via
``view._gallery_widget._owner_for_triage()`` and always commits through
``use_cases.selection.commit`` — including the empty, non-additive clear.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool

from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.state import selectors as gallery_selectors
from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    gallery_slot,
    make_gallery_context,
)
from tabs.image_gallery.ui import marquee_select
from tabs.image_gallery.widget import ImageGalleryWidget


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00")
    return p


def _wire(qtbot, tmp_path):
    context, store = make_gallery_context()
    context._tr = lambda key, default: default  # type: ignore[attr-defined]
    w = ImageGalleryWidget(context=context)
    qtbot.addWidget(w)
    ctrl = GalleryController(w, thread_pool=QThreadPool.globalInstance(), context=context)
    ctrl._start_triage = lambda items, **kw: None  # type: ignore[method-assign]
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    w.attach_controller(ctrl)
    a = _img(tmp_path, "a.png")
    b = _img(tmp_path, "b.png")
    ctrl.open_paths([a, b])
    return w, ctrl, store, a, b


def test_marquee_commit_and_clear_dispatch_slot(qtbot, tmp_path):
    w, ctrl, store, a, b = _wire(qtbot, tmp_path)
    view = w._grid_view

    marquee_select._commit(view, {a, b}, additive=False)

    slot = gallery_slot(store)
    assert set(gallery_selectors.get_selection(slot)) == {str(a), str(b)}
    assert view._selection == {str(a), str(b)}

    # Empty, non-additive band clears — and must dispatch, not only repaint.
    marquee_select._commit(view, set(), additive=False)

    assert gallery_selectors.get_selection(gallery_slot(store)) == []
    assert view._selection == set()
    assert ctrl.state.selected_paths == set()

    # A previously selected card must not resurrect on the next store emit.
    store.emit_state_change(GALLERY_SLOT_NAME)

    assert view._selection == set()
    assert gallery_selectors.get_selection(gallery_slot(store)) == []
