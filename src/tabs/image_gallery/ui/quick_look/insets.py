"""Quick look inset populates — source + sharpness-crop (plain functions).

Split from ``preview.py`` per CODE_PATTERNS.md thin owner + ui/ (the file
hit the 500-line contract gate): preview pixmaps stay in ``preview.py``,
inset content lives here. Import paths are unchanged via ``helpers.py``
re-exports.
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
    """Pin the source/crop inset blocks bottom-left inside the preview.

    Both blocks are absolute children of the preview host (overlaying the
    GPU canvas); at most one is visible per mode (fidelity ↔ crop).
    Bottom-left with 12px margins; fixed size from sizeHint with constant
    floors — never from the live size (that ratchets upward on every grow).
    """
    try:
        from sli_ui_toolkit.managers import scaled_px

        preview_host = getattr(overlay, "_preview_host", None)
        if preview_host is None:
            return
        margin = scaled_px(12)
        for attr in ("_source_inset_host", "_crop_host"):
            try:
                inset = getattr(overlay, attr, None)
                if inset is None:
                    continue
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


def populate_source_inset(overlay, item, is_fidelity: bool) -> None:
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
        # Reuse the already-stashed bounded preview when possible — avoids
        # a second decode for the non-fidelity crop inset.
        pm_full = getattr(overlay, "_preview_full", None)
        try:
            if pm_full is None or pm_full.isNull():
                pm_full = None
        except Exception:
            pm_full = None
        if pm_full is None:
            # Coarse-direct center crop (bounded — no full decode). Success
            # populates straight from the level's own bytes and returns; any
            # miss falls through to the thumbnail/reader ladder below.
            try:
                _direct = _pyramid_pixmap_for(getattr(item, "path", ""), center_third=True, long_edge=512)
            except Exception:
                _direct = None
            try:
                _direct_ok = _direct is not None and not _direct.isNull()
            except Exception:
                _direct_ok = False
            if _direct_ok:
                try:
                    crop_scaled = _direct.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    overlay._crop_pix.update_region("thumb", pixmap=crop_scaled)
                except Exception:
                    pass
                return
            try:
                # Bounded ladder only: item thumbnail, then an
                # aspect-correct scaled-reader read (long edge 1024) —
                # never a full QPixmap decode (~6 GB for a 40k source).
                # A miss fails open (inset skipped below).
                try:
                    _th = getattr(item, "thumbnail", None)
                    pm_full = _th if (_th is not None and not _th.isNull()) else None
                except Exception:
                    pm_full = None
                if pm_full is None:
                    try:
                        _ip = getattr(item, "path", "")
                        _idims = _source_dimensions(item, _ip)
                        if _idims is not None and _idims[0] > 0 and _idims[1] > 0:
                            _isc = min(1024.0 / _idims[0], 1024.0 / _idims[1], 1.0)
                            _itw = max(1, int(round(_idims[0] * _isc)))
                            _ith = max(1, int(round(_idims[1] * _isc)))
                            pm_full = _load_scaled_pixmap(_ip, _itw, _ith)
                    except Exception:
                        pm_full = None
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
            overlay._crop_pix.update_region("thumb", pixmap=crop_scaled)
        else:
            thumb = getattr(item, "thumbnail", None)
            if thumb is not None and not thumb.isNull():
                overlay._crop_pix.update_region("thumb", pixmap=thumb.scaled(scaled_px(150), scaled_px(84), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else:
                overlay._crop_pix.update_region("thumb", pixmap=None, text="—")
    except Exception:
        pass
