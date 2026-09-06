"""B1: path-only slots + session pixel cache + lazy rehydrate (P6 ordering).

- Project reopen performs ZERO ``load_pixel_store`` calls: restore records
  paths only; tiers fill on demand (async workers), same posture as
  image_compare's lazy ``rehydrate_session``.
- ``rehydrate_slots`` never mutates slot objects in place (S9 removal pin —
  the old ``slot.image = arr`` is gone; tiers arrive via cache + dispatch).
- P6 ordering: a dormant restored session kicks nothing (no чужі toasts);
  activation refreshes first, then demand-fills; delivery renders.
- Restore fills keep the slot on decode failure (layout preserved).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import CompareSlot
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.tab import MultiCompareTab
from tabs.multi_compare.use_cases import persistence


class _CapturingPool:
    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)

    def run_one(self):
        self.workers.pop(0).run()

    def run_all(self, limit: int = 30):
        for _ in range(limit):
            if not self.workers:
                return
            self.workers.pop(0).run()


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown: list = []
        self.updated: list = []
        self.closed: list = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _FakeMcStore:
    """Dispatch-only mutation through the real pure reducer (STORE invariants)."""

    def __init__(self, state=None):
        from tabs.multi_compare.models import MultiCompareState

        self.state = state if state is not None else MultiCompareState()
        self.dispatched: list = []

    def dispatch(self, action):
        self.dispatched.append(action)
        self.state = mc_reduce(self.state, action)


class _FakeWidget:
    def __init__(self, mc_store, toast_manager=None):
        self.store = mc_store
        self.canvas = SimpleNamespace(request_view_update=lambda: None)
        self.images_dropped = SimpleNamespace(connect=lambda *_: None)
        self.add_requested = SimpleNamespace(connect=lambda *_: None)
        self.save_requested = SimpleNamespace(connect=lambda *_: None)
        self.quick_save_requested = SimpleNamespace(connect=lambda *_: None)
        self.settings_requested = SimpleNamespace(connect=lambda *_: None)
        self.help_requested = SimpleNamespace(connect=lambda *_: None)
        self.divider_color_picker_requested = SimpleNamespace(connect=lambda *_: None)
        self.refreshed = 0

    @property
    def state(self):
        return self.store.state

    def refresh_from_session(self):
        self.refreshed += 1


class _FakeSessionStore:
    """Narrow session-slot surface persistence.py needs."""

    def __init__(self, session_ids, active_id):
        self.sessions = {
            sid: SimpleNamespace(id=sid, session_type="multi_compare", state_slots={})
            for sid in session_ids
        }
        self.active_id = active_id

    def get_workspace_session(self, session_id):
        return self.sessions.get(session_id)

    def get_active_workspace_session(self):
        return self.sessions[self.active_id]

    def get_session_state_slot(self, name, session_id=None):
        session = self.sessions.get(session_id or self.active_id)
        return session.state_slots.get(name) if session else None

    def set_session_state_slot(self, name, value, session_id=None, emit_scope=None):
        self.sessions[(session_id or self.active_id)].state_slots[name] = value


def _png(tmp_path, name, size=(96, 64)):
    path = tmp_path / name
    Image.new("RGB", size, (10, 120, 200)).save(path)
    return path


def _session_data(paths):
    return {
        "version": 1,
        "slots": [
            {"id": i, "path": str(p), "label": p.stem} for i, p in enumerate(paths)
        ],
        "root": {
            "type": "split",
            "direction": "h",
            "weights": [1.0] * len(paths),
            "children": [{"type": "leaf", "slot_id": i} for i in range(len(paths))],
        }
        if len(paths) > 1
        else {"type": "leaf", "slot_id": 0},
        "focused_slot_id": None,
        "zoom": 1.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "max_slots": 12,
        "label_settings": {},
        "divider_settings": {},
    }


def _make_bundle(pool, session_store, active_widget_state=None):
    mc_store = _FakeMcStore(active_widget_state)
    widget = _FakeWidget(mc_store)
    toast_manager = _FakeToastManager()
    emitted: list = []
    event_bus = SimpleNamespace(
        emitted=emitted,
        emit=lambda e: emitted.append(e),
        subscribe=lambda *a, **k: None,
    )
    context = SimpleNamespace(
        main_window=SimpleNamespace(toast_manager=toast_manager),
        thread_pool=pool,
        event_bus=event_bus,
        store=SimpleNamespace(settings=SimpleNamespace(auto_crop_black_borders=False)),
    )
    store = SimpleNamespace(settings=SimpleNamespace(auto_crop_black_borders=False))
    controller = MultiCompareController(widget, store=store, context=context)
    tab = MultiCompareTab()
    tab._widget = widget
    tab._controller = controller
    ctx = SimpleNamespace(store=session_store)
    return tab, controller, widget, mc_store, toast_manager, event_bus, ctx


def test_reopen_performs_zero_pixel_store_decodes(tmp_path, monkeypatch):
    """Deserialize + rehydrate of the ACTIVE session: paths only, no
    ``load_pixel_store`` — fills are queued workers (demand), not sync
    decodes (the old ``rehydrate_slots`` decoded every slot on the GUI)."""
    from shared.image_processing import pixel_cache_loader as pcl_mod
    from shared.image_processing import progressive_loader as prog_mod

    pool = _CapturingPool()
    sessions = _FakeSessionStore(["s1"], "s1")
    tab, controller, widget, mc_store, _, _, ctx = _make_bundle(pool, sessions)
    paths = [_png(tmp_path, "a.png"), _png(tmp_path, "b.png")]

    full_calls: list = []
    real_full = pcl_mod.load_pixel_store

    def _spy_full(path_str, **kwargs):
        full_calls.append(str(path_str))
        return real_full(path_str, **kwargs)

    preview_calls: list = []
    real_preview = prog_mod.load_preview_image

    def _spy_preview(path_str, **kwargs):
        preview_calls.append(str(path_str))
        return real_preview(path_str, **kwargs)

    monkeypatch.setattr(pcl_mod, "load_pixel_store", _spy_full)
    monkeypatch.setattr(prog_mod, "load_preview_image", _spy_preview)

    persistence.deserialize_session(tab, "s1", _session_data(paths), ctx)
    # Widget reads the restored (active) session state.
    mc_store.state = sessions.get_session_state_slot(persistence._STATE_SLOT, "s1")
    tab._active_session_id = "s1"
    persistence.rehydrate_session(tab, "s1", ctx)

    state = sessions.get_session_state_slot(persistence._STATE_SLOT, "s1")
    assert [s.path for s in state.slots] == [Path(p) for p in paths]
    assert full_calls == []  # 0 full decodes on reopen (was N sync in GUI)
    assert preview_calls == []  # not even preview ran inline — workers queued
    assert len(pool.workers) == 2  # one demand fill per slot
    assert all(s.revision == 0 for s in state.slots)
    assert widget.refreshed == 1  # unconditional refresh (P6 ordering)

    # Demand phase: preview workers land → preview tier, still 0 full decodes.
    pool.run_one()
    pool.run_one()
    from tabs.multi_compare.pipeline.cache import resolve_slot_source

    assert all(
        resolve_slot_source(controller.pixel_cache, s) is not None
        for s in mc_store.state.slots
    )
    assert full_calls == []
    # Full-res second stage queued per slot (bounded FIFO workers parked in
    # the pool), decodes only when those workers run — after reopen, not in it.
    assert len(pool.workers) == 2


def test_dormant_session_rehydrate_kicks_nothing(tmp_path, monkeypatch):
    """P6 conditional-restore pin: rehydrating a non-active session records
    paths only — no workers, no toasts, no refresh of the visible grid."""
    from shared.image_processing import pixel_cache_loader as pcl_mod
    from shared.image_processing import progressive_loader as prog_mod

    pool = _CapturingPool()
    sessions = _FakeSessionStore(["s-active", "s-dormant"], "s-active")
    tab, controller, widget, mc_store, toast_manager, _, ctx = _make_bundle(
        pool, sessions
    )
    paths = [_png(tmp_path, "a.png"), _png(tmp_path, "b.png")]

    monkeypatch.setattr(
        pcl_mod, "load_pixel_store", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not decode"))
    )
    monkeypatch.setattr(
        prog_mod, "load_preview_image", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not decode"))
    )

    persistence.deserialize_session(tab, "s-dormant", _session_data(paths), ctx)
    tab._active_session_id = "s-active"
    persistence.rehydrate_session(tab, "s-dormant", ctx)

    dormant = sessions.get_session_state_slot(persistence._STATE_SLOT, "s-dormant")
    assert [s.path for s in dormant.slots] == [Path(p) for p in paths]
    assert pool.workers == []
    assert toast_manager.shown == []
    assert widget.refreshed == 0


def test_activation_refreshes_then_demand_fills(tmp_path):
    """P6 repro→fix: switching to a restored path-only session refreshes
    first and kicks demand fills; the delivered tier renders composition."""
    from tabs.multi_compare.services.composition_builder import build_composition_plan

    pool = _CapturingPool()
    sessions = _FakeSessionStore(["s-active", "s-dormant"], "s-active")
    tab, controller, widget, mc_store, _, _, ctx = _make_bundle(pool, sessions)
    paths = [_png(tmp_path, "a.png"), _png(tmp_path, "b.png")]

    persistence.deserialize_session(tab, "s-dormant", _session_data(paths), ctx)
    dormant = sessions.get_session_state_slot(persistence._STATE_SLOT, "s-dormant")
    # Before activation the restored tree is all-imageless → plan None (blank
    # would show without the activation fill — the P6 repro half).
    assert build_composition_plan(dormant) is None

    # Switch: widget now reads the dormant session's state.
    sessions.active_id = "s-dormant"
    mc_store.state = dormant
    tab.on_active_session_changed("s-dormant", ctx)

    assert widget.refreshed == 1  # refresh ran on activation...
    assert len(pool.workers) == 2  # ...and demand fills kicked after it
    pool.run_all()  # preview workers land (+ inline full stage, no pool drain issue)

    from tabs.multi_compare.pipeline.cache import resolve_slot_source

    live = mc_store.state
    assert all(s.revision >= 1 for s in live.slots)
    sources = {
        s.id: resolve_slot_source(controller.pixel_cache, s) for s in live.slots
    }
    assert all(v is not None for v in sources.values())
    plan = build_composition_plan(live, sources=sources)
    assert plan is not None  # restored session renders after demand fill


def test_rehydrate_never_mutates_slots_in_place(tmp_path):
    """S9 pin: rehydrate performs zero in-place writes — slot object
    identity and revisions survive restore untouched (tiers arrive later
    via cache + ``note_slot_pixels`` dispatch, never ``slot.image =``)."""
    pool = _CapturingPool()
    sessions = _FakeSessionStore(["s1"], "s1")
    tab, controller, widget, mc_store, _, _, ctx = _make_bundle(pool, sessions)
    # Missing files: nothing kickable — pure no-op restore.
    data = _session_data([tmp_path / "gone-a.png", tmp_path / "gone-b.png"])
    persistence.deserialize_session(tab, "s1", data, ctx)
    mc_store.state = sessions.get_session_state_slot(persistence._STATE_SLOT, "s1")
    tab._active_session_id = "s1"

    before = list(mc_store.state.slots)
    before_ids = [id(s) for s in before]
    n_dispatched = len(mc_store.dispatched)
    persistence.rehydrate_session(tab, "s1", ctx)

    after = sessions.get_session_state_slot(persistence._STATE_SLOT, "s1")
    assert [id(s) for s in after.slots] == before_ids  # same objects, untouched
    assert all(s.revision == 0 for s in after.slots)
    assert len(mc_store.dispatched) == n_dispatched  # no stealth dispatches
    assert pool.workers == []


def test_restore_fill_failure_keeps_slot(tmp_path):
    """Corrupt-at-restore: the restored slot survives (error toast only) —
    fresh-add drops its staged slot, restore must keep the layout."""
    pool = _CapturingPool()
    sessions = _FakeSessionStore(["s1"], "s1")
    tab, controller, widget, mc_store, _, event_bus, ctx = _make_bundle(pool, sessions)
    bad = tmp_path / "corrupt.png"
    bad.write_bytes(b"not an image at all" * 64)

    persistence.deserialize_session(tab, "s1", _session_data([bad]), ctx)
    mc_store.state = sessions.get_session_state_slot(persistence._STATE_SLOT, "s1")
    tab._active_session_id = "s1"
    persistence.rehydrate_session(tab, "s1", ctx)

    assert len(pool.workers) == 1
    pool.run_all()  # preview fails → keep_slot_on_error path

    assert len(mc_store.state.slots) == 1  # layout preserved
    assert len(event_bus.emitted) == 1  # surfaced, never silent
    assert "corrupt.png" in str(getattr(event_bus.emitted[0], "error", event_bus.emitted[0]))


def test_collect_pixel_cache_sources_returns_open_session_stores(tmp_path):
    """Save path: only this session's live, open pixel stores are offered
    for spill embedding (B1: resolved from the session cache)."""
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    pool = _CapturingPool()
    sessions = _FakeSessionStore(["s1", "s2"], "s1")
    tab, controller, widget, mc_store, _, _, ctx = _make_bundle(pool, sessions)
    file_a = _png(tmp_path, "a.png")
    file_b = _png(tmp_path, "b.png")

    persistence.deserialize_session(tab, "s1", _session_data([file_a]), ctx)
    persistence.deserialize_session(tab, "s2", _session_data([file_b]), ctx)
    store_a = TiledPixelStore.from_path(str(file_a))
    controller.pixel_cache.put_pixel(file_a, store_a)

    sources = persistence.collect_pixel_cache_sources(tab, "s1", ctx)
    assert list(sources.keys()) == [str(file_a)]
    assert sources[str(file_a)] is store_a
    # Other session's path is not offered even though its file exists.
    assert persistence.collect_pixel_cache_sources(tab, "s2", ctx) == {}


def test_slots_carry_no_pixels_and_cache_evict_closes():
    """State shape pin: ``CompareSlot`` has no pixel field; eviction close
    touches cache entries only (undo snapshots hold paths, never stores)."""
    import tabs.multi_compare.pipeline.cache as _cache_mod
    from tabs.multi_compare.pipeline.cache import MultiComparePixelCache

    slot = CompareSlot(id=0, path=Path("a.png"), label="A")
    assert not hasattr(slot, "image")
    assert slot.revision == 0

    class _Store:
        def __init__(self, name):
            self.name = name
            self.is_open = True

    closed: list = []
    real_close = _cache_mod.MultiComparePixelCache._close_store

    def _spy_close(store):
        closed.append(store)
        try:
            store.is_open = False
        except Exception:
            pass

    _cache_mod.MultiComparePixelCache._close_store = staticmethod(_spy_close)
    try:
        cache = MultiComparePixelCache(max_pixel=1, max_preview=1)
        first, second = _Store("first"), _Store("second")
        cache.put_pixel("a.png", first)
        cache.put_pixel("b.png", second)  # evicts a.png (LRU bound 1)
    finally:
        _cache_mod.MultiComparePixelCache._close_store = real_close

    assert closed == [first]
    assert cache.get_pixel("b.png") is second
