"""Target bug: an in-flight PSNR/SSIM result is accepted after the pair became
incomparable, because the no-worker path never bumps the staleness token.

Bug row: "Metrics PSNR/SSIM no staleness token"
(``docs/bugs/README.md`` → ``docs/dev/KNOWN_BUGS.md`` review wave 2, W5).

Observed at the branch base (``c52ab867``): ``MetricsService`` has a
``_metrics_request_id`` token and drops late results for a *newer* request,
but ``calculate_metrics_async`` returns early (missing/mismatched images)
without invalidating the pending id. The worker for the previous pair then
finishes and its numbers are dispatched onto the now-empty pair. The fix
bumps the token on both no-worker paths, so the stale result is dropped.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core.evidence.journal import record_evidence, reset_journal, verdict
from tabs.image_compare.services.analysis.metrics import MetricsService
from tabs.image_compare.services.analysis.runtime import (
    AnalysisRuntime,
    CoreUpdateDispatcher,
    UIUpdateDispatcher,
)

APP = QApplication.instance() or QApplication([])

STALE_PSNR = 41.25
STALE_SSIM = 0.93


class _CapturingPool:
    """Collects submitted workers instead of running them."""

    def __init__(self) -> None:
        self.started: list[object] = []

    def start(self, worker) -> None:
        self.started.append(worker)


def _image() -> SimpleNamespace:
    return SimpleNamespace(size=(8, 8), generation=None)


def _build_service() -> tuple[MetricsService, _CapturingPool, SimpleNamespace]:
    state = SimpleNamespace(
        auto_calculate_psnr=True,
        auto_calculate_ssim=False,
        psnr_value=None,
        ssim_value=None,
        image1=_image(),
        image2=_image(),
    )
    pool = _CapturingPool()
    runtime = AnalysisRuntime(
        thread_pool=pool,
        ui_updates=UIUpdateDispatcher(),
        core_updates=CoreUpdateDispatcher(),
        toast_manager_getter=lambda: None,
    )
    store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(diff_mode="off"),
            session_data=SimpleNamespace(image_state=state),
        ),
    )
    return MetricsService(store, runtime), pool, state


@pytest.fixture(autouse=True)
def _fresh_journal():
    reset_journal()
    yield
    reset_journal()


def test_metrics_staleness_repro_and_fix() -> None:
    service, pool, state = _build_service()

    # Pair A starts a worker; its request id owns the in-flight calculation.
    service.calculate_metrics_async(calc_psnr=True, calc_ssim=False)
    assert len(pool.started) == 1
    pending_request_id = service._metrics_request_id

    # The user removes the second image while that worker still runs: the
    # pair is no longer comparable, so the pending result must be invalidated.
    state.image2 = None
    service.calculate_metrics_async(calc_psnr=True, calc_ssim=False)
    assert len(pool.started) == 1  # no worker for an incomparable pair

    # The worker for pair A finally lands.
    service.on_metrics_calculated(
        (STALE_PSNR, STALE_SSIM), request_id=pending_request_id
    )

    served = state.psnr_value
    bug_present = served == STALE_PSNR
    signal = (
        f"stale_psnr={served!r} stale_ssim={state.ssim_value!r} "
        f"pair_complete={state.image1 is not None and state.image2 is not None} "
        f"pending_request_id={pending_request_id} "
        f"current_request_id={service._metrics_request_id}"
    )
    ids = (
        "tabs/image_compare/services/analysis/metrics.py::calculate_metrics_async",
        "tabs/image_compare/services/analysis/metrics.py::on_metrics_calculated",
    )

    if bug_present:
        record_evidence(
            "bug.metrics_staleness",
            kind="target_bug",
            verdict="reproduced",
            signal=signal,
            reason="a result for the previous pair was dispatched after the current pair became incomparable",
            ids=ids,
            area="image_compare.metrics",
        )
        pytest.fail(f"reproduced: {signal}")

    record_evidence(
        "bug.metrics_staleness",
        kind="target_bug",
        verdict="fixed",
        signal=signal,
        reason="pending metrics request was invalidated on the no-worker path; stale result dropped",
        ids=ids,
        area="image_compare.metrics",
    )
    assert verdict(None, "bug.metrics_staleness").verdict == "fixed"
