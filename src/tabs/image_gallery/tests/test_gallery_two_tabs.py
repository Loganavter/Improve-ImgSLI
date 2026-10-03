"""Two live gallery copies must not clobber each other (Wave ISO).

Regression for the session-isolation bug: both the controller and the
widget subscribed globally (``scope == 'gallery'``) and read the slot via
the ACTIVE session, so opening tab B (empty/loading slot) replaced tab A's
grouped mirror. Every live copy now owns its ``session_id`` and skips emits
while inactive; activation re-renders from the OWN slot.

Offscreen throughout: fake two-session store (real ``GallerySlotReducer``
via ``_gallery_dispatch_doubles``), widget doubles for the controller half,
a real ``ImageGalleryWidget`` for the render half, no window switching.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core.state_management.gallery_actions import (
    GalleryFilterSet,
    GalleryPoolOpened,
    GallerySelectionSet,
    GalleryTriageFinished,
)
from tabs.image_gallery.tests._gallery_dispatch_doubles import (
    FakeGallerySession,
    FakeGalleryStore,
    make_gallery_context,
)

A1, A2 = "/pics/a1.png", "/pics/a2.png"
B1 = "/other/b1.png"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _DropPool:
    """Synchronous no-op thread pool: background workers are dropped."""

    def start(self, worker, *args, **kwargs):
        return None


def _widget_double():
    from PySide6.QtCore import QObject, Signal

    class _W(QObject):
        folder_pick_requested = Signal()
        analyze_requested = Signal(object)
        filter_text_changed = Signal(str)

        def __init__(self):
            super().__init__()
            self.labels: list = []
            self.grids: list = []

        def set_folder_label(self, folder):
            self.labels.append(folder)

        def rebuild_grid(self, items):
            self.grids.append(list(items))

    return _W()


def _two_session_store() -> FakeGalleryStore:
    ctx, store = make_gallery_context("A")
    store._sessions["B"] = FakeGallerySession("B")
    store._active_id = "A"
    return store


def _bind_maybe(obj, session_id: str) -> None:
    bind = getattr(obj, "bind_gallery_session", None)
    if callable(bind):
        bind(session_id)


def _controller_for(store, session_id: str):
    from tabs.image_gallery.controller import GalleryController

    ctx = SimpleNamespace(store=store)
    ctrl = GalleryController(
        _widget_double(), thread_pool=_DropPool(), context=ctx
    )
    _bind_maybe(ctrl, session_id)
    return ctrl


def _open_grouped_pool(ctrl, folder: str, entries: list[str]) -> None:
    """Dispatch a grouped pool + selection/filter/triage via the copy itself."""
    ctrl._emit_gallery(
        GalleryPoolOpened(
            folder=folder, entries=[(p, 1000 + i) for i, p in enumerate(entries)]
        )
    )
    ctrl._emit_gallery(GallerySelectionSet(selected_ids=[entries[-1]]))
    ctrl._emit_gallery(GalleryFilterSet(filter_text="keep"))
    ctrl._emit_gallery(
        GalleryTriageFinished(triage_state="done", mode=None, source_path=None, ranks={})
    )
    # Mirror the slot the way an activation restore would.
    ctrl._sync_from_slot()


def _mirror_snapshot(ctrl) -> dict:
    return {
        "items": [str(it.path) for it in ctrl.state.items],
        "selection": [str(p) for p in ctrl.state.selected_order],
        "filter": ctrl.state.filter_text,
        "folder": str(ctrl.state.folder) if ctrl.state.folder else None,
    }


def test_inactive_copy_ignores_foreign_pool_emits() -> None:
    """B's pool dispatches (incl. the EMPTY intermediate) leave A's mirror intact."""
    store = _two_session_store()
    ctrl_a = _controller_for(store, "A")
    _open_grouped_pool(ctrl_a, "/pics", [A1, A2])
    before = _mirror_snapshot(ctrl_a)
    assert before["items"] == [A1, A2]
    assert before["selection"] == [A2]

    ctrl_b = _controller_for(store, "B")
    store._active_id = "B"

    # The killer timing: tab 2 opens on an empty/loading slot first.
    ctrl_b._emit_gallery(GalleryPoolOpened(folder="/other", entries=[]))
    ctrl_a._on_store_changed("gallery")
    assert _mirror_snapshot(ctrl_a) == before

    # Then the loaded pool lands — still none of A's business.
    ctrl_b._emit_gallery(GalleryPoolOpened(folder="/other", entries=[(B1, 7)]))
    ctrl_a._on_store_changed("gallery")
    assert _mirror_snapshot(ctrl_a) == before


def test_activation_round_trip_keeps_both_pools(qapp) -> None:
    """A -> B -> A: each activation restores that session's OWN slot."""
    del qapp
    store = _two_session_store()
    ctrl_a = _controller_for(store, "A")
    _open_grouped_pool(ctrl_a, "/pics", [A1, A2])
    snap_a = _mirror_snapshot(ctrl_a)

    ctrl_b = _controller_for(store, "B")
    store._active_id = "B"
    _open_grouped_pool(ctrl_b, "/other", [B1])
    snap_b = _mirror_snapshot(ctrl_b)
    assert snap_b["items"] == [B1]

    # A was untouched by B's dispatches (inactive skip).
    ctrl_a._on_store_changed("gallery")
    assert _mirror_snapshot(ctrl_a) == snap_a

    # Switch back to A: restore from A's own slot.
    store._active_id = "A"
    ctrl_a._sync_from_slot()
    assert _mirror_snapshot(ctrl_a) == snap_a

    # And B still restores cleanly afterwards.
    store._active_id = "B"
    ctrl_b._sync_from_slot()
    assert _mirror_snapshot(ctrl_b) == snap_b


def test_widget_render_ignores_foreign_pool_while_inactive(qapp) -> None:
    """The widget half skips foreign-slot renders while its copy is inactive."""
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.widget import ImageGalleryWidget

    store = _two_session_store()
    ctx = SimpleNamespace(store=store)
    widget_a = ImageGalleryWidget(None, context=None)
    widget_a._context = ctx
    widget_a._init_gallery_store_subscription()
    _bind_maybe(widget_a, "A")

    items = [GalleryItem(path=Path(A1), mtime_ns=1), GalleryItem(path=Path(A2), mtime_ns=2)]
    widget_a._items = list(items)
    widget_a._series = []
    before = [str(it.path) for it in widget_a._items]

    # B opens elsewhere: empty slot first, then loaded.
    store._active_id = "B"
    store.get_dispatcher().dispatch(
        GalleryPoolOpened(folder="/other", entries=[]), scope="gallery"
    )
    widget_a._on_gallery_store_changed("gallery")
    assert [str(it.path) for it in widget_a._items] == before

    store.get_dispatcher().dispatch(
        GalleryPoolOpened(folder="/other", entries=[(B1, 7)]), scope="gallery"
    )
    widget_a._on_gallery_store_changed("gallery")
    assert [str(it.path) for it in widget_a._items] == before


def test_tab_reactivation_refreshes_from_own_slot(qapp) -> None:
    """``on_activated`` re-renders from the OWN slot even when the id is unchanged
    (emits skipped while inactive left the mirror stale)."""
    from tabs.image_gallery.tab import ImageGalleryTab

    del qapp
    store = _two_session_store()
    ctrl_a = _controller_for(store, "A")
    _open_grouped_pool(ctrl_a, "/pics", [A1, A2])
    snap_a = _mirror_snapshot(ctrl_a)

    tab = ImageGalleryTab()
    tab._controller = ctrl_a
    widget_double = _widget_double()
    widget_double.setFocus = lambda *a, **k: None  # type: ignore[attr-defined]
    tab._widget = widget_double
    tab._active_session_id = "A"

    # Simulate missed emits while inactive: the mirror went stale.
    ctrl_a.state.items = []
    assert _mirror_snapshot(ctrl_a)["items"] == []

    ctx = SimpleNamespace(store=store)
    store._active_id = "A"
    tab.on_activated(ctx)
    assert _mirror_snapshot(ctrl_a) == snap_a


def test_background_worker_completion_dispatches_into_own_slot() -> None:
    """Wave CORE write side: B's late worker completion arriving while A is
    ACTIVE lands in B's OWN slot — never in the foreign active session's.

    Before session-targeted dispatch, ``_emit_gallery`` addressed the active
    session, so a background tab's thumbnail/triage/analysis completion
    finishing after a tab switch clobbered the newly-active tab's pool.
    """
    from core.state_management.gallery_actions import GalleryThumbnailsReady
    from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
    from tabs.image_gallery.state import selectors as gallery_selectors

    store = _two_session_store()
    ctrl_a = _controller_for(store, "A")
    _open_grouped_pool(ctrl_a, "/pics", [A1, A2])

    ctrl_b = _controller_for(store, "B")
    # A stays active throughout: B is the background tab whose worker
    # finishes late (thumbnail completion for its just-opened pool).
    assert store._active_id == "A"
    ctrl_b._emit_gallery(GalleryPoolOpened(folder="/other", entries=[(B1, 7)]))
    ctrl_b._emit_gallery(GalleryThumbnailsReady(ready=[(B1, "loaded")]))

    slot_a = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id="A")
    slot_b = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id="B")
    assert gallery_selectors.get_item_paths(slot_a) == [A1, A2]
    assert gallery_selectors.get_item_paths(slot_b) == [B1]
    assert gallery_selectors.get_item_by_path(slot_b, B1).status == "loaded"
    # A's mirror never saw B's writes (inactive skip on the read side).
    ctrl_a._on_store_changed("gallery")
    assert _mirror_snapshot(ctrl_a)["items"] == [A1, A2]


def test_retriage_quiet_regroups_restored_pool(monkeypatch) -> None:
    """Restore brings the pool back FLAT — retriage regroups it quietly."""
    from tabs.image_gallery.models import GalleryItem, TriageState

    store = _two_session_store()
    ctrl = _controller_for(store, "A")
    ctrl.state.items = [
        GalleryItem(path=Path(f"/p/{n}.png"), mtime_ns=1) for n in range(3)
    ]
    ctrl.state.triage_state = TriageState.IDLE
    calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: calls.append((list(items), cover_grid)),
    )
    assert ctrl.retriage_quiet() is True
    assert len(calls) == 1 and calls[0][1] is False
    assert [str(it.path) for it in calls[0][0]] == [f"/p/{n}.png" for n in range(3)]


def test_retriage_quiet_skips_empty_and_running(monkeypatch) -> None:
    from tabs.image_gallery.models import TriageState

    store = _two_session_store()
    ctrl = _controller_for(store, "A")
    calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: calls.append(True),
    )
    ctrl.state.items = []
    assert ctrl.retriage_quiet() is False
    from tabs.image_gallery.models import GalleryItem

    ctrl.state.items = [GalleryItem(path=Path("/p/x.png"), mtime_ns=1)]
    ctrl.state.triage_state = TriageState.RUNNING
    assert ctrl.retriage_quiet() is False
    assert calls == []


def test_session_switch_regroups_restored_pool() -> None:
    """Gallery→gallery switches land in on_active_session_changed (not
    on_activated) — the restored flat pool must regroup there too."""
    from tabs.image_gallery.tab import ImageGalleryTab

    calls: list = []
    ctrl = SimpleNamespace(
        bind_gallery_session=lambda sid: None,
        retriage_quiet=lambda: calls.append(True) or True,
    )
    tab = ImageGalleryTab()
    tab._controller = ctrl
    tab._widget = None
    tab._active_session_id = "sess-A"
    tab.on_active_session_changed(
        "sess-B", SimpleNamespace(store=None)
    )
    assert calls == [True]
    assert tab._active_session_id == "sess-B"


def _painted_pngs(tmp_path, names, color=(200, 30, 30)):
    from PIL import Image

    out = []
    for n in names:
        p = tmp_path / n
        Image.new("RGB", (64, 64), color).save(p)
        out.append(p)
    return out


def test_retriage_quiet_sync_when_cached(qapp, tmp_path, monkeypatch) -> None:
    """All signatures cached → inline regroup, no worker hop, series now."""
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.services import clustering as _clustering

    _clustering.clear_signature_cache()
    paths = _painted_pngs(tmp_path, ["s1.png", "s2.png"])
    for p in paths:
        _clustering.signature_for(p)
    store = _two_session_store()
    ctrl = _controller_for(store, "A")
    ctrl.state.items = [GalleryItem(path=p, mtime_ns=1) for p in paths]
    from tabs.image_gallery.models import TriageState

    ctrl.state.triage_state = TriageState.IDLE
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(True),
    )
    assert ctrl.retriage_quiet() is True
    assert triage_calls == []
    assert len(ctrl.state.series) == 1  # grouped synchronously, no ticks


def test_retriage_quiet_worker_fallback_when_uncached(tmp_path, monkeypatch) -> None:
    from tabs.image_gallery.models import GalleryItem, TriageState
    from tabs.image_gallery.services import clustering as _clustering

    _clustering.clear_signature_cache()
    (tmp_path / "u1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    store = _two_session_store()
    ctrl = _controller_for(store, "A")
    ctrl.state.items = [GalleryItem(path=tmp_path / "u1.png", mtime_ns=1)]
    ctrl.state.triage_state = TriageState.IDLE
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(cover_grid),
    )
    assert ctrl.retriage_quiet() is True
    assert triage_calls == [False]


def test_triage_tail_skips_repeated_analyses(qapp, tmp_path, monkeypatch) -> None:
    """Same content twice → Stage-2 analyses start once, tie-break unaffected."""
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.services import clustering as _clustering

    _clustering.clear_signature_cache()
    paths = _painted_pngs(tmp_path, ["m1.png", "m2.png"])
    store = _two_session_store()
    ctrl = _controller_for(store, "A")
    ctrl.state.items = [GalleryItem(path=p, mtime_ns=1) for p in paths]
    analysis_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_artifact_analysis", lambda *a, **k: analysis_calls.append("a")
    )
    monkeypatch.setattr(
        ctrl, "_start_fidelity_analysis", lambda *a, **k: analysis_calls.append("f")
    )
    ctrl._apply_triage_result([], None, None)
    assert sorted(analysis_calls) == ["a", "f"]
    ctrl._apply_triage_result([], None, None)
    assert sorted(analysis_calls) == ["a", "f"]  # skipped: same fingerprint
    ctrl.state.items[0].artifacts = {"x": "y"}  # type: ignore[attr-defined]
    ctrl._apply_triage_result([], None, None)
    assert sorted(analysis_calls) == ["a", "a", "f", "f"]  # changed → rerun


def test_signatures_cached_unit(tmp_path) -> None:
    from tabs.image_gallery.services import clustering as _clustering

    _clustering.clear_signature_cache()
    assert _clustering.signatures_cached([]) is False
    a = tmp_path / "c1.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert _clustering.signatures_cached([a]) is False
    _clustering.signature_for(a)
    assert _clustering.signatures_cached([a]) is True
    assert _clustering.signatures_cached([tmp_path / "nope.png"]) is False
