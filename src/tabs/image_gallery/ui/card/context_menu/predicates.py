"""Selection/target predicates for the gallery card context menu.

Split out of ``ui/card/context_menu.py`` per the module→package split
(``plan-gallery-split-2026-10-17``); function names/bodies moved verbatim.
"""

from __future__ import annotations

from pathlib import Path

from .translator import _t


def _selection_count(owner) -> int:
    """Number of selected cards — through the ONE reader (``action_scope``).

    The menu header uses the RESOLVED context instead (``len(ctx.targets)``);
    this helper stays for callers/tests that need the raw selection size, and
    never reads the ``state`` mirror itself (the slot is the authority).
    """
    try:
        from tabs.image_gallery.use_cases import action_scope

        return len(action_scope.selected_paths(owner))
    except Exception:
        return 0


def _targets_are_single_series(owner, targets) -> bool:
    """True when *targets* are exactly one whole live series (fail-open False).

    Grouping a complete series would pin it onto a fresh id and rebuild
    for nothing — the menu hides Group in that case (Ungroup stays: it
    dissolves). Reads controller ``state.series`` plus the grid mirror
    (``_grid_view._series`` clusters); the UNGROUPED tail is not a series.
    """
    try:
        tset = {str(p) for p in (targets or [])}
    except Exception:
        return False
    if len(tset) < 2:
        return False
    try:
        candidates: list = []
        try:
            st = getattr(owner, "state", None)
            if st is not None and getattr(st, "series", None):
                candidates.extend(list(st.series or []))
        except Exception:
            pass
        try:
            gv = getattr(owner, "_grid_view", None)
            if gv is not None and getattr(gv, "_series", None):
                candidates.extend(list(gv._series or []))
        except Exception:
            pass
        for entry in candidates:
            try:
                if hasattr(entry, "members"):
                    members = list(getattr(entry, "members", None) or [])
                elif isinstance(entry, (list, tuple)):
                    members = list(entry)
                else:
                    continue
                if len(members) >= 2 and {str(getattr(m, "path", None)) for m in members} == tset:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _targets_any_grouped(owner, targets) -> bool:
    """True unless every target is positively UNGROUPED (fail-open True).

    Hides Ungroup for an all-UNGROUPED set (nothing to dissolve — the
    move path would no-op). Targets missing from the known pool (storeless
    doubles) keep the old visible behavior; only a positively-known
    all-ungrouped set hides the entry. Mirrors ``_targets_all_rejected``.
    """
    try:
        tset = {str(t) for t in (targets or [])}
        if not tset:
            return False
        from tabs.image_gallery.use_cases import triage as _triage

        pool: dict[str, bool] = {}
        for it in _triage._items_of(owner):
            try:
                pool[str(Path(it.path))] = getattr(it, "series_id", None) is not None
            except Exception:
                continue
        if any(t not in pool for t in tset):
            return True
        return any(pool[t] for t in tset)
    except Exception:
        return True


def _targets_all_rejected(owner, targets) -> bool:
    """True when every target card is currently rejected (fail-open False).

    Drives the Reject/Unreject label; mirrors the uniform direction in
    ``_ctx_toggle_reject`` (all rejected → unreject, else reject).
    """
    try:
        if not targets:
            return False
        from tabs.image_gallery.use_cases import triage as _triage

        flags: dict[str, bool] = {}
        for it in _triage._items_of(owner):
            try:
                flags[str(Path(it.path))] = bool(
                    getattr(it, "rejected", getattr(it, "triage_rejected", False))
                )
            except Exception:
                continue
        return bool(targets) and all(flags.get(str(t), False) for t in targets)
    except Exception:
        return False


def _selection_label(translate, n: int) -> str:
    if n <= 0:
        return _t(translate, "image_gallery.selection.none", "No selection")
    if n == 1:
        return _t(translate, "image_gallery.selection.one", "1 selected")
    raw = _t(translate, "image_gallery.selection.many", "{n} selected")
    try:
        if "{n}" in raw:
            return raw.format(n=n)
        return f"{n} selected"
    except Exception:
        return f"{n} selected"


def _is_source(owner, path) -> bool:
    """True when the clicked card is already the series source (fail-open False)."""
    try:
        p = str(Path(path))
    except Exception:
        return False
    try:
        st = getattr(owner, "state", None)
        src = getattr(st, "source_path", None) if st is not None else None
        if src is not None:
            return str(Path(src)) == p
    except Exception:
        pass
    try:
        from tabs.image_gallery.services.rank_badge import KIND_SOURCE
        from tabs.image_gallery.use_cases import triage as _triage

        for it in _triage._items_of(owner):
            if str(Path(getattr(it, "path", ""))) == p:
                return str(getattr(it, "badge_kind", "")) == KIND_SOURCE
    except Exception:
        pass
    return False
