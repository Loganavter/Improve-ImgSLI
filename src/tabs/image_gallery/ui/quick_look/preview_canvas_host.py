"""Quick-look GPU preview hosting — canvas slot lifecycle (no owner state).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one canvas-slot lifecycle: cover/fallback/label-repopulate share one GPU-path attribution"

Split from ``preview.py`` (500-line contract gate): the QLabel preview
stays there, everything canvas-shaped lives here. All functions fail
open to the QLabel path — import this module lazily and treat ``None``
/ ``False`` as "no GPU today".
"""

from __future__ import annotations


def _qlc_enabled() -> bool:
    """[ql-cover] warmup trace gate (IMGSLI_QL_COVER_DEBUG=1), fail-open."""
    try:
        from tabs.image_gallery.debug import ql_cover_enabled

        return bool(ql_cover_enabled())
    except Exception:
        return False


def _qlc_log(msg: str, *args) -> None:
    try:
        from tabs.image_gallery.debug import ql_cover

        ql_cover(msg, *args)
    except Exception:
        pass


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
    _drop_cover(overlay, "release")
    try:
        overlay._preview_canvas_pending = None
    except Exception:
        pass
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
    # Label returns as the visible surface — keep it exactly on the slot.
    _fit_preview_slot(overlay)


def _ensure_preview_canvas(overlay):
    """Create/reuse the canvas child in the preview slot; None if unavailable."""
    try:
        from shared.debug_flags import env_flag as _env_flag

        if _env_flag("IMGSLI_QL_NO_GPU"):
            if _qlc_enabled():
                _qlc_log("NO_GPU kill-switch -> label fallback")
            return None
    except Exception:
        pass
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

            canvas.setSizePolicy(_SP.Policy.Expanding, _SP.Policy.Expanding)
        except Exception:
            pass
        try:
            # Canvas is a layout-external child of the slot frame: it
            # mirrors ``preview_host.rect()`` (see _fit_preview_slot) and
            # never joins the layout, so the label<->canvas swap can never
            # split the slot between two stretched peers.
            overlay._preview_canvas = canvas
            _fit_preview_slot(overlay)
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
                # The label leaves the layout flow here: the sibling cover
                # below owns the pane (same pixmap) until the first GPU
                # frame, so the slot never splits between label + canvas.
                label.hide()
            reveal_preview_canvas(overlay, canvas)
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
        if _qlc_enabled():
            try:
                _qlc_log(
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
    _fit_preview_slot(overlay)


def _fit_preview_slot(overlay) -> None:
    """Mirror the slot frame's rect onto every layout-external child.

    ``_preview_host`` is the single laid-out geometry authority (IC-parity
    slot frame, see ``StartupPlaceholder`` in image_compare); the QLabel,
    the GPU canvas and the first-frame cover live outside any layout and
    copy ``host.rect()`` here. Called on the host's Resize and whenever a
    slot child is (re)created — so whichever surface is visible always
    occupies the exact same rect (seamless swap).
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
        for attr in ("_preview_label", "_preview_canvas", "_preview_cover"):
            try:
                child = getattr(overlay, attr, None)
                if child is not None:
                    child.setGeometry(rect)
            except Exception:
                pass
        _fit_cover(overlay)
    except Exception:
        pass


def _fit_cover(overlay) -> None:
    """Cover == slot frame geometry + aspect-fit pixmap (fail-open)."""
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
                src = getattr(overlay, "_preview_full", None)
                if src is not None and not src.isNull():
                    from PySide6.QtCore import Qt as _Qt

                    cover.setPixmap(src.scaled(w, h, _Qt.AspectRatioMode.KeepAspectRatio, _Qt.TransformationMode.SmoothTransformation))
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
    """Drop the first-frame cover (fail-open)."""
    try:
        cover = getattr(overlay, "_preview_cover", None)
        try:
            overlay._preview_cover = None
        except Exception:
            pass
        if cover is not None:
            if _qlc_enabled():
                _qlc_log("drop cover reason=%s", reason or "unspecified")
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
    """Opaque sibling cover over the canvas slot until its first GPU frame.

    Startup-placeholder pattern (compare tabs): the cover is a raster
    QLabel parented to ``_preview_host`` — a layout-external sibling of the
    canvas, never a child of the ``QRhiWidget`` itself. A child of the
    canvas inherits the canvas's own transparency window (no
    ``beginPass``/clear before the shell mounts, so the slot is a
    see-through hole until the first present); a sibling paints opaquely
    from the overlay's first paint regardless of RHI state. Dropped on
    ``firstFramePresented``, failure, and release; null pixmap still yields
    an opaque plate cover — never a transparent hole.
    """
    _drop_cover(overlay, "re-cover")
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
            if pixmap is not None and not pixmap.isNull():
                cover.setPixmap(pixmap)
        except Exception:
            pass
        try:
            # Opaque plate fill under the pixmap: letterbox margins (and a
            # null pixmap) show card background, never the desktop through
            # an unpresented canvas. Same tone as the QLabel-path margins.
            from tabs.image_gallery.ui.quick_look.labels_theme import _token_color

            bg = _token_color("gallery.card.background", "#ffffff")
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
        # Fit cover geometry + the stashed full pixmap to the live slot
        # (the label pixmap predates layout).
        _fit_preview_slot(overlay)
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
        if _qlc_enabled():
            _qlc_log("settle flush ran -> emit firstFramePresented")
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


def _wire_canvas_fallback(overlay, canvas, item) -> None:
    """No-frame / render-failed → back to QLabel (connect once per canvas)."""
    try:
        if getattr(canvas, "_gallery_fail_wired", False):
            return
        canvas._gallery_fail_wired = True  # type: ignore[attr-defined]
    except Exception:
        return

    def _on_first_frame(*_args) -> None:
        if _qlc_enabled():
            _qlc_log("firstFramePresented -> drop cover")
        _drop_cover(overlay, "first-frame")

    try:
        canvas.firstFramePresented.connect(_on_first_frame)
    except Exception:
        pass

    def _run_fall_back(reason: str) -> None:
        if _qlc_enabled():
            _qlc_log("fallback (%s) -> label path", reason)
        for _sig, _slot in (
            ("previewFailed", _on_preview_failed),
            ("renderFailed", _on_render_failed),
        ):
            try:
                getattr(canvas, _sig).disconnect(_slot)
            except Exception:
                pass
        _drop_cover(overlay, "fallback")
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

    def _on_preview_failed(*_args) -> None:
        """Watchdog no-frame path (1500ms without a presented frame)."""
        _run_fall_back("previewFailed")

    def _on_render_failed(*_args) -> None:
        """Qt RHI path (immediate render failure from QRhiWidget)."""
        _run_fall_back("renderFailed")

    for _sig, _slot in (
        ("previewFailed", _on_preview_failed),
        ("renderFailed", _on_render_failed),
    ):
        try:
            getattr(canvas, _sig).connect(_slot)
        except Exception:
            pass
