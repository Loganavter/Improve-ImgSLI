"""Quick-look canvas: source lifetime + module helpers (decode / shaders).

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).

Owns the held coarse store's lifetime (memo-vs-private ownership), the
no-present watchdog arm/fire/clear, plus the module-level bounded decode
helper and the shared overlay-shader lookup.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Decode caps owned by services/decode_policy.py (single home).
from tabs.image_gallery.services.decode_policy import (
    QL_FULL_EDGE_CAP as _QL_FULL_EDGE_CAP,
)

logger = logging.getLogger("ImproveImgSLI")


def _ql_decode_full_store(path, tmp_dir=None):
    """Background demand decode (worker): shared entry, bounded by the cap.

    One-line delegator to the single shared implementation
    (:func:`engine.cache.pyramid_demand.decode_full_store`); the demand
    pyramid keeps its ``_QL_FULL_EDGE_CAP`` edge bound. Pure Python -- no Qt.
    Never raises (None on failure or over-cap).
    """
    from engine.cache.pyramid_demand import decode_full_store

    return decode_full_store(path, cap_edge=_QL_FULL_EDGE_CAP, tmp_dir=tmp_dir)


def _overlay_shader_dir() -> Path | None:
    """Shared quad shaders by path (no cross-tab import); None = inert."""
    try:
        # +1 vs. the flat module: this body now lives one directory deeper
        # (preview_canvas/source.py), so anchor the ``tabs`` package here.
        tabs = Path(__file__).resolve().parents[4]
    except Exception:
        return None
    candidates = (
        tabs / "multi_compare" / "shaders" / "qrhi",
        tabs / "image_compare" / "canvas" / "shaders" / "overlay",
    )
    for cand in candidates:
        try:
            if (cand / "overlay.vert.qsb").is_file() and (cand / "overlay.frag.qsb").is_file():
                return cand
        except OSError:
            continue
    return None


# -- source lifetime --------------------------------------------------------


def set_source(self, store, *, preserve_view: bool = False) -> None:
    """Adopt ``store`` (closes the previous one it owns). Never raises.

    Ownership: a held store that is a live memo entry belongs to the
    host overlay's cache, not to this canvas — replacing/clearing it
    drops the ref WITHOUT closing (the cache closes it on
    evict/replace/overlay-release). Only privately-built (uncached)
    held stores are closed here. Fail-open: without a probe every held
    store closes as before.

    ``preserve_view`` (plan-ql-zoom-persist): a within-series walk must
    change the pixels without throwing away the user's wheel-zoom/pan, so
    the caller that navigates inside ONE series passes ``True`` and
    ``_zoom/_pan_x/_pan_y/_drag_last`` survive this call. Open / series
    change / delete / set-as-source / re-analyze keep the default
    ``False`` — today's unconditional reset, unchanged for every existing
    caller. Everything else here (frame + plan + watchdog bookkeeping)
    is identical either way.
    """
    try:
        _ql_changed = store is not self._store
    except Exception:
        _ql_changed = True
    try:
        if store is self._store:
            self._refresh_plan()
        else:
            self._close_held_store()
            self._store = store
            self._frame_key = None
            self._frame_bytes = None
            self._refresh_plan()
    except Exception:
        logger.debug("QuickLook preview: set_source failed open", exc_info=True)
    try:
        self._frame_ok = False
        self._ql_preframe_fails = 0
        self._settle_pumped = False
        self._settle_scheduled = False
        if not preserve_view:
            # Context change (open / series change / delete / set-as-source
            # / re-analyze): the previous item's view is meaningless here.
            # One call: the viewport may be shared with the source inset.
            self.set_view(1.0, 0.0, 0.0)
            self._drag_last = None
        self._frame_key = None
        try:
            from tabs.image_gallery.ui.quick_look.preview_watchdog import next_gen
            # Renews canvas._present_debt (new generation) via begin_source.
            gen = next_gen(self)
        except Exception:
            gen = None
        self._arm_watchdog(gen)
    except Exception:
        pass
    try:
        # IMGSLI_QL_COVER_DEBUG + debug.ql_cover (the existing QL diagnostic
        # gate/helper): lets the user confirm live which branch ran.
        from tabs.image_gallery.debug import ql_cover

        if preserve_view:
            ql_cover(
                "preview view: kept zoom=%.4f pan=(%.4f,%.4f)",
                float(self._zoom),
                float(self._pan_x),
                float(self._pan_y),
            )
        else:
            ql_cover("preview view: reset")
    except Exception:
        pass
    try:
        # A new coarse item retires the previous demand pyramid (its
        # full store sampled a different source); a re-set of the SAME
        # store keeps it (revisit fast path). Never raises.
        if _ql_changed:
            self._drop_ql_demand()
    except Exception:
        pass
    try:
        # A changed coarse item also invalidates any tiled full source
        # (it belonged to the previous item); the host re-registers the
        # new one via set_tiled_source right after.
        if _ql_changed:
            self.clear_tiled_source()
    except Exception:
        pass
    try:
        self.update()
    except Exception:
        pass


def _arm_watchdog(self, gen=None) -> None:
    """Yield to QLabel when no frame presents in time (never raises).

    Generation-guarded (see ``preview_watchdog``): a pending timer
    from a previous source never kills the new one.
    """
    try:
        from tabs.image_gallery.ui.quick_look.preview_watchdog import arm_watchdog
        arm_watchdog(self, gen)
    except Exception:
        pass


def _on_watchdog(self, expected_gen=None) -> None:
    """Fire a pending no-frame timer (never raises)."""
    try:
        from tabs.image_gallery.ui.quick_look.preview_watchdog import fire_watchdog
        fire_watchdog(self, expected_gen)
    except Exception:
        pass


def clear_source(self) -> None:
    """Release the held store + composition. Never raises.

    Ownership (see ``set_source``): a memoized held store is dropped,
    never closed; a privately-built one is closed. Already-closed held
    stores are never closed twice.
    """
    try:
        from tabs.image_gallery.ui.quick_look.preview_watchdog import invalidate
        # Renews canvas._present_debt (retires the pending timer) + disarms.
        invalidate(self)
    except Exception:
        pass
    try:
        self._close_held_store()
        self._active_composition = None
        self._active_render_plan = None
        self._frame_key = None
        self._frame_bytes = None
    except Exception:
        logger.debug("QuickLook preview: clear_source failed open", exc_info=True)
    try:
        # Retire the tiled full store FIRST: it may point at the same
        # canvas-private full store _drop_ql_demand is about to close.
        self.clear_tiled_source()
    except Exception:
        pass
    try:
        # Walk/item-change retires the demand build (generation bump
        # aborts decode + levels) and closes the canvas-private full
        # materials. Coarse memos stay open (host cache owns them).
        self._drop_ql_demand()
    except Exception:
        pass
    try:
        self.update()
    except Exception:
        pass


def _close_held_store(self) -> None:
    """Close the held store this canvas owns — never a memo, never twice.

    The host installs ``_ql_is_memo`` (see ``preview_canvas_host``): a
    held store that is a live cache entry is owned by the memo cache and
    is dropped WITHOUT closing. An already-closed held store is dropped
    without a second ``close()`` (``is_open`` guard). Only an open,
    privately-built held store is closed here. Never raises.
    """
    held = self._store
    self._store = None
    if held is None:
        return
    try:
        probe = getattr(self, "_ql_is_memo", None)
        if callable(probe) and bool(probe(held)):
            return  # memoized — the cache owns it, keep open.
    except Exception:
        pass
    try:
        if not bool(getattr(held, "is_open", True)):
            return  # already closed — never double-close.
    except Exception:
        pass
    try:
        held.close()
    except Exception:
        pass
