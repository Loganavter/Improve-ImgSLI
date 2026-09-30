"""Quick look preview + source dims — plain functions (no owner state).

The GPU canvas (``preview_canvas_host``) is the only live image surface.
Preview pixels never come from a full-res ``QPixmap`` decode of a huge
source: dimensions are probed first (``_fast_image_size``, no decode) and
anything over ``_PREVIEW_FULL_DECODE_EDGE`` goes through the scaled
``QImageReader`` read (``_load_scaled_pixmap``) — a 40k source would
otherwise cost ~6 GB for one ``QPixmap``. ``_stash_preview_source``
stashes ``_preview_full`` (pyramid-coarse first, bounded); the first-frame
cover re-derives its plate pixmap from it on every slot resize.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

# Full QPixmap decode above this edge is banned (RAM: edge^2 × 4B).
_PREVIEW_FULL_DECODE_EDGE = 2048


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
        pm = QPixmap(str(getattr(item, "path", "")))
        if pm is not None and not pm.isNull():
            out = _cover_crop(pm)
            if out is not None:
                return out
    except Exception:
        pass
    return None


def _fast_image_size(path: Path | str) -> tuple[int, int] | None:
    """Image dimensions without a full decode (QImageReader.size fast path).

    Falls back to QPixmap dims only when the reader cannot determine size.
    Never raises — returns None on any failure.
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
    try:
        pm = QPixmap(str(path))
        if pm is not None and not pm.isNull():
            return int(pm.width()), int(pm.height())
    except Exception:
        pass
    return None


def _load_scaled_pixmap(path: Path | str, target_w: int, target_h: int) -> QPixmap | None:
    """Small pixmap via QImageReader scaled read — avoids a full-res QPixmap decode.

    Falls back to QPixmap + scaled() when the reader path fails.
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
    try:
        pm = QPixmap(str(path))
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
            # Single-level pyramid (coarse base is already complete), so the
            # scale only satisfies the seam signature — L0 is always served.
            img = pyramid.best_pixels(box, 1.0)
        except Exception:
            img = None
        finally:
            try:
                pyramid.close()
            except Exception:
                pass
        if img is None:
            return None
        try:
            if img.isNull():
                return None
        except Exception:
            return None
        try:
            pm = QPixmap.fromImage(img)
        except Exception:
            return None
        try:
            if pm is None or pm.isNull():
                return None
        except Exception:
            return None
        return pm
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


def _stash_preview_source(overlay, item) -> None:
    """Stash the bounded source pixmap in ``overlay._preview_full``.

    The first-frame cover re-derives its plate from it at the live slot
    size. Coarse-direct first (bounded pyramid sample — no full-frame
    decode), then a ``QPixmap`` read, then the item thumbnail. NEVER raises.
    """
    try:
        from PySide6.QtGui import QPixmap

        try:
            overlay._preview_full = None
        except Exception:
            pass
        try:
            full = _pyramid_pixmap_for(getattr(item, "path", ""), long_edge=1024)
            if full is None or full.isNull():
                full = QPixmap(str(getattr(item, "path", "")))
            if full is not None and not full.isNull():
                try:
                    overlay._preview_full = full
                except Exception:
                    pass
        except Exception:
            pass
        if getattr(overlay, "_preview_full", None) is None:
            try:
                thumb = getattr(item, "thumbnail", None)
                if thumb is not None and not thumb.isNull():
                    overlay._preview_full = thumb
            except Exception:
                pass
    except Exception:
        pass


# Inset populates (source + sharpness-crop) live in ``insets.py``
# (CODE_PATTERNS.md thin-owner split — this file hit the 500-line
# contract gate); import paths are unchanged via ``helpers.py``.

