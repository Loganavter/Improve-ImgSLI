"""Quick-look host glue — reveal/fit of the cover plate + canvas slot.

Split from ``preview_canvas_host.py`` (plan-gallery-split-2026-10-17, Part
C2). Bodies moved verbatim; names/signatures unchanged. Plain functions
taking the overlay as their first argument (``CODE_PATTERNS.md``).

The cover is the static pre-first-frame raster sibling of the QRhiWidget
canvas; ``reveal_preview_canvas`` stages it for the first chrome paint and
``_fit_preview_slot`` mirrors the host rect onto every layout-external
child (seamless cover<->canvas swap).
"""

from __future__ import annotations

from ._refs import host as _host


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
        if _host()._qlc_enabled():
            try:
                _host()._qlc_log(
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
    _host()._fit_preview_slot(overlay)


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
        _host()._fit_cover(overlay)
    except Exception:
        pass


def _live_view_kwargs(overlay) -> dict:
    """``zoomed_frame`` kwargs for the canvas's live view (fail-open).

    The canvas is the single owner of the view (``current_view``); the plate
    must be built through the SAME transform the canvas will present, or a
    within-series walk — which keeps the zoom — flashes a fit-frame plate
    before the preserved frame lands. An overlay without a canvas, a foreign
    double without the accessor, or a raising accessor all yield no kwargs =
    the historical 1.0 fit (fail-open, backward compatible). Never raises.
    """
    try:
        canvas = getattr(overlay, "_preview_canvas", None)
        get_view = getattr(canvas, "current_view", None)
        if not callable(get_view):
            return {}
        zoom, pan_x, pan_y = get_view()
        return {"zoom": float(zoom), "pan_x": float(pan_x), "pan_y": float(pan_y)}
    except Exception:
        return {}


def _cover_pixmap_from_full(overlay, w: int, h: int, *, zoom=1.0, pan_x=0.0, pan_y=0.0):
    """Canvas-fit plate pixmap from the stashed source (same fit as live).

    Uses ``preview_zoom.zoomed_frame`` — the exact fit/crop the GPU canvas
    uses — so the cover plate and the GPU frame agree pixel-for-pixel (the
    old ``scaled(KeepAspectRatio)`` arithmetic was up to 2px off). The view
    (zoom/pan, normalized) is passed through verbatim; the defaults are the
    identity view, so a caller with no known view gets today's behaviour.
    Returns a ``QPixmap`` of exactly ``w`` x ``h`` (transparent letterbox
    margins; the cover's opaque plate shows through) or None. Never raises.
    """
    try:
        src = getattr(overlay, "_preview_full", None)
        if src is None or src.isNull():
            return None
        from PySide6.QtGui import QImage, QPixmap
        from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame

        frame = zoomed_frame(
            src.toImage(), int(w), int(h), float(zoom), float(pan_x), float(pan_y)
        )
        if frame is None:
            return None
        fw, fh, px = frame
        img = QImage(px, int(fw), int(fh), QImage.Format.Format_RGBA8888_Premultiplied).copy()
        pm = QPixmap.fromImage(img)
        return pm if (pm is not None and not pm.isNull()) else None
    except Exception:
        return None


def _fit_cover(overlay) -> None:
    """Cover == slot frame geometry + canvas-view plate pixmap (fail-open).

    The plate rides the canvas's own live view (``current_view``) so the
    pre-first-frame raster matches the frame the canvas is about to present.
    """
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
                pm = _host()._cover_pixmap_from_full(overlay, w, h, **_live_view_kwargs(overlay))
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
    """Drop the first-frame cover (fail-open).

    A close cover (``quicklook_preview_close_cover``, planted on hide to
    ride out the native canvas unmap) survives every drop except
    ``"re-cover"``: the hide stack releases several times after planting,
    and only the next show may clear it — otherwise the hole it was
    planted for reopens in the same stack.
    """
    try:
        cover = getattr(overlay, "_preview_cover", None)
        if cover is not None and reason != "re-cover":
            try:
                if cover.objectName() == "quicklook_preview_close_cover":
                    return
            except Exception:
                pass
        try:
            overlay._preview_cover = None
        except Exception:
            pass
        if cover is not None:
            if _host()._qlc_enabled():
                _host()._qlc_log("drop cover reason=%s", reason or "unspecified")
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
    _host()._drop_cover(overlay, "re-cover")
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
            # null pixmap) show the overlay surface, never the desktop through
            # an unpresented canvas. Same tone as the plate/panel token.
            from tabs.image_gallery.ui.quick_look.labels_theme import _is_dark_theme, _token_color

            bg = _token_color(
                "gallery.panel.background", "#ffffff" if not _is_dark_theme() else "#303030"
            )
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
        _host()._fit_preview_slot(overlay)
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
        if _host()._qlc_enabled():
            _host()._qlc_log("settle flush ran -> emit firstFramePresented")
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
