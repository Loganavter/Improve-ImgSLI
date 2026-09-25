"""Quick look preview + source dims — plain functions (no owner state).

Single-decode preview (``populate_preview`` stashes ``_preview_full``;
``_rescale_preview_to_host`` re-derives at live label size), scaled-reader
loads (``_load_scaled_pixmap``), fast dims (``_fast_image_size`` +
``_source_dimensions`` with metrics cache). Extracted verbatim from
``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


def _load_preview_pixmap(path: Path, target_w: int = 640, target_h: int = 456) -> QPixmap | None:
    try:
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


def _thumb_pixmap(item, size: int = 66) -> QPixmap | None:
    try:
        thumb = getattr(item, "thumbnail", None)
        if thumb is not None and not thumb.isNull():
            return thumb.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap(str(getattr(item, "path", "")))
        if pm is not None and not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
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


def _rescale_preview_to_host(overlay) -> None:
    """Rescale the stashed full preview pixmap to the live label size (W-B).

    Export-window idiom: the preview pane stretches with the card while the
    image inside keeps its aspect (``KeepAspectRatio`` letterbox, never a
    stretch). ``populate_preview`` stashes the unscaled source in
    ``overlay._preview_full``; this re-derives the shown pixmap from it on
    every card resize. No-op when nothing populatable is stashed (fake
    paths, null pixmaps) or the label has no size yet.
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

            scaled = full.scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            return
        try:
            if scaled is not None and not scaled.isNull():
                label.setPixmap(scaled)
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


def populate_preview(overlay, item) -> None:
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


def populate_source_inset(overlay, item, is_fidelity: bool) -> None:
    try:
        overlay._source_inset_host.setVisible(bool(is_fidelity))
        if is_fidelity:
            from tabs.image_gallery.ui.quick_look.source_inset import reposition_source_inset
            reposition_source_inset(overlay)
    except Exception:
        pass
    if not is_fidelity:
        return
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        src = overlay._source_path
        src_item = None
        owner = overlay._owner
        try:
            items = list(getattr(getattr(owner, "state", None), "items", []) or []) if owner is not None else []
            if src is not None:
                for it2 in items:
                    if Path(getattr(it2, "path", "")) == Path(src):
                        src_item = it2
                        break
        except Exception:
            pass
        pix = None
        if src_item is not None:
            try:
                thumb = getattr(src_item, "thumbnail", None)
                if thumb is not None and not thumb.isNull():
                    pix = thumb.scaled(
                        scaled_px(150),
                        scaled_px(84),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.FastTransformation,
                    )
                else:
                    # No thumbnail yet (fresh drop) — scaled reader read
                    # instead of a full QPixmap decode + smooth scale.
                    pix = _load_scaled_pixmap(Path(getattr(src_item, "path", src)), scaled_px(150), scaled_px(84))
            except Exception:
                pix = None
            if pix is None:
                try:
                    pix = _thumb_pixmap(src_item, scaled_px(150))
                except Exception:
                    pix = None
        elif src is not None:
            try:
                pix = _load_scaled_pixmap(src, scaled_px(150), scaled_px(84))
            except Exception:
                pix = None
            if pix is None:
                try:
                    pm2 = QPixmap(str(src))
                    if not pm2.isNull():
                        pix = pm2.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                except Exception:
                    pass
        if pix is not None and not pix.isNull():
            overlay._source_inset_pix.setPixmap(pix)
        else:
            overlay._source_inset_pix.setText("—")
        src_name = Path(src).name if src is not None else "source"
        caption = f"SOURCE · {src_name}"
        dims = _source_dimensions(src_item, src)
        if dims is not None:
            caption += f" · {dims[0]}×{dims[1]}"
        overlay._source_inset_label.setText(caption)
    except Exception:
        pass


def populate_crop(overlay, item, is_fidelity: bool = False) -> None:
    """Sharpness-crop inset — non-fidelity modes only.

    S4 v2 LIGHT is fidelity mode and draws no ``SHARPNESS CROP`` inset
    (camera/batch modes keep it). Hidden in fidelity, shown otherwise.
    """
    try:
        overlay._crop_host.setVisible(not bool(is_fidelity))
    except Exception:
        pass
    if is_fidelity:
        return
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        # Reuse the already-decoded preview when possible — avoids a
        # second full QPixmap load for the non-fidelity crop inset.
        pm_full = getattr(overlay, "_preview_full", None)
        try:
            if pm_full is None or pm_full.isNull():
                pm_full = None
        except Exception:
            pm_full = None
        if pm_full is None:
            try:
                pm_full = QPixmap(str(getattr(item, "path", "")))
                if pm_full is not None and pm_full.isNull():
                    pm_full = None
            except Exception:
                pm_full = None
        if pm_full is not None and not pm_full.isNull():
            w = pm_full.width()
            h = pm_full.height()
            cw = max(1, w // 3)
            ch = max(1, h // 3)
            x = max(0, (w - cw) // 2)
            y = max(0, (h - ch) // 2)
            crop = pm_full.copy(x, y, cw, ch)
            crop_scaled = crop.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            overlay._crop_pix.setPixmap(crop_scaled)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._crop_pix.setPixmap(thumb.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._crop_pix.setText("—")
    except Exception:
        pass
