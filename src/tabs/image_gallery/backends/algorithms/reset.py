"""The Algorithms backend's reset and release (ADR 009 wave A4).

The local detectors' domain owns exactly one measured cache: the Stage-2 local
metrics (``services.metrics_cache`` — gallery_local_metrics, the per-item
records the proxy/triage path persists). Everything else a metrics reset touches
belongs to the other backend (AI scorecards, VLM profile pins, Jev ranks, VLM
tie-break/brief, A/B verdicts, the Ask answers) or is not a backend's cache at
all (the per-item state, the proxy decode cache, the Stage-2 fingerprint, the
``GalleryState`` profile slots) — those stay in ``use_cases.cache_reset``, which
is the owner-facing half of the reset.

What this module adds beyond the old in-place ``reset``:

* the **generation** advance, first, before any store is touched: from that line
  on a worker holding the previous lease is stale, and its pin is refused by
  :meth:`assert_generation` (``backends.generation``). Both halves exist because
  they catch different things — the generation stops a write that has not
  happened yet, the clear removes what already happened;
* the **namespace check**: the store this module clears must declare
  ``CACHE_NAMESPACE == descriptor.cache_namespace`` (``backends.reset
  .require_namespace``), so a copy-pasted reset in the other adapter's module
  cannot clear the local records under the AI backend's banner.

``release`` is the teardown a reset must NOT do: a reset is followed by work that
reuses the same stores, so it keeps them and only empties their contents.
"""

from __future__ import annotations

import logging

from core.log_names import APP_LOGGER_NAME

from ..reset import dropped, require_namespace

logger = logging.getLogger(APP_LOGGER_NAME)


def reset(adapter) -> dict[str, int]:
    """Drop this backend's caches + profile generations; advance the generation.

    Returns ``{}``: the local metrics count is diagnostic (the reset summary
    publishes the AI-domain counts only, and this function must not invent a
    summary field the use case's callers assert against), so it is traced here.
    """
    # Function-level imports keep this module import-pure (the adapter package
    # loads at registry composition time; the services are only needed here).
    from tabs.image_gallery.services import metrics_cache

    require_namespace(adapter.descriptor, metrics_cache)
    # FIRST: everything already in flight is stale from this line on.
    adapter._generation += 1
    adapter._profiles.clear()
    adapter._current = None
    report = dropped("local_metrics", metrics_cache.clear_all)
    logger.debug(
        "metrics reset: backend=%s generation=%d local_metrics dropped=%d",
        adapter.descriptor.backend_id,
        adapter._generation,
        report["local_metrics"],
    )
    return {}


def release(adapter) -> None:
    """Tear down what a reset cannot: the adapter holds nothing persistent.

    The local metrics live in a directory whose name is a module constant
    (``services.metrics_cache`` builds it per call), so there is no open handle
    or bound directory to release — the reset already emptied it. Stated
    explicitly so a future persistent handle has an obvious home.
    """
    reset(adapter)


__all__ = ["release", "reset"]
