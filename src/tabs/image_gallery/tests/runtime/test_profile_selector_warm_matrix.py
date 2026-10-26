"""The metric-profile selector never spends an image call it cannot use.

Owner report 2026-10-22, item 4 ("a cached folder must not re-analyze anything").
The profile is an analysis-cache IDENTITY: the scorecard cache keys on the axis
set. So a selector answer can only matter while some analysis of this folder is
still going to be BUILT. Two states make the answer unusable by construction:

* **warm matrix** — every item already carries a scorecard (hydrated from disk
  or analyzed under the current set): nothing can be re-keyed. Measured live on
  a private lease: every warm reopen of a fully analyzed folder emitted exactly
  one probe-image POST that never applied (`metric profile: select scheduled`,
  no `applied` trace). One image call per folder open, forever.
* **frozen profile** — P5 stamps ``_profile_consumed_gen`` as soon as an AI
  payload of this generation was built; ``_apply_profile_outcome`` rejects a
  late reply by design, so asking for it is pure cost.

Both are skipped with a trace. An unanalyzed matrix still kicks the selector
(control test), so the stage itself is not disabled.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery import controller as controller_mod
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, Mode
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.use_cases import pipeline_stages as ps


class _Ctrl:
    """Minimal surface ``_run_profile_select_on_settle`` reads (no Qt)."""

    def __init__(self, items, *, gen: int = 3) -> None:
        self.state = SimpleNamespace(
            items=list(items), series=[], mode=Mode.CAMERA, metric_profile=None
        )
        self._judgment_domain = "ai"
        self._folder_gen = gen
        self._profile_consumed_gen = None
        self._stage_gate = ps.StageGate()
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True, api_key="k", model="m", base_url="http://h"
            )
        )
        self.widget = SimpleNamespace(refresh_cards=lambda its: None)
        self.launched: list = []
        self.selector_calls = 0

    def _pool_start(self, worker, priority=None) -> None:
        self.launched.append(worker)

    def _is_current_folder_gen(self, gen) -> bool:
        return True

    def _run_profile_select_on_settle(self):
        return controller_mod.GalleryController._run_profile_select_on_settle(self)


def _item(name: str, *, analyzed: bool) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    it.metrics.update({"sharpness": 40.0, "noise": 0.3})
    if analyzed:
        it.analysis = AiAnalysisResult(
            description="", tags=(), model="m", analyzed_at_iso="t", axes={"sharpness": 70}
        )
    return it


def _profile() -> MetricProfile:
    return MetricProfile(
        axis_ids=("sharpness", "noise"), mode="camera", source="vlm", salient_axes=("sharpness",)
    )


def _install_selector(monkeypatch, ctrl: _Ctrl) -> None:
    def _factory():
        def _selector(items, *, mode=None, settings=None):
            ctrl.selector_calls += 1
            return _profile()

        return _selector

    monkeypatch.setattr(controller_mod, "_profile_selector", _factory)


def test_a_warm_matrix_does_not_kick_the_selector(monkeypatch) -> None:
    """Once the MODEL has chosen the axes, a warm matrix has nothing to re-key.

    The heuristic case is the exception (`test_a_warm_matrix_with_a_heuristic_profile_still_asks_the_selector`):
    skipping there meant the model never got to choose for a cached folder.
    """
    ctrl = _Ctrl([_item("a.png", analyzed=True), _item("b.png", analyzed=True)])
    ctrl.state.metric_profile = _profile()  # source="vlm"
    _install_selector(monkeypatch, ctrl)
    ctrl._run_profile_select_on_settle()
    assert ctrl.selector_calls == 0, "a fully analyzed matrix has nothing to re-key"
    assert ctrl.launched == []


def test_a_frozen_profile_does_not_kick_the_selector(monkeypatch) -> None:
    ctrl = _Ctrl([_item("a.png", analyzed=False), _item("b.png", analyzed=False)])
    ctrl._profile_consumed_gen = ctrl._folder_gen
    _install_selector(monkeypatch, ctrl)
    ctrl._run_profile_select_on_settle()
    assert ctrl.selector_calls == 0, "a frozen generation rejects any answer by design"
    assert ctrl.launched == []


def test_an_unanalyzed_matrix_still_kicks_the_selector(monkeypatch) -> None:
    """Control: the stage is not disabled — only the no-op states are skipped."""
    ctrl = _Ctrl([_item("a.png", analyzed=False), _item("b.png", analyzed=False)])
    _install_selector(monkeypatch, ctrl)
    ctrl._run_profile_select_on_settle()
    assert ctrl.selector_calls == 0, "the selector runs inside the worker, not on the UI thread"
    assert len(ctrl.launched) == 1, "the stage must still schedule its worker"


# -- the settle hydrates with a REAL identity, before the selector -----------


def test_the_settle_hydrates_the_cache_before_the_selector() -> None:
    """The open-time hydrate cannot match a real analysis (mode is None there).

    The settle is the first moment ``mode`` and the profile exist, i.e. the
    identity a scorecard was written under — so the cache pass must run THERE,
    before the selector/AI tails (live 2026-10-22: without it a warm folder
    looked unanalyzed at every open and the selector spent a probe image).
    """
    from tabs.image_gallery.use_cases import triage_run

    order: list[str] = []

    class _SettleOwner:
        def __init__(self) -> None:
            self._folder_gen = 4
            self._metrics_settled_gen = -1
            self._profile_settle_pending_gen = None
            self.state = SimpleNamespace(items=[], series=[], mode="camera")
            self._judgment_domain = "algorithms"

        def _mark_local_pass(self, items, phase):
            return None

        def refresh_metric_profile(self):
            order.append("profile")

        def _hydrate_ai_cache(self, items, *, ctx=None):
            order.append("hydrate")
            return 0

        def _run_profile_select_on_settle(self):
            order.append("select")

        def _apply_fusion_ranks(self, series, *, mode=None):
            return None

    owner = _SettleOwner()
    triage_run._settle_metrics_pass(owner, [SimpleNamespace(path=Path("/gallery/a.png"))])
    assert order[:2] == ["profile", "hydrate"], order
    assert "select" in order, "the selector kick still runs after the hydrate"
    assert order.index("hydrate") < order.index("select")


def _heuristic_profile() -> MetricProfile:
    return MetricProfile(
        axis_ids=("sharpness", "noise"), mode="camera", source="heuristic", salient_axes=("sharpness",)
    )


def test_a_warm_matrix_with_a_heuristic_profile_still_asks_the_selector(monkeypatch) -> None:
    """Owner report 2026-10-26: the VLM never chose the axes for a warm folder.

    The "warm matrix" skip answers "do the cards have numbers", not "did the model
    pick the metrics". While the profile is still the heuristic fallback the
    selector must run once, or that folder keeps heuristic axes forever (the log
    showed ``profile source: heuristic-camera (fallback)`` plus
    ``analysis cache complete … no profile request`` on the same open).
    """
    ctrl = _Ctrl([_item("a.png", analyzed=True), _item("b.png", analyzed=True)])
    ctrl.state.metric_profile = _heuristic_profile()
    _install_selector(monkeypatch, ctrl)
    ctrl._run_profile_select_on_settle()
    assert len(ctrl.launched) == 1, "a heuristic profile must still ask the selector"
    assert ctrl.selector_calls == 0, "the selector runs inside the worker"


def test_a_warm_matrix_with_a_vlm_profile_is_still_skipped(monkeypatch) -> None:
    """The original owner decision stands once the model has chosen."""
    ctrl = _Ctrl([_item("a.png", analyzed=True), _item("b.png", analyzed=True)])
    ctrl.state.metric_profile = _profile()  # source="vlm"
    _install_selector(monkeypatch, ctrl)
    ctrl._run_profile_select_on_settle()
    assert ctrl.launched == [], "a vlm-pinned profile has nothing to re-key"
    assert ctrl.selector_calls == 0
