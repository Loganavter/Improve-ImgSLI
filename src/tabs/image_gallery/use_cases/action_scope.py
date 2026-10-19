"""Target resolution for gallery actions — the ONE scope mechanism.

Every gallery action (Analyze, Find similar, Reset metrics cache, Make best,
Reject, Remove, Group/Ungroup, carry, keyboard actions) needs the same answer
to one question: *which cards does this apply to?* Before this module each
call site answered it itself, and they disagreed — Analyze did
``next(iter(state.selected_paths))``, i.e. it let **set iteration order**
decide which member of a multi-selection got analyzed. That is not a scope
decision: the owner asked for a group action and one arbitrary card ran.

Precedence (``resolve_targets``), in order:

    a) ``card_path`` given AND selection non-empty AND does not contain it
       -> ``[card_path]``          (right-clicking an unselected card acts on
                                    that card only — file-manager rule)
    b) selection non-empty        -> the selection, in ``selected_order`` order
    c) ``card_path`` given        -> ``[card_path]``
    d) focused card / first item  -> ``[path]``
    e) otherwise                  -> ``[]``

WHY this order: a context menu opened on a card carries that card as
``card_path``; if the card is part of the selection, the action is a
*selection* action (b) — that is the bug fix (all members, not one). If it is
not part of the selection, the user pointed at exactly one card (a) / (c).
With no card context (keyboard, menu-less paths) the selection wins (b),
then the keyboard focus, then the first visible item (d) — and nothing at
all (e) is a valid answer that callers must honour (an empty scope is never
"the first card by accident").

The selection read (``selected_paths``) is also single-sourced here:

- when the owner exposes a gallery store slot, the slot selection is
  authoritative (even when empty — a cleared selection must not resurrect a
  stale local mirror);
- otherwise ``owner.state.selected_paths`` with ``state.selected_order``
  applied for a stable dispatch order (missing entries appended sorted);
- always deduped, always ``Path``, never raises.

No Qt import at module level, no app boot needed (unit tests use a
SimpleNamespace owner). The focused-card fallback imports ``QApplication``
lazily and degrades to the first item when Qt is unavailable.
"""

from __future__ import annotations

from pathlib import Path

PathList = list[Path]


def _as_path(value) -> Path | None:
    """Coerce *value* to ``Path``; None when it is not path-like."""
    try:
        return value if isinstance(value, Path) else Path(value)
    except Exception:
        return None


def _dedupe(paths) -> PathList:
    """Stable de-dupe (first occurrence wins), dropping uncoercible values."""
    out: PathList = []
    seen: set[Path] = set()
    for raw in paths:
        p = _as_path(raw)
        if p is None or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _slot_selection(owner) -> list[str] | None:
    """Gallery slot selection (ordered path-id strings), or None.

    Returns None when no store/slot is reachable (storeless unit contexts) so
    callers fall back to the local mirror. When the slot exists it is
    authoritative — even when empty.

    Candidates: the owner itself, its ``_owner_for_triage()`` protocol result
    (G5), then the ``widget``/``_widget`` child links. Each candidate's own
    session is addressed explicitly (Wave ISO) — never the active-session
    default, which would read a foreign tab's selection.
    """
    try:
        from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
        from tabs.image_gallery.state import selectors as _selectors
    except Exception:
        return None
    candidates = [owner]
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        proto = resolve() if callable(resolve) else None
        if proto is not None:
            candidates.append(proto)
    except Exception:
        pass
    for attr in ("widget", "_widget"):
        try:
            candidates.append(getattr(owner, attr, None))
        except Exception:
            pass
    for cand in candidates:
        if cand is None:
            continue
        try:
            ctx = getattr(cand, "_context", None) or getattr(cand, "context", None)
            store = getattr(ctx, "store", None) or getattr(cand, "store", None)
            if store is None or not hasattr(store, "get_session_state_slot"):
                continue
            try:
                from tabs.image_gallery.ui.gallery_store import (
                    resolve_owner_session_id,
                )

                own_id = resolve_owner_session_id(cand)
            except Exception:
                own_id = None
            slot = store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=own_id)
            if slot is None:
                continue
            return list(_selectors.get_selection(slot))
        except Exception:
            continue
    return None


def _state_selection(owner) -> PathList:
    """``owner.state.selected_paths`` ordered by ``selected_order``."""
    state = getattr(owner, "state", None)
    try:
        selected = list(getattr(state, "selected_paths", None) or ())
    except Exception:
        selected = []
    paths = _dedupe(selected)
    if not paths:
        return []
    try:
        order = list(getattr(state, "selected_order", None) or [])
    except Exception:
        order = []
    if not order:
        try:
            return sorted(paths, key=str)
        except Exception:
            return paths
    index: dict[Path, int] = {}
    for i, raw in enumerate(order):
        p = _as_path(raw)
        if p is not None and p not in index:
            index[p] = i
    known = sorted((p for p in paths if p in index), key=lambda p: index[p])
    missing = sorted((p for p in paths if p not in index), key=str)
    return known + missing


def selected_paths(owner) -> PathList:
    """The current selection as an ordered, deduped list of ``Path``.

    Single source of truth for "what is selected": the gallery store slot
    when the owner exposes one (authoritative, even when empty), else
    ``state.selected_paths`` ordered by ``state.selected_order``. Stable for
    repeated calls, never raises, never mutates.
    """
    try:
        slot_sel = _slot_selection(owner)
    except Exception:
        slot_sel = None
    if slot_sel is not None:
        return _dedupe(slot_sel)
    try:
        return _state_selection(owner)
    except Exception:
        return []


def _focused_path(owner) -> Path | None:
    """Path of the card holding keyboard focus, or None (fail-soft)."""
    for attr in ("focused_path", "_focused_path", "focused_card_path"):
        try:
            value = getattr(owner, attr, None)
            value = value() if callable(value) else value
        except Exception:
            continue
        p = _as_path(value) if value is not None else None
        if p is not None:
            return p
    try:
        from PySide6.QtWidgets import QApplication

        widget = QApplication.focusWidget()
        prop = widget.property("gallery_path") if widget is not None else None
        if prop:
            return _as_path(str(prop))
    except Exception:
        pass
    return None


def _first_item_path(owner) -> Path | None:
    """Path of the first gallery item (state.items → _items → items)."""
    for holder in (getattr(owner, "state", None), owner):
        if holder is None:
            continue
        try:
            items = list(getattr(holder, "items", None) or ())
        except Exception:
            items = []
        if not items:
            try:
                items = list(getattr(holder, "_items", None) or ())
            except Exception:
                items = []
        for item in items:
            try:
                raw = item.get("path") if isinstance(item, dict) else getattr(item, "path", None)
            except Exception:
                raw = None
            p = _as_path(raw) if raw is not None else None
            if p is not None:
                return p
    return None


def resolve_targets(owner, *, card_path=None) -> PathList:
    """Cards an action applies to — the precedence table in the module docstring.

    ``card_path`` is the card the action was invoked on (context menu), or
    None for menu-less paths (keyboard). Returns a fresh list; callers must
    treat ``[]`` as "nothing to do" rather than substituting a default.
    """
    card: Path | None = None
    if card_path is not None:
        card = _as_path(card_path)
        if card is None:
            # Unusable card context: act on the raw value alone rather than
            # falling back to the selection (fail-soft, never raises).
            return [card_path]
    try:
        selection = selected_paths(owner)
    except Exception:
        selection = []
    if card is not None:
        if selection and card not in selection:
            return [card]
        if selection:
            return list(selection)
        return [card]
    if selection:
        return list(selection)
    focused = _focused_path(owner)
    if focused is not None:
        return [focused]
    first = _first_item_path(owner)
    if first is not None:
        return [first]
    return []


def apply_to_targets(owner, fn, *, card_path=None) -> int:
    """Resolve once, apply *fn* per target, isolate per-item failures.

    Returns how many targets *fn* was applied to successfully. A non-callable
    *fn* or an empty scope is a no-op (0), never an exception.
    """
    if not callable(fn):
        return 0
    applied = 0
    try:
        targets = resolve_targets(owner, card_path=card_path)
    except Exception:
        return 0
    for path in targets:
        try:
            fn(path)
            applied += 1
        except Exception:
            continue
    return applied


__all__ = [
    "apply_to_targets",
    "resolve_targets",
    "selected_paths",
]
