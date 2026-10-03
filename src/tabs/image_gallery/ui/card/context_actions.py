"""Per-card context-menu action handlers (split out of ``context_menu.py``).

The menu builder (``context_menu.py``) is already at the file-size ceiling;
the action bodies are use-case glue, not menu construction, so they live
here — same split rationale as ``menu_track.py`` / ``sort_view_menu.py``.
"""

from __future__ import annotations

from pathlib import Path


def _action_targets(owner, path: Path) -> list[Path]:
    """Cards a per-card menu action applies to (file-manager rule).

    Clicked-inside-selection → the whole selection (ordered by
    ``selected_order`` when available, like the keyboard path);
    clicked-outside → just the clicked card. Right-click never mutates
    the selection itself.
    """
    try:
        clicked = Path(path) if not isinstance(path, Path) else path
    except Exception:
        return [path]
    try:
        sel = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
        sel_set = {Path(p) if not isinstance(p, Path) else p for p in sel}
    except Exception:
        return [clicked]
    if clicked not in sel_set:
        return [clicked]
    try:
        order = getattr(getattr(owner, "state", None), "selected_order", None)
    except Exception:
        order = None
    if order:
        try:
            ordered = [Path(p) if not isinstance(p, Path) else p for p in order]
            targets = [p for p in ordered if p in sel_set]
            missing = [p for p in sel_set if p not in set(targets)]
            try:
                missing = sorted(missing, key=str)
            except Exception:
                pass
            targets.extend(missing)
            return targets
        except Exception:
            pass
    try:
        return sorted(sel_set, key=str)
    except Exception:
        return list(sel_set)


def _ctx_make_best(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        # Group: each target becomes best of its own series (same-series
        # multi-pick → last target wins, selection order).
        for target in _action_targets(owner, path):
            try:
                _triage.make_best(owner, target)
            except Exception:
                continue
    except Exception:
        pass


def _ctx_toggle_reject(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.use_cases import triage as _triage

        _dbg("reject clicked path=%s owner=%s", path, type(owner).__name__)
        targets = _action_targets(owner, path)
        # Uniform direction from the clicked card (not per-item flip):
        # any mix → reject all; all rejected → unreject all.
        try:
            clicked = Path(path) if not isinstance(path, Path) else path
            cur = False
            for it in _triage._items_of(owner):
                try:
                    if Path(it.path) == clicked:
                        cur = bool(getattr(it, "rejected", getattr(it, "triage_rejected", False)))
                        break
                except Exception:
                    continue
        except Exception:
            cur = False
        try:
            result = _triage.set_rejected_paths(owner, targets, not cur)
        except Exception:
            _dbg("reject set_rejected_paths raised path=%s", path, exc_info=True)
            return
        _dbg("reject set_rejected_paths returned %r path=%s", result, path)
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


def _ctx_move(owner, path: Path) -> bool:
    """Menu ``Move`` (parity with IC/MC ``Move``): copy-deliver the menu-rule targets.

    Clicked-inside-selection → whole selection via ``carry_selected``;
    clicked-outside → the clicked card alone via a direct ``begin_image_carry``
    (files stay on disk — no source deletion anywhere). Never mutates the
    selection itself. Returns True when a carry started, False otherwise
    (empty selection, missing files, or no carry service — never raises).
    """
    try:
        targets = _action_targets(owner, path)
    except Exception:
        return False
    if not targets:
        return False
    try:
        clicked = Path(path) if not isinstance(path, Path) else path
    except Exception:
        return False
    try:
        sel = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
        sel_set = {Path(p) if not isinstance(p, Path) else p for p in sel}
    except Exception:
        sel_set = set()
    try:
        if clicked in sel_set:
            from tabs.image_gallery.use_cases import carry as _carry

            return bool(_carry.carry_selected(owner))
        existing = [p for p in targets if p.is_file()]
        if not existing:
            return False
        from events.image_carry import begin_image_carry

        return bool(begin_image_carry(existing))
    except Exception:
        return False


def _ctx_remove(owner, path: Path) -> None:
    """Remove target cards from the grid (files on disk stay; list-mode parity).

    Group: whole selection when the clicked card is selected, else one card.
    """
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        targets = _action_targets(owner, path)
        if len(targets) > 1:
            _triage.remove_paths_from_grid(owner, targets)
        else:
            _triage.remove_from_grid(owner, targets[0])
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
