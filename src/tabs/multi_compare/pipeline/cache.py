"""Session-owned pixel cache for the multi-compare tab (B1 state reshape).

Pixels live here — keyed ``(normpath, mtime_ns, size)`` — never in
:mod:`tabs.multi_compare.models` (``CompareSlot`` is a path-only
``SlotSource`` after B1, mirroring image_compare's
``state/document.py`` ``ImageItem``). Two tiers share one lifecycle:

- ``preview``: bounded ``QImage`` progressive previews (no lifecycle).
- ``pixel``: full-res ``TiledPixelStore`` (memmap-backed, must be closed).

Eviction closes the evicted store (``close_pixel_store`` + pyramid sweep,
PipelineCache-shaped). Undo-safety falls out of the shape: Redux snapshots
hold paths only, so no store referenced by an undo snapshot can ever be
closed out from under it — the cache is the sole owner, and eviction only
touches entries the cache itself holds. Render paths re-resolve through
:func:`resolve_slot_source` every frame, so an evicted-then-redrawn slot
demand-fills again instead of touching a closed store.

Single-flight keys (``use_cases/preview_decode._fs_key``) delegate to
:func:`cache_key_for_path` — one construction site for both.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

_PIXEL_CACHE_MAX = 16
_PREVIEW_CACHE_MAX = 16


def cache_key_for_path(path: Path | str) -> tuple[str, int, int]:
    """Content key ``(normpath, mtime_ns, size)`` (IC ``key_for`` parity).

    ``mtime+size`` keeps an overwritten-in-place file from colliding with
    its own stale decode; ``normpath`` heals textual variants of the same
    file (``/x/./f.png`` vs ``/x/f.png``, ``str`` vs ``Path``).
    """
    try:
        norm = os.path.normpath(os.fspath(path))
    except Exception:
        return (str(path), 0, 0)
    try:
        st = os.stat(norm)
        return (
            norm,
            int(getattr(st, "st_mtime_ns", 0) or 0),
            int(getattr(st, "st_size", 0) or 0),
        )
    except OSError:
        return (norm, 0, 0)


def _is_usable_pixel(store: Any) -> bool:
    is_open = getattr(store, "is_open", None)
    try:
        if callable(is_open):
            return bool(is_open())
        if is_open is not None:
            return bool(is_open)
    except Exception:
        return False
    return store is not None


def _is_usable_preview(qimage: Any) -> bool:
    try:
        return qimage is not None and not qimage.isNull()
    except Exception:
        return False


class MultiComparePixelCache:
    """Tab-lifetime pixel owner for multi-compare slots.

    Owned by ``MultiCompareController`` (one per tab page, shared across
    that page's MC sessions — keys are content-addressed, so sharing is
    safe). Never referenced from Redux state.
    """

    def __init__(
        self,
        max_pixel: int = _PIXEL_CACHE_MAX,
        max_preview: int = _PREVIEW_CACHE_MAX,
    ):
        self._pixel: OrderedDict[tuple, Any] = OrderedDict()
        self._preview: OrderedDict[tuple, Any] = OrderedDict()
        self._max_pixel = int(max_pixel)
        self._max_preview = int(max_preview)
        # Monotonic mutation counter (zoom-fanout fit cache invalidation):
        # bumped on every put/evict/clear, so a memoized per-slot size can
        # key on it and never go stale when an on-disk file replacement (or
        # eviction) swaps the resolved tier without a slot revision bump.
        self._generation = 0

    @property
    def generation(self) -> int:
        """Monotonic mutation counter (see ``__init__``)."""
        return self._generation

    def _bump_generation(self) -> None:
        self._generation += 1

    # -- pixel tier (TiledPixelStore, close on evict) --

    def get_pixel(self, path: Path | str) -> Any | None:
        key = cache_key_for_path(path)
        store = self._pixel.get(key)
        if store is None:
            return None
        if not _is_usable_pixel(store):
            self._pixel.pop(key, None)
            return None
        try:
            self._pixel.move_to_end(key)
        except Exception:
            pass
        return store

    def put_pixel(self, path: Path | str, store: Any) -> None:
        if store is None:
            return
        key = cache_key_for_path(path)
        self._pixel[key] = store
        self._bump_generation()
        try:
            self._pixel.move_to_end(key)
        except Exception:
            pass
        while len(self._pixel) > self._max_pixel:
            try:
                _k, old = self._pixel.popitem(last=False)
            except Exception:
                break
            self._close_store(old)

    def get_or_load_pixel(
        self, path: Path | str, *, crop_service: Any = None
    ) -> Any | None:
        """Sync demand fill (blocking export/offscreen paths only).

        Render paths must use :func:`resolve_slot_source` (never block the
        GUI); this is for export composition, which already runs
        synchronously and must not silently drop an evicted slot.
        """
        hit = self.get_pixel(path)
        if hit is not None:
            return hit
        try:
            from shared.image_processing.pixel_cache_loader import load_pixel_store
        except Exception:
            return None
        try:
            from shared.image_processing import embedded_pixel_cache as _emb
        except Exception:
            _emb = None
        try:
            store = load_pixel_store(
                path, crop_service=crop_service, embedded_cache=_emb
            )
        except Exception:
            logger.debug("mc cache: sync demand fill failed for %s", path)
            return None
        if store is not None:
            self.put_pixel(path, store)
        return store

    # -- preview tier (QImage, no lifecycle) --

    def get_preview(self, path: Path | str) -> Any | None:
        key = cache_key_for_path(path)
        qimage = self._preview.get(key)
        if not _is_usable_preview(qimage):
            if qimage is not None:
                self._preview.pop(key, None)
            return None
        try:
            self._preview.move_to_end(key)
        except Exception:
            pass
        return qimage

    def put_preview(self, path: Path | str, qimage: Any) -> None:
        if not _is_usable_preview(qimage):
            return
        key = cache_key_for_path(path)
        self._preview[key] = qimage
        self._bump_generation()
        try:
            self._preview.move_to_end(key)
        except Exception:
            pass
        while len(self._preview) > self._max_preview:
            try:
                self._preview.popitem(last=False)
            except Exception:
                break

    # -- combined resolve (render paths: never decodes) --

    def resolve(self, path: Path | str | None) -> Any | None:
        """Pixel tier first, then preview, else ``None`` (imageless)."""
        if path is None:
            return None
        try:
            if not Path(path).name:
                return None
        except Exception:
            return None
        hit = self.get_pixel(path)
        if hit is not None:
            return hit
        return self.get_preview(path)

    def source_size(self, path: Path | str | None) -> tuple[int, int] | None:
        """``(w, h)`` for the resolved tier, ``None`` when imageless."""
        source = self.resolve(path)
        if source is None:
            return None
        try:
            from shared.image_processing.tiled_pixel_store import pixel_source_size

            w, h = pixel_source_size(source)
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None
        return (int(w), int(h))

    # -- lifecycle --

    def evict(self, path: Path | str) -> None:
        """Drop all tiers for ``path``; pixel stores are closed (undo-safe:
        Redux snapshots hold paths only, never these objects)."""
        key = cache_key_for_path(path)
        old = self._pixel.pop(key, None)
        self._close_store(old)
        self._preview.pop(key, None)
        self._bump_generation()

    def clear(self) -> None:
        for store in list(self._pixel.values()):
            self._close_store(store)
        self._pixel.clear()
        self._preview.clear()
        self._bump_generation()

    def open_pixel_sources(self) -> dict[str, Any]:
        """``{normpath: open TiledPixelStore}`` snapshot for project save."""
        out: dict[str, Any] = {}
        for key, store in list(self._pixel.items()):
            if not _is_usable_pixel(store):
                continue
            try:
                out[str(key[0])] = store
            except Exception:
                continue
        return out

    @staticmethod
    def _close_store(store: Any) -> None:
        if store is None:
            return
        try:
            from shared.image_processing.tiled_pixel_store import close_pixel_store

            close_pixel_store(store)
        except Exception:
            pass

    # -- introspection for tests --

    @property
    def pixel_size(self) -> int:
        return len(self._pixel)

    @property
    def preview_size(self) -> int:
        return len(self._preview)


def resolve_slot_source(cache: MultiComparePixelCache | None, slot: Any) -> Any | None:
    """Pixel source for a path-only slot (``None`` cache → ``None``).

    Every composition/render read path goes through here instead of
    ``slot.image`` (deleted in B1) — headless fakes without a cache read
    as imageless, same as a slot with no tier yet.
    """
    if cache is None or slot is None:
        return None
    return cache.resolve(getattr(slot, "path", None))


def slot_source_size(
    cache: MultiComparePixelCache | None, slot: Any
) -> tuple[int, int] | None:
    """``(w, h)`` for a slot's cached tier, ``None`` when imageless."""
    if cache is None or slot is None:
        return None
    return cache.source_size(getattr(slot, "path", None))


def sizes_for_slots(
    cache: MultiComparePixelCache | None, slots: Any,
) -> dict[int, tuple[int, int]] | None:
    """``{slot_id: (w, h)}`` for cached tiers (dispatch payload helper).

    Keeps the ``SetSplitWeights`` reducer pure (B1): sizes are resolved at
    the dispatch call site from the session cache instead of read off the
    slot. ``None`` when the cache is missing (headless fakes read as all
    imageless, same as before B1).
    """
    if cache is None or slots is None:
        return None
    out: dict[int, tuple[int, int]] = {}
    try:
        for slot in slots:
            size = slot_source_size(cache, slot)
            if size is not None:
                try:
                    out[int(slot.id)] = size
                except Exception:
                    continue
    except Exception:
        return None
    return out or None
