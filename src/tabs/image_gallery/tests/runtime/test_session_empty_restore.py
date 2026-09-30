"""Session-isolation: an empty gallery session must show an empty view.

Regression for "closed the gallery, opened a new gallery tab, the old image
was still there": ``restore_from`` used to ``return`` on an empty/absent
slot, leaving the controller-local mirror + grid on the previous session's
pool. The slot is authoritative — restore clears (``clear_to_empty``), and
closing the last gallery session clears when no gallery session is active.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from core.state_management.gallery_actions import GalleryPoolOpened
from tabs.contract import TabContext
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.tab import ImageGalleryTab
from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    FakeGallerySession,
    FakeGalleryStore,
)


def _ctx_with(store: FakeGalleryStore) -> TabContext:
    ctx = TabContext()
    ctx.store = store  # type: ignore[attr-defined]
    return ctx


def _open_tab_with_pool(tmp_path: Path, qtbot, store: FakeGalleryStore):
    """Real tab+page on *store*; session A carries one pooled image."""
    parent = tmp_path / "Imgs"
    parent.mkdir(exist_ok=True)
    a = parent / "a.jpg"
    a.write_bytes(b"\x00")
    tab = ImageGalleryTab()
    host = QWidget()
    qtbot.addWidget(host)
    ctx = _ctx_with(store)
    page = tab.create_page(host, ctx)
    qtbot.addWidget(page)
    store.get_dispatcher().dispatch(
        GalleryPoolOpened(folder=str(parent), entries=[(str(a), 1)]),
        scope=GALLERY_SLOT_NAME,
    )
    tab.on_active_session_changed("A", ctx)
    assert [str(i.path) for i in tab._controller.state.items] == [str(a)]
    assert [str(i.path) for i in tab._widget._items] == [str(a)]
    # NOTE: keep `host` alive — its C++ object parents the page; dropping
    # the last python ref deletes the whole widget tree (shiboken).
    return tab, ctx, a, host


def _assert_empty_view(tab: ImageGalleryTab) -> None:
    assert tab._controller.state.items == []
    assert tab._widget._items == []
    assert tab._widget._series == []
    assert (
        tab._widget._content_stack.currentWidget() is tab._widget._empty_state
    )


def test_switch_to_empty_session_clears_pool(tmp_path: Path, qtbot):
    store = FakeGalleryStore("A")
    store._sessions["B"] = FakeGallerySession("B")
    tab, ctx, _a, _host = _open_tab_with_pool(tmp_path, qtbot, store)
    store._active_id = "B"
    tab.on_active_session_changed("B", ctx)
    _assert_empty_view(tab)


def test_close_last_gallery_session_clears_view(tmp_path: Path, qtbot):
    store = FakeGalleryStore("A")
    tab, ctx, _a, _host = _open_tab_with_pool(tmp_path, qtbot, store)
    # Last gallery session goes away: no active session remains.
    store._sessions.pop("A")
    store._active_id = None  # type: ignore[assignment]
    tab.on_session_closed("A", ctx)
    _assert_empty_view(tab)


def test_close_with_other_gallery_session_keeps_restore(tmp_path: Path, qtbot):
    store = FakeGalleryStore("A")
    store._sessions["B"] = FakeGallerySession("B")
    tab, ctx, _a, _host = _open_tab_with_pool(tmp_path, qtbot, store)
    # Closing A while B is active must not wipe B's restore: the close
    # clears (no gallery session active *at close time* only if B is not
    # active — here B IS active, so close is a no-op for the view), then
    # activation of B restores its (empty) slot.
    store._active_id = "B"
    tab.on_session_closed("A", ctx)
    tab.on_active_session_changed("B", ctx)
    _assert_empty_view(tab)
