"""Phase 2b+3 — bounded gallery scheduler + unified proxy wiring.

Guards the measured Phase-0 waste (open_folder queued N thumbnail
workers + the triage tail fanned out three whole-pool batch workers on
QThreadPool.globalInstance()): one ``GalleryController.schedule(items,
priority)`` entry owns gallery concurrency on a dedicated pool, thumbs
for ``widget.visible_paths()`` go first with the rest draining from a
pausable background queue, and the triage tail is a single chunked
proxy step (50 items per worker) delivered strictly by path.

Conventions: storeless controller doubles (context=None), a dedicated
per-test QThreadPool (never globalInstance), module-attr monkeypatches
for decode/worker bodies, qtbot.waitUntil for cross-thread delivery.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QThreadPool

from tabs.image_gallery import controller as _ctrl_module
from tabs.image_gallery.controller import (
    BACKGROUND_THUMB_PRIORITY,
    VISIBLE_THUMB_PRIORITY,
    GalleryController,
    _scheduler_thread_count,
)
from tabs.image_gallery.models import GalleryItem, Mode, ThumbnailStatus


class _SignalStub:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a, **kw):
        for fn in list(self._slots):
            fn(*a, **kw)


class _WidgetStub:
    """Controller double with the Phase-2a visible-range API."""

    def __init__(self, visible: list[Path] | None = None):
        self.folder_pick_requested = _SignalStub()
        self.analyze_requested = _SignalStub()
        self.filter_text_changed = _SignalStub()
        self.visible_range_changed = _SignalStub()
        self._visible = list(visible or [])
        self._items: list = []
        self.refreshed: list = []
        self.bg_progress: list[tuple[int, int]] = []
        self._filters = []

    def visible_paths(self) -> list[Path]:
        return list(self._visible)

    def installEventFilter(self, filt) -> None:
        self._filters.append(filt)

    def set_folder_label(self, folder) -> None:
        pass

    def rebuild_grid(self, items) -> None:
        self._items = list(items)

    def refresh_card(self, item) -> None:
        self.refreshed.append(item)

    def refresh_cards(self, items) -> None:
        self.refreshed.extend(items)

    def set_triage(self, *a) -> None:
        pass

    def set_scanning(self, *a) -> None:
        pass

    def set_background_scanning(self, n: int, total: int) -> None:
        self.bg_progress.append((int(n), int(total)))

    def set_triage_done(self) -> None:
        pass

    def set_card_visible(self, path, visible: bool) -> None:
        pass

    def reset_session_view(self) -> None:
        pass

    def pick_folder_dialog(self, start_dir: str = ""):
        return None


def _make_ctrl(widget: _WidgetStub, *, max_threads: int = 4) -> tuple[GalleryController, QThreadPool]:
    pool = QThreadPool()
    pool.setMaxThreadCount(max_threads)
    ctrl = GalleryController(widget, thread_pool=pool, context=None)
    return ctrl, pool


def _items(n: int, tag: str = "sched") -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{tag}_{i:03d}.png"), mtime_ns=i)
        for i in range(n)
    ]


@pytest.fixture()
def real_thumb(monkeypatch, tmp_path: Path):
    """Fake thumbnail body returning one real tiny PNG (QPixmap loads)."""
    from PIL import Image

    cover = tmp_path / "cover.png"
    Image.new("RGB", (32, 32), (10, 120, 200)).save(cover)
    started: list[str] = []

    def _fake(path, mtime_ns, **kw):
        started.append(str(path))
        return cover

    monkeypatch.setattr(_ctrl_module, "render_and_cache_thumbnail", _fake)
    return started


def test_scheduler_thread_count_bounds() -> None:
    assert 4 <= _scheduler_thread_count() <= 8


def test_visible_thumbs_land_before_offscreen(qtbot, real_thumb) -> None:
    """Offscreen order: visible cards decode before background ones."""
    items = _items(8)
    widget = _WidgetStub(visible=[it.path for it in items[:3]])
    ctrl, _pool = _make_ctrl(widget, max_threads=1)  # single lane: strict order
    ctrl.state.items = list(items)
    ctrl._begin_folder_schedule(items, ctrl._folder_gen)
    qtbot.waitUntil(lambda: len(real_thumb) == len(items), timeout=8000)
    qtbot.waitUntil(
        lambda: all(it.thumbnail_status == ThumbnailStatus.LOADED for it in items),
        timeout=8000,
    )
    first_three = set(real_thumb[:3])
    assert first_three == {str(it.path) for it in items[:3]}
    assert set(real_thumb) == {str(it.path) for it in items}


def test_scroll_reprioritizes_newly_visible(qtbot, real_thumb, monkeypatch) -> None:
    """visible_range_changed jumps newly visible items to the front."""
    items = _items(6)
    widget = _WidgetStub(visible=[it.path for it in items[:2]])
    ctrl, _pool = _make_ctrl(widget, max_threads=1)
    ctrl.state.items = list(items)
    ctrl.pause_background()  # background lane held: only visible starts
    ctrl._begin_folder_schedule(items, ctrl._folder_gen)
    qtbot.waitUntil(lambda: len(real_thumb) == 2, timeout=8000)
    assert set(real_thumb) == {str(it.path) for it in items[:2]}
    # Scroll: a later card becomes visible mid-flight.
    widget._visible = [items[5].path]
    widget.visible_range_changed.emit([items[5].path])
    qtbot.waitUntil(lambda: len(real_thumb) == 3, timeout=8000)
    assert real_thumb[2] == str(items[5].path)
    # Resume drains the held background lane without further input.
    ctrl.resume_background()
    qtbot.waitUntil(lambda: len(real_thumb) == len(items), timeout=8000)


def test_background_queue_drains_without_user_input(qtbot, real_thumb) -> None:
    items = _items(10)
    widget = _WidgetStub(visible=[items[0].path])
    ctrl, _pool = _make_ctrl(widget, max_threads=2)
    ctrl.state.items = list(items)
    ctrl._begin_folder_schedule(items, ctrl._folder_gen)
    qtbot.waitUntil(
        lambda: all(it.thumbnail_status == ThumbnailStatus.LOADED for it in items),
        timeout=8000,
    )
    assert ctrl.sched_stats()["pending"] == 0


def test_pause_holds_background_and_resume_drains(qtbot, real_thumb) -> None:
    items = _items(6)
    widget = _WidgetStub(visible=[items[0].path])
    ctrl, _pool = _make_ctrl(widget, max_threads=2)
    ctrl.state.items = list(items)
    ctrl.pause_background()
    ctrl._begin_folder_schedule(items, ctrl._folder_gen)
    qtbot.waitUntil(lambda: len(real_thumb) >= 1, timeout=8000)
    # Background lane held: only the visible card starts.
    qtbot.wait(300)
    assert set(real_thumb) == {str(items[0].path)}
    assert ctrl.sched_stats()["queued"] == len(items) - 1
    ctrl.resume_background()
    qtbot.waitUntil(lambda: len(real_thumb) == len(items), timeout=8000)


def test_folder_switch_drops_stale_queue_and_deliveries(qtbot, real_thumb) -> None:
    """Switch mid-flight: queued old-gen entries never start; late
    deliveries from the old gen never land."""
    old = _items(6, tag="old")
    new = _items(3, tag="new")
    widget = _WidgetStub(visible=[it.path for it in old[:1]])
    ctrl, _pool = _make_ctrl(widget, max_threads=2)
    ctrl.state.items = list(old)
    ctrl.pause_background()
    ctrl._begin_folder_schedule(old, ctrl._folder_gen)
    qtbot.waitUntil(lambda: len(real_thumb) >= 1, timeout=8000)
    stale_gen = ctrl._folder_gen
    # Folder switch: generation bumps, paused leftovers drop.
    ctrl._next_folder_gen()
    ctrl.state.items = list(new)
    assert ctrl.sched_stats()["queued"] == 0
    ctrl.resume_background()
    qtbot.wait(400)
    # Old background entries never started — only the pre-switch visible
    # card decoded.
    assert set(real_thumb) == {str(old[0].path)}
    # Direct stale delivery is dropped by the gen check (backstop).
    before = {str(it.path): it.thumbnail_status for it in new}
    ctrl._on_thumbnail_ready(old[2].path, old[2].path, stale_gen)
    after = {str(it.path): it.thumbnail_status for it in new}
    assert before == after
    assert ctrl._find_item(old[2].path) is None


def test_pool_depth_bounded_under_synthetic_load(qtbot, monkeypatch) -> None:
    """12 blocked thumbs on a 2-lane pool: active/peak never exceed cap."""
    gate = threading.Event()
    started: list[str] = []

    def _blocking(path, mtime_ns, **kw):
        started.append(str(path))
        assert gate.wait(15)
        return None  # fail-closed delivery (ERROR card), still accounted

    monkeypatch.setattr(_ctrl_module, "render_and_cache_thumbnail", _blocking)
    items = _items(12)
    widget = _WidgetStub()
    ctrl, pool = _make_ctrl(widget, max_threads=2)
    ctrl.state.items = list(items)
    for it in items:
        ctrl._load_thumbnail(it)
    qtbot.waitUntil(lambda: ctrl.sched_stats()["active"] == 2, timeout=8000)
    stats = ctrl.sched_stats()
    assert stats["active"] <= 2
    assert stats["peak"] <= 2
    assert pool.activeThreadCount() <= 2
    assert stats["pending"] == len(items)
    gate.set()
    qtbot.waitUntil(lambda: ctrl.sched_stats()["pending"] == 0, timeout=15000)
    assert set(started) == {str(it.path) for it in items}


def test_kill_switch_no_thumbs(monkeypatch, qtbot, real_thumb) -> None:
    monkeypatch.setenv("IMGSLI_GALLERY_NO_THUMBS", "1")
    items = _items(4)
    widget = _WidgetStub()
    ctrl, _pool = _make_ctrl(widget)
    ctrl.state.items = list(items)
    assert ctrl.schedule(items, VISIBLE_THUMB_PRIORITY) == 0
    assert real_thumb == []
    assert all(it.thumbnail_status != ThumbnailStatus.LOADED for it in items)


def test_kill_switches_skip_proxy_stages(monkeypatch, qtbot) -> None:
    from tabs.image_gallery.services import proxy as _proxy

    calls: list = []

    def _fake(items, source, *, include_camera=False):
        calls.append((len(items), source, include_camera))
        return {}

    monkeypatch.setattr(_proxy, "run_proxy_stages_sync", _fake)
    items = _items(4)
    widget = _WidgetStub()
    ctrl, _pool = _make_ctrl(widget)
    ctrl.state.items = list(items)
    # All Stage-2 lanes off: no worker at all.
    monkeypatch.setenv("IMGSLI_GALLERY_NO_ARTIFACTS", "1")
    monkeypatch.setenv("IMGSLI_GALLERY_NO_FIDELITY", "1")
    monkeypatch.setenv("IMGSLI_GALLERY_NO_CAMERA", "1")
    ctrl._start_proxy_analysis(list(items), Path("/src.png"), Mode.CAMERA)
    qtbot.wait(300)
    assert calls == []
    # Legacy per-stage entry points honor their own flags too.
    ran: list = []

    def _boom(_items, _source):
        ran.append(1)
        return {}

    monkeypatch.setattr(ctrl, "_run_artifacts_sync", _boom)
    ctrl._start_artifact_analysis(list(items), Path("/src.png"))
    qtbot.wait(300)
    assert ran == []


def test_proxy_chunking_and_progress(monkeypatch, qtbot) -> None:
    """120 items -> 3 chunk workers (50/50/20); progress only multi-chunk."""
    from tabs.image_gallery.services import proxy as _proxy

    calls: list[tuple[int, object, bool]] = []

    def _fake(items, source, *, include_camera=False):
        calls.append((len(items), source, include_camera))
        return {}

    monkeypatch.setattr(_proxy, "run_proxy_stages_sync", _fake)
    items = _items(120, tag="chunk")
    widget = _WidgetStub()
    ctrl, _pool = _make_ctrl(widget, max_threads=2)
    ctrl.state.items = list(items)
    ctrl._start_proxy_analysis(list(items), Path("/src.png"), Mode.FIDELITY)
    qtbot.waitUntil(lambda: len(calls) == 3, timeout=8000)
    assert sorted(c[0] for c in calls) == [20, 50, 50]
    assert all(c[1] == Path("/src.png") for c in calls)
    assert all(c[2] is False for c in calls)
    qtbot.waitUntil(lambda: len(widget.bg_progress) == 3, timeout=8000)
    assert widget.bg_progress == [(1, 3), (2, 3), (3, 3)]
    # Single-chunk (small folder): silent, no progress hook traffic.
    widget.bg_progress.clear()
    small = _items(10, tag="small")
    ctrl.state.items = list(small)
    ctrl._start_proxy_analysis(list(small), Path("/src.png"), Mode.FIDELITY)
    qtbot.waitUntil(lambda: len(calls) == 4, timeout=8000)
    qtbot.waitUntil(lambda: ctrl._proxy_done == 1, timeout=8000)
    assert widget.bg_progress == []


def test_proxy_delivery_applies_strictly_by_path(monkeypatch, qtbot) -> None:
    """Canned per-path results land on their own items only (fail-closed)."""
    from tabs.image_gallery.services import proxy as _proxy

    items = _items(3, tag="own")
    ghost = str(Path("/gallery/ghost.png"))

    def _fake(batch, source, *, include_camera=False):
        out = {}
        for it in batch:
            key = str(it.path)
            if key.endswith("own_001.png"):
                out[key] = {
                    "artifacts": {"banding": "mild"},
                    "fidelity": {"ssim": 0.5, "hf_ratio": 0.1, "delta_e": 2.0, "upscale_factor": 1},
                    "camera": {"sharpness": 10.0},
                }
            else:
                out[key] = {}  # unreadable: fail-closed, nothing applied
        out[ghost] = {"artifacts": {"banding": "flagged"}}  # neighbor: no item
        return out

    monkeypatch.setattr(_proxy, "run_proxy_stages_sync", _fake)
    widget = _WidgetStub()
    ctrl, _pool = _make_ctrl(widget, max_threads=1)
    ctrl.state.items = list(items)
    ctrl._start_proxy_analysis(list(items), Path("/src.png"), Mode.CAMERA)
    qtbot.waitUntil(lambda: items[1].metrics.get("ssim") == 0.5, timeout=8000)
    from tabs.image_gallery.use_cases import quality as _quality

    assert _quality.severities(items[1]) == {"banding": "mild"}
    assert items[1].metrics.get("sharpness") == 10.0
    # Siblings untouched; ghost result delivered to nobody.
    assert items[0].metrics.get("ssim") is None
    assert items[2].metrics.get("ssim") is None
    assert _quality.severities(items[0]) == {}
    assert ctrl._find_item(Path(ghost)) is None


def test_proxy_cache_stays_bounded_under_200(monkeypatch, tmp_path: Path) -> None:
    """200 synthetic proxies stay within the single 96-entry LRU bound.

    Follow-up F1 made proxy.py own one true-LRU cap (96): the fill itself
    bounds to 96, so the controller trim is a no-op here (still asserted
    for the over-cap path it owns). Warm survivors serve without decode.
    """
    from PIL import Image

    from tabs.image_gallery.services import proxy as _proxy

    _proxy.clear_proxy_cache()
    try:
        paths = []
        for i in range(200):
            p = tmp_path / f"px_{i:03d}.png"
            Image.new("RGB", (32, 32), (i % 256, 100, 50)).save(p)
            paths.append(p)
        for p in paths:
            assert _proxy.proxy_for(p) is not None
        assert len(_proxy._PROXY_CACHE) == _proxy.PROXY_CACHE_LIMIT
        widget = _WidgetStub()
        ctrl, _pool = _make_ctrl(widget)
        evicted = ctrl._trim_proxy_cache()
        assert evicted == 0
        assert len(_proxy._PROXY_CACHE) <= 96
        # Warm survivors still serve without a decode.
        assert _proxy.proxy_for(paths[-1]) is not None
        assert len(_proxy._PROXY_CACHE) <= 96
    finally:
        _proxy.clear_proxy_cache()


def test_stale_proxy_chunk_dropped(monkeypatch, qtbot) -> None:
    items = _items(2, tag="stale")
    widget = _WidgetStub()
    ctrl, _pool = _make_ctrl(widget)
    ctrl.state.items = list(items)
    stale_gen = ctrl._folder_gen
    ctrl._next_folder_gen()
    ctrl._on_proxy_batch_ready(
        {str(items[0].path): {"artifacts": {"banding": "flagged"}}}, stale_gen
    )
    from tabs.image_gallery.use_cases import quality as _quality

    assert _quality.severities(items[0]) == {}


def test_visibility_filter_pauses_and_resumes() -> None:
    """Hide/Show events drive the background lane (no tab.py change)."""
    widget = _WidgetStub()
    ctrl, _pool = _make_ctrl(widget)
    filt = ctrl._visibility_pause_filter
    assert filt is not None
    assert widget._filters == [filt]

    class _Watched:
        def __init__(self, hidden: bool):
            self._hidden = hidden

        def isHidden(self) -> bool:
            return self._hidden

    assert filt.eventFilter(_Watched(True), QEvent(QEvent.Type.Hide)) is False
    assert ctrl._bg_paused is True
    assert filt.eventFilter(_Watched(True), QEvent(QEvent.Type.Show)) is False
    assert ctrl._bg_paused is False
    # Ancestor-driven hide (window minimize): ignored, never pauses.
    ctrl.resume_background()
    assert filt.eventFilter(_Watched(False), QEvent(QEvent.Type.Hide)) is False
    assert ctrl._bg_paused is False
