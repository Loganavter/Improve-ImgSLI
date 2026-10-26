"""The analysis-backend registry — one id, one cache namespace, one adapter.

Registration is the only write operation and it is strict:

* a duplicate ``backend_id`` is a bug in the wiring (two adapters answering to
  one name), refused with ``ValueError``;
* a duplicate ``cache_namespace`` is worse — the two backends would share (and
  clear) each other's disk judgments — so it raises ``CacheNamespaceCollision``
  with both ids named.

Lookup never repairs a miss: ``registry[backend_id]`` raises ``KeyError`` for an
unknown id and names the registered set. There is no default adapter and no
``get()`` fallback — ADR 009 forbids a fallback branch in the core, and a silent
default is exactly the "whose numbers are these" defect the ADR removes.

Plugin-module convention
------------------------
A backend lives in its own module and exports its instance as ``BACKEND``::

    # tabs/image_gallery/backends/algorithms.py
    BACKEND = AlgorithmsBackend()

Discovery is by IMPORT, never by a hand-maintained list: the composition point
imports the backend modules and calls :func:`register` with each module's
``BACKEND`` (:mod:`tabs.image_gallery.backends.composition`, wired by the tab
when it builds its controller — wave A2). The registry itself imports nothing,
so it stays a plain store and a broken plugin module fails at import (loudly)
rather than disappearing from a list nobody re-reads.
"""

from __future__ import annotations

from .contract import AnalysisBackend, BackendDescriptor
from .errors import CacheNamespaceCollision

#: Every adapter must expose these as callables; a missing one is a registration
#: bug, not a backend that "does not support" an operation.
_REQUIRED_METHODS: tuple[str, ...] = (
    "make_profile",
    "measure",
    "rank",
    "reset",
    "release",
)


def _validate_descriptor(descriptor: BackendDescriptor) -> None:
    if not isinstance(descriptor, BackendDescriptor):
        raise TypeError(
            "adapter.descriptor must be a BackendDescriptor, got "
            f"{type(descriptor).__name__}"
        )
    if not descriptor.backend_id:
        raise ValueError("BackendDescriptor.backend_id must be a non-empty string")
    if not descriptor.cache_namespace:
        raise ValueError(
            f"backend {descriptor.backend_id!r} must declare a cache_namespace"
        )
    if not isinstance(descriptor.schema_version, int) or descriptor.schema_version < 1:
        raise ValueError(
            f"backend {descriptor.backend_id!r} schema_version must be an int >= 1, "
            f"got {descriptor.schema_version!r}"
        )
    if not isinstance(descriptor.capabilities, frozenset) or not all(
        isinstance(name, str) and name for name in descriptor.capabilities
    ):
        raise ValueError(
            f"backend {descriptor.backend_id!r} capabilities must be a frozenset of "
            "non-empty strings"
        )


class AnalysisBackendRegistry:
    """Store of registered adapters, keyed by ``backend_id``.

    One instance per process is exported as :data:`registry`; tests construct
    their own so a probe adapter never leaks into the app's set.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, AnalysisBackend] = {}
        self._namespace_owner: dict[str, str] = {}

    def register(self, adapter: AnalysisBackend) -> None:
        """Add *adapter*; refuse a duplicate id or a duplicate cache namespace."""
        descriptor = getattr(adapter, "descriptor", None)
        _validate_descriptor(descriptor)

        existing = self._by_id.get(descriptor.backend_id)
        if existing is not None:
            raise ValueError(
                f"duplicate backend_id {descriptor.backend_id!r}: already registered "
                f"by {type(existing).__name__}"
            )

        namespace_owner = self._namespace_owner.get(descriptor.cache_namespace)
        if namespace_owner is not None:
            raise CacheNamespaceCollision(
                cache_namespace=descriptor.cache_namespace,
                existing_backend_id=namespace_owner,
                new_backend_id=descriptor.backend_id,
            )

        for method in _REQUIRED_METHODS:
            if not callable(getattr(adapter, method, None)):
                raise TypeError(
                    f"backend {descriptor.backend_id!r} does not implement "
                    f"{method}() — the adapter contract requires it"
                )

        self._by_id[descriptor.backend_id] = adapter
        self._namespace_owner[descriptor.cache_namespace] = descriptor.backend_id

    def __getitem__(self, backend_id: str) -> AnalysisBackend:
        """Return the adapter registered under *backend_id*.

        ``KeyError`` when unknown — never a default adapter, never ``None``.
        """
        try:
            return self._by_id[backend_id]
        except KeyError:
            raise KeyError(
                f"unknown analysis backend {backend_id!r}; "
                f"registered: {sorted(self._by_id)}"
            ) from None

    def iter_backends(self) -> tuple[AnalysisBackend, ...]:
        """Every registered adapter, in ``backend_id`` order (stable across runs)."""
        return tuple(self._by_id[backend_id] for backend_id in sorted(self._by_id))


#: The process-wide store. Plugin discovery registers into THIS instance.
registry = AnalysisBackendRegistry()

#: Module-level bindings of the store's two write/read seams, so callers use
#: ``register(adapter)`` / ``iter_backends()`` as the ADR 009 interface states.
register = registry.register
iter_backends = registry.iter_backends


__all__ = [
    "AnalysisBackendRegistry",
    "iter_backends",
    "register",
    "registry",
]
