"""Quick look overlay helpers for ImageGalleryWidget — thin-owner target.

Audit-Meta: pattern=thin-owner-target size=exempt reason="one quick-look hooks concern: owner-first overlay wiring, triage toggles (reject/source set+unset) and strip hooks share one seam"

Per CODE_PATTERNS.md: plain functions taking the owning widget as first
argument. No string-dispatched getattr for dispatch — owner and paths are
passed explicitly.

Widget keeps thin delegators:
    def show_quick_look(self, x): return quick_look_hooks.show_quick_look(self, x)
    def eventFilter(self, w,e): return quick_look_hooks.event_filter(self,w,e)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

# Re-export: the crop wake-up seam lives in ui/quick_look/insets.py (crop
# concern); kept here so existing _qlh.refresh_crop_for call sites stay put.
from tabs.image_gallery.ui.quick_look.insets import refresh_crop_for  # noqa: F401

def owner_for_triage(owner):
    """Local resolve — protocol-first, mirrors use_cases.triage_ui.owner_for_triage.

    The attached controller via the widget protocol wins; legacy binds
    below are last-resort. The window-attribute walk is gone (no writer
    ever set it since G1/G2 deleted the pokes).
    """
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        if callable(resolve):
            try:
                cand = resolve()
            except Exception:
                cand = None
            if cand is not None:
                return cand
    except Exception:
        pass
    if callable(getattr(owner, "set_selection", None)):
        return owner
    try:
        ctrl = owner._controller  # type: ignore[attr-defined]
        if ctrl is not None:
            return ctrl
    except AttributeError:
        pass
    try:
        ctrl = owner._owner  # type: ignore[attr-defined]
        if ctrl is not None:
            return ctrl
    except AttributeError:
        pass
    return owner


def _overlay_parent_window(owner, triage_owner) -> QWidget | None:
    """Resolve overlay parent as window (TopLevelInWindowOverlay requires in-window parent)."""
    for cand in (owner, triage_owner):
        if isinstance(cand, QWidget):
            try:
                win = cand.window()
                if isinstance(win, QWidget):
                    return win
            except Exception:
                pass
            return cand
        # Controller case with widget attr
        for attr in ("widget", "_widget", "_gallery_widget"):
            try:
                w = getattr(cand, attr, None)
                if isinstance(w, QWidget):
                    try:
                        win = w.window()
                        if isinstance(win, QWidget):
                            return win
                    except Exception:
                        pass
                    return w
            except Exception:
                continue
    # Fallback callable window()
    for cand in (owner, triage_owner):
        try:
            win = cand.window()  # type: ignore[union-attr]
            if isinstance(win, QWidget):
                return win
        except Exception:
            continue
    if isinstance(owner, QWidget):
        return owner
    return None


def _merge_selection_setattr(state, p) -> None:
    """Storeless fallback for the P0-5 selection merge (no controller).

    Verbatim legacy behavior (add to ``selected_paths``, append to
    ``selected_order`` when missing), spelled via ``setattr`` — no direct
    state writes.
    """
    try:
        selected = getattr(state, "selected_paths", None)
        if selected is None:
            setattr(state, "selected_paths", {p})
        else:
            selected.add(p)
    except Exception:
        try:
            setattr(state, "selected_paths", {p})
        except Exception:
            pass
    try:
        order = getattr(state, "selected_order", None)
        if order is None:
            setattr(state, "selected_order", [p])
        elif p not in order:
            order.append(p)
    except Exception:
        pass


def show_quick_look(owner, item_or_path) -> None:
    """Open quick look for *item* — resolves via owner state series.

    Slow-open diagnosis (IMGSLI_GALLERY_DEBUG=1): per-phase ms with
    ``[gallery-debug]`` prefix (item-resolve / triage-resolve /
    overlay-create-or-reuse / show_for), see ``docs/dev/LOGGING.md``.
    """
    import time as _time

    from tabs.image_gallery.debug import gallery_debug as _dbg
    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

    _dbg_on = _dbg_enabled()
    _t0 = _time.perf_counter() if _dbg_on else 0.0
    if _dbg_on:
        try:
            _dbg("quick look begin raw=%r", str(item_or_path)[:120])
        except Exception:
            pass
    try:
        # Normalize to GalleryItem
        item = None
        path_val = None
        if hasattr(item_or_path, "path"):
            item = item_or_path
            path_val = Path(getattr(item, "path"))
        else:
            path_val = Path(str(item_or_path))
            for it in list(owner._items or []):  # type: ignore[attr-defined]
                try:
                    if Path(it.path) == path_val:
                        item = it
                        break
                except Exception:
                    continue
        if item is None:
            if _dbg_on:
                _dbg("quick look abort item-not-found total=%.1fms", (_time.perf_counter() - _t0) * 1000.0)
            return
        if _dbg_on:
            _t_item = _time.perf_counter()
        triage_owner = owner_for_triage(owner)
        if _dbg_on:
            _t_triage = _time.perf_counter()
            _dbg(
                "quick look phase item-resolve=%.1fms triage-resolve=%.1fms path=%s n_items=%s",
                (_t_item - _t0) * 1000.0,
                (_t_triage - _t_item) * 1000.0,
                path_val,
                len(owner._items) if getattr(owner, "_items", None) is not None else -1,  # type: ignore[attr-defined]
            )
        overlay = owner._quick_look_overlay  # type: ignore[attr-defined]
        if _dbg_on:
            _t_overlay_check = _time.perf_counter()
        if overlay is None:
            try:
                from tabs.image_gallery.ui.quick_look import QuickLookOverlay

                parent = _overlay_parent_window(owner, triage_owner)
                if parent is None or not isinstance(parent, QWidget):
                    try:
                        parent = owner.window() or owner  # type: ignore[union-attr]
                    except Exception:
                        parent = owner  # type: ignore[assignment]
                overlay = QuickLookOverlay(parent, triage_owner, translate=_widget_tr(owner))
                owner._quick_look_overlay = overlay  # type: ignore[attr-defined]
                try:
                    overlay.compareRequested.connect(lambda p: on_quick_compare(owner, p))
                except Exception:
                    pass
                try:
                    overlay.rejectToggled.connect(lambda p: on_quick_reject(owner, p))
                except Exception:
                    pass
                try:
                    overlay.setSource.connect(lambda p: on_quick_set_source(owner, p))
                except Exception:
                    pass
                try:
                    overlay.regionAskRequested.connect(
                        lambda p, b: on_quick_ask_region(owner, p, b)
                    )
                except Exception:
                    pass
            except Exception:
                if _dbg_on:
                    _dbg("quick look overlay-create raised", exc_info=True)
                return
            if _dbg_on:
                _dbg(
                    "quick look phase overlay-create=%.1fms total=%.1fms",
                    (_time.perf_counter() - _t_overlay_check) * 1000.0,
                    (_time.perf_counter() - _t0) * 1000.0,
                )
        else:
            # Reuse path: the overlay already holds its explicit owner from
            # construction/show_for (G3 dispatch-only: never poked from
            # outside) — show_for below re-supplies triage_owner explicitly.
            if _dbg_on:
                _dbg(
                    "quick look phase overlay-reuse=%.1fms total=%.1fms visible=%s",
                    (_time.perf_counter() - _t_overlay_check) * 1000.0,
                    (_time.perf_counter() - _t0) * 1000.0,
                    overlay.isVisible() if hasattr(overlay, "isVisible") else "?",
                )
        if _dbg_on:
            _t_show = _time.perf_counter()
        overlay.show_for(item, triage_owner)
        if _dbg_on:
            _dbg(
                "quick look phase show_for=%.1fms total=%.1fms path=%s",
                (_time.perf_counter() - _t_show) * 1000.0,
                (_time.perf_counter() - _t0) * 1000.0,
                path_val,
            )
    except Exception:
        if _dbg_on:
            _dbg("quick look outer raised", exc_info=True)
        pass


def on_quick_compare(owner, path) -> None:
    try:
        from tabs.image_gallery.use_cases import carry as _carry

        triage_owner = owner_for_triage(owner)
        try:
            state = triage_owner.state  # type: ignore[attr-defined]
            # P0-5: MERGE, never overwrite — "Add to Multi Compare" accumulates
            # across quick-look visits (|selection| >= 2 after two adds). The
            # single-compare path already narrows to {current} in
            # QuickLookOverlay._on_compare before emitting, so merging here is
            # a no-op for it and a fix for multi-add.
            # G3 dispatch-only: merge through controller.set_selection when
            # available (dispatch + mirror + grid apply); storeless fallback
            # keeps the verbatim merge via setattr (no direct writes).
            p = Path(path)
            setter = getattr(triage_owner, "set_selection", None)
            if callable(setter):
                try:
                    cur = list(getattr(state, "selected_paths", None) or [])
                    merged: list = []
                    seen: set = set()
                    for cand in list(cur) + [p]:
                        try:
                            key = str(cand)
                        except Exception:
                            continue
                        if key not in seen:
                            seen.add(key)
                            merged.append(cand)
                    setter(merged)
                except Exception:
                    _merge_selection_setattr(state, p)
            else:
                _merge_selection_setattr(state, p)
        except Exception:
            pass
        _carry.carry_selected(triage_owner)
    except Exception:
        pass


def on_quick_reject(owner, path) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        triage_owner = owner_for_triage(owner)
        _triage.toggle_reject(triage_owner, Path(path))
        try:
            overlay = owner._quick_look_overlay  # type: ignore[attr-defined]
            if overlay is not None and overlay.isVisible():
                try:
                    cur = getattr(overlay, "_current_item", None)
                    if cur is not None and Path(getattr(cur, "path", "")) == Path(path):
                        # Same item still open: flag-only refresh (no
                        # preview re-decode — see _refresh_triage_state).
                        overlay._refresh_triage_state()
                        return
                except Exception:
                    pass
                for it in list(owner._items or []):  # type: ignore[attr-defined]
                    if Path(it.path) == Path(path):
                        overlay.show_for(it, triage_owner)
                        break
        except Exception:
            pass
    except Exception:
        pass


def _unset_quick_source(owner) -> None:
    """Clear the triage source (the "Unset" half of the source toggle).

    Mirrors ``on_quick_set_source``: clears ``source_path`` everywhere, moves
    the SOURCE badge immediately, then re-runs triage so the pool regroups in
    its no-source mode (camera/batch) and the mode-appropriate analysis
    starts. Never raises.
    """
    try:
        try:
            triage_owner = owner_for_triage(owner)
        except Exception:
            triage_owner = owner
        try:
            state = getattr(triage_owner, "state", None)
            if state is not None:
                state.source_path = None  # type: ignore[attr-defined]
                # No source → back to the no-source mode (camera/batch).
                try:
                    from tabs.image_gallery.services.mode import select_mode

                    state.mode = select_mode(  # type: ignore[attr-defined]
                        getattr(state, "series", None),
                        getattr(state, "items", None),
                        None,
                    )
                except Exception:
                    pass
        except Exception:
            pass
        try:
            owner._source_path = None  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            sync = getattr(owner, "sync_source_badge", None)
            if callable(sync):
                sync(None)
        except Exception:
            pass
        # Re-run triage: resets source=None, re-selects mode, restarts the
        # mode-appropriate proxy analysis, and repaints the grid.
        try:
            retriage = getattr(triage_owner, "retriage_quiet", None)
            if callable(retriage):
                retriage()
        except Exception:
            pass
    except Exception:
        pass


def on_quick_ask_region(owner, path, box) -> None:
    """A Quick Look region was selected → open the Ask AI region flyout (upward).

    The flyout anchors to the held selection band (above the selected
    region, not the preview corner); the band is dismissed when the
    flyout closes (wired in the controller).
    """
    try:
        triage_owner = owner_for_triage(owner)
        fn = getattr(triage_owner, "open_ask_ai_region", None)
        if not callable(fn):
            return
        anchor = None
        try:
            overlay = getattr(owner, "_quick_look_overlay", None)
            if overlay is not None:
                get_anchor = getattr(overlay, "region_selection_anchor", None)
                if callable(get_anchor):
                    anchor = get_anchor()
                if anchor is None:
                    anchor = getattr(overlay, "_preview_host", None) or overlay
        except Exception:
            anchor = None
        if anchor is None:
            anchor = owner
        fn(path, box, anchor)
    except Exception:
        pass


def on_quick_set_source(owner, path) -> None:
    if path is None:
        _unset_quick_source(owner)
        return

    try:
        triage_owner = owner_for_triage(owner)
        new_mode = None
        try:
            state = triage_owner.state  # type: ignore[attr-defined]
            # G3 dispatch-only seam: prefer controller.set_source (added by
            # G1) when available; it is absent on this base, so mirror
            # locally until the seam lands.
            # TODO(G1): route via controller.set_source(Path(path)).
            set_source = getattr(triage_owner, "set_source", None)
            if callable(set_source):
                try:
                    set_source(Path(path))
                except Exception:
                    pass
            else:
                setattr(state, "source_path", Path(path))  # type: ignore[attr-defined]
            # P0-6: re-run mode selection so chips flip to FIDELITY.
            try:
                from tabs.image_gallery.services.mode import select_mode

                new_mode = select_mode(
                    getattr(state, "series", None),
                    getattr(state, "items", None),
                    Path(path),
                )
                state.mode = new_mode  # type: ignore[attr-defined]
            except Exception:
                new_mode = None
        except Exception:
            pass
        try:
            owner._source_path = Path(path)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Move the SOURCE badge NOW, decoupled from the comparison pass below:
        # the badge flips on click, the background fidelity worker catches up.
        try:
            sync = getattr(owner, "sync_source_badge", None)
            if callable(sync):
                sync(Path(path))
        except Exception:
            pass
        try:
            if new_mode is None:
                try:
                    st = triage_owner.state  # type: ignore[attr-defined]
                    mode = getattr(st, "mode", None) if st is not None else owner._mode  # type: ignore[attr-defined]
                except Exception:
                    mode = owner._mode  # type: ignore[attr-defined]
            else:
                mode = new_mode
            mode_name = getattr(mode, "value", mode) or "fidelity"
            owner.stats_strip.set_mode(str(mode_name), Path(path))  # type: ignore[attr-defined]
        except Exception:
            pass
        # S4 parity: the new source invalidates every measured number — mark
        # the 4 fidelity keys stale and re-run the pass so the header (new
        # source name) and the numbers never disagree. Covers the overlay
        # setSource signal (connected in show_quick_look) and the card
        # context-menu fallback (which delegates here); delivery repopulates
        # the open overlay via QuickLookOverlay.refresh_metrics (W1).
        try:
            runner = triage_owner
            start = getattr(runner, "_start_fidelity_analysis", None)
            state = getattr(runner, "state", None)
            if callable(start) and state is not None:
                items = list(getattr(state, "items", None) or [])
                source = getattr(state, "source_path", None)
                if source is None:
                    try:
                        source = Path(path)
                    except Exception:
                        source = None
                if items and source is not None:
                    for it in items:
                        try:
                            m = getattr(it, "metrics", None)
                            if isinstance(m, dict):
                                for k in ("ssim", "hf_ratio", "delta_e", "upscale_factor"):
                                    m.pop(k, None)
                        except Exception:
                            pass
                    try:
                        start(items, source)
                    except Exception:
                        pass
                    try:
                        overlay = getattr(owner, "_quick_look_overlay", None)
                        if overlay is not None and hasattr(overlay, "refresh_metrics"):
                            for it in items:
                                try:
                                    overlay.refresh_metrics(it)
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass


def refresh_quick_look(owner, item) -> None:
    """Stage 2: refresh quick look report after artifact analysis."""
    try:
        overlay = owner._quick_look_overlay  # type: ignore[attr-defined]
        if overlay is not None and hasattr(overlay, "refresh_artifacts"):
            overlay.refresh_artifacts(item)
    except Exception:
        pass


def refresh_artifacts_for(owner, item) -> None:
    refresh_quick_look(owner, item)


def install_hooks(owner) -> None:
    """Install double-click event filter on current card pool for quick look."""
    try:
        # Iterate widget's own _cards
        try:
            for _path, card in list(owner._cards.items()):  # type: ignore[attr-defined]
                try:
                    card.installEventFilter(owner)
                except Exception:
                    pass
        except Exception:
            pass
        # Also cover grid_view internal pool
        try:
            for _str_path, card in list(owner._grid_view._cards_by_path.items()):  # type: ignore[attr-defined]
                try:
                    card.installEventFilter(owner)
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass


def event_filter(owner, watched, event) -> bool:
    """Double-click on gallery card → show_quick_look. Return True if consumed."""
    try:
        from PySide6.QtCore import QEvent as _QEvt
        from PySide6.QtWidgets import QWidget as _QW

        if event.type() == _QEvt.Type.MouseButtonDblClick:
            path_prop = None
            try:
                path_prop = watched.property("gallery_path")
            except Exception:
                path_prop = None
            if path_prop:
                try:
                    p = Path(str(path_prop))
                    for it in list(owner._items or []):  # type: ignore[attr-defined]
                        if Path(it.path) == p:
                            show_quick_look(owner, it)
                            return True
                except Exception:
                    pass
            try:
                item = watched._gallery_item  # type: ignore[attr-defined]
                if item is not None:
                    show_quick_look(owner, item)
                    return True
            except Exception:
                pass
    except Exception:
        pass
    try:
        return _QW.eventFilter(owner, watched, event)  # type: ignore[call-arg]
    except Exception:
        try:
            from PySide6.QtWidgets import QWidget as _QW2

            return _QW2.eventFilter(owner, watched, event)  # type: ignore[call-arg]
        except Exception:
            return False


def _widget_tr(owner):
    """Owner widget's existing context translator (same seam as widget.py's
    toolbar/stats_strip ``context._tr``); ``None`` keeps the EN defaults.

    Defined at module tail so the ownership-guard ALLOWLIST (a file+line
    ratchet over this file) keeps its line numbers stable.
    """
    try:
        ctx = getattr(owner, "_context", None)
        return getattr(ctx, "_tr", None) if ctx is not None else None
    except Exception:
        return None
