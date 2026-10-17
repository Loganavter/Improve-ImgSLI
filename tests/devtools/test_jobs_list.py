"""``core.control.jobs`` + the two job methods on ``ControlHandlers``.

Two layers, deliberately:

* **Runtime** — ``jobs_list``/``jobs_cancel`` over a duck-typed gallery owner
  (the same attribute surface ``jobs.py`` reads from the live controller) and
  over a **real** ``SaveFlowCoordinator`` plus the **real**
  ``write_pil_image_cancelable``, so "cancel leaves no partial artifact" is
  proven by the encoder rather than restated.
* **Seam** (``test_*_seam_*``) — the duck-typed contract is pinned against the
  *real* gallery/export sources by reading them, because a root ``tests/`` file
  may not deep-import a tab package (``test_root_tests_no_tab_internals_leak``;
  the runtime half is covered by the owner double above).

Falsification (written first):
* an empty list must mean "nothing is running", never an error;
* a kind with no cooperative cancel must get a *named* refusal, not a fake one;
* a cancelled export must leave neither the final file nor its ``.tmp``.

Recorded follow-up (not fixed here — those files are read-only for this task):
``ExportSaveFlowCoordinator._export_worker_task`` swallows the cancel sentinel
and returns ``None``, and ``GenericWorker`` emits no ``result`` for ``None``, so
the coordinator's ``_save_cancellation`` entry lingers until shutdown. The last
export test pins ``jobs_list``'s answer to that: an entry whose cancel event is
set is never reported as a running job (no zombie row).
"""

from __future__ import annotations

import re
import threading
import time
import types
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from core.control import jobs
from core.control.handlers import ControlHandlers, MethodError
from shared.image_processing.pil_save import write_pil_image_cancelable
from sli_ui_toolkit.workers import GenericWorker
from tabs._shared.save_flow import SaveFlowCoordinator

REPO_ROOT = Path(__file__).resolve().parents[2]
GALLERY = REPO_ROOT / "src" / "tabs" / "image_gallery"


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, seconds: float, until=None) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(until()) if until is not None else False


@pytest.fixture(autouse=True)
def _clear_observation_clock():
    jobs._OBSERVED_SINCE.clear()
    yield
    jobs._OBSERVED_SINCE.clear()


def _item(index: int, *, thumb="not_loaded", ai="not_analyzed"):
    return types.SimpleNamespace(
        path=Path(f"/gallery/job_{index:03d}.png"),
        thumbnail_status=thumb,
        analysis_status=ai,
    )


class _GalleryOwner:
    """Duck-typed live gallery controller — exactly the surface jobs.py reads.

    The real class provides ``sched_stats()``, ``state.items``, ``_proxy_done``
    / ``_proxy_total``, ``_bg_paused`` and per-item ``thumbnail_status`` /
    ``analysis_status``; ``test_gallery_seam_matches_the_real_controller`` pins
    that against the real sources.
    """

    def __init__(self, items, *, pending=0, active=0, queued=0, paused=False):
        self.state = types.SimpleNamespace(items=list(items))
        self._sched = {"pending": pending, "active": active, "peak": active, "queued": queued}
        self._bg_paused = paused
        self._proxy_done = 0
        self._proxy_total = 0
        self._gallery_session_id = "s1"

    def sched_stats(self) -> dict:
        return dict(self._sched)


def _handlers(window, tabs: list) -> ControlHandlers:
    """A real handler whose live tab list is the given (duck-typed) tabs."""
    handlers = ControlHandlers(window=window)
    handlers._tabs = lambda: list(tabs)  # type: ignore[method-assign]
    return handlers


def _gallery_handler(owner: _GalleryOwner) -> ControlHandlers:
    tab = types.SimpleNamespace(_controller=owner)
    return _handlers(types.SimpleNamespace(_toast_manager=None), [("image_gallery", tab)])


# --- gallery pool / metrics / ai -------------------------------------------


def test_jobs_list_reports_a_running_gallery_pool():
    """A throttled pool reports a row with the frozen keys and real progress."""
    owner = _GalleryOwner(
        [_item(i, thumb="loaded" if i < 2 else "loading") for i in range(6)],
        pending=3,
        active=1,
        queued=2,
    )

    result = _gallery_handler(owner).jobs_list({})

    assert result["count"] == 1
    row = result["jobs"][0]
    assert tuple(row) == jobs.JOB_KEYS, "the row shape is frozen"
    assert row["kind"] == "gallery_pool"
    assert row["status"] == "running"
    assert row["progress"] == {"done": 2, "total": 6}
    assert "2/6 loaded" in row["message"]
    assert isinstance(row["elapsed_s"], float)


def test_jobs_list_with_nothing_running_is_empty():
    """An idle live owner answers an empty list — not an error, no rows."""
    owner = _GalleryOwner([_item(i, thumb="loaded") for i in range(4)])
    assert _gallery_handler(owner).jobs_list({}) == {"count": 0, "jobs": []}


def test_jobs_list_marks_a_paused_background_lane():
    owner = _GalleryOwner([_item(i) for i in range(3)], queued=3, paused=True)
    row = _gallery_handler(owner).jobs_list({})["jobs"][0]
    assert row["kind"] == "gallery_pool"
    assert row["status"] == "paused"


def test_jobs_list_reports_the_metrics_and_ai_passes():
    """Chunk counters and the derived AI aggregate are both visible."""
    owner = _GalleryOwner(
        [
            _item(0, ai="done", thumb="loaded"),
            _item(1, ai="error", thumb="loaded"),
            _item(2, ai="pending", thumb="loaded"),
            _item(3, thumb="loaded"),
        ]
    )
    owner._proxy_total = 5
    owner._proxy_done = 2

    rows = {row["kind"]: row for row in _gallery_handler(owner).jobs_list({})["jobs"]}

    assert rows["metrics_pass"]["progress"] == {"done": 2, "total": 5}
    assert rows["metrics_pass"]["status"] == "running"
    assert rows["ai_analysis"]["progress"] == {"done": 2, "total": 3}
    assert "gallery_pool" not in rows, "nothing is queued in the pool"


def test_jobs_list_does_not_resolve_a_lazy_export_service():
    """Reading jobs must never materialize a tab as a side effect."""
    built: list = []

    class _Lazy:
        _tried = False
        _resolved = None

        def __getattr__(self, name):  # pragma: no cover - must never be reached
            built.append(name)
            raise AssertionError("jobs_list resolved a lazy service")

    window = types.SimpleNamespace(
        _toast_manager=None,
        presenter=types.SimpleNamespace(features=types.SimpleNamespace(export=_Lazy())),
    )
    assert _handlers(window, []).jobs_list({}) == {"count": 0, "jobs": []}
    assert built == []


# --- honest refusals --------------------------------------------------------


def test_jobs_cancel_refuses_a_kind_without_a_real_cancel():
    owner = _GalleryOwner([_item(i) for i in range(3)], queued=3)
    handlers = _gallery_handler(owner)
    row = handlers.jobs_list({})["jobs"][0]

    with pytest.raises(MethodError) as excinfo:
        handlers.jobs_cancel({"id": row["id"]})

    assert "cancel is not supported for kind 'gallery_pool'" in excinfo.value.message
    assert "only exports" in (excinfo.value.hint or "")


def test_jobs_cancel_unknown_id_is_an_error():
    with pytest.raises(MethodError) as excinfo:
        _handlers(types.SimpleNamespace(), []).jobs_cancel({"id": "export:nope:99"})
    assert "no running job" in excinfo.value.message


def test_jobs_cancel_without_an_id_is_an_error():
    with pytest.raises(MethodError):
        _handlers(types.SimpleNamespace(), []).jobs_cancel({})


def test_the_frozen_surface_and_capabilities_include_both_job_methods():
    from core.control import handlers as handlers_module

    assert "jobs_list" in handlers_module.METHODS
    assert "jobs_cancel" in handlers_module.METHODS
    assert _handlers(types.SimpleNamespace(), []).capabilities()["live_jobs"] is True


# --- export: the one real cancel --------------------------------------------


def _export_handlers(coordinator: SaveFlowCoordinator) -> ControlHandlers:
    controller = types.SimpleNamespace(_save_flow=types.SimpleNamespace(_flow=coordinator))
    tab = types.SimpleNamespace(_controller=controller)
    return _handlers(types.SimpleNamespace(_toast_manager=None), [("multi_compare", tab)])


def _flow(pool: QThreadPool) -> SaveFlowCoordinator:
    return SaveFlowCoordinator(
        get_thread_pool=lambda: pool,
        get_toast_manager=lambda: None,
        tr_func=lambda key, *a: key,
    )


def _options(tmp_path: Path) -> dict:
    return {"output_dir": str(tmp_path), "file_name": "out", "format": "PNG"}


def test_jobs_cancel_stops_the_export_and_leaves_no_partial_artifact(tmp_path):
    """The real cancel path: the encoder aborts and writes nothing at all."""
    from PIL import Image

    app = _qapp()
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    coordinator = _flow(pool)
    proceed = threading.Event()
    target = tmp_path / "out.png"
    image = Image.new("RGB", (64, 64), (1, 2, 3))

    def task(**kw):
        # Runs after the cancel was requested: the real cancelable writer must
        # refuse the very first write and clean up its own tmp file.
        proceed.wait(5)
        write_pil_image_cancelable(image, str(target), "PNG", {}, cancel_event=kw["cancel_event"])
        return str(target)

    coordinator.start_with_worker(_options(tmp_path), lambda ev: GenericWorker(task, cancel_event=ev))
    assert _pump(app, 3.0, lambda: bool(coordinator._save_cancellation))
    handlers = _export_handlers(coordinator)

    rows = handlers.jobs_list({})["jobs"]
    assert [row["kind"] for row in rows] == ["export"]
    assert rows[0]["status"] == "running"
    assert rows[0]["message"] == "export in progress"  # no toast manager attached

    cancelled = handlers.jobs_cancel({"id": rows[0]["id"]})
    proceed.set()
    assert _pump(app, 3.0, lambda: not coordinator._save_cancellation), "the flow never settled"

    assert cancelled == {"cancelled": True, "id": rows[0]["id"], "kind": "export"}
    assert not target.exists(), "the cancelled export left its output behind"
    assert not (tmp_path / "out.png.tmp").exists(), "the cancelled export left a partial tmp file"
    assert handlers.jobs_list({}) == {"count": 0, "jobs": []}


def test_jobs_list_drops_an_export_whose_cancel_was_requested(tmp_path):
    """A cancel-requested entry is never listed as a running job (no zombie).

    Mirrors the real worker shape that swallows the cancel sentinel and returns
    ``None``, leaving the coordinator's registry entry behind; the row must
    still disappear the moment its cancel event is set.
    """
    app = _qapp()
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    coordinator = _flow(pool)
    started = threading.Event()

    def task(**kw):
        started.set()
        kw["cancel_event"].wait(5)
        return None

    coordinator.start_with_worker(_options(tmp_path), lambda ev: GenericWorker(task, cancel_event=ev))
    assert _pump(app, 3.0, started.is_set)
    assert _pump(app, 3.0, lambda: bool(coordinator._save_cancellation))
    handlers = _export_handlers(coordinator)
    row = handlers.jobs_list({})["jobs"][0]

    handlers.jobs_cancel({"id": row["id"]})
    _pump(app, 3.0, lambda: False)

    assert handlers.jobs_list({}) == {"count": 0, "jobs": []}, (
        "a cancelled export must not linger as a running row"
    )
    assert coordinator._save_cancellation, "the coordinator's own registry entry lingers (app-side)"


# --- seam: the duck-typed contract against the real sources -----------------


def _source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_gallery_seam_matches_the_real_controller():
    """The attributes jobs.py reads really exist on the live gallery objects."""
    controller = _source("src/tabs/image_gallery/controller.py")
    assert re.search(r"^    def sched_stats\(self\)", controller, re.M)
    assert "_proxy_done = 0" in controller and "_proxy_total = 0" in controller
    assert "_bg_paused" in controller

    scheduler = _source("src/tabs/image_gallery/use_cases/scheduler.py")
    for counter in ("_sched_pending", "_sched_active", "_sched_peak", "_bg_queue"):
        assert counter in scheduler, counter
    assert '"pending"' in scheduler and '"active"' in scheduler and '"queued"' in scheduler

    # Chunk progress is the app's own; it must keep being incremented per chunk.
    assert "_proxy_done += 1" in _source("src/tabs/image_gallery/use_cases/proxy_pass.py")

    models = _source("src/tabs/image_gallery/models.py")
    assert re.search(r"^    items:", models, re.M), "GalleryState.items"
    for field in ("thumbnail_status", "analysis_status"):
        assert field in models, field


def test_export_seam_matches_the_real_save_flow():
    """The cancel handle jobs.py sets is the coordinator's own, and it cleans up."""
    save_flow = _source("src/tabs/_shared/save_flow.py")
    assert "self._save_cancellation: dict[int, threading.Event] = {}" in save_flow
    assert "self._save_cancellation[toast_id] = cancel_event" in save_flow
    assert "cancel_event.set()" in save_flow, "the toast's Cancel button sets the event"
    assert "self._save_cancellation.pop(save_task_id, None)" in save_flow

    # Atomicity: the encoder writes a tmp file and removes it when it aborts.
    pil_save = _source("src/shared/image_processing/pil_save.py")
    assert 'tmp_path = full_path + ".tmp"' in pil_save
    assert "os.replace(tmp_path, full_path)" in pil_save
    assert pil_save.count("os.remove(tmp_path)") >= 2
