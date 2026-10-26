"""Work generations: how a worker proves it still owns the world it began in.

ADR 009 wave A4 makes ``reset`` an **iteration over the registry**, so a reset no
longer names the caches it clears — it asks each adapter to drop its own. The
same move fixes the other half of that contract: a cache the reset cleared can be
re-written a moment later by a worker that was already in flight, which makes the
reset look like it did nothing (the recurring "reset did nothing" report).

The barrier (``use_cases.reset_barrier``) bumps the owner's two epoch tokens and
every *landing* path compares them. That covers "apply this result to the item",
not "write this result into a cache": the three measured worker-thread pins
(``services.jev_client._pin``, the profile pin in ``use_cases.profile_ai``, the
A/B verdict in ``use_cases.pairwise_rank``) write straight to their store with no
adapter in between. A4 gives each adapter a **generation**: a monotonic integer
its ``reset`` advances, addressed together with the ownership that makes it
meaningful.

Why a pair and not a bare counter: a generation without its backend id is a
number two adapters both hold, i.e. exactly the "whose numbers are these" defect
ADR 009 removes. ``WorkGeneration`` therefore travels as ``(backend_id,
generation)`` and the refusal is decided by the OWNING adapter
(``AnalysisBackend.assert_generation``) — a worker holding the AI backend's old
generation cannot be validated by the Algorithms one.

The rule at the write site is *snapshot at the start of the work, compare
immediately before the write* (never at the top only): a pass that began before
the reset is stale from the reset's first line, so comparing at entry would
always pass and comparing at landing only catches the item, not the store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.log_names import APP_LOGGER_NAME

from .errors import BackendContractError

logger = logging.getLogger(APP_LOGGER_NAME)


@dataclass(frozen=True)
class WorkGeneration:
    """One backend's generation, as a worker snapshotted it when it started.

    Frozen: a lease is a claim about the past and must not be edited into
    matching whatever the adapter says now.
    """

    backend_id: str
    generation: int


def current_generation(backend_id: str) -> WorkGeneration | None:
    """The live lease of *backend_id*'s adapter, or ``None`` when unwired.

    Resolved through the ONE composition point, so a primitives-only caller (a
    use case driven by a test, a worker started before the page exists) gets the
    same adapter instance the app writes through. Composition failures are
    fail-open (``None`` = "unversioned", the convention
    ``ai_analysis._epoch_is_current`` already uses for its own ``epoch=None``):
    a cache write must not start raising because a registry could not be built.
    """
    try:
        from .composition import backend

        return backend(backend_id).lease()
    except Exception:
        logger.debug(
            "generation: no lease for backend %r; the write stays unversioned",
            backend_id,
            exc_info=True,
        )
        return None


def require_current(lease: WorkGeneration | None, *, operation: str) -> None:
    """Raise the OWNING adapter's typed refusal when *lease* is stale.

    ``None`` is an unversioned caller and passes (see :func:`current_generation`).
    The check is delegated, not re-implemented: the adapter owns the generation,
    so it owns the answer, and a second comparison here would be the fourth
    ad-hoc epoch check this wave exists to remove.
    """
    if lease is None:
        return
    from .composition import backend

    backend(lease.backend_id).assert_generation(lease, operation=operation)


def generation_is_current(lease: WorkGeneration | None, *, operation: str) -> bool:
    """Bool form of :func:`require_current` for the three pin sites.

    The pins document "never raises" (a disk cache write must not fail a pass),
    so they ask this instead of catching the typed error themselves: the refusal
    is still the adapter's, and it is traced here with the operation that lost
    its world. An unexpected failure is treated as current — the same
    fail-open direction as the reset barrier.
    """
    try:
        require_current(lease, operation=operation)
    except BackendContractError as exc:
        logger.debug("dropped stale work (%s): %s", operation, exc)
        return False
    except Exception:
        logger.debug(
            "generation check failed (%s); treating the write as current",
            operation,
            exc_info=True,
        )
        return True
    return True


__all__ = [
    "WorkGeneration",
    "current_generation",
    "generation_is_current",
    "require_current",
]
