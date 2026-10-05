"""Quick look inset populates — source inset (plain functions).

Split from ``preview.py`` per CODE_PATTERNS.md thin owner + ui/ (the file
hit the 500-line contract gate): preview pixmaps stay in ``preview.py``,
inset content lives here. Import paths are unchanged via ``helpers.py``
re-exports. The sharpness-crop inset was removed (see ``populate_crop``).
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.ui.quick_look.preview import (
    _load_scaled_pixmap,
    _pyramid_pixmap_for,
    _source_dimensions,
    _thumb_pixmap,
)

def reposition_preview_insets(overlay) -> None:
    """Pin the source inset block bottom-left inside the preview.

    The block is an absolute child of the preview host (overlaying the
    GPU canvas). Bottom-left with 12px margins; fixed size from sizeHint
    with constant floors — never from the live size (that ratchets upward
    on every grow).
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        preview_host = getattr(overlay, "_preview_host", None)
        if preview_host is None:
            return
        margin = scaled_px(12)
        for attr in ("_source_inset_host",):
            try:
                inset = getattr(overlay, attr, None)
                if inset is None:
                    continue
                try:
                    # Explicit hide only (isHidden, not isVisible):
                    # positioning must also run while an ancestor is still
                    # hidden (pre-show repositions).
                    if inset.isHidden():
                        continue
                except Exception:
                    pass
                w = inset.sizeHint().width()
                h = inset.sizeHint().height()
                if w <= 0:
                    w = scaled_px(158)
                if h <= 0:
                    h = scaled_px(124)
                w = max(w, scaled_px(158))
                h = max(h, scaled_px(124))
                max_w = max(0, preview_host.width() - margin * 2)
                max_h = max(0, preview_host.height() - margin * 2)
                if max_w > 0 and w > max_w:
                    w = max_w
                if max_h > 0 and h > max_h:
                    h = max_h
                inset.setFixedSize(w, h)
                inset.move(margin, max(margin, preview_host.height() - h - margin))
                try:
                    inset.raise_()
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass


def populate_source_inset(overlay, item, is_fidelity: bool, owner=None) -> None:
    """Source inset block (fidelity mode). *owner* is the explicit triage
    owner (threaded from the overlay's ``show_for``); when None, falls back
    to the overlay's stored owner for direct unit calls (back-compat —
    production always passes it).
    """
    try:
        # Self-source (hub_detection returns the item itself when the folder
        # has nothing smaller/similar): the inset would duplicate the main
        # preview pixel-for-pixel — hide it, the caption below already names
        # the file.
        try:
            _same = Path(getattr(item, "path", "")) == Path(getattr(overlay, "_source_path", None) or "")
        except Exception:
            _same = False
        overlay._source_inset_host.setVisible(bool(is_fidelity) and not _same)
    except Exception:
        pass
    if not is_fidelity:
        return
    try:
        if Path(getattr(item, "path", "")) == Path(getattr(overlay, "_source_path", None) or ""):
            return
    except Exception:
        pass
    try:
        from sli_ui_toolkit.managers import scaled_px
        from PySide6.QtCore import Qt
        src = overlay._source_path
        src_item = None
        # Explicit triage owner (threaded from show_for); overlay fallback
        # for direct unit calls (back-compat).
        if owner is None:
            try:
                owner = overlay._owner
            except Exception:
                owner = None
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
                    # Coarse-direct first (bounded pyramid sample); the
                    # scaled-reader ladder below stays as fallback.
                    try:
                        _pyr = _pyramid_pixmap_for(getattr(src_item, "path", src), long_edge=512)
                    except Exception:
                        _pyr = None
                    try:
                        _pyr_ok = _pyr is not None and not _pyr.isNull()
                    except Exception:
                        _pyr_ok = False
                    if _pyr_ok:
                        try:
                            pix = _pyr.scaled(
                                scaled_px(150),
                                scaled_px(84),
                                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.FastTransformation,
                            )
                        except Exception:
                            pix = None
                    if pix is None:
                        # No thumbnail yet (fresh drop) — scaled reader read
                        # instead of a full QPixmap decode + smooth scale.
                        pix = _load_scaled_pixmap(Path(getattr(src_item, "path", src)), scaled_px(150), scaled_px(84))
            except Exception:
                pix = None
            if pix is None:
                try:
                    pix = _thumb_pixmap(src_item, scaled_px(150), scaled_px(84))
                except Exception:
                    pix = None
        elif src is not None:
            try:
                pix = _load_scaled_pixmap(src, scaled_px(150), scaled_px(84))
            except Exception:
                pix = None
            if pix is None:
                # Bounded last resort: coarse pyramid sample (no full
                # decode). A miss fails open (inset shows "—" below).
                try:
                    _pyr2 = _pyramid_pixmap_for(src, long_edge=512)
                    if _pyr2 is not None and not _pyr2.isNull():
                        pix = _pyr2.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.FastTransformation)
                except Exception:
                    pass
        if pix is not None and not pix.isNull():
            overlay._source_inset_pix.update_region("thumb", pixmap=pix)
        else:
            overlay._source_inset_pix.update_region("thumb", pixmap=None, text="—")
        src_name = Path(src).name if src is not None else "source"
        caption = f"SOURCE · {src_name}"
        dims = _source_dimensions(src_item, src)
        if dims is not None:
            caption += f" · {dims[0]}×{dims[1]}"
        overlay._source_inset_label.setText(caption)
        # Full caption as tooltip (the pill elides the tail).
        try:
            overlay._source_inset_host.setToolTip(caption)
            overlay._source_inset_pix.setToolTip(caption)
            overlay._source_inset_label.setToolTip(caption)
        except Exception:
            pass
    except Exception:
        pass


def populate_crop(overlay, item, is_fidelity: bool = False) -> None:
    """Sharpness-crop inset — REMOVED, kept as a no-op for call compat.

    The corner crop block no longer exists (no widget, no decode work).
    """
    return


def refresh_crop_for(owner, item_or_path) -> bool:
    """Sharpness-crop refresh — REMOVED, always False (kept for call compat)."""
    return False
