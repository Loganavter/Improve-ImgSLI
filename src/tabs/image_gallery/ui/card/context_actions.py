"""Per-card context-menu action handlers (split out of ``context_menu.py``).

The menu builder (``context_menu.py``) is already at the file-size ceiling;
the action bodies are use-case glue, not menu construction, so they live
here — same split rationale as ``menu_track.py`` / ``sort_view_menu.py``.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.use_cases import action_scope


def _action_targets(owner, path: Path, targets=None) -> list[Path]:
    """Cards a per-card menu action applies to (file-manager rule).

    LEGACY ADAPTER: the menu resolves the scope ONCE through the ONE mechanism
    (``use_cases.action_scope``) and passes ``targets=``; drag/series call
    sites that have no action context still resolve here. Clicked-inside-
    selection → the whole selection (``selected_order``); clicked-outside →
    just the clicked card. Right-click never mutates the selection itself.
    """
    if targets is not None:
        return list(targets)
    return action_scope.resolve_targets(owner, card_path=path)


def _scope_targets(owner, action_id: str, path, targets=None) -> list[Path]:
    """Targets for one action: the passed context, else the policy's answer."""
    if targets is not None:
        return list(targets)
    scope = action_scope.resolve_scope(owner, action_id, card_path=path)
    return list(scope.targets)



def _resolve_move_controller(owner):
    """Controller owning ``move_paths_to_series`` (duck-typed, never raises).

    Menu owners are usually the controller already (widget passes
    ``_owner_for_triage()``); widget-shaped owners resolve through it.
    None when no controller is reachable (storeless doubles) — callers
    degrade gracefully.
    """
    try:
        if callable(getattr(owner, "move_paths_to_series", None)):
            return owner
    except Exception:
        pass
    for attr in ("_owner_for_triage",):
        try:
            resolver = getattr(owner, attr, None)
            cand = resolver() if callable(resolver) else None
            if callable(getattr(cand, "move_paths_to_series", None)):
                return cand
        except Exception:
            continue
    try:
        widget = getattr(owner, "_gallery_widget", None)
        resolver = getattr(widget, "_owner_for_triage", None)
        cand = resolver() if callable(resolver) else None
        if callable(getattr(cand, "move_paths_to_series", None)):
            return cand
    except Exception:
        pass
    return None


def _ctx_ungroup(owner, path: Path, targets=None) -> bool:
    """Move menu targets out of their series into the UNGROUPED tail.

    File-manager rule via ``_action_targets`` (whole selection when the
    clicked card is selected, else the clicked card alone) — or the
    ``targets=`` the menu already resolved. The explicit path to UNGROUPED
    when no tail section exists to drop onto — drop fallback covers the tail
    only when it is visible. Returns the moved count (0 = already ungrouped /
    nothing dispatched).
    """
    try:
        targets = _action_targets(owner, path, targets)
    except Exception:
        return False
    if not targets:
        return False
    try:
        ctrl = _resolve_move_controller(owner)
    except Exception:
        ctrl = None
    if ctrl is None:
        return False
    try:
        return int(ctrl.move_paths_to_series(list(targets), None))
    except Exception:
        return 0


def _ctx_group(owner, path: Path, targets=None):
    """Pin menu targets into a brand-new manual series (multi-select).

    File-manager rule via ``_action_targets`` (whole selection when the
    clicked card is selected, else the clicked card alone) — or the
    ``targets=`` the menu already resolved. Needs ≥2 targets — grouping one
    card is a no-op section-wise (use Ungroup to dissolve instead). Returns
    the new series id, or None when nothing moved / no controller is reachable
    (storeless doubles degrade gracefully).
    """
    try:
        targets = _action_targets(owner, path, targets)
    except Exception:
        return None
    if not targets or len(targets) < 2:
        return None
    try:
        ctrl = _resolve_move_controller(owner)
    except Exception:
        ctrl = None
    if ctrl is None or not callable(getattr(ctrl, "group_paths_as_new_series", None)):
        return None
    try:
        return ctrl.group_paths_as_new_series(list(targets))
    except Exception:
        return None


def _ctx_make_best(owner, path: Path, targets=None) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        # Group: each target becomes best of its own series (same-series
        # multi-pick → last target wins, selection order).
        for target in _scope_targets(owner, "gallery.card.make_best", path, targets):
            try:
                _triage.make_best(owner, target)
            except Exception:
                continue
    except Exception:
        pass


def apply_reject(owner, path: Path, targets=None) -> int:
    """The ONE reject application: uniform direction, any caller.

    ``path`` supplies the DIRECTION (a mixed set → reject all; an all-rejected
    set → unreject all) and ``targets`` is the scope the caller resolved. The
    card menu and Quick Look both call this, so the same card cannot be
    rejected in one surface and unforbidden in the other (owner requirement:
    "QL reject == menu reject for the same card"). Returns the updated count.
    """
    from tabs.image_gallery.debug import gallery_debug as _dbg
    from tabs.image_gallery.use_cases import triage as _triage

    paths = _scope_targets(owner, "gallery.card.reject", path, targets)
    _dbg("reject clicked path=%s targets=%d owner=%s", path, len(paths), type(owner).__name__)
    if not paths:
        return 0
    # Uniform direction from the invoked card (not per-item flip):
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
        return int(_triage.set_rejected_paths(owner, paths, not cur))
    except Exception:
        _dbg("reject set_rejected_paths raised path=%s", path, exc_info=True)
        return 0


def _ctx_toggle_reject(owner, path: Path, targets=None) -> None:
    try:
        apply_reject(owner, path, targets)
    except Exception:
        pass


def apply_remove(owner, path: Path, targets=None) -> int:
    """The ONE remove-from-view application (menu and Quick Look).

    Removes the resolved targets from the grid; the file on disk stays. One
    target goes through ``remove_from_grid`` (the single-card semantic), more
    through ``remove_paths_from_grid`` — the exact split the card menu used, so
    Quick Look Delete and the menu agree for the same card.
    """
    from tabs.image_gallery.use_cases import triage as _triage

    paths = _scope_targets(owner, "gallery.card.remove", path, targets)
    if not paths:
        return 0
    if len(paths) > 1:
        return int(_triage.remove_paths_from_grid(owner, paths))
    return 1 if _triage.remove_from_grid(owner, paths[0]) else 0


def _ctx_remove(owner, path: Path, targets=None) -> None:
    """Remove target cards from the grid (files on disk stay; list-mode parity).

    Group: whole selection when the clicked card is selected, else one card.
    """
    try:
        apply_remove(owner, path, targets)
    except Exception:
        pass


def _ctx_move(owner, path: Path, targets=None) -> bool:
    """Menu ``Move`` (parity with IC/MC ``Move``): copy-deliver the menu-rule targets.

    Clicked-inside-selection → whole selection via ``carry_selected``;
    clicked-outside → the clicked card alone via a direct ``begin_image_carry``
    (files stay on disk — no source deletion anywhere). Never mutates the
    selection itself. Returns True when a carry started, False otherwise
    (empty selection, missing files, or no carry service — never raises).
    """
    try:
        targets = _action_targets(owner, path, targets)
    except Exception:
        return False
    if not targets:
        return False
    try:
        clicked = Path(path) if not isinstance(path, Path) else path
    except Exception:
        return False
    # The selection read is single-sourced (``action_scope``), never the
    # ``state`` mirror directly.
    sel_set = {p for p in action_scope.selected_paths(owner)}
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


def _ctx_reset_metrics(owner, path: Path, targets=None) -> None:
    """Reset the measured-metrics caches for the menu targets, then recompute.

    Targets come from the ONE scope resolver (``use_cases.action_scope``):
    whole selection when the clicked card is selected, else the clicked card
    alone — and that resolved scope IS what gets cleared. Until 2026-10-27 this
    handler resolved the scope and then passed ``paths=None`` (the whole pool),
    so a three-card selection zeroed every card of the tab (owner report:
    "Почему я выделил 3 изображения, а он экшн повесил на все, которые есть в
    вкладке?"). An empty scope clears nothing — no widening. Never raises.

    DEFERRED (wave 2, ``use_cases/cache_reset.py``): the per-backend measured
    stores are still swept whole (``clear_metrics_caches`` — "the MEASURED
    stores are always swept whole"), so a two-card reset still drops the pool's
    measured caches; only the per-card item state is scoped. See DONE.md.
    """
    try:
        targets = _scope_targets(owner, "gallery.card.reset_metrics", path, targets)
    except Exception:
        targets = []
    if not targets:
        return
    try:
        from tabs.image_gallery.use_cases import cache_reset as _cache_reset

        _cache_reset.reset_metrics_caches(owner, paths=list(targets))
    except Exception:
        pass


def _ctx_set_source(owner, path: Path, targets=None) -> bool:
    """Fidelity only: set the ONE resolved target as source (menu & registry).

    Rule 8: the menu and the Find Action row must answer the same. The scope is
    resolved by ``action_scope`` (kind ``single``): a multi-selection is a
    named refusal in both surfaces, never "the clicked card silently wins".
    Returns False (no-op) when the scope is not exactly one card.
    """
    try:
        scope_targets = _scope_targets(owner, "gallery.card.set_source", path, targets)
    except Exception:
        scope_targets = []
    if len(scope_targets) != 1:
        return False
    try:
        p = Path(scope_targets[0])
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
        return False
    return True
