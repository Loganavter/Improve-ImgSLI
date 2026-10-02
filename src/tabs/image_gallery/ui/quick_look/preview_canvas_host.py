"""Quick-look GPU preview hosting — canvas slot lifecycle (no owner state).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one canvas-slot lifecycle: canvas/cover share one GPU-path attribution"

Split from ``preview.py`` (500-line contract gate): the canvas slot
lifecycle lives here, preview pixmaps stay there. The QRhiWidget canvas is
the only live image surface; the cover plate is a static pre-first-frame
fallback (kept when no frame ever presents). All functions fail open —
import this module lazily and treat ``None`` / ``False`` as "no GPU today".
"""

from __future__ import annotations


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
                        _close_store_quiet(old)
                    elif old is live:
                        # Same-key rebuild while live points at the stale
                        # entry: the live ref is being replaced, so close it.
                        _close_store_quiet(old)
            elif len(cache) >= _preview_store_cache_max():
                try:
                    oldest = next(iter(cache))
                except StopIteration:
                    oldest = None
                if oldest is not None:
                    evicted = cache.pop(oldest, None)
                    if evicted is not None and evicted is not store and evicted is not live:
                        _close_store_quiet(evicted)
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
                                _close_store_quiet(ev2)
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
                _close_store_quiet(st)
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
    if _is_preview_store_memo(overlay, store):
        return  # memoized — cache owns it, keep open.
    _close_store_quiet(store)


def release_preview_canvas_for_walk(overlay) -> None:
    """Walk-step release (populate-next): hide the canvas, close only the
    non-memoized live store, keep both memo dicts.

    Ownership rule: the walk keeps memos (the ``_preview_store_cache`` bound
    caps open fds/memmaps — that is what the bound is for; the pixmap stash
    ``_stash_cache`` is never dropped here either), so a walk back to a seen
    item reuses the memoized store with zero source decodes and zero
    ``_store_from_pixmap`` materializations. Overlay hide/close take the
    full ``release_preview_canvas`` instead (drops everything). Never raises.

    The live ``_preview_full`` pixmap IS dropped here (memos stay): it
    carries the previous item's pixels with no provenance, and a failed
    coarse build for the next item would otherwise leave it behind for
    ``populate_crop`` to paint as the new item's crop (neighbor content).
    ``_populate_preview_canvas`` re-stashes synchronously right after.
    """
    _drop_cover(overlay, "release-walk")
    try:
        overlay._preview_full = None
    except Exception:
        pass
    try:
        overlay._preview_canvas_pending = None
    except Exception:
        pass
    try:
        # Retire any in-flight tiled full-store decode (its result closes).
        overlay._ql_tiled_token = int(getattr(overlay, "_ql_tiled_token", 0) or 0) + 1
    except Exception:
        pass
    try:
        # Retire any in-flight neighbor prefetch (its result closes).
        overlay._ql_prefetch_token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0) + 1
    except Exception:
        pass
    try:
        canvas = getattr(overlay, "_preview_canvas", None)
        if canvas is not None:
            try:
                canvas.clear_source()
            except Exception:
                pass
            try:
                canvas.hide()
            except Exception:
                pass
    except Exception:
        pass
    _close_preview_store(overlay)
    # Keep the slot children exactly on the frame (canvas is hidden now).
    _fit_preview_slot(overlay)


def release_preview_canvas(overlay) -> None:
    """Overlay release (hide/close): walk step + drop every memoized store."""
    release_preview_canvas_for_walk(overlay)
    try:
        # Hide/close retires prefetches even when no walk populate follows.
        overlay._ql_prefetch_token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0) + 1
    except Exception:
        pass
    _drop_preview_store_cache(overlay)
    _drop_tiled_store_cache(overlay)


def _install_memo_probe(overlay, canvas) -> None:
    """Install the canvas ownership probe (idempotent, fail-open).

    The probe closes over *overlay* and reads its CURRENT store cache, so
    evict/replace/drop are always reflected without re-installing.
    """
    try:
        canvas._ql_is_memo = lambda s, _ov=overlay: _is_preview_store_memo(_ov, s)
    except Exception:
        pass


def _ensure_preview_canvas(overlay):
    """Create/reuse the canvas child in the preview slot; None if unavailable."""
    try:
        from shared.debug_flags import env_flag as _env_flag

        if _env_flag("IMGSLI_QL_NO_GPU"):
            if _qlc_enabled():
                _qlc_log("NO_GPU kill-switch -> no canvas")
            return None
    except Exception:
        pass
    try:
        canvas = getattr(overlay, "_preview_canvas", None)
        if canvas is not None:
            _install_memo_probe(overlay, canvas)
            return canvas
        try:
            from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget as _Canvas
        except Exception:
            return None
        # The canvas is created on every platform, offscreen included: it
        # simply never presents without a live RHI (the cover plate stays up
        # as the static preview, exactly like image_compare's canvas).
        host = getattr(overlay, "_preview_host", None)
        if host is None:
            return None
        canvas = _Canvas(host)
        _install_memo_probe(overlay, canvas)
        try:
            from PySide6.QtWidgets import QSizePolicy as _SP

            canvas.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Expanding)
        except Exception:
            pass
        try:
            # Canvas is a layout-external child of the slot frame: it
            # mirrors ``preview_host.rect()`` (see _fit_preview_slot) and
            # never joins the layout, so the cover<->canvas swap can never
            # split the slot between two stretched peers.
            overlay._preview_canvas = canvas
            _fit_preview_slot(overlay)
        except Exception:
            pass
        return canvas
    except Exception:
        return None


def _coarse_store_for(path, *, long_edge: int = 1024):
    """Bounded coarse store via the frozen wave-A1 pyramid seam.

    ``PyramidPixelStore.coarse_from_source`` never materializes a full
    frame (shrink-on-load / bounded scaled read); None on any miss so
    callers keep the cover plate and never feed the canvas. No second LOD
    entry, no
    ``TiledPixelStore.from_path`` full decode on this path.
    """
    try:
        from engine.store.pyramid_pixel_store import PyramidPixelStore
    except Exception:
        return None
    try:
        cap = max(1, int(long_edge))
    except Exception:
        return None
    try:
        return PyramidPixelStore.coarse_from_source(str(path), long_edge=cap)
    except Exception:
        return None


def _decode_full_store_uncapped(path, tmp_dir=None):
    """Background full-resolution decode for the tiled live path (worker).

    Delegates to the single shared engine decode entry
    (:func:`engine.cache.pyramid_demand.decode_full_store`) with **no** edge
    cap: the tiled single-source path exists precisely to show the full store
    at any resolution. Never raises (None on any failure).
    """
    from engine.cache.pyramid_demand import decode_full_store

    return decode_full_store(path, cap_edge=None, tmp_dir=tmp_dir)


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
        if key not in cache and len(cache) >= _preview_store_cache_max():
            try:
                oldest = next(iter(cache))
            except StopIteration:
                oldest = None
            if oldest is not None:
                evicted = cache.pop(oldest, None)
                if evicted is not None:
                    _close_store_quiet(evicted)
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
        _close_store_quiet(store)


def _populate_tiled_source(overlay, canvas, path, key) -> None:
    """Register a full ``TiledPixelStore`` with the canvas for array-tile draw.

    Memo hit: hand the memoized store straight to ``set_tiled_source`` (zero
    decode). Miss: kick one background uncapped decode whose result installs
    the store (memoized) and calls ``set_tiled_source`` only if the same item
    is still displayed (token guard). Every failure fails open — the
    raster/cover surface keeps serving. Never raises.
    """
    try:
        path_s = str(path or "")
        if not path_s:
            return
        if key is None:
            key = path_s  # stat-failed memo key: still a stable identity.
        setter = getattr(canvas, "set_tiled_source", None)
        if not callable(setter):
            return
        memo = _tiled_store_cache_lookup(overlay, key)
        if memo is not None:
            try:
                setter(key, memo)
            except Exception:
                pass
            return
        try:
            overlay._ql_tiled_token = int(getattr(overlay, "_ql_tiled_token", 0) or 0) + 1
            token = int(overlay._ql_tiled_token)
        except Exception:
            token = None
        try:
            from engine.store.tiled_pixel_store import resolve_pixel_spill_dir

            tmp_dir = resolve_pixel_spill_dir()
        except Exception:
            tmp_dir = None
        try:
            from PySide6.QtCore import QThreadPool

            from sli_ui_toolkit.workers import GenericWorker

            pool = QThreadPool.globalInstance()
        except Exception:
            pool = None
        if pool is None:
            return

        def _on_ready(store, _t=token, _k=key) -> None:
            try:
                live = token is None or int(getattr(overlay, "_ql_tiled_token", -1) or 0) == int(_t)
            except Exception:
                live = False
            if not live:
                # Walked away — close the private result, keep memos.
                _close_store_quiet(store)
                return
            try:
                ok = store is not None and bool(store.is_open)
            except Exception:
                ok = False
            if not ok:
                return
            _tiled_store_cache_store(overlay, _k, store)
            try:
                # Same item still on the canvas? (update() the canvas after.)
                canvas_now = getattr(overlay, "_preview_canvas", None)
                if canvas_now is not None:
                    setter_now = getattr(canvas_now, "set_tiled_source", None)
                    if callable(setter_now):
                        setter_now(_k, store)
            except Exception:
                pass
            # Full-res data just landed: wake the sharpness-crop inset
            # (path-guarded inside; no-op unless it is still unfilled).
            try:
                from tabs.image_gallery.ui import quick_look_hooks as _qlh

                _qlh.refresh_crop_for(overlay, getattr(overlay, "_current_item", None))
            except Exception:
                pass

        worker = GenericWorker(_decode_full_store_uncapped, path_s, tmp_dir)
        worker.signals.result.connect(_on_ready)
        pool.start(worker)
    except Exception:
        pass


def _arm_tiled_dwell(overlay, canvas, path, key) -> None:
    """Stage the tiled full-store kick for dwell-fire or zoom>1 (never raises).

    Dwell-gate: a plain show stages the kick but starts NO decode — the
    tiled memo stays empty and the bounded coarse store keeps driving 1.0
    frames. The canvas fires the staged kick on dwell (``_ql_on_dwell``,
    same ``_ql_gen`` retirement as the pyramid pre-warm — no second timer)
    or immediately on wheel-zoom past 1.0. A tiled memo hit still installs
    synchronously (zero decode, same as before). Any miss fails open with
    the staged kick dropped. Never raises.
    """
    try:
        path_s = str(path or "")
        if not path_s:
            return
        if key is None:
            key = path_s  # stat-failed memo key: still a stable identity.
        setter = getattr(canvas, "set_tiled_source", None)
        if not callable(setter):
            return
        memo = _tiled_store_cache_lookup(overlay, key)
        if memo is not None:
            try:
                setter(key, memo)
            except Exception:
                pass
            return
        try:
            z = float(getattr(canvas, "_zoom", 1.0))
        except Exception:
            z = 1.0
        if z > 1.0:
            # Already zoomed past 1.0: dwell is bypassed, kick now.
            _populate_tiled_source(overlay, canvas, path_s, key)
            return
        try:
            import weakref

            canvas._ql_tiled_pending = {
                "overlay": weakref.ref(overlay),
                "path": path_s,
                "key": key,
            }
        except Exception:
            pass
    except Exception:
        pass


def _schedule_prefetch(overlay, item) -> None:
    """Defer the neighbor prefetch past show settle (never raises).

    Posted as ``singleShot(0)`` so the live coarse build owns the thread
    pool + disk while ``show_for``/``_populate`` are still settling; the
    fire re-checks the prefetch token, so a walk that landed in between
    supersedes this schedule (its own populate scheduled a fresh one).
    Without an event loop the fire runs inline — still token-guarded.
    Never raises.
    """
    try:
        token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
    except Exception:
        token = 0
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda _t=token: _fire_scheduled_prefetch(overlay, item, _t))
    except Exception:
        try:
            _fire_scheduled_prefetch(overlay, item, token)
        except Exception:
            pass


def _fire_scheduled_prefetch(overlay, item, token) -> None:
    """Settle-time prefetch fire: token-gated ``_prefetch_neighbors``."""
    try:
        try:
            live = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
        except Exception:
            return
        if int(live) != int(token):
            return  # superseded by a newer show/walk — its schedule covers it.
        _prefetch_neighbors(overlay, item)
    except Exception:
        pass


def _prefetch_neighbors(overlay, item) -> None:
    """Background coarse+memo prefetch for walk neighbors (fail-open).

    Bounds: prev/next of ``overlay._series_items`` around
    ``overlay._current_idx`` only (at most two workers). Each neighbor gets
    the bounded coarse build (``_coarse_store_for`` — NEVER the uncapped
    full decode) whose result installs the materialized store in
    ``_preview_store_cache`` plus the sampled pixmap in ``_stash_cache``
    under the SAME ``_stash_cache_key`` the walk path reads — so a revisit
    is a memo hit with zero source decodes. Guarded by
    ``overlay._ql_prefetch_token`` (bumped on every show/walk populate and
    on walk/hide release): stale workers close their store via
    ``_close_store_quiet`` and never install. Never touches the live
    ``_preview_store`` / ``_preview_full`` / canvas source — memos only.
    Any miss leaves existing behavior bit-for-bit. Never raises.
    """
    try:
        try:
            series = list(getattr(overlay, "_series_items", None) or [])
        except Exception:
            return
        if len(series) < 2:
            return
        try:
            idx = int(getattr(overlay, "_current_idx", 0) or 0)
        except Exception:
            return
        targets = []
        for cand in (idx - 1, idx + 1):
            if 0 <= cand < len(series):
                try:
                    targets.append(series[cand])
                except Exception:
                    pass
        if not targets:
            return
        try:
            token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0)
        except Exception:
            token = 0
        try:
            from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key, _stash_cache_lookup
        except Exception:
            return
        try:
            from PySide6.QtCore import QThreadPool

            from sli_ui_toolkit.workers import GenericWorker

            pool = QThreadPool.globalInstance()
        except Exception:
            pool = None
        if pool is None:
            return
        for target in targets:
            try:
                path_s = str(getattr(target, "path", "") or "")
                if not path_s:
                    continue
                try:
                    key = _stash_cache_key(path_s)
                except Exception:
                    key = None
                if key is None:
                    key = path_s  # stat-failed memo key: stable identity.
                # Already memoized (store or pixmap): zero work. A pixmap
                # hit with a store miss is left to the walk path, which
                # materializes it synchronously with no source decode.
                if _preview_store_cache_lookup(overlay, key) is not None:
                    continue
                try:
                    if _stash_cache_lookup(overlay, key) is not None:
                        continue
                except Exception:
                    pass
            except Exception:
                continue

            def _on_prefetch_ready(store, _t=token, _k=key) -> None:
                try:
                    live = int(getattr(overlay, "_ql_prefetch_token", -1) or 0) == int(_t)
                except Exception:
                    live = False
                if not live:
                    # Walked/hid away — close the private result, keep memos.
                    _close_store_quiet(store)
                    return
                try:
                    ok = store is not None and bool(store.is_open)
                except Exception:
                    ok = False
                if not ok:
                    return
                # The walk may have populated meanwhile — keep its memo.
                if _preview_store_cache_lookup(overlay, _k) is not None:
                    _close_store_quiet(store)
                    return
                _preview_store_cache_store(overlay, _k, store)
                try:
                    from tabs.image_gallery.ui.quick_look.preview import (
                        _sample_coarse_pixmap,
                        _stash_cache_store,
                    )

                    pm = _sample_coarse_pixmap(store)
                    try:
                        _pm_ok = pm is not None and not pm.isNull()
                    except Exception:
                        _pm_ok = False
                    if _pm_ok:
                        _stash_cache_store(overlay, _k, pm)
                except Exception:
                    pass

            try:
                worker = GenericWorker(_coarse_store_for, path_s)
                worker.signals.result.connect(_on_prefetch_ready)
                pool.start(worker)
            except Exception:
                pass
    except Exception:
        pass


def _store_from_pixmap(pm):
    """Canvas store from a memoized stash pixmap — no source decode.

    Lossless in-memory PNG round-trip (the stash holds opaque coarse
    pixmaps, so no alpha-premultiply rounding): a memo-hit revisit feeds
    the canvas without rebuilding the coarse store from source. Bounded to
    ``_PREVIEW_FULL_DECODE_EDGE``; fail-open None (the caller falls back
    to the bounded coarse build). Never raises.
    """
    try:
        try:
            w, h = int(pm.width()), int(pm.height())
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None
        try:
            from tabs.image_gallery.ui.quick_look.preview import _PREVIEW_FULL_DECODE_EDGE

            if max(w, h) > int(_PREVIEW_FULL_DECODE_EDGE):
                return None
        except Exception:
            pass
        try:
            from PySide6.QtCore import QBuffer, QIODevice

            img = pm.toImage()
            buf = QBuffer()
            try:
                buf.open(QIODevice.WriteOnly)
                if not bool(img.save(buf, "PNG")):
                    return None
                data = bytes(buf.data())
            finally:
                try:
                    buf.close()
                except Exception:
                    pass
        except Exception:
            return None
        if not data:
            return None
        try:
            from io import BytesIO

            from PIL import Image as _PILImage

            from engine.store.tiled_pixel_store import TiledPixelStore

            with _PILImage.open(BytesIO(data)) as _im:
                pil = _im.convert("RGBA")
            store = TiledPixelStore.from_pil(pil)
        except Exception:
            return None
        try:
            if not bool(store.is_open):
                return None
        except Exception:
            return None
        return store
    except Exception:
        return None


def _populate_preview_canvas(overlay, item) -> bool:
    """GPU branch: bounded coarse store (frozen seam) into the canvas slot.

    The canvas is the only live surface; the raster cover plate holds the
    pane until its first GPU frame. Memo hit: the memoized bounded store is
    handed to the canvas directly with zero source decodes and zero PNG
    round-trip. Miss: a single coarse build is shared by the canvas store
    and the stash pixmap (no double decode) and the store is memoized
    beside the pixmap under the same key.
    Inner gallery-debug timings (``preview-coarse`` / ``preview-stash`` /
    ``preview-set-source``) split the outer ``preview=`` total. Miss
    (empty path, unreadable source, unbuilt coarse) fails closed to False
    and the cover persists — never a neighbor's content, never a
    full-frame decode.
    After the canvas takes the coarse store, the source path is handed to
    ``canvas.note_ql_source`` so wheel-zoom past 1.0x (or dwell) can
    demand-build background lazy pyramid levels for sharp zoom; walks
    retire it through the canvas generation (never built on plain walks).
    """
    import time as _time

    try:
        # Every show/walk populate retires in-flight neighbor prefetches
        # (their results close); hide/close retire via the release paths.
        overlay._ql_prefetch_token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0) + 1
    except Exception:
        pass
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

        _dbg_on = bool(_dbg_enabled())
    except Exception:
        _dbg_on = False
        _dbg = None
    canvas = _ensure_preview_canvas(overlay)
    if canvas is None:
        return False
    try:
        raw = getattr(item, "path", "")
        if not raw:
            return False
        # FAST PATH: memoized stash — a walk back to a seen item skips
        # every source decode AND the PNG encode+decode round-trip: the
        # materialized bounded store is memoized beside the pixmap under the
        # same key and handed to the canvas directly.
        try:
            from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key, _stash_cache_lookup

            _key = _stash_cache_key(raw)
            _memo = _stash_cache_lookup(overlay, _key)
        except Exception:
            _key = None
            _memo = None
        if _memo is not None:
            _t = _time.perf_counter() if _dbg_on else 0.0
            try:
                _memo_store = _preview_store_cache_lookup(overlay, _key)
            except Exception:
                _memo_store = None
            if _memo_store is None:
                try:
                    _memo_store = _store_from_pixmap(_memo)
                except Exception:
                    _memo_store = None
                if _memo_store is not None:
                    try:
                        _preview_store_cache_store(overlay, _key, _memo_store)
                    except Exception:
                        pass
            if _memo_store is not None:
                _close_preview_store(overlay)  # cache-aware: keeps memos open
                try:
                    overlay._preview_store = _memo_store
                except Exception:
                    pass
                try:
                    overlay._preview_full = _memo
                except Exception:
                    pass
                try:
                    canvas.set_source(_memo_store)
                except Exception:
                    try:
                        _preview_store_cache_discard(overlay, _memo_store)
                    except Exception:
                        pass
                    _close_preview_store(overlay)
                    try:
                        _close_store_quiet(_memo_store)
                    except Exception:
                        pass
                    return False
                # Demand-pyramid source: the canvas builds full-res levels
                # ONLY on zoom>1.0 or dwell (never on plain walks); the walk
                # release retires it via clear_source's generation bump.
                try:
                    note = getattr(canvas, "note_ql_source", None)
                    if callable(note):
                        note(str(raw))
                except Exception:
                    pass
                try:  # tiled single-source: dwell-gated (no on-show decode)
                    _arm_tiled_dwell(overlay, canvas, raw, _key)
                except Exception:
                    pass
                try:
                    reveal_preview_canvas(overlay, canvas)
                    _wire_canvas_fallback(overlay, canvas, item)
                    _cover_until_first_frame(overlay, canvas)
                except Exception:
                    pass
                if _dbg_on:
                    _dbg(
                        "quick look populate preview-stash-hit=%.1fms path=%s",
                        (_time.perf_counter() - _t) * 1000.0,
                        raw,
                    )
                try:  # settle-time neighbor prefetch (memos only, token-guarded)
                    _schedule_prefetch(overlay, item)
                except Exception:
                    pass
                return True
            # Materialize miss fails open to the bounded build below.
        _close_preview_store(overlay)  # never stack stores (fd/memmap leak)
        _t = _time.perf_counter() if _dbg_on else 0.0
        store = _coarse_store_for(raw)
        if _dbg_on:
            _dbg(
                "quick look populate preview-coarse=%.1fms path=%s",
                (_time.perf_counter() - _t) * 1000.0,
                raw,
            )
            _t = _time.perf_counter()
        if store is None:
            return False
        try:
            overlay._preview_store = store
        except Exception:
            pass
        # Stash the bounded source: the cover plate is derived from it at the
        # live slot size (same fit as the canvas), no black flash. The stash
        # samples this same open store — no second bounded decode.
        try:
            from tabs.image_gallery.ui.quick_look.preview import _stash_preview_source

            _stash_preview_source(overlay, item, _coarse=store)
        except Exception:
            pass
        # Memoize the materialized bounded store beside the pixmap memo so
        # the next revisit skips the PNG round-trip entirely (same key).
        try:
            _preview_store_cache_store(overlay, _key, store)
        except Exception:
            pass
        if _dbg_on:
            _dbg(
                "quick look populate preview-stash=%.1fms path=%s",
                (_time.perf_counter() - _t) * 1000.0,
                raw,
            )
            _t = _time.perf_counter()
        try:
            canvas.set_source(store)
        except Exception:
            try:
                _preview_store_cache_discard(overlay, store)
            except Exception:
                pass
            _close_preview_store(overlay)
            try:
                _close_store_quiet(store)
            except Exception:
                pass
            return False
        # Demand-pyramid source (see the memo-hit path above).
        try:
            note = getattr(canvas, "note_ql_source", None)
            if callable(note):
                note(str(raw))
        except Exception:
            pass
        try:  # tiled single-source: dwell-gated (no on-show decode)
            _arm_tiled_dwell(overlay, canvas, raw, _key)
        except Exception:
            pass
        try:
            reveal_preview_canvas(overlay, canvas)
            _wire_canvas_fallback(overlay, canvas, item)
            _cover_until_first_frame(overlay, canvas)
        except Exception:
            pass
        if _dbg_on:
            _dbg(
                "quick look populate preview-set-source=%.1fms path=%s",
                (_time.perf_counter() - _t) * 1000.0,
                raw,
            )
        try:  # settle-time neighbor prefetch (memos only, token-guarded)
            _schedule_prefetch(overlay, item)
        except Exception:
            pass
        return True
    except Exception:
        try:
            _close_preview_store(overlay)
        except Exception:
            pass
        return False


def reveal_preview_canvas(overlay, canvas) -> None:
    """Show the RHI canvas no earlier than the overlay chrome.

    ``QRhiWidget`` presents on its own render-thread clock and can composite
    a frame before the raster chrome paints. On a cold open (overlay not
    yet painted once) the canvas stays hidden and is staged for the first
    ``paintEvent``; once the chrome has painted — including every walk
    while open — it shows immediately (no added flicker).

    Show-then-update (2026-09-28): ``set_source`` ends with ``update()``,
    but on a walk the canvas is still hidden at that point (the populate
    release hid it), so the update is dropped; a re-shown ``QRhiWidget``
    does not render without an explicit update (only first exposure
    self-renders). Every ``show()`` below is therefore followed by
    ``update()`` — without it walks never present and die by watchdog
    with a healthy shell (``shell_ready=True``).
    """
    try:
        overlay._preview_canvas_pending = None
    except Exception:
        pass
    try:
        warm = bool(getattr(overlay, "_ql_chrome_painted", False)) and bool(overlay.isVisible())
    except Exception:
        warm = False
    if warm:
        try:
            canvas.show()
        except Exception:
            pass
        try:
            canvas.update()
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.quick_look.preview_watchdog import ensure_repump

            ensure_repump(canvas)
        except Exception:
            pass
        if _qlc_enabled():
            try:
                _qlc_log(
                    "reveal warm show+update canvas=%sx%s",
                    int(canvas.width()),
                    int(canvas.height()),
                )
            except Exception:
                pass
        return
    try:
        canvas.hide()
    except Exception:
        pass
    try:
        overlay._preview_canvas_pending = canvas
    except Exception:
        pass


def reveal_pending_preview_canvas(overlay) -> None:
    """Show a staged cold-open canvas (first chrome paint landed)."""
    try:
        canvas = getattr(overlay, "_preview_canvas_pending", None)
    except Exception:
        canvas = None
    try:
        overlay._preview_canvas_pending = None
    except Exception:
        pass
    if canvas is None:
        return
    try:
        if not bool(overlay.isVisible()):
            try:
                overlay._preview_canvas_pending = canvas
            except Exception:
                pass
            return
    except Exception:
        pass
    try:
        canvas.show()
    except Exception:
        pass
    try:
        canvas.update()
    except Exception:
        pass
    try:
        from tabs.image_gallery.ui.quick_look.preview_watchdog import ensure_repump

        ensure_repump(canvas)
    except Exception:
        pass
    _fit_preview_slot(overlay)


def _fit_preview_slot(overlay) -> None:
    """Mirror the slot frame's rect onto every layout-external child.

    ``_preview_host`` is the single laid-out geometry authority (IC-parity
    slot frame, see ``StartupPlaceholder`` in image_compare); the GPU canvas
    and the first-frame cover live outside any layout and copy
    ``host.rect()`` here. Called on the host's Resize and whenever a slot
    child is (re)created — so whichever surface is visible always occupies
    the exact same rect (seamless swap).
    """
    try:
        host = getattr(overlay, "_preview_host", None)
        if host is None:
            return
        try:
            rect = host.rect()
            assert rect.width() > 0 and rect.height() > 0
        except Exception:
            return
        for attr in ("_preview_canvas", "_preview_cover"):
            try:
                child = getattr(overlay, attr, None)
                if child is not None:
                    child.setGeometry(rect)
            except Exception:
                pass
        _fit_cover(overlay)
    except Exception:
        pass


def _cover_pixmap_from_full(overlay, w: int, h: int):
    """Canvas-fit plate pixmap from the stashed source (same fit as live).

    Uses ``preview_zoom.zoomed_frame`` — the exact fit/crop the GPU canvas
    uses — so the cover plate and the first GPU frame agree pixel-for-pixel
    (the old ``scaled(KeepAspectRatio)`` arithmetic was up to 2px off).
    Returns a ``QPixmap`` of exactly ``w`` x ``h`` (transparent letterbox
    margins; the cover's opaque plate shows through) or None. Never raises.
    """
    try:
        src = getattr(overlay, "_preview_full", None)
        if src is None or src.isNull():
            return None
        from PySide6.QtGui import QImage, QPixmap
        from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame

        frame = zoomed_frame(src.toImage(), int(w), int(h), 1.0)
        if frame is None:
            return None
        fw, fh, px = frame
        img = QImage(px, int(fw), int(fh), QImage.Format.Format_RGBA8888_Premultiplied).copy()
        pm = QPixmap.fromImage(img)
        return pm if (pm is not None and not pm.isNull()) else None
    except Exception:
        return None


def _fit_cover(overlay) -> None:
    """Cover == slot frame geometry + canvas-fit plate pixmap (fail-open)."""
    try:
        cover = getattr(overlay, "_preview_cover", None)
        host = getattr(overlay, "_preview_host", None)
        if cover is None or host is None:
            return
        try:
            rect = host.rect()
            w, h = int(rect.width()), int(rect.height())
            assert w > 0 and h > 0
        except Exception:
            return
        try:
            cover.setGeometry(rect)
        except Exception:
            pass
        try:
            if getattr(cover, "_ql_fit_for", None) != (w, h):
                pm = _cover_pixmap_from_full(overlay, w, h)
                if pm is not None:
                    cover.setPixmap(pm)
                cover._ql_fit_for = (w, h)
        except Exception:
            pass
        try:
            cover.show()
            cover.raise_()
        except Exception:
            pass
    except Exception:
        pass


def _drop_cover(overlay, reason: str = "") -> None:
    """Drop the first-frame cover (fail-open)."""
    try:
        cover = getattr(overlay, "_preview_cover", None)
        try:
            overlay._preview_cover = None
        except Exception:
            pass
        if cover is not None:
            if _qlc_enabled():
                _qlc_log("drop cover reason=%s", reason or "unspecified")
            try:
                cover.hide()
            except Exception:
                pass
            try:
                cover.deleteLater()
            except Exception:
                pass
    except Exception:
        pass


def _cover_until_first_frame(overlay, canvas) -> None:
    """Opaque sibling cover over the canvas slot until its first GPU frame.

    Startup-placeholder pattern (compare tabs): the cover is a raster
    QLabel parented to ``_preview_host`` — a layout-external sibling of the
    canvas, never a child of the ``QRhiWidget`` itself. A child of the
    canvas inherits the canvas's own transparency window (no
    ``beginPass``/clear before the shell mounts, so the slot is a
    see-through hole until the first present); a sibling paints opaquely
    from the overlay's first paint regardless of RHI state. The plate is
    derived from ``overlay._preview_full`` through the same fit as the live
    canvas (``_fit_cover``); a NULL source still yields an opaque plate
    cover — never a transparent hole. Dropped on ``firstFramePresented``.
    """
    _drop_cover(overlay, "re-cover")
    try:
        host = getattr(overlay, "_preview_host", None)
        if host is None:
            return
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QLabel as _QLabel

        cover = _QLabel(host)
        try:
            cover.setObjectName("quicklook_preview_cover")
        except Exception:
            pass
        try:
            cover.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass
        try:
            # Opaque plate fill under the pixmap: letterbox margins (and a
            # null pixmap) show card background, never the desktop through
            # an unpresented canvas. Same tone as the card background.
            from tabs.image_gallery.ui.quick_look.labels_theme import _token_color

            bg = _token_color("gallery.card.background", "#ffffff")
            if bg is not None:
                try:
                    pal = cover.palette()
                    pal.setColor(cover.backgroundRole(), bg)
                    cover.setPalette(pal)
                except Exception:
                    pass
            try:
                # Always: letterbox margins stay opaque even if the token
                # above ever resolves to nothing (palette default is opaque).
                cover.setAutoFillBackground(True)
            except Exception:
                pass
        except Exception:
            pass
        try:
            cover.setGeometry(host.rect())
        except Exception:
            pass
        try:
            cover.show()
            cover.raise_()
        except Exception:
            pass
        try:
            overlay._preview_cover = cover
        except Exception:
            pass
        # Fit cover geometry + the stashed source to the live slot.
        _fit_preview_slot(overlay)
    except Exception:
        pass


def settle_first_frame(canvas) -> None:
    """Restack the compositor, then report the first settled frame.

    MC parity (``multi_compare/ui/canvas_widget.py``): on Wayland/Vulkan a
    presented frame is recorded while the compositor still shows the
    untouched surface — only a restack makes it visible, so the cover drops
    after the flush, never on the present itself. Deferred one event-loop
    turn; ``activate=False`` (the overlay already has focus).
    """
    try:
        if getattr(canvas, "_settle_scheduled", False):
            return
        canvas._settle_scheduled = True
    except Exception:
        pass

    def _flush_emit() -> None:
        try:
            from ui.canvas_infra.rhi.rhi_present_sync import flush_qrhi_compositor

            flush_qrhi_compositor(canvas, reason="ql-first-present", activate=False)
        except Exception:
            pass
        if _qlc_enabled():
            _qlc_log("settle flush ran -> emit firstFramePresented")
        try:
            if not canvas._frame_ok:
                canvas._frame_ok = True
                try:
                    canvas.firstFramePresented.emit()
                except Exception:
                    pass
        except Exception:
            pass

    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, _flush_emit)
    except Exception:
        _flush_emit()


def _wire_canvas_fallback(overlay, canvas, item) -> None:
    """No-frame / render-failed → keep the cover plate (connect once per canvas)."""
    try:
        if getattr(canvas, "_gallery_fail_wired", False):
            return
        canvas._gallery_fail_wired = True  # type: ignore[attr-defined]
    except Exception:
        return

    def _on_first_frame(*_args) -> None:
        if _qlc_enabled():
            _qlc_log("firstFramePresented -> drop cover")
        _drop_cover(overlay, "first-frame")
        # The canvas just presented: pyramid/thumbnail caches are warm —
        # fill the sharpness-crop inset now instead of waiting for the
        # analysis round-trip (see quick_look_hooks.refresh_crop_for).
        try:
            from tabs.image_gallery.ui import quick_look_hooks as _qlh

            _qlh.refresh_crop_for(overlay, item)
        except Exception:
            pass

    try:
        canvas.firstFramePresented.connect(_on_first_frame)
    except Exception:
        pass

    def _run_fall_back(reason: str) -> None:
        # No label to hand off to: keep the cover up as the static preview
        # (it persists until a first frame ever lands).
        if _qlc_enabled():
            _qlc_log("fallback (%s) -> cover retained", reason)

    def _on_preview_failed(*_args) -> None:
        """Watchdog no-frame path (1500ms without a presented frame)."""
        _run_fall_back("previewFailed")

    def _on_render_failed(*_args) -> None:
        """Qt RHI path (immediate render failure from QRhiWidget)."""
        _run_fall_back("renderFailed")

    for _sig, _slot in (
        ("previewFailed", _on_preview_failed),
        ("renderFailed", _on_render_failed),
    ):
        try:
            getattr(canvas, _sig).connect(_slot)
        except Exception:
            pass
