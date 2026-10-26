"""What a reset drops, and the ONE place that decides whose cache it is (A4).

``use_cases.cache_reset.clear_metrics_caches`` used to clear the measured caches
BY NAME: a sixteen-step list of ``ai_cache.clear_all()``,
``profile_cache.clear_default_cache()``, ``jev_cache.clear_default_cache()``, …
in a use case that owns none of them. Adding a cache therefore meant editing the
reset (and a forgotten edit was invisible until someone noticed a stale number
after a reset), while the adapters that generate those caches had no way to say
"this one is mine".

Wave A4 inverts the direction: the reset iterates the registry and asks each
adapter to ``reset()`` itself. This module holds what both adapters' reset
modules share, so "which caches do I own" is answered once:

* :func:`require_namespace` — every cache module declares the ONE
  ``descriptor.cache_namespace`` it stores under (``CACHE_NAMESPACE``); clearing
  a cache whose declared namespace is not the adapter's is ``BackendMismatch``.
  The registry refuses a *duplicate* namespace at registration
  (``CacheNamespaceCollision``); this refuses a *wrong* one at the clear, i.e.
  the case a registry cannot see: the AI adapter reaching for the local metrics
  store.
* :func:`dropped` — a clear that reports how many entries it removed and never
  raises. The per-store clear helpers already swallow their own I/O errors; a
  reset that let one propagate would leave the barrier half-applied (the epochs
  bumped, the rest of the stores untouched).

The report keys
---------------
An adapter's ``reset`` returns the counts of what it dropped, keyed by the
public fields of the reset summary it publishes (ai_files, profiles,
jev_files, vlm_files, pairwise_verdicts); an adapter that publishes
no count returns ``{}``. The summary's shape is the use case's API, so the
adapter names its caches in the vocabulary the caller already shows — and
``clear_metrics_caches`` merges whatever comes back instead of knowing which
cache produced which number.
"""

from __future__ import annotations

import logging
from typing import Callable

from core.log_names import APP_LOGGER_NAME

from .contract import BackendDescriptor
from .errors import BackendMismatch

logger = logging.getLogger(APP_LOGGER_NAME)


def require_namespace(descriptor: BackendDescriptor, *modules) -> None:
    """Refuse a cache module that declares another backend's namespace.

    ``modules`` are the ``services``/``use_cases`` cache modules an adapter is
    about to clear; each declares ``CACHE_NAMESPACE``. A module without the
    declaration is a wiring bug of the same kind (an anonymous cache cannot be
    owned), so it is refused with the same typed error rather than cleared
    hopefully.
    """
    for module in modules:
        name = getattr(module, "__name__", repr(module))
        declared = str(getattr(module, "CACHE_NAMESPACE", "") or "")
        if declared != descriptor.cache_namespace:
            raise BackendMismatch(
                what=f"cache namespace of {name}",
                expected_backend_id=descriptor.cache_namespace,
                actual_backend_id=declared or "<undeclared>",
            )


def dropped(name: str, clear: Callable[[], object]) -> dict[str, int]:
    """Run one store's ``clear`` and report ``{name: entries_removed}``.

    Never raises: the stores' own helpers already log their I/O failures, and a
    reset that aborted here would leave the barrier's epochs advanced with the
    remaining caches intact (the partial reset this whole path removes).
    """
    try:
        return {name: int(clear() or 0)}  # type: ignore[arg-type]
    except Exception:
        logger.debug("reset: %s clear failed", name, exc_info=True)
        return {name: 0}


__all__ = ["dropped", "require_namespace"]
