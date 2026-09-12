"""Process-wide registry of mipmap pyramids keyed by base-store uid.

A pyramid is a derived cache of one :class:`TiledPixelStore`, so it is keyed
by ``image_uid(store)`` rather than stored on document slots — slot swaps,
clones and snapshot rebuilds then cannot desynchronize a pyramid from its
base. Validity is delegated to ``PyramidPixelStore.valid`` (base store
generation): entries whose base was closed or re-unified are swept — and
their derived spill files closed — on the next registry access.

Builds run elsewhere (the image-compare session controller drives a worker);
this module only owns identity and lifecycle.
"""

from __future__ import annotations

from shared.image_processing.pyramid_pixel_store import PyramidPixelStore
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid

_pyramids: dict[int, PyramidPixelStore] = {}


def sweep() -> None:
    """Close and drop every pyramid whose base store is gone."""
    dead = [uid for uid, pyramid in _pyramids.items() if not pyramid.valid]
    for uid in dead:
        _pyramids.pop(uid).close()


def pyramid_for(store) -> PyramidPixelStore | None:
    """Registered pyramid for ``store``, or None (never a stale one)."""
    if not isinstance(store, TiledPixelStore):
        return None
    uid = image_uid(store)
    pyramid = _pyramids.get(uid)
    if pyramid is not None and not pyramid.valid:
        _pyramids.pop(uid).close()
        return None
    return pyramid


def ensure_pyramid(store) -> PyramidPixelStore | None:
    """Register (or return the existing) pyramid for ``store``.

    Returns None for non-tiled sources (preview-tier PIL images) and closed
    stores. The returned pyramid may still be building; consumers clamp via
    ``best_level_for_scale``.
    """
    if not isinstance(store, TiledPixelStore) or not store.is_open:
        return None
    sweep()
    uid = image_uid(store)
    pyramid = _pyramids.get(uid)
    if pyramid is None:
        pyramid = PyramidPixelStore(store)
        _pyramids[uid] = pyramid
    return pyramid


def clear() -> None:
    for pyramid in _pyramids.values():
        pyramid.close()
    _pyramids.clear()
