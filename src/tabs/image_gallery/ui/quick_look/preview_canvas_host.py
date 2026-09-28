"""Quick-look GPU preview hosting — canvas slot lifecycle (no owner state).

Split from ``preview.py`` (500-line contract gate): the QLabel preview
stays there, everything canvas-shaped lives here. All functions fail
open to the QLabel path — import this module lazily and treat ``None``
/ ``False`` as "no GPU today".
"""

from __future__ import annotations


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
        try:
            # Offscreen cannot present RHI — the QLabel fallback owns those
            # runs (tests, headless dumps); real platforms are unaffected.
            from PySide6.QtWidgets import QApplication as _QA

            _app = _QA.instance()
            if _app is not None and str(_app.platformName() or "").lower() == "offscreen":
                return None
        except Exception:
            pass
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


def _coarse_store_for(path, *, long_edge: int = 1024):
    """Bounded coarse store via the frozen wave-A1 pyramid seam.

    ``PyramidPixelStore.coarse_from_source`` never materializes a full
    frame (shrink-on-load / bounded scaled read); None on any miss so
    callers degrade to the QLabel ladder. No second LOD entry, no
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


def _populate_preview_canvas(overlay, item) -> bool:
    """GPU branch: bounded coarse store (frozen seam) into the canvas slot.

    Miss (empty path, unreadable source, unbuilt coarse) fails closed to
    False — the caller keeps its QLabel fallback; never a neighbor's
    content, never a full-frame decode.
    """
    canvas = _ensure_preview_canvas(overlay)
    if canvas is None:
        return False
    try:
        raw = getattr(item, "path", "")
        if not raw:
            return False
        _close_preview_store(overlay)  # never stack stores (fd/memmap leak)
        store = _coarse_store_for(raw)
        if store is None:
            return False
        try:
            overlay._preview_store = store
        except Exception:
            pass
        try:
            # Fill the QLabel path first: its pixmap becomes the cover shown
            # over the canvas until the first GPU frame (startup-placeholder
            # pattern from the compare tabs) — no black flash.
            from tabs.image_gallery.ui.quick_look.preview import _populate_preview_label

            _populate_preview_label(overlay, item)
        except Exception:
            pass
        try:
            canvas.set_source(store)
        except Exception:
            _close_preview_store(overlay)
            return False
        try:
            label = getattr(overlay, "_preview_label", None)
            pm = label.pixmap() if label is not None else None
            if label is not None:
                label.hide()
            canvas.show()
            _wire_canvas_fallback(overlay, canvas, item)
            _cover_until_first_frame(overlay, canvas, pm)
        except Exception:
            pass
        return True
    except Exception:
        try:
            _close_preview_store(overlay)
        except Exception:
            pass
        return False


def _drop_cover(overlay) -> None:
    """Drop the first-frame cover (fail-open)."""
    try:
        cover = getattr(overlay, "_preview_cover", None)
        try:
            overlay._preview_cover = None
        except Exception:
            pass
        if cover is not None:
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


def _cover_until_first_frame(overlay, canvas, pixmap) -> None:
    """Cover the canvas with the QLabel pixmap until its first GPU frame."""
    _drop_cover(overlay)
    try:
        if pixmap is None or pixmap.isNull():
            return
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QLabel as _QLabel
        from PySide6.QtWidgets import QVBoxLayout as _QVL

        cover = _QLabel(canvas)
        try:
            cover.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            cover.setPixmap(pixmap)
        except Exception:
            pass
        try:
            lay = canvas.layout()
            if lay is None:
                lay = _QVL(canvas)
                try:
                    lay.setContentsMargins(0, 0, 0, 0)
                except Exception:
                    pass
                canvas.setLayout(lay)
            lay.addWidget(cover)
        except Exception:
            try:
                cover.setGeometry(canvas.rect())
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
    except Exception:
        pass


def _wire_canvas_fallback(overlay, canvas, item) -> None:
    """No-frame / render-failed → back to QLabel (connect once per canvas)."""
    try:
        if getattr(canvas, "_gallery_fail_wired", False):
            return
        canvas._gallery_fail_wired = True  # type: ignore[attr-defined]
    except Exception:
        return

    def _on_first_frame(*_args) -> None:
        _drop_cover(overlay)

    try:
        canvas.firstFramePresented.connect(_on_first_frame)
    except Exception:
        pass

    def _fall_back(*_args) -> None:
        for _sig in ("previewFailed", "renderFailed"):
            try:
                getattr(canvas, _sig).disconnect(_fall_back)
            except Exception:
                pass
        _drop_cover(overlay)
        try:
            from tabs.image_gallery.ui.quick_look.preview import _populate_preview_label
        except Exception:
            return
        try:
            release_preview_canvas(overlay)
        except Exception:
            pass
        try:
            _populate_preview_label(overlay, item)
        except Exception:
            pass

    for _sig in ("previewFailed", "renderFailed"):
        try:
            getattr(canvas, _sig).connect(_fall_back)
        except Exception:
            pass
