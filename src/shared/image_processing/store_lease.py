"""Generation tokens for safe async access to ``TiledPixelStore``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore


@dataclass(frozen=True)
class StoreLease:
    """Captures ``(store, generation)`` so workers can reject stale I/O."""

    store: "TiledPixelStore | None"
    generation: int

    @classmethod
    def capture(cls, store) -> "StoreLease | None":
        from shared.image_processing.tiled_pixel_store import TiledPixelStore

        if not isinstance(store, TiledPixelStore):
            return None
        return cls(store=store, generation=store.generation)

    @property
    def valid(self) -> bool:
        if self.store is None:
            return False
        return self.store.is_open and self.store.generation == self.generation

    def restore(self) -> "TiledPixelStore | None":
        if not self.valid:
            return None
        return self.store
