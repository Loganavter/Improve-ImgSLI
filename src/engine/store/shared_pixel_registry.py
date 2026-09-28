"""Shared pixel-store registry — one spill memmap per file across tabs.

Same image open in gallery + image_compare + multi_compare decodes 3x and
holds 3 spill memmaps + 3 pyramids. ``TiledPixelStore.close()`` deletes the
spill file, so sharing "as is" would let one tab pull the pixels from under
the others. This registry hands out non-owning views (``owns_file=False`` —
a mechanism that exists in the ctor but is never used) and only the registry
entry owns: real close + spill delete happen at refcount zero.

Key (decision A-box, 2026-09-28): ``(realpath, mtime_ns, size,
crop-fingerprint)`` where the fingerprint is the resolved crop box
``(l, t, r, b)`` or ``None``. Same box shares even across different
``CropService`` instances (the box is the true content input — two services
with the same config produce identical pixels); different boxes never share.
A failed crop probe is *unknown*, not "no crop": it bypasses the registry
(fail-open miss, today's behavior) instead of risking a wrong share.

Ownership handoff (atomic decode-then-publish):

- ``acquire()`` is lookup-only and never decodes. Miss → caller decodes via
  today's ``from_path`` path *outside* the registry lock, then offers the
  fresh store to ``publish()``.
- ``publish()`` re-stats the path: a file that changed mid-decode is torn
  content and is NOT shared (fail-open: caller keeps its direct store).
  A concurrent publish for the same key wins; the loser's redundant spill
  is closed (deleted) and the loser attaches to the winner.
- The lock is held only for dict/memmap ops — decode never holds it.

``release()`` is a drop-in replacement for ``close()``: registry views
detach + drop one ref (real close + delete at zero); foreign (directly
decoded) stores are simply closed, exactly like today. It never raises.
Views are registry-aware (``_SharedView.close()`` releases its ref), so
unmigrated ``close()`` call sites stay correct — Wave 3 migration is
explicitness, not a leak fix.

Engine seal: no Qt, no timers, no tabs/plugins/store imports. Every public
entry point fails open (returns ``None`` / no-op, never raises) so callers
fall back to direct ``from_path``.
"""

from __future__ import annotations

import logging
import operator
import os
import threading
from dataclasses import dataclass, field

from engine.store.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

# Must match engine.cache.image_identity._UID_INFO_KEY. Used literally (no
# private import); tests do the same. Views inherit the base entry's uid tag
# so pyramid_registry dedupes pyramids across tabs for free; a fingerprint
# mismatch falls back to a fresh tag (extra pyramid, never wrong content).
_UID_INFO_KEY = "_imgsli_uid"

_INVALID = object()


@dataclass
class SharedHandle:
    """One tab's hold on a shared spill.

    ``store`` is a non-owning view (``owns_file=False``): closing it detaches
    but never deletes the spill. ``generation_at_acquire`` snapshots the
    *base entry's* generation so consumers can detect a real close/reopen
    (views carry independent generation counters — see §6.4 of the plan).
    """

    store: TiledPixelStore
    generation_at_acquire: int
    _registry_key: tuple | None = field(default=None, repr=False, compare=False)


class _SharedView(TiledPixelStore):
    """Non-owning registry view: ``close()`` detaches AND drops one ref.

    Unmigrated ``store.close()`` call sites therefore stay correct (no leak,
    no premature delete) — ``release()`` is preferred for clarity.
    """

    def __init__(self, memmap, path, *, tile_size: int, registry_key: tuple):
        super().__init__(memmap, path, tile_size=tile_size, owns_file=False)
        self._registry_key = registry_key
        self._registry_released = False

    def close(self) -> None:
        first = not self._registry_released
        self._registry_released = True
        try:
            super().close()
        finally:
            if first:
                try:
                    _on_view_closed(self._registry_key)
                except Exception:
                    pass


@dataclass
class _Entry:
    base: TiledPixelStore  # owning store (owns_file=True); never escapes
    memmap: object  # base's memmap, shared read-only by views
    spill_path: str | None
    tile_size: int
    refs: int = 0


_entries: dict[tuple, _Entry] = {}
_lock = threading.Lock()


def _stat(path: str) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None


def _normalize_path(path: str | os.PathLike) -> str | None:
    try:
        return os.path.realpath(os.fspath(path))
    except Exception:
        return None


def _normalize_fingerprint(fp) -> object | None:
    """Crop fingerprint → hashable key part, or ``_INVALID`` (fail-open)."""
    if fp is None:
        return None
    if isinstance(fp, str):
        return fp
    if isinstance(fp, (tuple, list)) and len(fp) == 4:
        try:
            return ("box", tuple(operator.index(v) for v in fp))
        except Exception:
            return _INVALID
    # CropBox is a NamedTuple (tuple subclass, len 4) — handled above.
    return _INVALID


def _key_for(
    path: str | os.PathLike, fingerprint, *, _stat_result=None
) -> tuple | None:
    norm = _normalize_path(path)
    if norm is None:
        return None
    stat_result = _stat_result if _stat_result is not None else _stat(norm)
    if stat_result is None:
        return None
    fp = _normalize_fingerprint(fingerprint)
    if fp is _INVALID:
        return None
    mtime_ns, size = stat_result
    return (norm, int(mtime_ns), int(size), fp)


def _sweep_locked() -> None:
    """Drop entries whose base died or that hold zero refs (backstop)."""
    dead = [
        key
        for key, entry in _entries.items()
        if entry.refs <= 0 or not entry.base.is_open
    ]
    for key in dead:
        _drop_locked(key)


def _drop_locked(key: tuple) -> None:
    entry = _entries.pop(key, None)
    if entry is None:
        return
    try:
        entry.base.close()  # owning close: nulls refs + deletes the spill
    except Exception as exc:
        logger.debug("[SharedPixels] entry base close failed: %s", exc)


def _share_uid(base: TiledPixelStore, view: TiledPixelStore) -> None:
    """Give ``view`` the base entry's image uid (pyramid dedup for free)."""
    try:
        from engine.cache.image_identity import image_uid

        image_uid(base)  # ensure the base is tagged
        tag = base.info.get(_UID_INFO_KEY)
        if tag is not None:
            view.info[_UID_INFO_KEY] = tag
    except Exception:
        pass


def _attach_locked(key: tuple, entry: _Entry) -> SharedHandle | None:
    try:
        memmap = entry.memmap
        if memmap is None or not entry.base.is_open:
            return None
        entry.refs += 1
        view = _SharedView(
            memmap, entry.spill_path, tile_size=entry.tile_size, registry_key=key
        )
        _share_uid(entry.base, view)
        return SharedHandle(
            store=view,
            generation_at_acquire=entry.base.generation,
            _registry_key=key,
        )
    except Exception as exc:
        logger.debug("[SharedPixels] attach failed: %s", exc)
        try:
            entry.refs = max(0, entry.refs - 1)
        except Exception:
            pass
        return None


def acquire(
    path: str | os.PathLike,
    *,
    crop_fingerprint: str | tuple | list | None = None,
    embedded_hit: bool = False,
) -> SharedHandle | None:
    """Look up a shared spill for ``path``; ``None`` on any miss (fail-open).

    The embedded tier never consults the registry (``embedded_hit=True`` →
    ``None``); bad input (unstatable path, invalid fingerprint) also yields
    ``None`` — the caller falls back to direct ``from_path``.
    """
    try:
        if embedded_hit:
            return None
        key = _key_for(path, crop_fingerprint)
        if key is None:
            return None
        with _lock:
            _sweep_locked()
            entry = _entries.get(key)
            if entry is None:
                return None
            if not entry.base.is_open:
                _drop_locked(key)
                return None
            handle = _attach_locked(key, entry)
            if handle is not None:
                logger.debug(
                    "[SharedPixels] acquire hit refs=%d path=%s",
                    entry.refs, key[0],
                )
            return handle
    except Exception as exc:
        logger.debug("[SharedPixels] acquire failed: %s", exc)
        return None


def publish(
    path: str | os.PathLike,
    store: TiledPixelStore | None,
    *,
    crop_fingerprint: str | tuple | list | None = None,
    expected: tuple[int, int] | None = None,
) -> SharedHandle | None:
    """Offer a freshly-decoded owning ``store`` to the registry.

    Returns a handle (registry takes ownership — caller must NOT close the
    passed store) or ``None`` (caller keeps ownership, today's behavior).
    ``expected`` is the pre-decode ``(mtime_ns, size)``: a mid-decode file
    change means torn content and is never published.
    """
    try:
        if (
            store is None
            or not isinstance(store, TiledPixelStore)
            or not store.is_open
        ):
            return None
        if getattr(store, "_owns_file", True) is not True:
            return None  # only file-owning spill stores anchor entries
        if getattr(store, "_shared_entry_key", None) is not None:
            return None  # already published (or a view in disguise)
        if isinstance(store, _SharedView):
            return None
        current = _stat(os.path.realpath(os.fspath(path)))
        if current is None:
            return None
        if expected is not None and tuple(expected) != tuple(current):
            return None  # changed mid-decode: torn, don't share
        key = _key_for(path, crop_fingerprint, _stat_result=current)
        if key is None:
            return None
        with _lock:
            _sweep_locked()
            existing = _entries.get(key)
            if existing is not None and existing.base.is_open:
                # Lost the race: drop our redundant spill, join the winner.
                try:
                    store.close()
                except Exception:
                    pass
                return _attach_locked(key, existing)
            if existing is not None:
                _drop_locked(key)
            try:
                memmap = store._memmap  # single private touchpoint, same package
            except Exception:
                return None
            try:
                tile_size = int(store.tile_size)
            except Exception:
                return None
            entry = _Entry(
                base=store,
                memmap=memmap,
                spill_path=store.path,
                tile_size=tile_size,
                refs=0,
            )
            _entries[key] = entry
            try:
                store._shared_entry_key = key
            except Exception:
                pass
            handle = _attach_locked(key, entry)
            if handle is None:
                # Attach failed after taking ownership: roll back so the
                # caller-visible state stays "we own nothing".
                _drop_locked(key)
                try:
                    delattr(store, "_shared_entry_key")
                except Exception:
                    pass
                return None
            logger.debug("[SharedPixels] publish path=%s", key[0])
            return handle
    except Exception as exc:
        logger.debug("[SharedPixels] publish failed: %s", exc)
        return None


def _on_view_closed(key: tuple | None) -> None:
    if key is None:
        return
    with _lock:
        entry = _entries.get(key)
        if entry is None:
            return
        entry.refs = max(0, entry.refs - 1)
        if entry.refs <= 0:
            _drop_locked(key)


def release(handle: SharedHandle | None) -> None:
    """Drop-in replacement for ``close()``. Never raises.

    Registry views detach + drop one ref (real close + spill delete happen
    at refcount zero); foreign stores are closed exactly like today;
    ``None`` is a no-op.
    """
    try:
        if handle is None:
            return
        store = getattr(handle, "store", None)
        if store is None:
            return
        if isinstance(store, TiledPixelStore):
            try:
                store.close()  # views release their ref via _SharedView.close()
            except Exception:
                pass
    except Exception:
        pass


def sweep() -> None:
    """Drop dead/zero-ref entries (public backstop; acquire sweeps anyway)."""
    try:
        with _lock:
            _sweep_locked()
    except Exception:
        pass


def live_refs() -> int:
    """Debug counter of outstanding shared holds (log-gated, off by default)."""
    try:
        with _lock:
            return int(sum(entry.refs for entry in _entries.values()))
    except Exception:
        return 0


def entry_count() -> int:
    try:
        with _lock:
            return len(_entries)
    except Exception:
        return 0


def clear() -> None:
    """Close every base (deleting spills) and empty the registry (tests)."""
    try:
        with _lock:
            for key in list(_entries.keys()):
                _drop_locked(key)
    except Exception:
        pass
