"""Shared pixel-cache loader — single source for B10 snippet ×4.

Four call sites duplicated the same ``lookup → from_embedded_cache/from_path``
branch. This helper centralizes it so the registry check and the store
creation live in one place.
"""

from __future__ import annotations

from pathlib import Path


def load_pixel_store(path: str | Path, *, auto_crop: bool = True):
    """Return a ``TiledPixelStore`` for *path*, using embedded cache if present.

    Mirrors the previously duplicated snippet:
    ``cached = pixel_cache_registry.lookup(str(path)); if cached: from_embedded_cache else from_path``.
    """
    from shared.image_processing import pixel_cache_registry
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    key = str(path)
    cached = pixel_cache_registry.lookup(key)
    if cached is not None:
        cache_path, width, height = cached
        return TiledPixelStore.from_embedded_cache(cache_path, width, height)
    # ``auto_crop`` is only meaningful for image_compare call sites that pass it;
    # multi_compare always uses the default. Inspect signature lazily.
    try:
        return TiledPixelStore.from_path(key, auto_crop=auto_crop)
    except TypeError:
        return TiledPixelStore.from_path(key)
