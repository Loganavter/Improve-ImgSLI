# Audit-Meta: pattern=single-resolver reason="one scope machine: the policy table (one row per action id), the scope kinds and the resolver must agree — the five independent resolvers this module replaced are exactly what a split re-creates; the table is scanned by a contract test and every caller reads Scope from here."
"""Target resolution for gallery actions — the ONE scope mechanism.

Every gallery action (Analyze, Find similar, Reset metrics cache, Make best,
Reject, Remove, Group/Ungroup, carry, keyboard actions, Quick Look buttons,
stats-strip passes, domain switch) needs the same answer to one question:
*which cards does this apply to?* Before this module each call site answered it
itself, and five independent answers existed at once:

* ``selected`` — the card menu, keyboard, drag, Ask AI;
* ``selected[0]`` — the ``B`` key and the ``Enter`` fallback;
* one card — Quick Look reject/delete/source/compare and "Make source";
* ``visible`` + a silent cap — the domain switch and the folder settle;
* ``pool``/``series`` — the stats strip, series headers, Run triage, Ctrl+A.

They disagreed in both directions, which is the owner report of 2026-10-27:
*"выбрал 2 карточки — обработалось 100, и наоборот"*. Two selected cards lost
their numbers to a pool-wide "reset"; ``Ctrl+A`` selected every card of the
tab while the filter showed two; a domain switch analyzed ``visible∩12`` no
matter what was selected.

THE table (:data:`ACTION_SCOPE_POLICY`) is the single declaration of what each
action means; :func:`resolve_scope` is the single implementation. Nothing else
decides.

Scope kinds
-----------

selection
    The selection, in ``selected_order`` order, and nothing else. An empty
    answer is a refusal — never a card the user did not pick.
selection_or_card
    File-manager rule: the whole selection when the invoked card is part of
    it, otherwise just that card (right-click on an unselected card).
single
    selection_or_card restricted to exactly one target; anything else is
    an ambiguous_scope refusal. This is how "Make source" answers the same
    way in the card menu and in the registry (rule 8).
card
    Exactly the invoked card (Quick Look: one card is on screen).
focus
    The card that actually holds keyboard focus — an EXPLICIT input, never a
    fallback.
visible
    The cards in the viewport, intersected with the active filter. NO
    fail-open to the pool: an unlaid-out grid or an empty viewport is a
    refusal, because "everything" is exactly the answer the owner complained
    about.
selection_else_visible
    Rule 7 (domain switch / folder settle): the selection when it is
    non-empty, otherwise ``visible`` bounded by the per-action cap. The cap is
    never silent — ``Scope.reason`` names it and how much it dropped.
series
    Every member of the series the invoked card belongs to (series headers,
    series-wide actions).
pool
    Every card of the tab, in pool order (stats strip, Run triage).
parked
    The cards a judge-run call ceiling parked (the "continue" affordance).

Precedence inside selection_or_card / single:

    a) ``card_path`` given AND selection non-empty AND does not contain it
       -> ``[card_path]``          (right-clicking an unselected card acts on
                                    that card only — file-manager rule)
    b) selection non-empty        -> the selection, in ``selected_order`` order
    c) ``card_path`` given        -> ``[card_path]``
    d) ``focused=True``           -> the card holding keyboard focus, if any
    e) otherwise                  -> ``[]`` (a refusal)

WHY: a context menu opened on a card carries that card as ``card_path``; if the
card is part of the selection, the action is a *selection* action (b) — that is
the bug fix (all members, not one). If it is not part of the selection, the
user pointed at exactly one card (a) / (c). With no card context the selection
wins (b). Focus is NEVER inferred: the keyboard entry passes ``focused=True``
explicitly, everything else stops at (e). An empty answer is a valid result
callers must honour — there is no "first card by accident" fallback any more.

The selection read (``selected_paths``) is single-sourced here:

- when the owner exposes a gallery store slot, the slot selection is
  authoritative (even when empty — a cleared selection must not resurrect a
  stale local mirror);
- otherwise ``owner.state.selected_paths`` with ``state.selected_order``
  applied for a stable dispatch order (missing entries appended sorted);
- always deduped, always ``Path``, never raises.

Rule 1 (one writer) and rule 2 (one reader) are structural: writes go through
``use_cases.gallery_slot.set_selection`` and reads through
``action_scope.selected_paths`` — enforced by
``tests/contracts/test_gallery_action_context.py``.

No Qt import at module level, no app boot needed (unit tests use a
SimpleNamespace owner). The focused-card fallback imports ``QApplication``
lazily and degrades to nothing when Qt is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

PathList = list[Path]

# -- scope kinds -------------------------------------------------------------

SCOPE_SELECTION = "selection"
SCOPE_SELECTION_OR_CARD = "selection_or_card"
SCOPE_CARD = "card"
SCOPE_FOCUS = "focus"
SCOPE_VISIBLE = "visible"
SCOPE_SERIES = "series"
SCOPE_POOL = "pool"
SCOPE_PARKED = "parked"
#: Rule 7's kind: the selection when non-empty, else the capped viewport.
SCOPE_SELECTION_ELSE_VISIBLE = "selection_else_visible"
#: Rule 8's kind: selection_or_card narrowed to exactly one target.
SCOPE_SINGLE = "single"

SCOPES: tuple[str, ...] = (
    SCOPE_SELECTION,
    SCOPE_SELECTION_OR_CARD,
    SCOPE_CARD,
    SCOPE_FOCUS,
    SCOPE_VISIBLE,
    SCOPE_SERIES,
    SCOPE_POOL,
    SCOPE_PARKED,
    SCOPE_SELECTION_ELSE_VISIBLE,
    SCOPE_SINGLE,
)

# -- named refusals (the shared vocabulary with action_context) ---------------

REFUSAL_EMPTY_SCOPE = "empty_scope"
REFUSAL_AMBIGUOUS_SCOPE = "ambiguous_scope"
REFUSAL_UNKNOWN_ACTION = "unknown_action"
REFUSAL_NO_VIEWPORT = "no_viewport"
REFUSAL_NOT_LAID_OUT = "not_laid_out"
REFUSAL_NO_ITEMS = "no_items"
REFUSAL_NO_SERIES = "no_series"
REFUSAL_NO_PARKED = "no_parked"

#: The default lazy-AI bound for selection_else_visible (mirrors
#: ``GalleryController._AI_VISIBLE_CAP``; the owner's value wins when present).
DEFAULT_VISIBLE_CAP = 12

#: Actions whose visible branch is bounded (rule 7). Only the domain switch and
#: the folder settle analyze in the background; a user-invoked Ctrl+A is not
#: capped (it is an explicit selection).
CAPPED_VISIBLE_ACTIONS = frozenset(
    {"gallery.domain.switch", "gallery.settle.auto"}
)

# -- THE policy table: action id -> scope kind --------------------------------

ACTION_SCOPE_POLICY: dict[str, str] = {
    # Card context menu. Canonical ids (``gallery.card.*``) come first; the
    # menu's historical ids are the same actions under the names its event
    # handler dispatches.
    "gallery.card.analyze": SCOPE_SELECTION_OR_CARD,
    "gallery.card.find_similar": SCOPE_SELECTION_OR_CARD,
    "gallery.card.ask_ai": SCOPE_SELECTION_OR_CARD,
    "gallery.card.make_best": SCOPE_SELECTION_OR_CARD,
    "gallery.card.reject": SCOPE_SELECTION_OR_CARD,
    "gallery.card.remove": SCOPE_SELECTION_OR_CARD,
    "gallery.card.group": SCOPE_SELECTION_OR_CARD,
    "gallery.card.ungroup": SCOPE_SELECTION_OR_CARD,
    "gallery.card.reset_metrics": SCOPE_SELECTION_OR_CARD,
    # Rule 8: one answer in the menu AND the registry — exactly one card, or a
    # named refusal (a multi-selection cannot name "the" source image).
    "gallery.card.set_source": SCOPE_SINGLE,
    "gallery.selection.analyze": SCOPE_SELECTION_OR_CARD,
    "gallery.selection.find_similar": SCOPE_SELECTION_OR_CARD,
    "gallery.selection.ask_ai": SCOPE_SELECTION_OR_CARD,
    "gallery.ask_ai": SCOPE_CARD,
    "gallery.make_best": SCOPE_SELECTION_OR_CARD,
    "gallery.reject": SCOPE_SELECTION_OR_CARD,
    "gallery.remove": SCOPE_SELECTION_OR_CARD,
    "gallery.group": SCOPE_SELECTION_OR_CARD,
    "gallery.ungroup": SCOPE_SELECTION_OR_CARD,
    "gallery.reset_metrics": SCOPE_SELECTION_OR_CARD,
    "gallery.set_as_source": SCOPE_SINGLE,
    # Keyboard. Rule 10: ``B`` applies to the whole selection (an empty
    # selection may use the explicitly focused card, never a first item).
    "gallery.key.delete": SCOPE_SELECTION,
    "gallery.key.make_best": SCOPE_SELECTION,
    "gallery.key.compare": SCOPE_SELECTION,
    # Quick Look: one card is on screen. Never rewrites the selection (rule 9).
    "gallery.quick_look.reject": SCOPE_CARD,
    "gallery.quick_look.delete": SCOPE_CARD,
    "gallery.quick_look.set_source": SCOPE_CARD,
    "gallery.quick_look.compare": SCOPE_CARD,
    # Stats strip — pool-wide BY DESIGN (the labels say so).
    "gallery.stats.keep_best": SCOPE_POOL,
    "gallery.stats.show_all": SCOPE_POOL,
    "gallery.stats.clean_rejected": SCOPE_POOL,
    "gallery.stats.compare_finalists": SCOPE_POOL,
    # Series header — the series the header stands for.
    "gallery.series.ask_ai": SCOPE_SERIES,
    "gallery.series.rename": SCOPE_SERIES,
    "gallery.series.delete": SCOPE_SERIES,
    "gallery.series.reset": SCOPE_SERIES,
    "gallery.series.recluster": SCOPE_SERIES,
    # Find Action (registry) ids.
    "gallery.keep-best-of-series": SCOPE_POOL,
    "gallery.clean-rejected": SCOPE_POOL,
    "gallery.run-triage": SCOPE_POOL,
    "gallery.set-as-source": SCOPE_SINGLE,
    "gallery.reset-metrics": SCOPE_SELECTION_OR_CARD,
    "gallery.continue-judge": SCOPE_PARKED,
    # View: the domain switch / settle (rule 7).
    "gallery.domain.switch": SCOPE_SELECTION_ELSE_VISIBLE,
    "gallery.settle.auto": SCOPE_SELECTION_ELSE_VISIBLE,
    # Ctrl+A: what is VISIBLE, filter included (rule 6).
    "select_all": SCOPE_VISIBLE,
    # The re-analyze offer's three scopes (the flyout asks WHICH set to redo).
    "gallery.reanalyze.visible": SCOPE_VISIBLE,
    "gallery.reanalyze.selection": SCOPE_SELECTION,
    "gallery.reanalyze.all": SCOPE_POOL,
}


@dataclass(frozen=True)
class Scope:
    """One resolved scope: which cards, why, and a named refusal.

    ``targets`` is a tuple of ``Path`` (empty when refused). ``reason`` is the
    ONE tracer line — ``action=… kind=… n=… card=…`` plus the discriminator
    that decided it (``source=selection``, ``cap=12 available=40``,
    ``refused=…``) — logged by :func:`resolve_scope` and readable by tests.
    ``refused`` is a stable machine token (``None`` when the scope is valid).
    """

    kind: str
    targets: tuple[Path, ...]
    reason: str = ""
    refused: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.targets


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


# -- pool / series / visible reads -------------------------------------------


def _items(owner) -> list:
    """The owner's pool items (never raises)."""
    try:
        return list(getattr(getattr(owner, "state", None), "items", None) or ())
    except Exception:
        return []


def _pool_paths(owner) -> PathList:
    """Every card of the tab, in pool order."""
    out: PathList = []
    for item in _items(owner):
        p = _as_path(getattr(item, "path", None))
        if p is not None:
            out.append(p)
    return _dedupe(out)


def _grid(owner):
    """The object exposing ``visible_paths*`` (grid view), or None.

    Covers the flat shapes (``owner._grid_view`` / ``owner.grid_view``) and the
    production nesting (``owner.widget._grid_view``), plus a widget-shaped owner
    that carries the method itself.
    """
    candidates = []
    for attr in ("_grid_view", "grid_view"):
        try:
            candidates.append(getattr(owner, attr, None))
        except Exception:
            pass
    for attr in ("widget", "_widget", "_gallery_widget"):
        try:
            holder = getattr(owner, attr, None)
        except Exception:
            holder = None
        if holder is None:
            continue
        for inner in ("_grid_view", "grid_view"):
            try:
                candidates.append(getattr(holder, inner, None))
            except Exception:
                pass
        candidates.append(holder)
    candidates.append(owner)
    for cand in candidates:
        if cand is None:
            continue
        if callable(getattr(cand, "visible_paths_strict", None)) or callable(
            getattr(cand, "visible_paths", None)
        ):
            return cand
    return None


def _filter_allowed(owner) -> set[str] | None:
    """Paths the active filter lets through, or None when there is no filter.

    Uses the SAME fast pass the grid paints with (``match_fast_items``), so the
    scope cannot disagree with what the user sees. A filter that cannot be
    evaluated answers an EMPTY set — never "everything" (a silent widening to
    the pool is the defect this module removes).
    """
    try:
        text = str(getattr(getattr(owner, "state", None), "filter_text", "") or "")
    except Exception:
        text = ""
    if not text.strip():
        return None
    try:
        from tabs.image_gallery.use_cases import filtering

        allowed = filtering.filter_allowed_paths(_items(owner), text)
    except Exception:
        logger.debug("scope: filter evaluation failed — refusing instead of widening", exc_info=True)
        return set()
    if allowed is None:
        return None
    return {str(p) for p in allowed}


def _visible_paths(owner) -> tuple[PathList | None, str | None]:
    """``(paths, refusal)`` — the viewport ∩ filter, or a named refusal.

    ``visible_paths_strict`` (``ui/grid_view``) distinguishes "not laid out"
    from "nothing visible"; the legacy ``visible_paths`` fails open to the whole
    pool for the thumbnail scheduler, which is exactly why a scope may not use
    it without the strict probe.
    """
    grid = _grid(owner)
    if grid is None:
        return None, REFUSAL_NO_VIEWPORT
    strict = getattr(grid, "visible_paths_strict", None)
    if callable(strict):
        try:
            paths = strict()
        except Exception:
            return None, REFUSAL_NO_VIEWPORT
        if paths is None:
            return None, REFUSAL_NOT_LAID_OUT
        paths = list(paths)
    else:
        visible = getattr(grid, "visible_paths", None)
        if not callable(visible):
            return None, REFUSAL_NO_VIEWPORT
        try:
            paths = list(visible() or ())
        except Exception:
            return None, REFUSAL_NO_VIEWPORT
        if not paths:
            # No strict probe: an empty answer cannot be told apart from "not
            # laid out", and widening to the pool is not allowed either.
            return None, REFUSAL_EMPTY_SCOPE
    allowed = _filter_allowed(owner)
    if allowed is not None:
        paths = [p for p in paths if str(p) in allowed]
    paths = _dedupe(paths)
    if not paths:
        return None, REFUSAL_EMPTY_SCOPE
    return paths, None


def _visible_cap(owner) -> int:
    try:
        cap = int(getattr(owner, "_AI_VISIBLE_CAP", 0) or 0)
    except Exception:
        cap = 0
    return cap if cap > 0 else DEFAULT_VISIBLE_CAP


def _series_members(owner, anchor: Path | None) -> PathList:
    """Members of the series holding *anchor* (pool/grid mirrors, deduped)."""
    if anchor is None:
        return []
    want = str(anchor)
    candidates: list = []
    for holder in (getattr(owner, "state", None), getattr(owner, "_grid_view", None)):
        if holder is None:
            continue
        try:
            entries = getattr(holder, "series", None) or getattr(holder, "_series", None)
        except Exception:
            entries = None
        if entries:
            candidates.extend(list(entries))
    for entry in candidates:
        try:
            members = getattr(entry, "members", None)
            if members is None and isinstance(entry, (list, tuple)):
                members = entry
            if not members:
                continue
            paths = _dedupe(getattr(m, "path", m) for m in members)
            if any(str(p) == want for p in paths):
                return paths
        except Exception:
            continue
    return []


def _parked_paths(owner) -> PathList:
    """Cards a judge-run call ceiling parked (deduped, pool order not needed)."""
    for attr in ("judge_run_parked_paths",):
        try:
            value = getattr(owner, attr, None)
            value = value() if callable(value) else value
        except Exception:
            value = None
        if value:
            return _dedupe(value)
    try:
        run = getattr(owner, "_judge_run", None)
        skipped = getattr(run, "skipped", None) if run is not None else None
    except Exception:
        skipped = None
    return _dedupe(skipped or ())


# -- the resolver -------------------------------------------------------------


def _make_scope(
    action_id: str,
    kind: str,
    targets=(),
    *,
    card: Path | None = None,
    extra: str = "",
    refused: str | None = None,
) -> Scope:
    """Build a Scope and emit its ONE tracer line (``scope action=… kind=…``)."""
    paths = tuple(_dedupe(targets))
    reason = (
        f"action={action_id} kind={kind} n={len(paths)} "
        f"card={card if card is not None else '-'}"
    )
    if extra:
        reason = f"{reason} {extra}"
    if refused:
        reason = f"{reason} refused={refused}"
    logger.debug("scope %s", reason)
    return Scope(kind=kind, targets=paths, reason=reason, refused=refused)


def _selection_or_card(selection: PathList, card: Path | None) -> PathList:
    """The file-manager precedence (a/b/c in the module docstring)."""
    if card is not None:
        if selection and card not in selection:
            return [card]
        if selection:
            return list(selection)
        return [card]
    return list(selection)


def resolve_scope(
    owner, action_id: str, *, card_path=None, focused: bool = False
) -> Scope:
    """Resolve *action_id* for *owner* — THE one scope decision.

    The kind comes from :data:`ACTION_SCOPE_POLICY`; an id with no row is a
    named unknown_action refusal (and a contract-test failure), never a
    guess. ``card_path`` is the card the action was invoked on (context menu /
    Quick Look), ``focused=True`` is the explicit keyboard input. Never raises.
    """
    card = _as_path(card_path) if card_path is not None else None
    kind = ACTION_SCOPE_POLICY.get(action_id)
    if kind is None:
        return _make_scope(
            action_id, "", (), card=card, refused=REFUSAL_UNKNOWN_ACTION
        )
    try:
        selection = selected_paths(owner)
    except Exception:
        selection = []

    if kind == SCOPE_SELECTION:
        if selection:
            return _make_scope(action_id, kind, selection, card=card, extra="source=selection")
        if focused:
            fp = _focused_path(owner)
            if fp is not None:
                return _make_scope(action_id, kind, [fp], card=card, extra="source=focus")
        return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_EMPTY_SCOPE)

    if kind == SCOPE_SELECTION_OR_CARD:
        targets = _selection_or_card(selection, card)
        if not targets and focused:
            fp = _focused_path(owner)
            if fp is not None:
                return _make_scope(action_id, kind, [fp], card=card, extra="source=focus")
        if not targets:
            return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_EMPTY_SCOPE)
        extra = (
            "source=card"
            if card is not None and card not in selection
            else "source=selection"
        )
        return _make_scope(action_id, kind, targets, card=card, extra=extra)

    if kind == SCOPE_SINGLE:
        targets = _selection_or_card(selection, card)
        if not targets and focused:
            fp = _focused_path(owner)
            if fp is not None:
                targets = [fp]
        if not targets:
            return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_EMPTY_SCOPE)
        if len(targets) != 1:
            return _make_scope(
                action_id,
                kind,
                targets,
                card=card,
                extra=f"available={len(targets)}",
                refused=REFUSAL_AMBIGUOUS_SCOPE,
            )
        return _make_scope(action_id, kind, targets, card=card, extra="source=single")

    if kind == SCOPE_CARD:
        if card is None and focused:
            card = _focused_path(owner)
        if card is None:
            return _make_scope(action_id, kind, (), card=None, refused=REFUSAL_EMPTY_SCOPE)
        return _make_scope(action_id, kind, [card], card=card, extra="source=card")

    if kind == SCOPE_FOCUS:
        fp = _focused_path(owner)
        if fp is None:
            return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_EMPTY_SCOPE)
        return _make_scope(action_id, kind, [fp], card=card, extra="source=focus")

    if kind == SCOPE_SELECTION_ELSE_VISIBLE:
        if selection:
            return _make_scope(
                action_id, kind, selection, card=card, extra="source=selection"
            )
        paths, refusal = _visible_paths(owner)
        if refusal is not None:
            return _make_scope(action_id, kind, (), card=card, refused=refusal)
        available = len(paths)
        cap = _visible_cap(owner) if action_id in CAPPED_VISIBLE_ACTIONS else 0
        if cap and available > cap:
            return _make_scope(
                action_id,
                kind,
                paths[:cap],
                card=card,
                extra=f"source=visible cap={cap} available={available}",
            )
        return _make_scope(
            action_id,
            kind,
            paths,
            card=card,
            extra=f"source=visible available={available}",
        )

    if kind == SCOPE_VISIBLE:
        paths, refusal = _visible_paths(owner)
        if refusal is not None:
            return _make_scope(action_id, kind, (), card=card, refused=refusal)
        return _make_scope(
            action_id, kind, paths, card=card, extra=f"source=visible available={len(paths)}"
        )

    if kind == SCOPE_POOL:
        paths = _pool_paths(owner)
        if not paths:
            return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_NO_ITEMS)
        return _make_scope(action_id, kind, paths, card=card, extra="source=pool")

    if kind == SCOPE_SERIES:
        anchor = card
        if anchor is None and selection:
            anchor = selection[0]
        members = _series_members(owner, anchor)
        if not members:
            return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_NO_SERIES)
        return _make_scope(action_id, kind, members, card=card, extra="source=series")

    if kind == SCOPE_PARKED:
        paths = _parked_paths(owner)
        if not paths:
            return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_NO_PARKED)
        return _make_scope(action_id, kind, paths, card=card, extra="source=parked")

    return _make_scope(action_id, kind, (), card=card, refused=REFUSAL_UNKNOWN_ACTION)


def pool_conflict(owner, action_id: str = "gallery.run-triage") -> Scope | None:
    """A POOL action that would silently ignore the selection — a refusal.

    Some passes (Run triage re-reads the folder) are pool-wide BY DESIGN. When a
    selection is live, running them anyway is the "two cards selected, a hundred
    processed" defect read from the other end. Returns a ``Scope`` carrying
    ``refused=ambiguous_scope`` (targets = the selection that would be ignored,
    ``reason`` naming both sizes) or ``None`` when no selection is live.
    """
    try:
        selection = selected_paths(owner)
    except Exception:
        selection = []
    if not selection:
        return None
    pool = resolve_scope(owner, action_id)
    return _make_scope(
        action_id,
        pool.kind,
        selection,
        extra=f"source=pool unavailable selection={len(selection)} pool={len(pool.targets)}",
        refused=REFUSAL_AMBIGUOUS_SCOPE,
    )


def resolve_targets(owner, *, card_path=None, focused: bool = False) -> PathList:
    """Cards an action applies to — the pre-policy precedence (legacy adapter).

    Kept for call sites that have no action id (drag payload, series-header
    adapters, the deprecated ``_ctx_*`` helpers); it IS the
    selection_or_card rule and delegates to the ONE resolver so the
    precedence cannot drift. New code passes an action id to
    :func:`resolve_scope` instead.
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
    if focused:
        focused_path = _focused_path(owner)
        if focused_path is not None:
            return [focused_path]
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
    "ACTION_SCOPE_POLICY",
    "apply_to_targets",
    "CAPPED_VISIBLE_ACTIONS",
    "DEFAULT_VISIBLE_CAP",
    "REFUSAL_AMBIGUOUS_SCOPE",
    "REFUSAL_EMPTY_SCOPE",
    "REFUSAL_NO_ITEMS",
    "REFUSAL_NO_PARKED",
    "REFUSAL_NO_SERIES",
    "REFUSAL_NO_VIEWPORT",
    "REFUSAL_NOT_LAID_OUT",
    "REFUSAL_UNKNOWN_ACTION",
    "SCOPES",
    "SCOPE_CARD",
    "SCOPE_FOCUS",
    "SCOPE_PARKED",
    "SCOPE_POOL",
    "SCOPE_SELECTION",
    "SCOPE_SELECTION_ELSE_VISIBLE",
    "SCOPE_SELECTION_OR_CARD",
    "SCOPE_SERIES",
    "SCOPE_SINGLE",
    "SCOPE_VISIBLE",
    "Scope",
    "resolve_scope",
    "resolve_targets",
    "selected_paths",
]
