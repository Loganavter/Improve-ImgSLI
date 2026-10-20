"""``jobs_list`` / ``jobs_cancel`` over a **real** ``GalleryController``.

``tests/devtools/test_jobs_list.py`` proves the control-channel contract over a
duck-typed owner double — a root ``tests/`` file may not deep-import a tab
package (tests/contracts/test_root_tests_no_tab_internals_leak.py). This file is
the runtime counterpart: the same reads run against a live controller, with the
real ``GalleryState.items``, the real scheduler counters and the real
``sched_stats()``, so the double cannot drift into a shape only it satisfies.

The export half attaches a **real** ``SaveFlowCoordinator`` to that controller
and drives a **real** ``GenericWorker``: that is where the registry lifecycle
bug lived. ``start_with_worker`` wired ``progress`` / ``result`` / ``error``
but never ``finished``, so a worker that completed without emitting a
``result`` (the swallowed cancel sentinel returns ``None``) left its
``_save_cancellation`` entry in place forever — a phantom "export in
progress" row for every later ``jobs_list``.

Falsification (written before the fix):
* an idle real controller answers an empty list, never an error;
* a kind without a cooperative cancel gets a *named* refusal;
* a settled export releases its registry entry, so it stops being listed.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtWidgets import QApplication
from sli_ui_toolkit.workers import GenericWorker

from core.control import jobs
from core.control.handlers import ControlHandlers, MethodError
from tabs._shared.save_flow import SaveFlowCoordinator
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AnalysisStatus, GalleryItem, ThumbnailStatus

_KEY = "image_gallery"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _clear_observation_clock():
    """``jobs._OBSERVED_SINCE`` is process-scoped — never leak a clock."""
    jobs._OBSERVED_SINCE.clear()
    yield
    jobs._OBSERVED_SINCE.clear()


def _pump(app: QApplication, seconds: float, until=None) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(until()) if until is not None else False


def _widget_double():
    """The exact widget surface ``GalleryController.__init__`` connects to."""

    class _W(QObject):
        folder_pick_requested = Signal()
        analyze_requested = Signal(object)
        filter_text_changed = Signal(str)
        visible_range_changed = Signal(object)

    return _W()


@pytest.fixture
def gallery():
    """A real (storeless) controller: no folder scan, no pools spawned."""
    controller = GalleryController(_widget_double(), thread_pool=QThreadPool(), context=None)
    yield controller
    controller._thread_pool.waitForDone(2000)


def _item(index: int, *, thumb=ThumbnailStatus.NOT_LOADED, ai=AnalysisStatus.NOT_ANALYZED):
    # Paths are never touched by the reads under test (no decode/stat).
    return GalleryItem(
        path=Path(f"/gallery/real_{index:03d}.png"),
        mtime_ns=index + 1,
        thumbnail_status=thumb,
        analysis_status=ai,
    )


def _handlers(controller: GalleryController) -> ControlHandlers:
    """A real handler whose live tab list holds the real gallery controller."""
    handlers = ControlHandlers(window=SimpleNamespace(_toast_manager=None))
    tab = SimpleNamespace(_controller=controller)
    handlers._tabs = lambda: [(_KEY, tab)]  # type: ignore[method-assign]
    return handlers


def _options(tmp_path: Path) -> dict:
    return {"output_dir": str(tmp_path), "file_name": "out", "format": "PNG"}


def _coordinator(pool: QThreadPool) -> SaveFlowCoordinator:
    return SaveFlowCoordinator(
        get_thread_pool=lambda: pool,
        get_toast_manager=lambda: None,
        tr_func=lambda key, *a: key,
    )


# --- gallery rows over the real controller ---------------------------------


def test_real_controller_reports_a_running_pool(qapp, gallery):
    """Counters and per-item status come from the controller's own state."""
    gallery.state.items = [
        _item(i, thumb=ThumbnailStatus.LOADED if i < 2 else ThumbnailStatus.LOADING)
        for i in range(6)
    ]
    gallery._sched_pending = 3
    gallery._sched_active = 1
    gallery._bg_queue = [(_item(6), gallery._folder_gen), (_item(7), gallery._folder_gen)]

    result = _handlers(gallery).jobs_list({})

    assert result["count"] == 1
    row = result["jobs"][0]
    assert tuple(row) == jobs.JOB_KEYS, "the row shape is frozen"
    assert row["id"] == f"pool:{_KEY}"
    assert row["kind"] == jobs.KIND_GALLERY_POOL
    assert row["status"] == "running"
    assert row["progress"] == {"done": 2, "total": 6}
    assert "2/6 loaded" in row["message"]
    assert isinstance(row["elapsed_s"], float)


def test_real_controller_with_nothing_running_is_empty(qapp, gallery):
    """An idle live controller answers an empty list — not an error, no rows."""
    gallery.state.items = [_item(i, thumb=ThumbnailStatus.LOADED) for i in range(4)]
    assert _handlers(gallery).jobs_list({}) == {"count": 0, "jobs": []}


def test_real_controller_reports_a_paused_lane(qapp, gallery):
    """``pause_background()`` is the real pause seam — not a test-only flag."""
    gallery.state.items = [_item(0)]
    gallery._bg_queue = [(_item(1), gallery._folder_gen)]

    gallery.pause_background()
    row = _handlers(gallery).jobs_list({})["jobs"][0]

    assert row["kind"] == jobs.KIND_GALLERY_POOL
    assert row["status"] == "paused"


def test_real_controller_reports_the_metrics_and_ai_passes(qapp, gallery):
    """Chunk counters and the derived AI aggregate read off the live state."""
    gallery.state.items = [
        _item(0, ai=AnalysisStatus.DONE, thumb=ThumbnailStatus.LOADED),
        _item(1, ai=AnalysisStatus.ERROR, thumb=ThumbnailStatus.LOADED),
        _item(2, ai=AnalysisStatus.PENDING, thumb=ThumbnailStatus.LOADED),
        _item(3, thumb=ThumbnailStatus.LOADED),
    ]
    gallery._proxy_total = 5
    gallery._proxy_done = 2

    rows = {row["kind"]: row for row in _handlers(gallery).jobs_list({})["jobs"]}

    assert rows["metrics_pass"]["id"] == f"metrics:{_KEY}"
    assert rows["metrics_pass"]["progress"] == {"done": 2, "total": 5}
    assert rows["ai_analysis"]["progress"] == {"done": 2, "total": 3}
    assert "gallery_pool" not in rows, "nothing is queued in the pool"


def test_real_pool_cancel_is_a_named_refusal(qapp, gallery):
    """The live controller exposes no cooperative pool cancel — say so."""
    gallery.state.items = [_item(0)]
    gallery._sched_pending = 1
    gallery._sched_active = 1
    handlers = _handlers(gallery)
    row = handlers.jobs_list({})["jobs"][0]

    with pytest.raises(MethodError) as excinfo:
        handlers.jobs_cancel({"id": row["id"]})

    assert "cancel is not supported for kind 'gallery_pool'" in excinfo.value.message
    assert "only exports" in (excinfo.value.hint or "")


def test_real_controller_unknown_id_is_an_error(qapp, gallery):
    with pytest.raises(MethodError) as excinfo:
        _handlers(gallery).jobs_cancel({"id": f"export:{_KEY}:99"})
    assert "no running job" in excinfo.value.message


# --- export rows over the real controller + the real save flow -------------


def _attach_flow(gallery: GalleryController, coordinator: SaveFlowCoordinator) -> None:
    """The attribute shape ``jobs._save_flows`` reads from a live controller."""
    gallery._save_flow = SimpleNamespace(_flow=coordinator)


def test_a_settled_export_releases_its_registry_entry(qapp, gallery, tmp_path):
    """No result signal (worker returned ``None``) still means the job is over.

    ``GenericWorker`` always emits ``finished``; the registry entry must not
    outlive the worker just because the body produced no ``result``.
    """
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    coordinator = _coordinator(pool)
    _attach_flow(gallery, coordinator)
    ran = threading.Event()

    def task(**_kw):
        ran.set()
        return None  # silent completion: only ``finished`` fires

    coordinator.start_with_worker(_options(tmp_path), lambda ev: GenericWorker(task, cancel_event=ev))
    assert _pump(qapp, 3.0, ran.is_set)
    assert _pump(qapp, 3.0, lambda: not coordinator._save_cancellation), (
        "a settled export must release its registry entry (the worker did finish)"
    )

    assert _handlers(gallery).jobs_list({}) == {"count": 0, "jobs": []}


def test_jobs_cancel_sets_the_real_coordinators_event(qapp, gallery, tmp_path):
    """The handle ``jobs_cancel`` hands out is the coordinator's own event."""
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    coordinator = _coordinator(pool)
    _attach_flow(gallery, coordinator)
    started = threading.Event()

    def task(**kw):
        started.set()
        kw["cancel_event"].wait(5)
        return None

    coordinator.start_with_worker(_options(tmp_path), lambda ev: GenericWorker(task, cancel_event=ev))
    assert _pump(qapp, 3.0, started.is_set)
    assert _pump(qapp, 3.0, lambda: bool(coordinator._save_cancellation))
    handlers = _handlers(gallery)

    rows = handlers.jobs_list({})["jobs"]
    assert [row["kind"] for row in rows] == [jobs.KIND_EXPORT]
    assert rows[0]["id"] == f"export:{_KEY}:1"

    result = handlers.jobs_cancel({"id": rows[0]["id"]})

    assert result == {"cancelled": True, "id": rows[0]["id"], "kind": jobs.KIND_EXPORT}
    assert all(ev.is_set() for ev in coordinator._save_cancellation.values()), (
        "the cancel handle must set the event the worker is waiting on"
    )
    assert _pump(qapp, 3.0, lambda: not coordinator._save_cancellation), (
        "the finished worker must release the entry after the cancel"
    )
    assert handlers.jobs_list({}) == {"count": 0, "jobs": []}
