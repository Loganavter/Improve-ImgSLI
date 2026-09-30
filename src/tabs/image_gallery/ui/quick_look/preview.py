"""Quick look preview + source dims — plain functions (no owner state).

The GPU canvas (``preview_canvas_host``) is the only live image surface.
Preview pixels never come from a full-res ``QPixmap`` decode of a huge
source: dimensions are probed first (``_fast_image_size``, no decode) and
anything over ``_PREVIEW_FULL_DECODE_EDGE`` goes through the scaled
``QImageReader`` read (``_load_scaled_pixmap``) — a 40k source would
otherwise cost ~6 GB for one ``QPixmap``. ``_stash_preview_source``
stashes ``_preview_full`` (pyramid-coarse first, bounded); the first-frame
cover re-derives its plate pixmap from it on every slot resize. The stash
is memoized per overlay (``_stash_cache_key`` — the crop memo's
normpath/mtime/size shape from ``insets.py``) so a walk back to a seen
item skips every decode; the host may pass its already-open coarse store
(``_coarse``) so the stash samples it instead of building a second one.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

# Full QPixmap decode above this edge is banned (RAM: edge^2 × 4B).
_PREVIEW_FULL_DECODE_EDGE = 2048

# Stash memo: per-overlay cache of the stashed bounded source, keyed
# (normpath, mtime_ns, size) like the crop memo (bounded, fail-open).
_STASH_CACHE_MAX = 4


def _stash_cache_key(item_path):
    """(normpath, mtime_ns, size) or None — fail-open, never raises."""
    try:
        norm = os.path.normpath(str(item_path))
        if not norm:
            return None
        st = os.stat(norm)
        return (norm, int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        return None


def _stash_cache_lookup(overlay, key):
    """Cached stash pixmap for *key*, or None on miss/any error."""
    try:
        if key is None:
            return None
        cache = getattr(overlay, "_stash_cache", None)
        if not isinstance(cache, dict):
            return None
        hit = cache.get(key)
        if hit is None:
            return None
        try:
            if hit.isNull():
                return None
        except Exception:
            return None
        try:  # LRU touch so eviction drops the stalest entry.
            cache.pop(key, None)
            cache[key] = hit
        except Exception:
            pass
        return hit
    except Exception:
        return None


def _stash_cache_store(overlay, key, pixmap) -> None:
    """Store the stash pixmap under *key* (bounded, fail-open)."""
    try:
        if key is None or pixmap is None:
            return
        try:
            if pixmap.isNull():
                return
        except Exception:
            return
        try:
            cache = getattr(overlay, "_stash_cache", None)
        except Exception:
            return
        if not isinstance(cache, dict):
            cache = {}
            try:
                overlay._stash_cache = cache
            except Exception:
                return
        try:
            if key not in cache and len(cache) >= _STASH_CACHE_MAX:
                try:
                    oldest = next(iter(cache))
                except StopIteration:
                    oldest = None
                if oldest is not None:
                    cache.pop(oldest, None)
            cache[key] = pixmap
        except Exception:
            pass
    except Exception:
        pass


def _thumb_pixmap(item, w: int = 66, h: int = 44) -> QPixmap | None:
    """Series-strip thumb: cover-scale to w×h, then center-crop to exactly w×h.

    Deterministic crop independent of the painter (the thumb region still
    paints ``image_fill="cover"``, but the pixmap itself already fills the
    66×44 frame, so no letterbox/pillarbox can leak through).
    """

    def _cover_crop(src: QPixmap | None) -> QPixmap | None:
        try:
            if src is None or src.isNull():
                return None
            w_i, h_i = int(w), int(h)
            scaled = src.scaled(w_i, h_i, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            try:
                if scaled.isNull():
                    return None
            except Exception:
                pass
            # ByExpanding guarantees scaled >= target on both axes; the
            # center copy below is then exactly w×h (min-guarded anyway).
            x = max(0, (scaled.width() - w_i) // 2)
            y = max(0, (scaled.height() - h_i) // 2)
            cw = min(w_i, scaled.width())
            ch = min(h_i, scaled.height())
            if cw <= 0 or ch <= 0:
                return scaled
            return scaled.copy(x, y, cw, ch)
        except Exception:
            return None

    try:
        thumb = getattr(item, "thumbnail", None)
        if thumb is not None and not thumb.isNull():
            out = _cover_crop(thumb)
            if out is not None:
                return out
        # Bounded fallback only: aspect-correct QImageReader scaled read
        # (long edge 512) then the same cover-crop — never a full-res
        # QPixmap decode (a 40k source would cost ~6 GB here).
        try:
            _p = str(getattr(item, "path", ""))
            _dims = _fast_image_size(_p)
            if _dims is not None and _dims[0] > 0 and _dims[1] > 0:
                _s = min(512.0 / _dims[0], 512.0 / _dims[1], 1.0)
                _rw = max(1, int(round(_dims[0] * _s)))
                _rh = max(1, int(round(_dims[1] * _s)))
            else:
                _rw, _rh = 512, 512
            pm = _load_scaled_pixmap(_p, _rw, _rh)
        except Exception:
            pm = None
        if pm is not None and not pm.isNull():
            out = _cover_crop(pm)
            if out is not None:
                return out
    except Exception:
        pass
    return None


def _fast_image_size(path: Path | str) -> tuple[int, int] | None:
    """Image dimensions without a full decode (QImageReader.size fast path).

    No QPixmap fallback: returns None when the reader cannot determine
    size. Never raises — returns None on any failure.
    """
    try:
        from PySide6.QtGui import QImageReader

        reader = QImageReader(str(path))
        try:
            reader.setAutoTransform(True)
        except Exception:
            pass
        size = reader.size()
        if size is not None and not size.isEmpty() and size.width() > 0 and size.height() > 0:
            return int(size.width()), int(size.height())
    except Exception:
        pass
    # No QPixmap dims fallback: probing dims must never pay a full-frame
    # decode (a 40k source would cost ~6 GB just to learn its size).
    # Callers treat None as fail-open (caption omits dims, cover persists).
    return None


def _load_scaled_pixmap(path: Path | str, target_w: int, target_h: int) -> QPixmap | None:
    """Small pixmap via QImageReader scaled read — avoids a full-res QPixmap decode.

    Falls back to a dims-gated full reader read (only when the source fits
    in ``_PREVIEW_FULL_DECODE_EDGE``); huge or unmeasurable sources fail
    open to None.
    """
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QImageReader, QPixmap as _PM

        reader = QImageReader(str(path))
        try:
            reader.setAutoTransform(True)
        except Exception:
            pass
        try:
            reader.setScaledSize(QSize(int(target_w), int(target_h)))
        except Exception:
            pass
        img = reader.read()
        if img is not None and not img.isNull():
            pm = _PM.fromImage(img)
            if pm is not None and not pm.isNull():
                # Reader scaled read may not preserve aspect — fit inside target.
                try:
                    if pm.width() > target_w or pm.height() > target_h:
                        pm = pm.scaled(
                            int(target_w),
                            int(target_h),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                except Exception:
                    pass
                return pm
    except Exception:
        pass
    # Bounded fallback only: a full read is allowed solely when the cheap
    # reader-size probe proves the source fits in _PREVIEW_FULL_DECODE_EDGE
    # (≤16 MB) — same pixels out as the old QPixmap decode for normal-size
    # sources. Huge or unmeasurable sources fail open to None (cover
    # persists / inset skipped) instead of a ~6 GB full-frame decode.
    try:
        dims = _fast_image_size(path)
        if dims is None or dims[0] <= 0 or dims[1] <= 0:
            return None
        if max(dims[0], dims[1]) > _PREVIEW_FULL_DECODE_EDGE:
            return None
        from PySide6.QtGui import QImageReader, QPixmap as _PM2

        _reader = QImageReader(str(path))
        try:
            _reader.setAutoTransform(True)
        except Exception:
            pass
        _img = _reader.read()
        if _img is None or _img.isNull():
            return None
        pm = _PM2.fromImage(_img)
        if pm is not None and not pm.isNull():
            return pm.scaled(
                int(target_w),
                int(target_h),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
    except Exception:
        pass
    return None


def _sample_coarse_pixmap(coarse, *, center_third: bool = False) -> QPixmap | None:
    """QPixmap from an OPEN coarse base — no build, no close of it.

    The ``best_pixels`` half of ``_pyramid_pixmap_for``: the host derives
    the stash from the coarse store it just built for the canvas (one
    bounded decode per walk, not two). The wrapper owns derived levels
    only — closing it never touches the caller's base. Never raises.
    """
    try:
        from engine.store.pyramid_pixel_store import PyramidPixelStore
    except Exception:
        return None
    try:
        try:
            base_w, base_h = coarse.size
        except Exception:
            return None
        if base_w <= 0 or base_h <= 0:
            return None
        if center_third:
            cw, ch = max(1, base_w // 3), max(1, base_h // 3)
            x = max(0, (base_w - cw) // 2)
            y = max(0, (base_h - ch) // 2)
            box = (x, y, x + cw, y + ch)
        else:
            box = (0, 0, base_w, base_h)
        try:
            pyramid = PyramidPixelStore(coarse)
        except Exception:
            return None
        try:
            # Single-level pyramid: L0 is already complete, the scale only
            # satisfies the seam signature.
            img = pyramid.best_pixels(box, 1.0)
        except Exception:
            img = None
        finally:
            try:
                pyramid.close()
            except Exception:
                pass
        try:
            _bad = img is None or img.isNull()
        except Exception:
            _bad = True
        if _bad:
            return None
        try:
            pm = QPixmap.fromImage(img)
            _bad = pm is None or pm.isNull()
        except Exception:
            _bad = True
        return None if _bad else pm
    except Exception:
        return None


def _pyramid_pixmap_for(path, *, center_third: bool = False, long_edge: int = 1024) -> QPixmap | None:
    """Coarse-direct pixmap via the frozen wave-A1 pyramid seam.

    Bounded decode (``coarse_from_source`` never materializes a full frame)
    sampled verbatim through ``PyramidPixelStore.best_pixels``; the returned
    pixmap holds level-native pixels and callers fit-scale it as before.
    Any miss — unreadable source, unbuilt level, stale store — fails closed
    to None so the caller keeps its existing fallback ladder (thumb /
    scaled-reader / full QPixmap). Never raises; mints no GPU resources;
    consumes the seam only (``best_pixels`` — no second LOD entry).
    """
    try:
        from engine.store.pyramid_pixel_store import PyramidPixelStore
    except Exception:
        return None
    coarse = None
    try:
        try:
            cap = max(1, int(long_edge))
        except Exception:
            return None
        try:
            coarse = PyramidPixelStore.coarse_from_source(str(path), long_edge=cap)
        except Exception:
            return None
        if coarse is None:
            return None
        return _sample_coarse_pixmap(coarse, center_third=bool(center_third))
    except Exception:
        return None
    finally:
        if coarse is not None:
            try:
                coarse.close()
            except Exception:
                pass


def _source_dimensions(src_item, src_path) -> tuple[int, int] | None:
    """Source image dimensions: metrics width/height first, QImageReader fast path."""
    metrics = getattr(src_item, "metrics", None) if src_item is not None else None
    if isinstance(metrics, dict):
        try:
            w = metrics.get("width")
            h = metrics.get("height")
            if w and h:
                return int(w), int(h)
        except Exception:
            pass
    try:
        if src_path is not None:
            dims = _fast_image_size(src_path)
            if dims is not None:
                # Cache for the next open — avoids even the reader hit.
                try:
                    if isinstance(metrics, dict):
                        metrics.setdefault("width", dims[0])
                        metrics.setdefault("height", dims[1])
                except Exception:
                    pass
                return dims
    except Exception:
        pass
    return None


# -- populate helpers -------------------------------------------------------


def populate_preview(overlay, item) -> None:
    """Single live image surface: the GPU canvas (``preview_canvas_host``).

    Never raises; a miss leaves the cover plate as the visible surface.
    """
    try:
        from tabs.image_gallery.ui.quick_look.preview_canvas_host import _populate_preview_canvas

        _populate_preview_canvas(overlay, item)
    except Exception:
        pass


def _stash_preview_source(overlay, item, _coarse=None) -> None:
    """Stash the bounded source pixmap in ``overlay._preview_full``.

    Memo hit returns the cached pixmap with zero decode work. Otherwise
    coarse-direct first — sampled from the host's already-open ``_coarse``
    store when provided (no second build), else ``_pyramid_pixmap_for`` —
    then the item thumbnail, then a scaled-reader read inside
    ``_PREVIEW_FULL_DECODE_EDGE``. Never a full-res decode; a miss leaves
    None so the cover persists. NEVER raises.
    """
    try:
        try:
            overlay._preview_full = None
        except Exception:
            pass
        try:
            _key = _stash_cache_key(getattr(item, "path", ""))
        except Exception:
            _key = None
        try:
            _hit = _stash_cache_lookup(overlay, _key)
        except Exception:
            _hit = None
        if _hit is not None:
            try:
                overlay._preview_full = _hit
            except Exception:
                pass
            return
        try:
            _path = getattr(item, "path", "")
            if _coarse is not None:
                try:
                    _open = bool(_coarse.is_open)
                except Exception:
                    _open = False
                full = _sample_coarse_pixmap(_coarse) if _open else None
            else:
                full = _pyramid_pixmap_for(_path, long_edge=1024)
            try:
                _full_ok = full is not None and not full.isNull()
            except Exception:
                _full_ok = False
            if not _full_ok:
                full = None
                try:
                    _thumb = getattr(item, "thumbnail", None)
                    if _thumb is not None and not _thumb.isNull():
                        full = _thumb
                except Exception:
                    full = None
            if full is None:
                # Aspect-correct target from the no-decode size probe, so
                # the reader read below cannot distort (exact dims when the
                # source already fits the edge: same pixels as a full read).
                try:
                    _dims = _source_dimensions(item, _path)
                    if _dims is not None and _dims[0] > 0 and _dims[1] > 0:
                        _sc = min(
                            float(_PREVIEW_FULL_DECODE_EDGE) / _dims[0],
                            float(_PREVIEW_FULL_DECODE_EDGE) / _dims[1],
                            1.0,
                        )
                        _tw = max(1, int(round(_dims[0] * _sc)))
                        _th = max(1, int(round(_dims[1] * _sc)))
                        full = _load_scaled_pixmap(_path, _tw, _th)
                except Exception:
                    full = None
            if full is not None and not full.isNull():
                try:
                    overlay._preview_full = full
                except Exception:
                    pass
                _stash_cache_store(overlay, _key, full)
        except Exception:
            pass
        if getattr(overlay, "_preview_full", None) is None:
            try:
                thumb = getattr(item, "thumbnail", None)
                if thumb is not None and not thumb.isNull():
                    overlay._preview_full = thumb
                    _stash_cache_store(overlay, _key, thumb)
            except Exception:
                pass
    except Exception:
        pass


# Inset populates (source + sharpness-crop) live in ``insets.py``
# (CODE_PATTERNS.md thin-owner split — this file hit the 500-line
# contract gate); import paths are unchanged via ``helpers.py``.

