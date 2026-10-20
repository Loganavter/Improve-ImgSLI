"""Card interaction + context menus for the gallery widget (plan Part B, Wave 3).

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps same-named one-line
delegators so call sites and tests do not move. Fail-open like the
surrounding widget chrome.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.debug import gallery_debug as _dbg


def _on_card_toggle(owner, path: Path, additive: bool = False) -> None:
    # Click opens, Ctrl+click selects (manual selection stays orthogonal
    # to triage — Ctrl-click/marquee → selection; plain click → quick look).
    if not additive:
        try:
            owner.show_quick_look(path)
            return
        except Exception:
            pass
    try:
        from tabs.image_gallery.use_cases import selection as _sel

        tri_owner = owner._owner_for_triage()
        _sel.toggle_card(tri_owner, path, additive=additive)
    except Exception:
        try:
            owner.analyze_requested.emit(path)
        except Exception:
            pass


def _on_empty_host_context(owner, global_pos) -> None:
    # FM background menu on empty canvas: Sort by / View (toolbar state).
    try:
        from PySide6.QtGui import QCursor

        gp = global_pos if global_pos is not None else QCursor.pos()
    except Exception:
        gp = global_pos
    try:
        sort_index = int(owner.toolbar.sort_index)
    except Exception:
        sort_index = None
    try:
        view_is_list: bool | None = bool(owner.toolbar._is_list)
    except Exception:
        view_is_list = None
    try:
        # ``_context`` is the TabContext the widget was built with (see
        # __init__) — the only translator source (the legacy
        # ``_gallery_context`` alias was never assigned).
        _ctx = getattr(owner, "_context", None)
        tr = getattr(_ctx, "_tr", None) if _ctx is not None else None
    except Exception:
        tr = None
    try:
        from tabs.image_gallery.ui.card.sort_view_menu import (
            popup_empty_context_menu,
        )

        popup_empty_context_menu(
            owner._grid_view,
            gp,
            tr,
            sort_index,
            owner.toolbar.set_sort_index,
            view_is_list,
            owner.toolbar.set_view_list,
        )
    except Exception:
        pass


def _on_card_context(owner, path: Path) -> None:
    # ContextMenu under cursor: selection section (ex-HUD) + per-card actions.
    # Use public sli_ui_toolkit.widgets ContextMenu via card helper.
    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

    import time as _time

    _dbg_on = _dbg_enabled()
    _t0 = _time.perf_counter() if _dbg_on else 0.0
    if _dbg_on:
        _dbg("ctx menu entry path=%s", path)
    try:
        # Owner is the attached controller (self when unattached) —
        # no attribute scan, no window walk (G2 gallery contract).
        tri_owner = owner._owner_for_triage()
        if _dbg_on:
            _t_owner = _time.perf_counter()
        card = owner._grid_view.card_for(path) if hasattr(owner, "_grid_view") else None
        anchor = card if card is not None else owner
        if _dbg_on:
            _dbg(
                "ctx menu phase resolve=%.1fms card_for=%.1fms anchor=%s owner=%s",
                (_t_owner - _t0) * 1000.0,
                (_time.perf_counter() - _t_owner) * 1000.0,
                type(anchor).__name__,
                type(tri_owner).__name__ if tri_owner is not None else "None",
            )
        # Try hover helper popup.
        from tabs.image_gallery.ui.card import popup_gallery_card_context_menu

        try:
            from PySide6.QtGui import QCursor

            gp = QCursor.pos()
        except Exception:
            gp = None
        def _ctx_owner():
            try:
                return owner._owner_for_triage()
            except Exception:
                return tri_owner

        def _ctx_ask(scope_kind: str):
            try:
                tri = _ctx_owner()
                fn = getattr(tri, "open_ask_ai", None)
                if callable(fn):
                    fn(scope_kind, card, Path(path))
            except Exception:
                pass

        try:
            sel_set = getattr(getattr(tri_owner, "state", None), "selected_paths", None) or set()
            sel_n = len(sel_set)
        except Exception:
            sel_n = 0
        try:
            # Same fix as the empty-canvas menu: the translator lives on
            # ``_context`` only.
            _ctx = getattr(owner, "_context", None)
            _tr = getattr(_ctx, "_tr", None) if _ctx is not None else None
        except Exception:
            _tr = None
        popup_gallery_card_context_menu(
            anchor,
            tri_owner,
            Path(path),
            global_pos=gp,
            selection_count=sel_n,
            # Scope callbacks for Analyze / Find similar (and carry when it
            # returns to the menu) are deliberately NOT passed: the menu
            # resolves the targets through ``use_cases.action_scope`` once and
            # hands them to the default paths. A zero-arg closure here used to
            # re-derive its own scope (``next(iter(selected_paths))``) and
            # analyzed one arbitrary card of a multi-selection. Ask AI keeps a
            # callback: it takes the kind string and the flyout owns its scope.
            on_ask_ai=_ctx_ask,
            translate=_tr,
        )
        if _dbg_on:
            _dbg("ctx menu done total=%.1fms path=%s", (_time.perf_counter() - _t0) * 1000.0, path)
    except Exception:
        if _dbg_on:
            _dbg("ctx menu raised path=%s", path, exc_info=True)
        pass


def _on_empty_file_dropped(owner, path_str: str) -> None:
    from tabs.image_gallery.ui import drag_drop as _drag_drop

    _drag_drop.on_empty_file_dropped(owner, path_str, owner._owner_for_triage())
