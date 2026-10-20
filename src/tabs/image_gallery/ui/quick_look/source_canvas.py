"""Quick Look SOURCE inset — engine canvas view of the source side.

Plan: plan-gallery-ql-source-canvas (2026-10-19). The inset used to be a
pixmap-only toolkit ``Button``. Its image surface is now a second
``QuickLookCanvasWidget`` — the SAME single-quad engine canvas the main
preview uses — parented to the source plate and fed by the SOURCE item's
bounded coarse store. It binds to the preview canvas's ``ViewportState``
(``QuickLookCanvasWidget.bind_view``): zoom/pan live in ONE state, so the
preview's wheel/pan moves the inset and the inset's frame is computed with
the preview's transform on its own (small) framebuffer.

The button stays as the rounded plate and keeps painting the cover pixmap:
that pixmap is the pre-first-frame plate (identical to the main preview's
cover contract) and the no-GPU/offscreen fallback. ``SourceInsetFrame``
(``overlay_build/inset_frame.py``) re-paints the plate's rounded thumb clip
above the canvas (a ``QRhiWidget`` cannot clip itself), so the visual
contract — pinned position/size, 8px plate, 5px image rounding, border — is
unchanged.

Source identity is token-guarded: ``populate_source_inset_canvas`` bumps
``overlay._source_inset_token`` and ``apply_source_inset_source`` refuses a
late/stale resolve, so a neighbour/previous pair can never replace the
current frame.

Interaction (``task-gallery-quicklook-source-screen``): the inset plate is a
swap hit target — hovering it (or holding LMB on it) shows the SOURCE in the
MAIN preview, leaving/releasing restores the viewed item. The swap is pixels
only: the main canvas keeps the SAME shared ``ViewportState`` (and renders from
the inset's already-open coarse store), so zoom/pan never move. The engine
canvas stays ``WA_TransparentForMouseEvents`` / NoFocus — never a hit target,
never a focus/section stop. The hit target + swap live in ``source_swap``
(500-line split); this module only retires a pending swap when the view goes.

No cache keys are touched: the bounded store memo here is a one-entry
path-keyed memo of its own (normpath/mtime/size, the stash key shape) and
never consumes the strip/preview caches.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QLabel

from tabs.image_gallery.ui.quick_look.source_swap import reset_source_swap

# Geometry/radius names are re-exported here as the inset's public surface
# (plate Build + tests import them from this module); the single definition
# lives in ``overlay_build/inset_frame.py`` so plate and clip frame agree.
from tabs.image_gallery.ui.quick_look.overlay_build.inset_frame import (  # noqa: F401
    SOURCE_INSET_FRAME_RADIUS,
    SOURCE_INSET_H,
    SOURCE_INSET_PAD,
    SOURCE_INSET_THUMB_RADIUS,
    SOURCE_INSET_W,
    SourceInsetFrame,
)

SOURCE_INSET_CANVAS_OBJECT = "quicklook_source_inset_canvas"
SOURCE_INSET_COVER_OBJECT = "quicklook_source_inset_cover"
SOURCE_INSET_FRAME_OBJECT = "quicklook_source_inset_frame"


# -- small geometry / ownership helpers -------------------------------------


def _plate(overlay):
    """The inset plate Button (the canvas's parent), or None."""
    try:
        return getattr(overlay, "_source_inset_pix", None)
    except Exception:
        return None


def _thumb_rect(plate) -> QRect:
    """The plate's inner image rect (the 4px-padded thumb region)."""
    try:
        r = plate.rect()
    except Exception:
        return QRect(0, 0, SOURCE_INSET_W, SOURCE_INSET_H)
    pad = SOURCE_INSET_PAD
    return QRect(
        pad,
        pad,
        max(1, int(r.width()) - pad * 2),
        max(1, int(r.height()) - pad * 2),
    )


def _next_token(overlay) -> int:
    """Bump and return the inset source token (one per populate)."""
    try:
        token = int(getattr(overlay, "_source_inset_token", 0) or 0) + 1
    except Exception:
        token = 1
    try:
        overlay._source_inset_token = token
    except Exception:
        pass
    return token


def _close_source_inset_store(overlay) -> None:
    """Close + drop the inset's bounded coarse store (never raises)."""
    try:
        store = getattr(overlay, "_source_inset_store", None)
    except Exception:
        store = None
    try:
        overlay._source_inset_store = None
        overlay._source_inset_store_key = None
    except Exception:
        pass
    if store is not None:
        try:
            store.close()
        except Exception:
            pass


def source_store_for(overlay, path):
    """Bounded coarse store for the SOURCE side, memoized (one entry).

    Same key shape as the preview stash (normpath/mtime/size) but a private
    one-entry memo: the inset owns its store's lifetime (``release_source_inset_canvas``
    closes it), so walk/evict in the preview caches can never close a store
    the inset is still sampling. Returns None on any miss (missing file,
    unreadable source, no decode) — the pixmap plate then stays up.
    """
    if path is None:
        return None
    try:
        key = _memo_key(path)
    except Exception:
        key = None
    try:
        store = getattr(overlay, "_source_inset_store", None)
        if (
            store is not None
            and key is not None
            and key == getattr(overlay, "_source_inset_store_key", None)
        ):
            try:
                if bool(store.is_open):
                    return store
            except Exception:
                pass
        _close_source_inset_store(overlay)
        from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
            _coarse_store_for,
        )

        store = _coarse_store_for(str(path))
    except Exception:
        store = None
    if store is None:
        return None
    try:
        overlay._source_inset_store = store
        overlay._source_inset_store_key = key
    except Exception:
        pass
    return store


def _memo_key(path):
    """(normpath, mtime_ns, size) — the stash key shape (no strip index here)."""
    try:
        import os

        norm = os.path.normpath(str(path))
        if not norm:
            return None
        st = os.stat(norm)
        return (norm, int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        return None


# -- surface lifecycle -------------------------------------------------------


def _ensure_cover(overlay, plate):
    """The pre-first-frame cover label (the plate pixmap above the canvas)."""
    cover = getattr(overlay, "_source_inset_cover", None)
    if cover is not None:
        return cover
    try:
        cover = QLabel(plate)
    except Exception:
        return None
    try:
        cover.setObjectName(SOURCE_INSET_COVER_OBJECT)
    except Exception:
        pass
    try:
        cover.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    except Exception:
        pass
    try:
        cover.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    except Exception:
        pass
    try:
        cover.setScaledContents(True)
    except Exception:
        pass
    try:
        overlay._source_inset_cover = cover
    except Exception:
        return cover
    return cover


def _ensure_frame(overlay, plate):
    """The rounded clip/border overlay above canvas + cover."""
    frame = getattr(overlay, "_source_inset_frame", None)
    if frame is not None:
        return frame
    try:
        frame = SourceInsetFrame(plate)
    except Exception:
        return None
    try:
        frame.setObjectName(SOURCE_INSET_FRAME_OBJECT)
    except Exception:
        pass
    try:
        overlay._source_inset_frame = frame
    except Exception:
        pass
    return frame


def _cover_crop(pixmap, w: int, h: int):
    """Cover-scale then center-crop *pixmap* to exactly ``w`` x ``h``."""
    try:
        if pixmap is None or pixmap.isNull():
            return None
        w_i, h_i = max(1, int(w)), max(1, int(h))
        scaled = pixmap.scaled(
            w_i,
            h_i,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.FastTransformation,
        )
        if scaled is None or scaled.isNull():
            return None
        x = max(0, (scaled.width() - w_i) // 2)
        y = max(0, (scaled.height() - h_i) // 2)
        return scaled.copy(x, y, min(w_i, scaled.width()), min(h_i, scaled.height()))
    except Exception:
        return None


def _set_cover_pixmap(overlay, pixmap) -> None:
    """Show the plate pixmap above the canvas (pre-first-frame cover)."""
    cover = getattr(overlay, "_source_inset_cover", None)
    if cover is None:
        return
    if pixmap is None:
        # No source pixels: the plate keeps its own "—" region, canvas empty.
        try:
            cover.hide()
        except Exception:
            pass
        return
    plate = _plate(overlay)
    rect = _thumb_rect(plate)
    pm = _cover_crop(pixmap, rect.width(), rect.height())
    if pm is None:
        return
    try:
        cover.setPixmap(pm)
        cover.setGeometry(rect)
        cover.show()
        cover.raise_()
        # Keep the rounded clip frame above the (square) cover pixmap.
        frame = getattr(overlay, "_source_inset_frame", None)
        if frame is not None:
            frame.raise_()
    except Exception:
        pass


def _drop_cover(overlay) -> None:
    """First engine frame landed: the plate stays, the cover goes."""
    cover = getattr(overlay, "_source_inset_cover", None)
    if cover is None:
        return
    try:
        cover.hide()
    except Exception:
        pass


def layout_source_inset_surfaces(overlay) -> None:
    """Mirror the plate's thumb rect onto canvas, cover and clip frame.

    Called from ``reposition_preview_insets`` (the pin hook) and after every
    populate. The plate's size is fixed by the layout, so this is stable even
    before the host geometry settles. Raise order: canvas < cover < frame.
    """
    plate = _plate(overlay)
    if plate is None:
        return
    rect = _thumb_rect(plate)
    for attr in ("_source_inset_canvas", "_source_inset_cover"):
        child = getattr(overlay, attr, None)
        if child is None:
            continue
        try:
            child.setGeometry(rect)
        except Exception:
            pass
    frame = getattr(overlay, "_source_inset_frame", None)
    if frame is not None:
        try:
            frame.setGeometry(rect)
        except Exception:
            pass
        try:
            frame.raise_()
        except Exception:
            pass


def ensure_source_inset_canvas(overlay):
    """Create/reuse the engine canvas on the source plate; None if unavailable."""
    plate = _plate(overlay)
    if plate is None:
        return None
    canvas = getattr(overlay, "_source_inset_canvas", None)
    if canvas is not None:
        _bind_view(overlay, canvas)
        layout_source_inset_surfaces(overlay)
        return canvas
    try:
        from tabs.image_gallery.ui.quick_look.preview_canvas import (
            QuickLookCanvasWidget as _Canvas,
        )
    except Exception:
        return None
    try:
        canvas = _Canvas(plate)
    except Exception:
        return None
    try:
        canvas.setObjectName(SOURCE_INSET_CANVAS_OBJECT)
    except Exception:
        pass
    try:
        # Navigation untouched: the inset is a view, not a control (the
        # plate's wheel/press routing stays exactly as before).
        canvas.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        canvas.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    except Exception:
        pass
    try:
        # Hidden until the source populate shows it; the plate pixmap is the
        # cover, exactly like the preview's pre-first-frame plate.
        canvas.hide()
    except Exception:
        pass
    try:
        overlay._source_inset_canvas = canvas
    except Exception:
        return canvas
    # This module owns the inset store (see source_store_for); the canvas
    # must never close a store the memo still hands out.
    try:
        canvas._ql_is_memo = (
            lambda store, _ov=overlay: getattr(_ov, "_source_inset_store", None) is store
        )
    except Exception:
        pass
    try:
        canvas.firstFramePresented.connect(lambda _ov=overlay: _drop_cover(_ov))
    except Exception:
        pass
    _ensure_cover(overlay, plate)
    _ensure_frame(overlay, plate)
    _bind_view(overlay, canvas)
    layout_source_inset_surfaces(overlay)
    return canvas


def _bind_view(overlay, canvas) -> None:
    """Bind the inset canvas to the main preview's (single) viewport."""
    try:
        main = getattr(overlay, "_preview_canvas", None)
    except Exception:
        main = None
    if main is None or main is canvas:
        return
    try:
        canvas.bind_view(main)
    except Exception:
        pass


def apply_source_inset_source(overlay, path, store, *, token) -> bool:
    """Install *store* as the inset source only while *token* is current.

    A late resolve (an older pair landing after a newer populate) returns
    False and leaves the current frame untouched — content identity is
    token-guarded, never just "last writer wins". Never raises.
    """
    try:
        current = int(getattr(overlay, "_source_inset_token", 0) or 0)
    except Exception:
        current = 0
    try:
        if token is None or int(token) != current:
            return False
    except Exception:
        return False
    canvas = ensure_source_inset_canvas(overlay)
    if canvas is None:
        return False
    if store is None:
        store = source_store_for(overlay, path)
    if store is None:
        return False
    try:
        # preserve_view: the shared viewport belongs to the preview context;
        # a source change must never reset what the user zoomed into.
        canvas.set_source(store, preserve_view=True)
    except Exception:
        return False
    try:
        overlay._source_inset_path = str(path)
    except Exception:
        pass
    try:
        canvas.show()
        canvas.update()
    except Exception:
        pass
    return True


def populate_source_inset_canvas(
    overlay, src_path, *, pixmap=None, store=None
) -> bool:
    """Feed the inset engine canvas the CURRENT source side (one populate).

    Bumps the token first, so any resolve still in flight for a previous
    pair is rejected by ``apply_source_inset_source``. The cover (plate
    pixmap) is shown until the canvas presents this source's first frame.
    Never raises; False means the pixmap plate stays the visible surface.
    """
    token = _next_token(overlay)
    if src_path is None:
        release_source_inset_canvas(overlay)
        return False
    if store is None:
        store = source_store_for(overlay, src_path)
    if store is None:
        release_source_inset_canvas(overlay)
        return False
    if not apply_source_inset_source(overlay, src_path, store, token=token):
        return False
    _set_cover_pixmap(overlay, pixmap)
    layout_source_inset_surfaces(overlay)
    return True


def release_source_inset_canvas(overlay) -> None:
    """Retire the inset view (hidden / self-source / overlay release).

    Bumps the token so a late resolve cannot resurrect the view after it was
    retired, clears the canvas (memo guard keeps the store's owner here),
    hides the cover and closes the private store. Never raises.
    """
    _next_token(overlay)
    # A retired inset has nothing to show in the main preview: forget a
    # pending swap (the populate that hid it repopulated the preview first).
    reset_source_swap(overlay)
    canvas = getattr(overlay, "_source_inset_canvas", None)
    if canvas is not None:
        try:
            canvas.clear_source()
        except Exception:
            pass
        try:
            canvas.hide()
        except Exception:
            pass
    cover = getattr(overlay, "_source_inset_cover", None)
    if cover is not None:
        try:
            cover.hide()
        except Exception:
            pass
    _close_source_inset_store(overlay)
