"""ContextMenu mirror for gallery card (ContextMenu, no QMenu)."""

from __future__ import annotations

from pathlib import Path


def popup_gallery_card_context_menu(card, owner, path: Path, global_pos=None, mode=None) -> None:  # type: ignore[no-untyped-def]
    """Popup ``ContextMenu`` mirroring hover capsule actions for *path*.

    Uses public ``sli_ui_toolkit.widgets`` ContextMenu API (no QMenu).
    ``mode`` controls inclusion of "Set as source" (fidelity only).
    """
    try:
        from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction

        from tabs.image_gallery.debug import gallery_debug as _dbg

        # Resolve mode: explicit > card attribute > owner state.
        _mode = mode
        if _mode is None:
            try:
                _mode = getattr(card, "_gallery_mode", None)
            except Exception:
                _mode = None
        if _mode is None and owner is not None:
            try:
                st = getattr(owner, "state", None)
                _mode = getattr(st, "mode", None) if st is not None else getattr(owner, "_mode", None)
            except Exception:
                pass
        try:
            ms = str(_mode.value).lower() if hasattr(_mode, "value") else str(_mode).lower() if _mode is not None else ""
        except Exception:
            ms = ""
        include_source = ms == "fidelity"

        entries = [
            ContextMenuAction(
                action_id="gallery.make_best",
                label="★ Make best",
                callback=lambda: _ctx_make_best(owner, path),
            ),
            ContextMenuAction(
                action_id="gallery.reject",
                label="✕ Reject",
                callback=lambda: _ctx_toggle_reject(owner, path),
            ),
            ContextMenuAction(
                action_id="gallery.compare",
                label="⇄ Compare",
                callback=lambda: _ctx_compare(owner, path),
            ),
        ]
        if include_source:
            entries.append(
                ContextMenuAction(
                    action_id="gallery.set_as_source",
                    label="Set as source",
                    callback=lambda: _ctx_set_source(owner, path),
                )
            )
        menu = ContextMenu(entries=entries)
        _dbg(
            "card menu popup path=%s mode=%r owner=%s n_entries=%d",
            path,
            ms,
            type(owner).__name__,
            len(entries),
        )
        # Flyout group identity for policy.
        try:
            menu.flyout_group = "context_menu"  # type: ignore[attr-defined]
        except Exception:
            pass
        if global_pos is not None:
            try:
                menu.popup_at(global_pos)
                return
            except Exception:
                pass
        # Fallback anchor popup.
        try:
            from sli_ui_toolkit.widgets import popup_context_menu_for_anchor

            popup_context_menu_for_anchor(card.window() or card, card, entries)
        except Exception:
            # Last resort: try menu.show
            try:
                menu.show()
            except Exception:
                pass
    except Exception:
        pass


def _ctx_make_best(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        _triage.make_best(owner, path)
    except Exception:
        pass


def _ctx_toggle_reject(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.use_cases import triage as _triage

        _dbg("reject clicked path=%s owner=%s", path, type(owner).__name__)
        try:
            result = _triage.toggle_reject(owner, path)
        except Exception:
            _dbg("reject toggle_reject raised path=%s", path, exc_info=True)
            return
        _dbg("reject toggle_reject returned %r path=%s", result, path)
    except Exception:
        pass


def _ctx_compare(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.use_cases import carry as _carry

        # Select path then carry.
        try:
            if hasattr(owner, "state") and hasattr(owner.state, "selected_paths"):
                owner.state.selected_paths.add(Path(path))
        except Exception:
            pass
        _carry.carry_selected(owner)
    except Exception:
        pass


def _ctx_set_source(owner, path: Path) -> None:
    """Fidelity only: set selected image as source hub (used by IconActionFlyout & ContextMenu)."""
    try:
        from pathlib import Path as _P

        p = _P(path)
        # Controller / widget state
        st = getattr(owner, "state", None)
        if st is not None:
            try:
                st.source_path = p
            except Exception:
                pass
        # Widget mirrors _source_path and stats strip chip
        w = getattr(owner, "widget", None)
        candidates = [w, owner]
        # Also try window's gallery widget
        try:
            win = None
            for cand in candidates:
                if cand is not None and hasattr(cand, "window"):
                    try:
                        win = cand.window()
                        if win is not None:
                            candidates.append(win)
                        break
                    except Exception:
                        pass
        except Exception:
            pass
        for cand in candidates:
            if cand is None:
                continue
            try:
                if hasattr(cand, "_source_path"):
                    cand._source_path = p  # type: ignore
            except Exception:
                pass
            try:
                if hasattr(cand, "stats_strip") and hasattr(cand.stats_strip, "set_mode"):
                    # Reuse mode from state
                    mode_val = getattr(st, "mode", None) if st is not None else getattr(cand, "_mode", None)
                    cand.stats_strip.set_mode(str(mode_val or "fidelity"), p)  # type: ignore
            except Exception:
                pass
            try:
                if hasattr(cand, "_grid_view") and hasattr(cand._grid_view, "_mode"):
                    # Grid stores mode; no direct update needed
                    pass
            except Exception:
                pass
        # Try generic helper (quick_look_hooks) as fallback
        try:
            from tabs.image_gallery.ui import quick_look_hooks as _qlh

            _qlh.on_quick_set_source(owner, p)
        except Exception:
            pass
    except Exception:
        pass
