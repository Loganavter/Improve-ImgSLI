"""Judge-run budget: state the cost of a run, then cap it (board 2026-10-24).

Extracted from ``use_cases/ai_analysis.py`` (file-size policy: that module
already carries an Audit-Meta exemption for the delivery/domain/offer cluster;
"how much may this run cost" is a different concern). Thin-owner helpers in the
same style: plain functions taking the owner (``GalleryController``).

What a judge run owes the user:

* an ESTIMATE before the first call — ``estimate_judge_run`` is a pure upper
  bound ("up to N cards x k calls"), with a token bound from the provider's
  image-token rule applied to the WIRE edge;
* a hard per-run CALL ceiling (``AiSettings.judge_run_call_ceiling``, 0 =
  unlimited) that stops the pass on the last whole card that fits and leaves a
  continue affordance (``judge_run_continue_available`` / ``continue_judge_run``);
* a run-level 429 handler (``_park_rate_limited_card``): the card is parked and
  the WHOLE queue pauses via ``use_cases/scheduler.pause_ai_queue`` — one
  request's retries never keep the other threads firing, and no card is lost.

The estimate is an upper bound BY CONSTRUCTION: the sampling lane may merge or
stop after the first draw, so the declared ``k`` is never printed as a
guaranteed draw count. The per-card request shape is untouched — batching cards
into one call is not a lever (measured 2026-10-22: 3 cards/call MAE 5.92 vs
5.81 single-card; Batch Prompting, arXiv 2301.08721, reports accuracy loss as
the batch grows).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tabs.image_gallery.models import ActivityPhase, AnalysisStatus
from tabs.image_gallery.services.activity import set_activity
from tabs.image_gallery.services.ai_client import _ai_debug
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_AI,
    ORIGIN_ACTION,
    context_for_paths,
)
from tabs.image_gallery.use_cases.analysis_batch import end as _ai_batch_end

logger = logging.getLogger("ImproveImgSLI")


# -- the pure estimator -------------------------------------------------------
# (the run-level ledger, ceiling and 429 parking follow below)

#: OpenAI-compatible vision billing rule: the image is split into tiles of
#: :data:`_IMAGE_TILE_EDGE_PX` and costs :data:`_IMAGE_TOKENS_PER_TILE` per tile
#: plus a :data:`_IMAGE_BASE_TOKENS` base. The edge used is the WIRE edge (the
#: user's ``vlm_max_edge_px`` through ``request.resolve_wire_max_edge``), i.e.
#: the image the provider actually receives, not the source file.
_IMAGE_TILE_EDGE_PX = 512
_IMAGE_TOKENS_PER_TILE = 85
_IMAGE_BASE_TOKENS = 170
#: Prompt + answer envelope per call, as an UPPER bound: the scorecard prompt
#: (axes + measured context + JSON envelope) plus the answer budget
#: (``request._ANALYZE_MIN_TOKENS`` = 1024 with reasoning headroom).
_PROMPT_TOKENS_MAX = 900
_ANSWER_TOKENS_MAX = 1600
#: ``vlm_max_edge_px == 0`` means "send the original bytes", which has no bound:
#: the estimator assumes the largest declared downscale choice (2048 px) and
#: the trace says the assumption.
_UNBOUNDED_EDGE_ASSUMED_PX = 2048

#: How many times ONE card may be re-parked by the run-level 429 handler before
#: its failure is reported as an error (a permanently limited provider must not
#: retry forever).
_AI_RATE_LIMIT_MAX_RETRIES = 2


@dataclass(frozen=True)
class JudgeRunEstimate:
    """Upper bound of ONE judge run's cost (see :func:`estimate_judge_run`)."""

    cards: int
    k: int
    calls_max: int
    tokens_max: int


def _wire_tokens_bound(edge_px: int) -> int:
    """Upper-bound image tokens for one wire copy at *edge_px* (never raises)."""
    try:
        edge = int(edge_px)
    except (TypeError, ValueError):
        edge = 0
    if edge <= 0:
        edge = _UNBOUNDED_EDGE_ASSUMED_PX
    tiles_per_side = max(1, -(-edge // _IMAGE_TILE_EDGE_PX))  # ceil division
    return _IMAGE_BASE_TOKENS + _IMAGE_TOKENS_PER_TILE * tiles_per_side * tiles_per_side


def estimate_judge_run(
    n_cards: int, k: int, *, wire_edge: int | None = None
) -> JudgeRunEstimate:
    """Upper-bound cost of a judge run over *n_cards* at *k* draws per card.

    Pure: no settings store, no I/O. ``k`` is the DECLARED draw count, so
    ``calls_max`` is a ceiling ("up to"), never a promise — the adaptive lane may
    merge after the first draw. ``tokens_max`` applies the provider's image-token
    rule to the wire edge (the user setting when *wire_edge* is omitted).
    """
    try:
        cards = max(0, int(n_cards))
    except (TypeError, ValueError):
        cards = 0
    try:
        draws = max(1, int(k))
    except (TypeError, ValueError):
        draws = 1
    if wire_edge is None:
        try:
            from tabs.image_gallery.services.ai_client import resolve_wire_max_edge

            edge = int(resolve_wire_max_edge())
        except Exception:
            edge = _UNBOUNDED_EDGE_ASSUMED_PX
    else:
        try:
            edge = int(wire_edge)
        except (TypeError, ValueError):
            edge = _UNBOUNDED_EDGE_ASSUMED_PX
    calls_max = cards * draws
    per_call = _wire_tokens_bound(edge) + _PROMPT_TOKENS_MAX + _ANSWER_TOKENS_MAX
    return JudgeRunEstimate(
        cards=cards, k=draws, calls_max=calls_max, tokens_max=calls_max * per_call
    )


_ESTIMATE_KEY = "image_gallery.activity.judge_estimate"
_CEILING_KEY = "image_gallery.activity.judge_ceiling_stop"
_ESTIMATE_DEFAULT = (
    "AI judge: up to {cards} × {k} = {calls} calls (estimate, ≤ {tokens} tokens)"
)
_CEILING_DEFAULT = (
    "AI judge paused at the {ceiling}-call limit — continue to analyze the rest"
)


@dataclass
class _JudgeRun:
    """The live run's budget ledger (owner attribute ``_judge_run``)."""

    gen: int
    k: int
    ceiling: int
    estimate: JudgeRunEstimate
    calls: int = 0
    pending: int = 0
    stopped: bool = False
    skipped: list = field(default_factory=list)


def _judge_settings(owner, settings=None):
    """The ``AiSettings`` row for budget/width, or None (a storeless double)."""
    if settings is not None:
        return settings
    try:
        store = getattr(owner, "_ai_settings_store", None)
        if store is None:
            return None
        return store.load()
    except Exception:
        return None


def _judge_k(owner, settings=None) -> int:
    row = _judge_settings(owner, settings)
    try:
        return max(1, int(getattr(row, "sample_count", 3) or 3))
    except Exception:
        return 1


def _judge_ceiling(owner, settings=None) -> int:
    row = _judge_settings(owner, settings)
    try:
        return max(0, int(getattr(row, "judge_run_call_ceiling", 0) or 0))
    except Exception:
        return 0


def _format_budget_text(owner, key: str, default: str, **values) -> str:
    """Translate *key* and fill its placeholders; fail open to the default."""
    # ONE translator helper for the whole tab (``ai_analysis._owner_tr``);
    # imported at CALL time — that module re-exports this one.
    try:
        from tabs.image_gallery.use_cases.ai_analysis import _owner_tr
    except Exception:
        _owner_tr = None
    template = _owner_tr(owner, key, default) if callable(_owner_tr) else default
    for candidate in (template, default):
        try:
            return candidate.format(**values)
        except Exception:
            continue
    return default


def _set_judge_activity(owner, text: str) -> None:
    """Show the run's budget line in the tab's ONE activity text slot.

    ``toolbar.scanning_label`` is the surface the scan/triage pass writes
    ("n/N" + spinner); the judge run reports its ESTIMATE and its ceiling stop
    there so the number exists on screen, not only in the trace. Fail-open: a
    storeless controller double has no widget/toolbar.
    """
    if not text:
        return
    try:
        label = owner.widget.toolbar.scanning_label
        label.setText(str(text))
        label.show()
    except Exception:
        pass


def _clear_judge_activity(owner) -> None:
    """Hide the run's budget line once the run has no card left in flight."""
    try:
        owner.widget.toolbar.set_triage_done()
    except Exception:
        pass


def begin_judge_run(owner, n_cards: int, *, settings=None) -> JudgeRunEstimate:
    """Open a run's budget ledger and STATE THE ESTIMATE before any call.

    Called from the analyze/reanalyze entry points (``controller.py``) — i.e.
    before the per-card loop in ``use_cases/ai_analyze.py`` schedules its first
    worker. ``n_cards`` is the context's target count: an upper bound, since a
    cache HIT spends nothing (the wording is "up to").
    """
    row = _judge_settings(owner, settings)
    k = _judge_k(owner, row)
    ceiling = _judge_ceiling(owner, row)
    est = estimate_judge_run(n_cards, k)
    gen = 0
    try:
        gen = int(getattr(owner, "_folder_gen", 0) or 0)
    except Exception:
        gen = 0
    try:
        owner._judge_run = _JudgeRun(
            gen=gen, k=k, ceiling=ceiling, estimate=est
        )
    except Exception:
        pass
    _ai_debug(
        "judge run start: up to %d x %d = %d calls (estimate, <= %d tokens, "
        "ceiling=%s)",
        est.cards,
        est.k,
        est.calls_max,
        est.tokens_max,
        ceiling or "unlimited",
    )
    if est.cards:
        _set_judge_activity(
            owner,
            _format_budget_text(
                owner,
                _ESTIMATE_KEY,
                _ESTIMATE_DEFAULT,
                cards=est.cards,
                k=est.k,
                calls=est.calls_max,
                tokens=est.tokens_max,
            ),
        )
    return est


def _current_judge_run(owner, settings=None) -> _JudgeRun | None:
    """The live run for this folder generation, creating a silent one if needed.

    The analyze entry points announce a run; a path that reached
    ``_begin_analysis`` without one (a legacy/deprecated adapter, a direct
    module call in a test) still gets a ledger, so the ceiling is never bypassed
    — it just does not re-announce an estimate it cannot size.
    """
    run = getattr(owner, "_judge_run", None)
    try:
        gen = int(getattr(owner, "_folder_gen", 0) or 0)
    except Exception:
        gen = 0
    if isinstance(run, _JudgeRun) and run.gen == gen:
        return run
    row = _judge_settings(owner, settings)
    run = _JudgeRun(
        gen=gen,
        k=_judge_k(owner, row),
        ceiling=_judge_ceiling(owner, row),
        estimate=JudgeRunEstimate(cards=0, k=_judge_k(owner, row), calls_max=0, tokens_max=0),
    )
    try:
        owner._judge_run = run
    except Exception:
        return run
    return run


def _reserve_judge_call(owner, item, settings=None) -> bool:
    """Reserve this card's calls against the run ceiling; False = stop.

    A card costs ``k`` calls (one per declared draw; the per-card request shape
    is untouched), so the pass stops on the last WHOLE card that fits and never
    exceeds the ceiling. The refused card is parked on the run's ``skipped``
    list — that list IS the continue affordance — and the trace line is exactly
    ``[ai] judge run stop: ceiling <N> calls``.
    """
    run = _current_judge_run(owner, settings)
    if run is None:  # a double that cannot hold state: never block the work
        return True
    cost = max(1, int(run.k))
    if run.ceiling <= 0 or run.calls + cost <= run.ceiling:
        run.calls += cost
        run.pending += 1
        return True
    try:
        path = item.path
    except Exception:
        path = None
    if path is not None and path not in run.skipped:
        run.skipped.append(path)
    if not run.stopped:
        run.stopped = True
        _ai_debug("judge run stop: ceiling %d calls", run.ceiling)
        _set_judge_activity(
            owner,
            _format_budget_text(
                owner, _CEILING_KEY, _CEILING_DEFAULT, ceiling=run.ceiling
            ),
        )
    return False


def _release_judge_call(owner) -> None:
    """One reserved card reached a terminal outcome (done / error / cancelled)."""
    run = getattr(owner, "_judge_run", None)
    if not isinstance(run, _JudgeRun):
        return
    run.pending = max(0, int(run.pending) - 1)
    if run.pending == 0 and not run.stopped:
        _ai_debug("judge run done: %d calls", run.calls)
        _clear_judge_activity(owner)


def judge_run_continue_available(owner) -> bool:
    """True when a ceiling stop left cards to analyze (the continue affordance)."""
    run = getattr(owner, "_judge_run", None)
    if not isinstance(run, _JudgeRun):
        return False
    return bool(run.stopped and run.ceiling > 0 and run.skipped)


def continue_judge_run(owner) -> bool:
    """Re-open the run for the cards the ceiling refused.

    The continuation starts a FRESH budget window over exactly the parked cards
    (the same ceiling still applies), so pressing continue can never silently
    spend more than one window at a time. Returns False when there is nothing
    to continue.
    """
    run = getattr(owner, "_judge_run", None)
    if not isinstance(run, _JudgeRun) or not run.stopped or not run.skipped:
        return False
    pending = list(run.skipped)
    # Re-open ONE budget window for the parked cards. Done before dispatch so a
    # fallback path that does not call ``begin_judge_run`` (the module-level
    # ``analyze``) still reserves against a fresh window; the controller entry
    # replaces this ledger with a new one anyway.
    run.skipped = []
    run.stopped = False
    run.calls = 0
    _ai_debug("judge run continue: %d cards (ceiling %d calls)", len(pending), run.ceiling)
    try:
        ctx = context_for_paths(owner, pending, origin=ORIGIN_ACTION)
        run_fn = getattr(owner, "analyze", None)
        if callable(run_fn):
            run_fn(ctx)
        else:
            from tabs.image_gallery.use_cases.ai_analysis import analyze

            analyze(owner, ctx)
    except Exception:
        # Nothing was dispatched: put the cards back so the affordance stays.
        run.skipped = list(pending)
        run.stopped = True
        logger.debug("judge run continue failed", exc_info=True)
        return False
    return True


def retry_parked_ai_cards(owner, paths) -> int:
    """Re-enter the ordinary analysis path for cards parked by a run-level 429.

    Same run ledger (so the ceiling still applies) and same per-card request
    shape: this is a re-queue, never a second pipeline. Returns how many cards
    were re-scheduled.
    """
    if not paths:
        return 0
    try:
        ctx = context_for_paths(owner, paths, origin=ORIGIN_ACTION)
    except Exception:
        return 0
    if ctx.backend != BACKEND_AI:
        return 0
    from tabs.image_gallery.use_cases.ai_analysis import _begin_analysis

    started = 0
    for path in paths:
        try:
            item = owner._find_item(path)
        except Exception:
            item = None
        if item is None:
            continue
        try:
            if getattr(item, "analysis_status", None) == AnalysisStatus.DONE:
                continue
            _begin_analysis(owner, ctx, item)
            started += 1
        except Exception:
            continue
    return started


def _park_rate_limited_card(owner, item, error) -> bool:
    """Park a 429'd card on the run-level retry path (False = report it).

    The card is NOT an error: its status goes back to NOT_ANALYZED with no
    message, it is queued on ``_ai_queue_retry``, and the WHOLE queue pauses for
    ``Retry-After`` (default: the transport's own backoff rule). After
    ``_AI_RATE_LIMIT_MAX_RETRIES`` parks the failure is reported normally.
    """
    try:
        path = item.path
    except Exception:
        return False
    attempts = getattr(owner, "_ai_queue_attempts", None)
    if not isinstance(attempts, dict):
        attempts = {}
        try:
            owner._ai_queue_attempts = attempts
        except Exception:
            return False
    key = str(path)
    used = int(attempts.get(key, 0) or 0)
    if used >= _AI_RATE_LIMIT_MAX_RETRIES:
        attempts.pop(key, None)
        return False
    attempts[key] = used + 1
    try:
        retry_after = getattr(error, "retry_after", None)
        from tabs.image_gallery.services.ai_client import _retry_delay_s

        delay = float(_retry_delay_s(retry_after, 1))
    except Exception:
        delay = 1.0
    try:
        if getattr(item, "analysis_status", None) == AnalysisStatus.PENDING:
            item.analysis_status = AnalysisStatus.NOT_ANALYZED
        item.analysis_error = None
        set_activity(item, ActivityPhase.WAITING, "ai")
        owner.widget.refresh_card(item)
    except Exception:
        logger.debug("429 park: card reset failed", exc_info=True)
    # This card's batch slot closes without a score; its retry opens a new one,
    # so the terminal rank still waits for the LAST arrival (never a partial
    # matrix) — no card is lost and nothing is ranked on the hole.
    _ai_batch_end(owner)
    try:
        parked = getattr(owner, "_ai_queue_retry", None)
        if not isinstance(parked, list):
            parked = []
            owner._ai_queue_retry = parked
        if path not in parked:
            parked.append(path)
    except Exception:
        logger.debug("429 park: retry queue write failed", exc_info=True)
    try:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        _scheduler.pause_ai_queue(owner, delay, "429 on %s" % path)
    except Exception:
        logger.debug("429 park: queue pause failed", exc_info=True)
    _ai_debug("rate limited: card parked for the run-level retry path=%s", path)
    return True


