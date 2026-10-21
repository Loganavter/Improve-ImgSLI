"""The AI analysis batch ledger: when is the scorecard matrix SETTLED?

plan-gallery-ai-judgement P3-A / owner decision D1.1: Jev is the TERMINAL
calculator. He runs ONCE per series, at the settle of the series' measurements,
on a COMPLETE matrix — never on every arriving scorecard (the old
``_on_analysis_ready`` → ``_queue_ai_rank_on_settle`` trigger asked for a rank on
a 3/6 and then a 5/6 matrix; live 2026-10-21 19:12).

"Arriving" is what this module counts. :func:`begin` is called where a payload
is actually built (``ai_analysis._begin_analysis``), :func:`end` where a result
(or error) comes back, and :func:`dispatch_terminal_rank` is the ONE trigger: it
refuses while any analysis of the folder generation is still in flight (the
partial-vector refusal in ``GalleryController._run_jev_ranks`` would drop it
anyway) and otherwise dispatches the Jev pass. The P1 re-run (the fingerprint
``StageGate.finished`` hands back) stays the only way a SECOND call can happen.

Why a counter and not a timer: a coalescing timer cannot distinguish "the batch
is over" from "the next arrival is 50 ms away", and the cost model is per image
call — a rank request per arrival was the defect. A generation-stamped counter
is exact, and a folder switch drops the old count with the generation.

Pure bookkeeping: no Qt, no HTTP. The owner attributes are plain ints, created
on first use so the many test doubles and legacy surfaces keep working.
"""

from __future__ import annotations

import logging

from tabs.image_gallery.services.ai_client import _ai_debug

logger = logging.getLogger("ImproveImgSLI")


def _gen(owner) -> int:
    try:
        return int(getattr(owner, "_folder_gen", 0) or 0)
    except Exception:
        return 0


def begin(owner) -> int:
    """One analysis payload is in flight for the owner's folder generation."""
    gen = _gen(owner)
    try:
        if getattr(owner, "_ai_batch_gen", None) != gen:
            owner._ai_batch_gen = gen
            owner._ai_batch_pending = 0
        owner._ai_batch_pending = int(getattr(owner, "_ai_batch_pending", 0) or 0) + 1
        return owner._ai_batch_pending
    except Exception:
        return 0


def pending(owner) -> int:
    """How many analyses of the CURRENT folder generation are still in flight."""
    try:
        if getattr(owner, "_ai_batch_gen", None) != _gen(owner):
            return 0
        return max(0, int(getattr(owner, "_ai_batch_pending", 0) or 0))
    except Exception:
        return 0


def end(owner) -> int:
    """One analysis payload reported (result or error). Never negative."""
    gen = _gen(owner)
    try:
        if getattr(owner, "_ai_batch_gen", None) != gen:
            # A late reply from a previous folder generation: it does not
            # belong to this matrix, so it must not settle this one.
            return 0
        owner._ai_batch_pending = max(0, int(getattr(owner, "_ai_batch_pending", 0) or 0) - 1)
        return owner._ai_batch_pending
    except Exception:
        return 0


def reset(owner) -> None:
    """Forget the batch (a folder switch / a fresh world)."""
    try:
        owner._ai_batch_gen = _gen(owner)
        owner._ai_batch_pending = 0
    except Exception:
        pass


def dispatch_terminal_rank(owner) -> bool:
    """The ONE Jev trigger: run the rank pass when the matrix has settled.

    Returns True when a dispatch was attempted. Refuses (and says why in the
    ``[ai]`` trace) while an analysis of this folder generation is still in
    flight — the settle of the METRICS pass often happens before the VLM work it
    starts has reported, so the terminal trigger is the last arrival, not the
    metrics settle itself. The stage gate and the completeness check downstream
    still dedupe and refuse; this is only the "is the batch over" question.

    The JUDGMENT DOMAIN is deliberately not read here: ``_run_jev_ranks`` owns
    that decision from the durable authority (and the analysis-engine gate
    ``G2`` keeps domain reads in the allowlisted sites). ``getattr`` keeps the
    many doubles that only implement ``_run_jev_ranks`` working (single-flight
    stays the only gate).
    """
    waiting = pending(owner)
    if waiting:
        _ai_debug(
            "terminal rank deferred: %d analysis still in flight (one Jev call "
            "per series, on the complete matrix)",
            waiting,
        )
        return False
    run = getattr(owner, "_run_jev_ranks", None)
    if not callable(run):
        return False
    try:
        run()
        return True
    except Exception:
        logger.debug("terminal rank dispatch failed", exc_info=True)
        return False


__all__ = ["begin", "dispatch_terminal_rank", "end", "pending", "reset"]
