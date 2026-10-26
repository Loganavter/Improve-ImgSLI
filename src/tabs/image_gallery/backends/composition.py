"""The ONE composition point for the gallery's analysis backends (ADR 009 A2).

Both adapters are registered here and nowhere else. ``ImageGalleryPlugin.
initialize`` calls :func:`register_gallery_backends` once per process — before any
controller exists, and never repeated (a ``create_page`` call is NOT the place:
the page can be rebuilt after ``dispose``, so a page-time registration would run
again on every rebuild). Every other consumer reaches an adapter through
:func:`backend`, which performs the same (idempotent) registration first, so a
primitives-only caller — a unit test, a use case run without a page — is never
told an adapter is missing.

Idempotence is by ``backend_id`` presence, not by catching the registry's
errors: the registry stays strict (a second ``register`` of the same id is still
``ValueError`` and a shared cache namespace still ``CacheNamespaceCollision``),
while a second composition pass is a no-op. So "registered twice" is an error
where it means two different adapters and a no-op where it means the same
composition running again.

Two rules this module keeps:

* **no import side effect** — importing ``backends.composition`` registers
  nothing; only the explicit call does. A test that enumerates the registry is
  never surprised by an import elsewhere in the suite.
* **one adapter instance per process** — the module-level ``BACKEND`` of each
  package is what gets registered, so ``registry["algorithms"] is
  backends.algorithms.BACKEND`` and an adapter's in-memory profile generations
  are the ones the app writes through.
"""

from __future__ import annotations

from .ai import BACKEND as AI_BACKEND
from .algorithms import BACKEND as ALGORITHMS_BACKEND
from .contract import AnalysisBackend, PAIRWISE_CAPABILITY, require_capability
from .registry import AnalysisBackendRegistry, registry

#: The adapters this tab composes, in a fixed order (registration order never
#: decides behaviour — lookups are by id — but a stable order keeps traces and
#: test failure messages readable).
ADAPTERS: tuple[AnalysisBackend, ...] = (ALGORITHMS_BACKEND, AI_BACKEND)


def register_gallery_backends(
    target: AnalysisBackendRegistry | None = None,
) -> tuple[AnalysisBackend, ...]:
    """Register both adapters into *target* (the process registry by default).

    Returns the registered set. Safe to call any number of times: an adapter
    whose ``backend_id`` is already present is left alone, so the app's single
    composition pass and a lazily-triggered accessor cannot collide.
    """
    store = registry if target is None else target
    known = {adapter.descriptor.backend_id for adapter in store.iter_backends()}
    for adapter in ADAPTERS:
        backend_id = adapter.descriptor.backend_id
        if backend_id in known:
            continue
        store.register(adapter)
        known.add(backend_id)
    return store.iter_backends()


def backend(backend_id: str) -> AnalysisBackend:
    """The adapter registered under *backend_id* (registering on first use).

    ``KeyError`` for an unknown id — the registry's own answer, naming the
    registered set. There is no default adapter and no other-backend fallback.
    """
    register_gallery_backends()
    return registry[backend_id]


def pairwise_backend(backend_id: str) -> AnalysisBackend:
    """The adapter that must DECLARE the A/B (pairwise) refinement.

    Pairwise is a capability, not a shared operation (ADR 009 A3): the pass is
    VLM work that spends per pair, so the caller asks the descriptor of the
    backend whose domain it wants — ``CapabilityNotDeclared`` names the backend
    and its declared set when that backend never promised the feature (the
    Algorithms one). No default and no other-backend retry: a refusal is an
    answer, the same as ``registry[backend_id]``'s ``KeyError``.
    """
    adapter = backend(backend_id)
    require_capability(adapter.descriptor, PAIRWISE_CAPABILITY)
    return adapter


def ai_profile_selector():
    """The default AI-profile producer for the controller's selector seam.

    Returns a callable with the shape the controller's
    ``_run_profile_select_on_settle`` already calls — ``(items, *, mode,
    settings) -> MetricProfile | None`` — implemented by the AI adapter: the
    selector lane's one pinned call, its 5..8/evidence gate and its ``None``
    ("no answer") behaviour are unchanged, but the answer is now MADE and OWNED
    by the backend that reads it. ``None`` is preserved (never raised at this
    seam) because the controller's landing path turns it into the visible
    "no axis set / no local fallback" error state.
    """
    from .context import SeriesContext, item_key_of
    from .contract import ProfileRequest
    from .errors import BackendContractError

    def _select(items, *, mode, settings=None):
        adapter = backend("ai")
        members = tuple(items or ())
        try:
            adapter.make_profile(
                ProfileRequest(
                    mode=str(getattr(mode, "value", mode) or ""),
                    member_keys=tuple(item_key_of(item) for item in members),
                ),
                context=SeriesContext(members=members, settings=settings),
            )
        except BackendContractError:
            # "The judge did not name an axis set" is a state the controller
            # already surfaces (PROFILE_REJECT_FAILED + the card error), not an
            # exception the worker should swallow silently.
            return None
        return adapter.profile

    return _select


__all__ = [
    "ADAPTERS",
    "AI_BACKEND",
    "ALGORITHMS_BACKEND",
    "ai_profile_selector",
    "backend",
    "pairwise_backend",
    "register_gallery_backends",
]
