"""Quick-look host glue — QL-cover debug gates + bounded store memos.

Split from ``preview_canvas_host.py`` (plan-gallery-split-2026-10-17, Part
C2). Bodies moved verbatim; names/signatures unchanged. Plain functions
taking the overlay as their first argument (``CODE_PATTERNS.md``).

Owns the two bounded memo dicts the canvas slot reuses across walks:
``_preview_store_cache`` (materialized bounded stores) and
``_ql_tiled_store_cache`` (full tiled stores). Closed entries are validated
before reuse and closed on evict/replace/release (fd/memmap hygiene).
"""

from __future__ import annotations

from ._refs import host as _host


def _qlc_enabled() -> bool:
    """[ql-cover] warmup trace gate (IMGSLI_QL_COVER_DEBUG=1), fail-open."""
    try:
        from tabs.image_gallery.debug import ql_cover_enabled

        return bool(ql_cover_enabled())
    except Exception:
        return False


def _qlc_log(msg: str, *args) -> None:
    try:
        from tabs.image_gallery.debug import ql_cover

        ql_cover(msg, *args)
    except Exception:
        pass


def _preview_store_cache_max() -> int:
    """Bound for the memoized store cache — mirrors the pixmap memo."""
    try:
        from tabs.image_gallery.ui.quick_look.preview import _STASH_CACHE_MAX

        return max(1, int(_STASH_CACHE_MAX))
    except Exception:
        return 4


def _close_store_quiet(store) -> None:
    """Close one store, fail-open (shared evict/replace path)."""
    try:
        if store is not None:
            store.close()
    except Exception:
        pass


def _preview_store_cache_lookup(overlay, key):
    """Memoized bounded store for *key*, or None on miss/closed/error.

    Validates ``is_open`` before reuse (never hands a closed store to the
    canvas); a closed entry is popped so the caller rebuilds once and
    re-memoizes. LRU-touches on hit so eviction drops the stalest entry —
    same key shape and bound as the pixmap memo. Never raises.
    """
    try:
        if key is None:
            return None
        try:
            cache = getattr(overlay, "_preview_store_cache", None)
        except Exception:
            return None
        if not isinstance(cache, dict):
            return None
        hit = cache.get(key)
        if hit is None:
            return None
        try:
            if not bool(hit.is_open):
                try:
                    cache.pop(key, None)
                except Exception:
                    pass
                return None
        except Exception:
            try:
                cache.pop(key, None)
            except Exception:
                pass
            return None
        try:  # LRU touch so eviction drops the stalest entry.
            cache.pop(key, None)
            cache[key] = hit
        except Exception:
            pass
        return hit
    except Exception:
        return None


def _preview_store_cache_store(overlay, key, store) -> None:
    """Memoize *store* under *key* (bounded, fail-open).

    Evicted/replaced entries are closed via the quiet close path (fd/memmap
    hygiene) unless the evicted entry is the live ``_preview_store`` (the
    canvas still reads it — the live close owns it). Never raises.
    """
    try:
        if key is None or store is None:
            return
        try:
            if not bool(store.is_open):
                return
        except Exception:
            return
        try:
            cache = getattr(overlay, "_preview_store_cache", None)
        except Exception:
            return
        if not isinstance(cache, dict):
            cache = {}
            try:
                overlay._preview_store_cache = cache
            except Exception:
                return
        try:
            live = getattr(overlay, "_preview_store", None)
        except Exception:
            live = None
        try:
            if key in cache:
                old = cache.get(key)
                if old is not None and old is not store:
                    cache.pop(key, None)
                    if old is not live:
                        _host()._close_store_quiet(old)
                    elif old is live:
                        # Same-key rebuild while live points at the stale
                        # entry: the live ref is being replaced, so close it.
                        _host()._close_store_quiet(old)
            elif len(cache) >= _host()._preview_store_cache_max():
                try:
                    oldest = next(iter(cache))
                except StopIteration:
                    oldest = None
                if oldest is not None:
                    evicted = cache.pop(oldest, None)
                    if evicted is not None and evicted is not store and evicted is not live:
                        _host()._close_store_quiet(evicted)
                    elif evicted is not None and evicted is live:
                        # Live oldest (should not happen — live is MRU) is
                        # still read by the canvas; re-insert so the live
                        # close owns it instead of leaking the new entry.
                        try:
                            cache[oldest] = evicted
                        except Exception:
                            pass
                        try:
                            oldest2 = next(iter(cache))
                        except StopIteration:
                            oldest2 = None
                        if oldest2 is not None and oldest2 is not oldest:
                            ev2 = cache.pop(oldest2, None)
                            if ev2 is not None and ev2 is not store and ev2 is not live:
                                _host()._close_store_quiet(ev2)
            cache[key] = store
        except Exception:
            pass
    except Exception:
        pass


def _preview_store_cache_discard(overlay, store) -> None:
    """Drop cache entries pointing at *store* (identity); caller closes it."""
    try:
        if store is None:
            return
        try:
            cache = getattr(overlay, "_preview_store_cache", None)
        except Exception:
            return
        if not isinstance(cache, dict):
            return
        try:
            for k, v in list(cache.items()):
                if v is store:
                    try:
                        cache.pop(k, None)
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass


def _is_preview_store_memo(overlay, store) -> bool:
    """Identity check: is *store* a live memoized entry (never raises).

    Shared by the host live-close (``_close_preview_store``) and the canvas
    ownership guard (``preview_canvas._close_held_store`` via the probe
    installed in ``_ensure_preview_canvas``): memoized stores are owned by
    the cache (evict/replace/overlay-release close them), never by whoever
    happens to hold them live. Closed entries still report True — closing
    stays a no-op for them via the ``is_open`` guard, never a double-close.
    """
    try:
        if store is None:
            return False
        try:
            cache = getattr(overlay, "_preview_store_cache", None)
        except Exception:
            return False
        if not isinstance(cache, dict):
            return False
        for v in cache.values():
            if v is store:
                return True
        return False
    except Exception:
        return False


def _drop_preview_store_cache(overlay) -> None:
    """Close + clear every memoized store (overlay release path)."""
    try:
        cache = getattr(overlay, "_preview_store_cache", None)
    except Exception:
        return
    if not isinstance(cache, dict):
        return
    try:
        live = getattr(overlay, "_preview_store", None)
    except Exception:
        live = None
    try:
        items = list(cache.items())
    except Exception:
        items = []
    try:
        cache.clear()
    except Exception:
        pass
    for _k, st in items:
        try:
            if st is not None and st is not live:
                _host()._close_store_quiet(st)
        except Exception:
            pass


def _close_preview_store(overlay) -> None:
    """Close + drop the stashed TiledPixelStore (fd/memmap hygiene).

    Cache-aware: when the live store is also the memoized entry (the
    revisit fast path hands the canvas the memoized object directly), the
    live ref is dropped WITHOUT closing so the memo stays open for the
    next revisit. Uncached lives close as before; memoized entries are
    closed on evict/replace (``_preview_store_cache_store``) and on overlay
    release (``_drop_preview_store_cache``).
    """
    try:
        store = getattr(overlay, "_preview_store", None)
    except Exception:
        store = None
    try:
        overlay._preview_store = None
    except Exception:
        pass
    if store is None:
        return
    if _host()._is_preview_store_memo(overlay, store):
        return  # memoized — cache owns it, keep open.
    _host()._close_store_quiet(store)


def _tiled_store_cache_lookup(overlay, key):
    """Memoized full tiled store for *key*, or None (validates ``is_open``)."""
    try:
        if key is None:
            return None
        cache = getattr(overlay, "_ql_tiled_store_cache", None)
        if not isinstance(cache, dict):
            return None
        hit = cache.get(key)
        if hit is None:
            return None
        try:
            if not bool(hit.is_open):
                cache.pop(key, None)
                return None
        except Exception:
            cache.pop(key, None)
            return None
        try:
            cache.pop(key, None)
            cache[key] = hit
        except Exception:
            pass
        return hit
    except Exception:
        return None


def _tiled_store_cache_store(overlay, key, store) -> None:
    """Memoize a full tiled store (bounded, host-owned; never raises)."""
    try:
        if key is None or store is None:
            return
        try:
            if not bool(store.is_open):
                return
        except Exception:
            return
        cache = getattr(overlay, "_ql_tiled_store_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            try:
                overlay._ql_tiled_store_cache = cache
            except Exception:
                return
        if key not in cache and len(cache) >= _host()._preview_store_cache_max():
            try:
                oldest = next(iter(cache))
            except StopIteration:
                oldest = None
            if oldest is not None:
                evicted = cache.pop(oldest, None)
                if evicted is not None:
                    _host()._close_store_quiet(evicted)
        cache[key] = store
    except Exception:
        pass


def _drop_tiled_store_cache(overlay) -> None:
    """Close + clear every memoized full tiled store (overlay release)."""
    try:
        cache = getattr(overlay, "_ql_tiled_store_cache", None)
    except Exception:
        return
    if not isinstance(cache, dict):
        return
    try:
        items = list(cache.items())
    except Exception:
        items = []
    try:
        cache.clear()
    except Exception:
        pass
    for _k, store in items:
        _host()._close_store_quiet(store)
