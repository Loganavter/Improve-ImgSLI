"""Quick-look host glue — canvas slot + tiled full-store source population.

Split from ``preview_canvas_host.py`` (plan-gallery-split-2026-10-17, Part
C2). Bodies moved verbatim; names/signatures unchanged. Plain functions
taking the overlay as their first argument (``CODE_PATTERNS.md``).

Creates/reuses the ``QuickLookCanvasWidget`` in the preview slot, feeds it
the bounded coarse store synchronously, and registers the full
``TiledPixelStore`` via one background uncapped decode (memoized,
token-guarded).
"""

from __future__ import annotations

# Decode caps owned by services/decode_policy.py (single home).
from tabs.image_gallery.services.decode_policy import (
    COARSE_LONG_EDGE,
    PREVIEW_FULL_DECODE_EDGE,
    exceeds_edge,
)

from ._refs import host as _host


def _ensure_preview_canvas(overlay):
    """Create/reuse the canvas child in the preview slot; None if unavailable."""
    try:
        from shared.debug_flags import env_flag as _env_flag

        if _env_flag("IMGSLI_QL_NO_GPU"):
            if _host()._qlc_enabled():
                _host()._qlc_log("NO_GPU kill-switch -> no canvas")
            return None
    except Exception:
        pass
    try:
        canvas = getattr(overlay, "_preview_canvas", None)
        if canvas is not None:
            _host()._install_memo_probe(overlay, canvas)
            _host()._watch_canvas_rhi(overlay, canvas)
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
        _host()._install_memo_probe(overlay, canvas)
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
            _host()._watch_canvas_rhi(overlay, canvas)
            _host()._fit_preview_slot(overlay)
        except Exception:
            pass
        return canvas
    except Exception:
        return None


def _coarse_store_for(path, *, long_edge: int = COARSE_LONG_EDGE):
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
        memo = _host()._tiled_store_cache_lookup(overlay, key)
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
                _host()._close_store_quiet(store)
                return
            try:
                ok = store is not None and bool(store.is_open)
            except Exception:
                ok = False
            if not ok:
                return
            _host()._tiled_store_cache_store(overlay, _k, store)
            try:
                # Same item still on the canvas? (update() the canvas after.)
                canvas_now = getattr(overlay, "_preview_canvas", None)
                if canvas_now is not None:
                    setter_now = getattr(canvas_now, "set_tiled_source", None)
                    if callable(setter_now):
                        setter_now(_k, store)
            except Exception:
                pass

        worker = GenericWorker(_host()._decode_full_store_uncapped, path_s, tmp_dir)
        worker.signals.result.connect(_on_ready)
        pool.start(worker)
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
            if exceeds_edge(w, h, PREVIEW_FULL_DECODE_EDGE):
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
    canvas = _host()._ensure_preview_canvas(overlay)
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
                _memo_store = _host()._preview_store_cache_lookup(overlay, _key)
            except Exception:
                _memo_store = None
            if _memo_store is None:
                try:
                    _memo_store = _host()._store_from_pixmap(_memo)
                except Exception:
                    _memo_store = None
                if _memo_store is not None:
                    try:
                        _host()._preview_store_cache_store(overlay, _key, _memo_store)
                    except Exception:
                        pass
            if _memo_store is not None:
                _host()._close_preview_store(overlay)  # cache-aware: keeps memos open
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
                        _host()._preview_store_cache_discard(overlay, _memo_store)
                    except Exception:
                        pass
                    _host()._close_preview_store(overlay)
                    try:
                        _host()._close_store_quiet(_memo_store)
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
                    _host()._arm_tiled_dwell(overlay, canvas, raw, _key)
                except Exception:
                    pass
                try:
                    _host().reveal_preview_canvas(overlay, canvas)
                    _host()._wire_canvas_fallback(overlay, canvas, item)
                    _host()._cover_until_first_frame(overlay, canvas)
                except Exception:
                    pass
                if _dbg_on:
                    _dbg(
                        "quick look populate preview-stash-hit=%.1fms path=%s",
                        (_time.perf_counter() - _t) * 1000.0,
                        raw,
                    )
                try:  # settle-time neighbor prefetch (memos only, token-guarded)
                    _host()._schedule_prefetch(overlay, item)
                except Exception:
                    pass
                return True
            # Materialize miss fails open to the bounded build below.
        _host()._close_preview_store(overlay)  # never stack stores (fd/memmap leak)
        _t = _time.perf_counter() if _dbg_on else 0.0
        store = _host()._coarse_store_for(raw)
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
            _host()._preview_store_cache_store(overlay, _key, store)
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
                _host()._preview_store_cache_discard(overlay, store)
            except Exception:
                pass
            _host()._close_preview_store(overlay)
            try:
                _host()._close_store_quiet(store)
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
            _host()._arm_tiled_dwell(overlay, canvas, raw, _key)
        except Exception:
            pass
        try:
            _host().reveal_preview_canvas(overlay, canvas)
            _host()._wire_canvas_fallback(overlay, canvas, item)
            _host()._cover_until_first_frame(overlay, canvas)
        except Exception:
            pass
        if _dbg_on:
            _dbg(
                "quick look populate preview-set-source=%.1fms path=%s",
                (_time.perf_counter() - _t) * 1000.0,
                raw,
            )
        try:  # settle-time neighbor prefetch (memos only, token-guarded)
            _host()._schedule_prefetch(overlay, item)
        except Exception:
            pass
        return True
    except Exception:
        try:
            _host()._close_preview_store(overlay)
        except Exception:
            pass
        return False
