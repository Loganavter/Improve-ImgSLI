"""P2 — the VLM metric-profile selector as a declared pipeline stage.

Falsification story (what each test would catch):

- the ``metric_profile`` stage not declared with ``requires=("metrics_ready",)``
  (a stage that could fire before the salience input exists);
- a settle that kicks the selector twice over the same folder generation (no
  single-flight) — or that lets a second settle spawn a second worker;
- a settle that kicks the selector BEFORE the heuristic profile is stored, so a
  failed/slow selector would leave the user with no profile at all (the
  heuristic is the fail-open fallback and must be stored FIRST);
- a selector that returns nothing / raises / is unavailable (module absent)
  wiping or crashing on the heuristic profile instead of leaving it;
- the AI being unusable (no key/base_url) still firing a request;
- a stale-generation result being applied to a folder that changed under it;
- a landed ``source="vlm"`` profile not reaching the consumers (the dots and
  ``measured_axes_for`` read the SAME stored profile).

Qt-free: a ``_FakeWorker`` double mirrors ``GenericWorker`` (captures the job,
delivers ``result``/``error``/``finished`` on ``run``); the selector is stubbed
through the frozen ``controller._profile_selector`` indirection — the selector
lane's module is never imported.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery import controller as controller_mod
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, Mode, Series
from tabs.image_gallery.services.metric_profile import MetricProfile, profile_for_mode
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.use_cases import pipeline_stages as ps
from tabs.image_gallery.use_cases import triage_run
from tabs.image_gallery.use_cases.profile_select import active_profile


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _vlm_profile(axis_ids=("ssim",)) -> MetricProfile:
    return MetricProfile(
        axis_ids=tuple(axis_ids),
        mode="camera",
        source="vlm",
        salient_axes=tuple(axis_ids),
    )


def _selector_returning(profile):
    def _sel(items, mode=None, settings=None):
        return profile

    return _sel


def _selector_raising(exc=None):
    def _sel(items, mode=None, settings=None):
        raise exc or RuntimeError("selector exploded")

    return _sel


class _Sig:
    """Minimal Qt-signal double (connect/emit, no Qt)."""

    def __init__(self) -> None:
        self._cbs: list = []

    def connect(self, cb) -> None:
        self._cbs.append(cb)

    def emit(self, *args) -> None:
        for cb in list(self._cbs):
            cb(*args)


class _FakeWorker:
    """``GenericWorker`` double: captures the job, delivers signals on ``run``.

    Mirrors ``sl_ui_toolkit.workers.GenericWorker.run`` — a None reply emits no
    ``result`` (only ``finished``), an exception emits ``error`` then
    ``finished``.
    """

    instances: list = []

    def __init__(self, fn, *args, **kwargs) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = SimpleNamespace(result=_Sig(), error=_Sig(), finished=_Sig())
        _FakeWorker.instances.append(self)

    def run(self) -> None:
        try:
            out = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 — mirrors GenericWorker
            self.signals.error.emit((type(exc), exc, "traceback"))
        else:
            if out is not None:
                self.signals.result.emit(out)
        finally:
            self.signals.finished.emit()


@pytest.fixture()
def fake_workers(monkeypatch):
    _FakeWorker.instances.clear()
    monkeypatch.setattr(controller_mod, "GenericWorker", _FakeWorker)
    return _FakeWorker


class _ProfileCtrl:
    """Minimal controller surface for the real P2 profile stage (no Qt)."""

    def __init__(self, items, *, mode=Mode.CAMERA, series=None, ai=True, gen=0) -> None:
        self.state = SimpleNamespace(
            items=list(items),
            series=list(series or []),
            mode=mode,
            metric_profile=None,
        )
        self._judgment_domain = "ai"
        self._folder_gen = gen
        self._metrics_settled_gen = -1
        self._stage_gate = ps.StageGate()
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=ai,
                api_key=("k" if ai else ""),
                model="m",
                base_url=("http://h" if ai else ""),
            )
        )
        self.widget = SimpleNamespace(
            refresh_cards=lambda its: None,
            refresh_card=lambda it: None,
        )
        self.profile_kicks = 0
        self.launched: list = []

    # Real primitives, bound to this fake.
    def _is_current_folder_gen(self, gen):
        return GalleryController._is_current_folder_gen(self, gen)

    def _pool_start(self, worker, priority):
        # Never runs the worker: tests drive ``worker.run()`` explicitly so the
        # in-flight vs completed gate states are both observable.
        self.launched.append(worker)

    def refresh_metric_profile(self):
        return GalleryController.refresh_metric_profile(self)

    def _run_profile_select_on_settle(self):
        self.profile_kicks += 1
        return GalleryController._run_profile_select_on_settle(self)

    def _apply_profile_outcome(self, profile, gen):
        return GalleryController._apply_profile_outcome(self, profile, gen)

    # Thin primitives ``_settle_metrics_pass`` touches (no-ops here).
    def _mark_local_pass(self, items, phase):
        return None

    def _apply_fusion_ranks(self, series, *, mode=None):
        return None

    def _run_ai_for_visible(self):
        return None

    def _run_jev_ranks(self):
        return None

    def _clear_series_priority(self):
        return None


# --------------------------------------------------------------------------
# (1) declared stage + single-flight gate
# --------------------------------------------------------------------------


def test_profile_stage_declares_metrics_ready() -> None:
    assert ps.stage_requires("metric_profile") == ("metrics_ready",)


def test_in_flight_kick_is_single_flight(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl._run_profile_select_on_settle()  # in flight (worker never run)
    ctrl._run_profile_select_on_settle()  # same (stage, gen) -> refused
    assert ctrl.profile_kicks == 2
    assert len(ctrl.launched) == 1, "a second in-flight kick must not spawn a worker"


def test_completed_stage_refuses_a_second_kick(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl._run_profile_select_on_settle()
    ctrl.launched[0].run()  # completes ok -> the fingerprint is recorded done
    ctrl._run_profile_select_on_settle()
    assert len(ctrl.launched) == 1, "a completed fingerprint must not re-run"


def test_folder_change_invalidates_the_profile_stage(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl._run_profile_select_on_settle()
    ctrl.launched[0].run()
    GalleryController._next_folder_gen(ctrl)  # fresh world: ledger invalidated
    ctrl.state.items = [a, b]
    ctrl._run_profile_select_on_settle()
    assert len(ctrl.launched) == 2, "a new folder generation must select again"


# --------------------------------------------------------------------------
# (2) driven from the settle, heuristic stored FIRST
# --------------------------------------------------------------------------


def test_settle_kicks_profile_once_with_the_heuristic_already_stored(
    monkeypatch, fake_workers
) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], series=[Series(id="s", members=[a, b])])
    # The selector returns nothing (benign non-answer): the heuristic must stay.
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(None)
    )
    triage_run._settle_metrics_pass(ctrl, [a, b])
    assert ctrl.profile_kicks == 1, "the settle is the ONE trigger of the selector"
    assert len(ctrl.launched) == 1
    # The heuristic profile is stored synchronously, BEFORE the async selector.
    stored = ctrl.state.metric_profile
    assert stored is not None and stored.source == "heuristic"
    ctrl.launched[0].run()  # None reply -> finished only -> no-op apply
    assert ctrl.state.metric_profile.source == "heuristic"


def test_second_settle_over_the_same_folder_is_a_noop(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    series = [Series(id="s", members=[a, b])]
    ctrl = _ProfileCtrl([a, b], series=series)
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    triage_run._settle_metrics_pass(ctrl, [a, b])
    ctrl.launched[0].run()
    triage_run._settle_metrics_pass(ctrl, [a, b])
    assert ctrl.profile_kicks == 2  # both settles kicked...
    assert len(ctrl.launched) == 1, "...but only one selector worker ran"


# --------------------------------------------------------------------------
# (3) a landed vlm profile reaches the consumers
# --------------------------------------------------------------------------


def test_vlm_profile_lands_on_state_and_consumers_follow(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], mode=Mode.CAMERA)
    heuristic_axes = profile_for_mode("camera").axis_ids
    assert "sharpness" in heuristic_axes and len(heuristic_axes) > 1  # a strict subset
    ctrl.refresh_metric_profile()  # heuristic stored first
    vlm = _vlm_profile(("sharpness",))
    monkeypatch.setattr(controller_mod, "_profile_selector", lambda: _selector_returning(vlm))
    ctrl._run_profile_select_on_settle()
    ctrl.launched[0].run()

    stored = ctrl.state.metric_profile
    assert stored is not None and stored.source == "vlm"
    assert active_profile(ctrl.state) == stored
    # The consumers read the SAME stored profile: axis list + the dots.
    assert measured_axes_for(Mode.CAMERA, profile=stored) == vlm.axis_ids
    colors, infos = metric_dots_for_item(a, Mode.CAMERA, profile=stored)
    assert len(colors) == len(vlm.axis_ids)
    assert len(infos) == len(vlm.axis_ids)


def test_stale_generation_result_is_dropped(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl.refresh_metric_profile()
    ctrl._run_profile_select_on_settle()
    worker = ctrl.launched[0]
    # A new folder world arrives before the selector answers.
    ctrl._folder_gen = 1
    ctrl.state.metric_profile = None  # fresh folder: profile cleared
    worker.run()
    assert ctrl.state.metric_profile is None, "a stale vlm profile must be dropped"


# --------------------------------------------------------------------------
# (4) fail-open: unavailable / unusable / fault -> the heuristic stays
# --------------------------------------------------------------------------


def test_selector_fault_keeps_the_heuristic_and_stays_retryable(
    monkeypatch, fake_workers
) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_raising()
    )
    ctrl.refresh_metric_profile()
    ctrl._run_profile_select_on_settle()
    ctrl.launched[0].run()  # error signal
    assert ctrl.state.metric_profile.source == "heuristic"
    # A fault passes ok=False, so the same fingerprint stays retryable.
    ctrl._run_profile_select_on_settle()
    assert len(ctrl.launched) == 2


def test_ai_unavailable_launches_no_worker(monkeypatch, fake_workers) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], ai=False)
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl.refresh_metric_profile()
    ctrl._run_profile_select_on_settle()
    assert ctrl.launched == [], "no AI key/base_url must never launch a request"
    assert ctrl.state.metric_profile.source == "heuristic"


def test_fewer_than_two_items_launches_no_worker(monkeypatch, fake_workers) -> None:
    a = _item("a.png", ssim=0.9)
    ctrl = _ProfileCtrl([a])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl.refresh_metric_profile()
    ctrl._run_profile_select_on_settle()
    assert ctrl.launched == []
    assert ctrl.state.metric_profile.source == "heuristic"


def test_launch_failure_keeps_the_heuristic_and_stays_retryable(
    monkeypatch, fake_workers
) -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )

    def _boom(worker, priority):
        raise RuntimeError("no pool")

    monkeypatch.setattr(ctrl, "_pool_start", _boom)
    ctrl.refresh_metric_profile()
    ctrl._run_profile_select_on_settle()  # must not raise
    assert ctrl.state.metric_profile.source == "heuristic"
    # The gate is released ok=False, so a later kick retries the same folder.
    relaunched: list = []
    monkeypatch.setattr(ctrl, "_pool_start", lambda w, p: relaunched.append(w))
    ctrl._run_profile_select_on_settle()
    assert len(relaunched) == 1


def test_missing_or_raising_selector_indirection_is_a_noop(
    monkeypatch, fake_workers
) -> None:
    """The selector lane's module may be absent (ImportError) — fail-open."""
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])

    def _absent():
        raise ImportError("use_cases.profile_ai is not installed")

    monkeypatch.setattr(controller_mod, "_profile_selector", _absent)
    ctrl.refresh_metric_profile()
    ctrl._run_profile_select_on_settle()
    assert ctrl.launched == []
    assert ctrl.state.metric_profile.source == "heuristic"


def test_instance_level_selector_override_is_used(monkeypatch, fake_workers) -> None:
    """The kick reads ``getattr(self, "_profile_selector", None)`` first."""
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    vlm = _vlm_profile(("ssim",))
    ctrl._profile_selector = lambda: _selector_returning(vlm)  # instance override
    monkeypatch.setattr(
        controller_mod,
        "_profile_selector",
        lambda: _selector_raising(RuntimeError("module default must not be used")),
    )
    ctrl._run_profile_select_on_settle()
    ctrl.launched[0].run()
    assert ctrl.state.metric_profile == vlm
