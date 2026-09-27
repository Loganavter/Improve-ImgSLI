"""Quick look preview + source dims — plain functions (no owner state).

Preview pixels never come from a full-res ``QPixmap`` decode of a huge
source: dimensions are probed first (``_fast_image_size``, no decode) and
anything over ``_PREVIEW_FULL_DECODE_EDGE`` goes through the scaled
``QImageReader`` read (``_load_scaled_pixmap``) — a 40k source would
otherwise cost ~6 GB for one ``QPixmap``. The stashed ``_preview_full``
is therefore at most ~2k on the long edge; ``_rescale_preview_to_host``
re-derives the shown pixmap from it on every card resize.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

# Full QPixmap decode above this edge is banned (RAM: edge^2 × 4B).
_PREVIEW_FULL_DECODE_EDGE = 2048


def _load_preview_pixmap(path: Path, target_w: int = 640, target_h: int = 456) -> QPixmap | None:
    """Preview pixmap for *path* without ever full-decoding a huge source."""
    try:
        dims = _fast_image_size(path)
        if dims is not None and max(int(dims[0]), int(dims[1])) > _PREVIEW_FULL_DECODE_EDGE:
            got = _load_scaled_pixmap(path, int(target_w), int(target_h))
            if got is not None and not got.isNull():
                return got
        pm = QPixmap(str(path))
        if pm.isNull():
            return None
        w = pm.width()
        h = pm.height()
        if w <= 0 or h <= 0:
            return pm
        return pm.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


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


def _preview_drag_live(overlay) -> bool:
    """True while a card-resize drag is live (border/ring ``_border_drag``)."""
    try:
        if getattr(overlay, "_border_drag", None) is not None:
            return True
    except Exception:
        pass
    return False


def _rescale_preview_to_host(overlay) -> None:
    """Rescale the stashed full preview pixmap to the live label size (W-B).

    Export-window idiom: the preview pane stretches with the card while the
    image inside keeps its aspect (``KeepAspectRatio`` letterbox, never a
    stretch). ``populate_preview`` stashes the unscaled source in
    ``overlay._preview_full``; this re-derives the shown pixmap from it on
    every card resize. No-op when nothing populatable is stashed (fake
    paths, null pixmaps) or the label has no size yet.

    Drag economy: repeated moves at one size (clamp-standstill leftovers,
    sub-pixel drag noise) skip the scale via ``_preview_scaled_for``; while
    a drag is live the cheap ``FastTransformation`` keeps the UI thread
    free, and the release path re-renders once with ``SmoothTransformation``
    (release clears the drag flag first, so the cached-Fast entry is
    re-done smooth — see the ``_preview_scaled_smooth`` guard below).
    """
    try:
        full = getattr(overlay, "_preview_full", None)
        label = getattr(overlay, "_preview_label", None)
        if full is None or label is None:
            return
        try:
            if full.isNull():
                return
        except Exception:
            return
        try:
            from sli_ui_toolkit.managers import scaled_px

            target_w = label.width()
            target_h = label.height()
            if target_w <= 0 or target_h <= 0:
                target_w, target_h = scaled_px(640), scaled_px(456)
        except Exception:
            return
        try:
            from PySide6.QtCore import Qt

            live = _preview_drag_live(overlay)
            want_smooth = not live
            try:
                cached_for = getattr(overlay, "_preview_scaled_for", None)
                cached_smooth = bool(getattr(overlay, "_preview_scaled_smooth", False))
            except Exception:
                cached_for, cached_smooth = None, False
            if cached_for == (int(target_w), int(target_h)) and (cached_smooth or not want_smooth):
                return
            scaled = full.scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
                if want_smooth
                else Qt.TransformationMode.FastTransformation,
            )
        except Exception:
            return
        try:
            if scaled is not None and not scaled.isNull():
                label.setPixmap(scaled)
                try:
                    overlay._preview_scaled_for = (int(target_w), int(target_h))
                    overlay._preview_scaled_smooth = bool(want_smooth)
                except Exception:
                    pass
        except Exception:
            pass
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


def _close_preview_store(overlay) -> None:
    """Close + drop the stashed TiledPixelStore (fd/memmap hygiene)."""
    try:
        store = getattr(overlay, "_preview_store", None)
    except Exception:
        store = None
    try:
        overlay._preview_store = None
    except Exception:
        pass
    if store is not None:
        try:
            store.close()
        except Exception:
            pass


def release_preview_canvas(overlay) -> None:
    """Lifecycle release (hide/close/populate-next); no-op off the GPU path."""
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
    try:
        label = getattr(overlay, "_preview_label", None)
        if label is not None:
            label.show()
    except Exception:
        pass


def _ensure_preview_canvas(overlay):
    """Create/reuse the canvas child in the preview slot; None if unavailable."""
    try:
        canvas = getattr(overlay, "_preview_canvas", None)
        if canvas is not None:
            return canvas
        try:
            from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget as _Canvas
        except Exception:
            return None
        host = getattr(overlay, "_preview_host", None)
        if host is None:
            return None
        canvas = _Canvas(host)
        try:
            from PySide6.QtWidgets import QSizePolicy as _SP

            from sli_ui_toolkit.managers import scaled_px as _spx

            canvas.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Expanding)
            canvas.setMinimumSize(_spx(640), _spx(456))
            lay = host.layout()
            if lay is not None:
                lay.addWidget(canvas, 1)
        except Exception:
            pass
        try:
            overlay._preview_canvas = canvas
        except Exception:
            pass
        return canvas
    except Exception:
        return None


def _populate_preview_canvas(overlay, item) -> bool:
    """GPU branch: TiledPixelStore (no crop_service) into the canvas slot."""
    canvas = _ensure_preview_canvas(overlay)
    if canvas is None:
        return False
    try:
        from engine.store.tiled_pixel_store import TiledPixelStore as _TPS
    except Exception:
        return False
    try:
        raw = getattr(item, "path", "")
        if not raw:
            return False
        _close_preview_store(overlay)  # never stack stores (fd/memmap leak)
        store = _TPS.from_path(raw, crop_service=None)
        if store is None:
            return False
        try:
            overlay._preview_store = store
        except Exception:
            pass
        try:
            canvas.set_source(store)
        except Exception:
            _close_preview_store(overlay)
            return False
        try:
            label = getattr(overlay, "_preview_label", None)
            if label is not None:
                label.hide()
            canvas.show()
        except Exception:
            pass
        return True
    except Exception:
        try:
            _close_preview_store(overlay)
        except Exception:
            pass
        return False


def populate_preview(overlay, item) -> None:
    # GPU branch first; any failure degrades to the QLabel path below.
    try:
        if _populate_preview_canvas(overlay, item):
            return
    except Exception:
        pass
    _populate_preview_label(overlay, item)


def _populate_preview_label(overlay, item) -> None:
    # Fallback: restore the label (the canvas branch may have hidden it).
    try:
        canvas = getattr(overlay, "_preview_canvas", None)
        if canvas is not None:
            canvas.hide()
    except Exception:
        pass
    try:
        overlay._preview_label.show()
    except Exception:
        pass
    # W-B: stash the unscaled source in ``overlay._preview_full`` so
    # ``_rescale_preview_to_host`` can re-derive the shown pixmap at the
    # live label size on every card resize (preview stretches with aspect,
    # export-window idiom). The initial shown pixmap keeps the old size.
    # Perf: single QPixmap decode — the shown pixmap is scaled from the
    # stashed full instead of a second QPixmap(path) load (was ~2x decode).
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        try:
            overlay._preview_full = None
        except Exception:
            pass
        try:
            overlay._preview_scaled_for = None
            overlay._preview_scaled_smooth = False
        except Exception:
            pass
        try:
            path = Path(getattr(item, "path", ""))
            dims = _fast_image_size(path)
            if dims is not None and max(int(dims[0]), int(dims[1])) > _PREVIEW_FULL_DECODE_EDGE:
                # Huge source: scaled reader read only (stash stays small).
                full = _load_scaled_pixmap(path, _PREVIEW_FULL_DECODE_EDGE, _PREVIEW_FULL_DECODE_EDGE)
            else:
                full = QPixmap(str(path))
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
        pm = None
        try:
            stashed = getattr(overlay, "_preview_full", None)
            if stashed is not None and not stashed.isNull():
                pm = stashed.scaled(
                    scaled_px(640),
                    scaled_px(456),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        except Exception:
            pm = None
        if pm is None or pm.isNull():
            pm = _load_preview_pixmap(Path(getattr(item, "path", "")), scaled_px(640), scaled_px(456))
        if pm is not None and not pm.isNull():
            overlay._preview_label.setPixmap(pm)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._preview_label.setPixmap(thumb.scaled(scaled_px(320), scaled_px(260), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._preview_label.setText("No preview")
                overlay._preview_label.setPixmap(QPixmap())
        # Settle the initial pixmap at the live label size when populated
        # after layout (keeps the old 640×456 pixels pre-layout).
        try:
            _rescale_preview_to_host(overlay)
        except Exception:
            pass
    except Exception:
        pass


# Inset populates (source + sharpness-crop) live in ``insets.py``
# (CODE_PATTERNS.md thin-owner split — this file hit the 500-line
# contract gate); import paths are unchanged via ``helpers.py``.

