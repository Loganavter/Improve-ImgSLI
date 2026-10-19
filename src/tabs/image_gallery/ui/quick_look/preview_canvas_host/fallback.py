"""Quick-look host glue — RHI-fail probe/recovery + canvas release paths.

Split from ``preview_canvas_host.py`` (plan-gallery-split-2026-10-17, Part
C2). Bodies moved verbatim; names/signatures unchanged. Plain functions
taking the overlay as their first argument (``CODE_PATTERNS.md``).

``_install_memo_probe`` hands the canvas the memo-identity guard; the RHI
watcher drops a canvas that never presented (capped); the release paths
hide the canvas, retire in-flight tokens and drop the bounded memos.
"""

from __future__ import annotations

from ._refs import host as _host

# RHI-fail recovery thresholds (capped drops of a never-presenting canvas).
_RHI_PREFRAME_FAIL_THRESHOLD = 3
_RHI_MAX_RECOVERIES = 5


def _install_memo_probe(overlay, canvas) -> None:
    """Install the canvas ownership probe (idempotent, fail-open).

    The probe closes over *overlay* and reads its CURRENT store cache, so
    evict/replace/drop are always reflected without re-installing.
    """
    try:
        canvas._ql_is_memo = lambda s, _ov=overlay: _host()._is_preview_store_memo(_ov, s)
    except Exception:
        pass


def _watch_canvas_rhi(overlay, canvas) -> None:
    """Recover a canvas that keeps failing before its first frame (once-ish).

    A canvas whose renders fail before the first settled frame (e.g. first
    render landing on a surface that cannot mint a QRhi after a menu-first
    focus dance) caches the failure and never presents — the overlay then
    shows the static cover forever, across close/reopen (the release path
    reuses the widget, so reopening alone never heals it). The
    discriminator is ``canvas._frame_ok`` (set by ``settle_first_frame``
    on the first settled present, cleared on every ``set_source``): a
    canvas that presented before fails from resize storms (existing
    behavior, untouched) — only never-presented failures count. On
    threshold, drop the poisoned canvas (capped); the next populate
    recreates it fresh, or immediately when the overlay is visible.
    Fail-open throughout.
    """
    try:
        if getattr(canvas, "_ql_rhi_watched", False):
            return
        canvas._ql_rhi_watched = True
    except Exception:
        return
    try:
        canvas.renderFailed.connect(lambda: _host()._on_canvas_rhi_failed(overlay, canvas))
    except Exception:
        pass


def _on_canvas_rhi_failed(overlay, canvas) -> None:
    try:
        try:
            presented = bool(getattr(canvas, "_frame_ok", False))
        except Exception:
            return
        if presented:
            return  # presented before: resize storms, never poisoned.
        fails = int(getattr(canvas, "_ql_preframe_fails", 0) or 0) + 1
        try:
            canvas._ql_preframe_fails = fails
        except Exception:
            pass
        if _host()._qlc_enabled():
            _host()._qlc_log("rhi preframe-fail %d/%d", fails, _host()._RHI_PREFRAME_FAIL_THRESHOLD)
    except Exception:
        return
    try:
        recs = int(getattr(overlay, "_ql_rhi_recoveries", 0) or 0)
    except Exception:
        recs = 0
    # Schedule exactly once (on the threshold crossing): later failures
    # must not queue duplicate recoveries.
    if fails != _host()._RHI_PREFRAME_FAIL_THRESHOLD or recs >= _host()._RHI_MAX_RECOVERIES:
        return
    try:
        overlay._ql_rhi_recoveries = recs + 1
    except Exception:
        pass
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(500, lambda: _host()._drop_poisoned_canvas(overlay, canvas))
    except Exception:
        pass


def _drop_poisoned_canvas(overlay, canvas) -> None:
    """Delete a persistently RHI-failed canvas so populate recreates it."""
    try:
        if getattr(overlay, "_preview_canvas", None) is not canvas:
            return
        if _host()._qlc_enabled():
            _host()._qlc_log("rhi recovery: dropping poisoned canvas")
        try:
            overlay._ql_tiled_token = int(getattr(overlay, "_ql_tiled_token", 0) or 0) + 1
        except Exception:
            pass
        try:
            overlay._preview_canvas = None
        except Exception:
            pass
        try:
            canvas.deleteLater()
        except Exception:
            pass
        try:
            visible = bool(overlay.isVisible())
        except Exception:
            visible = False
        if visible:
            try:
                overlay._populate()
            except Exception:
                pass
    except Exception:
        pass


def release_preview_canvas(overlay) -> None:
    """Overlay release (hide/close): walk step + drop every memoized store."""
    _host().release_preview_canvas_for_walk(overlay)
    try:
        # The source inset is a second engine canvas with its own private
        # store memo; hide/close retires both (walks keep them — the inset
        # re-populates synchronously on the next step).
        from tabs.image_gallery.ui.quick_look.source_canvas import (
            release_source_inset_canvas,
        )

        release_source_inset_canvas(overlay)
    except Exception:
        pass
    try:
        # Hide/close retires prefetches even when no walk populate follows.
        overlay._ql_prefetch_token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0) + 1
    except Exception:
        pass
    _host()._drop_preview_store_cache(overlay)
    _host()._drop_tiled_store_cache(overlay)


def release_preview_canvas_for_walk(overlay) -> None:
    """Walk-step release (populate-next): hide the canvas, close only the
    non-memoized live store, keep both memo dicts.

    Ownership rule: the walk keeps memos (the ``_preview_store_cache`` bound
    caps open fds/memmaps — that is what the bound is for; the pixmap stash
    ``_stash_cache`` is never dropped here either), so a walk back to a seen
    item reuses the memoized store with zero source decodes and zero
    ``_store_from_pixmap`` materializations. Overlay hide/close take the
    full ``release_preview_canvas`` instead (drops everything). Never raises.

    The live ``_preview_full`` pixmap IS dropped here (memos stay): it
    carries the previous item's pixels with no provenance.
    ``_populate_preview_canvas`` re-stashes synchronously right after.
    """
    _host()._drop_cover(overlay, "release-walk")
    try:
        overlay._preview_full = None
    except Exception:
        pass
    try:
        overlay._preview_canvas_pending = None
    except Exception:
        pass
    try:
        # Retire any in-flight tiled full-store decode (its result closes).
        overlay._ql_tiled_token = int(getattr(overlay, "_ql_tiled_token", 0) or 0) + 1
    except Exception:
        pass
    try:
        # Retire any in-flight neighbor prefetch (its result closes).
        overlay._ql_prefetch_token = int(getattr(overlay, "_ql_prefetch_token", 0) or 0) + 1
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
    _host()._close_preview_store(overlay)
    # Keep the slot children exactly on the frame (canvas is hidden now).
    _host()._fit_preview_slot(overlay)


def _wire_canvas_fallback(overlay, canvas, item) -> None:
    """No-frame / render-failed → keep the cover plate (connect once per canvas)."""
    try:
        if getattr(canvas, "_gallery_fail_wired", False):
            return
        canvas._gallery_fail_wired = True  # type: ignore[attr-defined]
    except Exception:
        return

    def _on_first_frame(*_args) -> None:
        if _host()._qlc_enabled():
            _host()._qlc_log("firstFramePresented -> drop cover")
        _host()._drop_cover(overlay, "first-frame")

    try:
        canvas.firstFramePresented.connect(_on_first_frame)
    except Exception:
        pass

    def _run_fall_back(reason: str) -> None:
        # No label to hand off to: keep the cover up as the static preview
        # (it persists until a first frame ever lands).
        if _host()._qlc_enabled():
            _host()._qlc_log("fallback (%s) -> cover retained", reason)

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
