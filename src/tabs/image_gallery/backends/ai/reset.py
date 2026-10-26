"""The AI backend's reset and release (ADR 009 wave A4).

The judge's domain owns every measured cache a paid backend can fill, and this
module is the ONE place that knows the list — it used to live in
``use_cases.cache_reset`` as sixteen named clears, with the Ask-AI answer cache
simply missing (it survived every reset).

Owned stores, all under ``descriptor.cache_namespace == "ai"``:

* ``services.ai_cache`` — the per-image scorecards (ai_files);
* ``services.profile_cache`` — the pinned VLM metric-profile answers
  (profiles);
* ``services.jev_cache`` — the pinned Jev rank orders (jev_files);
* ``services.vlm_cache`` — the tie-break / compare-brief files (vlm_files);
* ``use_cases.pairwise_rank.DEFAULT_CACHE`` — the process-wide A/B verdicts, the
  one measurement cache with no disk half (pairwise_verdicts);
* the Ask-AI answer caches bound to their owners through
  :meth:`AIBackend.new_ask_cache` (counted only in the trace: the reset summary's
  public fields are the five above, and inventing a sixth would change an API
  the existing tests assert exactly).

The generation is advanced FIRST, before any store is touched: a pin written by a
worker that started before this line is refused by
:meth:`AIBackend.assert_generation`, which is what the three worker-thread pins
(``jev_client._pin``, the profile pin in ``profile_ai``, the A/B ``store.put``)
ask immediately before they write.

``release`` is the teardown a reset must not do: a reset is followed by work that
reuses the same stores (the next populate hydrates through them), so it empties
their contents and keeps the objects; ``release`` drops the Ask bindings too.
"""

from __future__ import annotations

import logging

from core.log_names import APP_LOGGER_NAME

from ..reset import dropped, require_namespace

logger = logging.getLogger(APP_LOGGER_NAME)


def reset(adapter) -> dict[str, int]:
    """Drop every cache this backend owns; advance the generation; report counts.

    The returned mapping is merged into the reset summary by
    ``use_cases.cache_reset.clear_metrics_caches`` — the adapter names its own
    caches, the use case publishes them, and neither keeps a list of the
    other's.
    """
    # Function-level imports: the adapter package is imported at registry
    # composition time, and these five modules are only needed when a reset
    # actually runs (``use_cases.pairwise_rank`` in particular is heavy).
    from tabs.image_gallery.services import (
        ai_cache,
        jev_cache,
        profile_cache,
        vlm_cache,
    )
    from tabs.image_gallery.use_cases import pairwise_rank

    require_namespace(
        adapter.descriptor,
        ai_cache,
        profile_cache,
        jev_cache,
        vlm_cache,
        pairwise_rank,
    )
    # FIRST: every worker already in flight is stale from this line on.
    adapter._generation += 1
    adapter._profiles.clear()
    adapter._current = None

    report: dict[str, int] = {}
    report.update(dropped("ai_files", ai_cache.clear_all))
    report.update(dropped("profiles", profile_cache.clear_default_cache))
    report.update(dropped("jev_files", jev_cache.clear_default_cache))
    report.update(dropped("vlm_files", vlm_cache.clear_default_cache))
    report.update(dropped("pairwise_verdicts", pairwise_rank.clear_default_cache))
    # The Ask-AI answers are in-process and per owner; they are a measurement of
    # the same world (a paid answer about the items just zeroed), so they go too.
    answers = adapter.clear_ask_caches()
    logger.debug(
        "metrics reset: backend=%s generation=%d ask_answers=%d",
        adapter.descriptor.backend_id,
        adapter._generation,
        answers,
    )
    return report


def release(adapter) -> None:
    """Reset, then drop the per-owner Ask bindings the reset alone keeps.

    A reset keeps each owner's answer dict so the same session can ask again
    without re-binding; ``release`` is the end of the session, so the bindings
    (a ``WeakKeyDictionary`` keyed by owner — it would be collected anyway) are
    dropped explicitly instead of being left to the collector.
    """
    reset(adapter)
    try:
        adapter._ask_caches.clear()
    except Exception:
        logger.debug("profile release: ask bindings drop failed", exc_info=True)


__all__ = ["release", "reset"]
