"""Scanning/triage status badges + session-view reset for the gallery widget.

Bodies extracted from ``ImageGalleryWidget`` (plan Part B, Wave 2) per
``CODE_PATTERNS.md`` (thin owner + functions-taking-owner); the widget
keeps same-named one-line delegators so call sites and tests do not move.

These functions are fail-open like the surrounding widget chrome: a
storeless / unattached widget must never raise.
"""

from __future__ import annotations

from tabs.image_gallery.debug import gallery_debug as _dbg


def set_scanning(owner, n: int, total: int) -> None:
    """S1: progressive scanning n/N — toolbar spinner + empty_state."""
    try:
        n_i = int(n)
        t_i = int(total)
    except Exception:
        n_i = int(n) if isinstance(n, int) else 0
        t_i = int(total) if isinstance(total, int) else 0
    _dbg("view-cycle scanning cover n=%d total=%d", n_i, t_i)
    try:
        owner.toolbar.set_scanning(n_i, t_i)
    except Exception:
        pass
    try:
        owner._empty_state.set_state("scanning", n_i, t_i)
    except TypeError:
        try:
            owner._empty_state.set_state("scanning", n_i)
        except Exception:
            pass
    except Exception:
        pass
    try:
        # Stack switch — empty stays visible during scanning
        if hasattr(owner, "_content_stack"):
            owner._content_stack.setCurrentWidget(owner._empty_state)
            owner._empty_state.show()
            owner._grid_view.show()  # keep in stack but not current
        else:
            owner._empty_state.show()
            owner._grid_view.hide()
    except Exception:
        pass


def set_background_scanning(owner, n: int, total: int) -> None:
    """S1 progress without hiding the grid (append path).

    Same toolbar spinner as :func:`set_scanning`, but the current
    series view stays visible — appending one image must not tear
    down good groups behind a spinner while the pool retriages.
    """
    try:
        n_i = int(n)
        t_i = int(total)
    except Exception:
        n_i = int(n) if isinstance(n, int) else 0
        t_i = int(total) if isinstance(total, int) else 0
    _dbg("view-cycle scanning background n=%d total=%d", n_i, t_i)
    try:
        owner.toolbar.set_scanning(n_i, t_i)
    except Exception:
        pass


def set_triage_done(owner) -> None:
    """S2: triage complete — hide spinner."""
    try:
        owner.toolbar.set_triage_done()
    except Exception:
        pass
    try:
        owner._empty_state.set_state("ready")
    except Exception:
        pass


def reset_session_view(owner) -> None:
    """Reset the view for a session with no pool data (slot-authoritative clear).

    Called by ``GalleryController.clear_to_empty`` when a restore finds
    an empty/absent slot: drops the series view, hides the stats strip,
    stops the spinner, clears the filter edit (signal-blocked, no loop)
    and lands on the default empty state. No dispatch — the slot is
    already empty, there is nothing to persist.
    """
    try:
        owner._series = []
    except Exception:
        pass
    try:
        owner._mode = None
    except Exception:
        pass
    try:
        owner._source_path = None
    except Exception:
        pass
    try:
        owner._collapsed = {}
    except Exception:
        pass
    try:
        gv = getattr(owner, "_grid_view", None)
        if gv is not None and hasattr(gv, "set_series"):
            gv.set_series([], hub_names=[], collapsed={})
    except Exception:
        pass
    try:
        owner.stats_strip.hide()
    except Exception:
        pass
    try:
        owner.set_triage_done()
    except Exception:
        pass
    try:
        owner.rebuild_grid([])
    except Exception:
        pass
    try:
        owner._empty_state.restore_empty_message()
    except Exception:
        pass
    try:
        owner._render_gallery_filter("")
    except Exception:
        pass
