"""The RESET barrier: what a metrics reset must invalidate before it clears.

Owner decision 2026-10-26: **Reset metrics cache** is a HARD BARRIER — after
``cache_reset.clear_metrics_caches`` returns, no result of a pre-reset run may
land in memory, on disk or on a card. Clearing the caches alone cannot deliver
that: every producer already in flight still holds a delivery token that the
clear never moved, so its result would arrive as a fresh measurement into the
empty world (the exact "reset did nothing" report).

Two monotonic tokens cover every producer, and the clear advances BOTH as its
very first action:

* ``owner._domain_epoch`` — the judgment-domain token, read by
  ``ai_analysis._epoch_is_current``. Covers AI scorecards (``save_analysis``),
  Jev ranks, the metric-profile selector, the series-priority hint and the
  pairwise refinement — all of which already snapshot it.
* ``owner._analysis_epoch`` — the measured-metrics token for work that has NO
  judgment domain: the Stage-2 proxy chunks (``proxy_pass``), triage
  (``triage_run``) and the per-stage producers (``metrics_stage2``). Each of
  them snapshots it in the worker closure at start and compares it at landing
  through ``ai_analysis._analysis_epoch_is_current`` (ONE gate, like G10 on the
  domain side).

The ledgers are retired in the same step: an in-flight batch count, a settled /
phase / stage-gate marker, a judge run or a paused AI queue all describe the
pass that just ended, and a later settle must not read any of them as a fact
about the now-empty world. This mirrors the folder-generation rollover
(``controller._next_folder_gen``) — the reset is a fresh world of the same
folder generation.

This module is deliberately dependency-light (plain functions over the owner,
imports resolved lazily) so the many test doubles that own only some of these
attributes keep working; every step is fail-open and never raises.
"""

from __future__ import annotations

import logging

from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def bump_delivery_epochs(owner) -> None:
    """Advance BOTH current-work tokens (the barrier's first action).

    Must run BEFORE any cache is cleared: a delivery that races the clear is
    stale from this line on.
    """
    try:
        owner._domain_epoch = int(getattr(owner, "_domain_epoch", 0) or 0) + 1
    except Exception:
        logger.debug("metrics reset: domain epoch bump failed", exc_info=True)
    try:
        owner._analysis_epoch = int(getattr(owner, "_analysis_epoch", 0) or 0) + 1
    except Exception:
        logger.debug("metrics reset: analysis epoch bump failed", exc_info=True)


def clear_delivery_ledgers(owner) -> None:
    """Retire every ledger that still describes the pre-reset world.

    The same shape as ``controller._next_folder_gen``: the winner marker, the
    analysis-phase markers, the stage gate and the judge run all belong to the
    pass that just ended. Plus the AI queue ledgers — a paused queue or a parked
    429 card would re-run pre-reset work straight through the barrier.
    """
    try:
        from tabs.image_gallery.use_cases import analysis_batch as _analysis_batch

        _analysis_batch.reset(owner)
    except Exception:
        logger.debug("metrics reset: analysis batch reset failed", exc_info=True)
    try:
        owner._metrics_settled_gen = -1
        owner._jev_inflight_gen = -1
        owner._ai_tail_started_gen = -1
        owner._done_held_gen = -1
    except Exception:
        logger.debug("metrics reset: analysis phase ledger clear failed", exc_info=True)
    try:
        gate = getattr(owner, "_stage_gate", None)
        if gate is not None:
            gate.invalidate()
    except Exception:
        logger.debug("metrics reset: stage gate invalidate failed", exc_info=True)
    try:
        owner._judge_run = None
        from tabs.image_gallery.controller import _refresh_continue_action

        _refresh_continue_action(owner)
    except Exception:
        logger.debug("metrics reset: judge run ledger clear failed", exc_info=True)
    try:
        owner._ai_queue_retry = []
        owner._ai_queue_attempts = {}
    except Exception:
        logger.debug("metrics reset: AI retry ledger clear failed", exc_info=True)
    # A paused queue owns a ``threading.Event`` its in-flight workers are BLOCKED
    # in. Release it so they reach the send gate and are dropped there on the
    # bumped epoch, instead of parking until the pause deadline. Deliberately
    # NOT ``scheduler.resume_ai_queue``: that re-dispatches the parked cards —
    # exactly the pre-reset work the barrier must not restart.
    try:
        pause = getattr(owner, "_ai_queue_pause", None)
        if pause is not None:
            try:
                pause.event.set()
            except Exception:
                pass
            owner._ai_queue_pause = None
    except Exception:
        logger.debug("metrics reset: AI queue pause clear failed", exc_info=True)


__all__ = ["bump_delivery_epochs", "clear_delivery_ledgers"]
