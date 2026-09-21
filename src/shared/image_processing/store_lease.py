"""Generation tokens for safe async access to ``TiledPixelStore``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.store.tiled_pixel_store import TiledPixelStore


@dataclass(frozen=True)
class StoreLease:
    """Captures ``(store, generation)`` so workers can reject stale I/O.

    Check-use contract (no store-side locking exists, so TOCTOU is
    narrowed, never closed): holders check ``guard()`` BEFORE a read, hold
    the ``pinned()`` strong reference across the whole read window (never
    re-derive the store mid-window), then re-check ``guard()`` AFTER any
    blocking call (thread join, ``as_completed``) or tile read — and treat
    a read-time ``RuntimeError`` (closed mid-read) as abort, returning
    ``None`` like a stale lease instead of propagating. Entry points and
    tile loops share the ``guard()`` choke point so ``None`` (unguarded,
    e.g. PIL sources with nothing to invalidate) and stale behave
    identically at every site.
    """

    store: "TiledPixelStore | None"
    generation: int

    @classmethod
    def capture(cls, store) -> "StoreLease | None":
        from engine.store.tiled_pixel_store import TiledPixelStore

        if not isinstance(store, TiledPixelStore):
            return None
        return cls(store=store, generation=store.generation)

    @classmethod
    def guard(cls, *leases: "StoreLease | None") -> bool:
        """True when every lease is ``None`` (unguarded) or valid.

        Single choke point for the None-guard parity every entry point and
        tile loop repeats: ``if not StoreLease.guard(l1, l2): return None``.
        """
        return all(lease is None or lease.valid for lease in leases)

    @classmethod
    def any_stale(cls, *leases: "StoreLease | None") -> bool:
        """Inverse of ``guard()``: True when at least one lease went stale."""
        return not cls.guard(*leases)

    @property
    def valid(self) -> bool:
        if self.store is None:
            return False
        return self.store.is_open and self.store.generation == self.generation

    def pinned(self) -> "TiledPixelStore | None":
        """Restore the guarded store for a check-use window, or ``None``.

        Hold the returned reference across the whole read (never re-derive
        the store mid-window) and re-check ``valid``/``guard()`` after any
        blocking call — close-then-read races surface as stale, not as
        torn state.
        """
        return self.restore()

    def restore(self) -> "TiledPixelStore | None":
        if not self.valid:
            return None
        return self.store
