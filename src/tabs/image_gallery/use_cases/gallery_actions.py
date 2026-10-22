"""Group / carry / find-similar / reset-metrics actions — context in, nothing resolved.

Every function here takes an ``ActionContext`` (``use_cases.action_context``)
and acts on its ``targets``. None of them reads the selection, the focused card
or the first visible item: an empty scope is a named :class:`Refusal`, so mass
processing can never "go around" a point action's input.

WHY a separate module: the per-card menu handlers in
``ui/card/context_actions.py`` take ``(owner, card_path)`` and resolve their own
scope — fine as legacy adapters for drag/drop and series-header call sites, but
the action SURFACE (menu, keyboard, registry) must receive the already-resolved
context. This module is that surface for the non-analyzer actions.

Behavior is unchanged from the handlers it replaces; only the scope source
moved out. ``reset_metrics`` no longer widens an empty scope to the whole pool
(the old ``paths=[] -> paths=None`` path): an empty context is refused.
"""

from __future__ import annotations

from tabs.image_gallery.use_cases.action_context import (
    REFUSAL_EMPTY_SCOPE,
    REFUSAL_NO_HANDLER,
    REFUSAL_NO_ITEMS,
    ActionContext,
    Refusal,
)


def _guard(ctx: ActionContext) -> Refusal | None:
    if not isinstance(ctx, ActionContext):
        raise TypeError("gallery actions require an ActionContext")
    if ctx.is_empty:
        return Refusal(REFUSAL_EMPTY_SCOPE, (), "no targets were resolved")
    return None


def _move_controller(owner):
    """The object owning ``move_paths_to_series`` (controller or triage owner).

    Same duck-typed probe the legacy menu handlers use; it resolves a HANDLER,
    never a scope.
    """
    if callable(getattr(owner, "move_paths_to_series", None)):
        return owner
    for attr in ("_owner_for_triage", "widget", "_widget"):
        try:
            cand = getattr(owner, attr, None)
            cand = cand() if callable(cand) and attr == "_owner_for_triage" else cand
        except Exception:
            cand = None
        if cand is not None and callable(getattr(cand, "move_paths_to_series", None)):
            return cand
    return None


def group(owner, ctx: ActionContext):
    """Pin ``ctx.targets`` into a brand-new manual series (needs ≥2)."""
    refusal = _guard(ctx)
    if refusal is not None:
        return refusal
    if len(ctx.targets) < 2:
        return Refusal(
            REFUSAL_NO_ITEMS, ctx.targets, "grouping one card is not a group action"
        )
    ctrl = _move_controller(owner)
    if ctrl is None or not callable(getattr(ctrl, "group_paths_as_new_series", None)):
        return Refusal(REFUSAL_NO_HANDLER, ctx.targets, "no series controller")
    new_id = None
    try:
        new_id = ctrl.group_paths_as_new_series(list(ctx.targets))
    except Exception:
        return Refusal(REFUSAL_NO_HANDLER, ctx.targets, "group dispatch failed")
    if new_id is None:
        return Refusal(REFUSAL_NO_ITEMS, ctx.targets, "no target is in the pool")
    return None


def ungroup(owner, ctx: ActionContext):
    """Move ``ctx.targets`` out of their series into the UNGROUPED tail."""
    refusal = _guard(ctx)
    if refusal is not None:
        return refusal
    ctrl = _move_controller(owner)
    if ctrl is None:
        return Refusal(REFUSAL_NO_HANDLER, ctx.targets, "no series controller")
    try:
        moved = int(ctrl.move_paths_to_series(list(ctx.targets), None))
    except Exception:
        return Refusal(REFUSAL_NO_HANDLER, ctx.targets, "ungroup dispatch failed")
    if moved <= 0:
        return Refusal(REFUSAL_NO_ITEMS, ctx.targets, "no target was grouped")
    return None


def find_similar(owner, ctx: ActionContext, *, threshold: float = 0.15):
    """Find-similar stub over ``ctx.targets`` (semantic search is still pending).

    Kept as the action's honest result: the scope is the context's, never a
    second selection read.
    """
    refusal = _guard(ctx)
    if refusal is not None:
        return refusal
    import logging

    logging.getLogger("ImproveImgSLI").debug(
        "find_similar_selected: stub — %d target(s), threshold=%s (not implemented)",
        len(ctx.targets),
        threshold,
    )
    return Refusal(
        REFUSAL_NO_HANDLER, ctx.targets, "semantic search is not implemented"
    )


def carry(owner, ctx: ActionContext, *, pixmap=None):
    """Carry ``ctx.targets`` through the ImageCarryService (no dispatch fallback)."""
    refusal = _guard(ctx)
    if refusal is not None:
        return refusal
    from shared.image_extensions import is_loadable_image_path

    paths = [p for p in ctx.targets if is_loadable_image_path(p)]
    if not paths:
        return Refusal(REFUSAL_NO_ITEMS, ctx.targets, "no target is a loadable image")
    from tabs.image_gallery.use_cases import carry as _carry

    dispatched = _carry._dispatch_via_image_carry(paths, pixmap=pixmap)
    if not dispatched:
        return Refusal(REFUSAL_NO_HANDLER, ctx.targets, "no ImageCarryService available")
    return None


def reset_metrics(owner, ctx: ActionContext):
    """Clear + recompute the measured caches for ``ctx.targets``.

    An empty context is REFUSED — the old call site widened it to ``paths=None``
    (whole pool), i.e. a mass operation the user never asked for.
    """
    refusal = _guard(ctx)
    if refusal is not None:
        return refusal
    from tabs.image_gallery.use_cases import cache_reset as _cache_reset

    try:
        # Owner decision 2026-10-22: a reset zeroes the WHOLE pool — the scope
        # of the menu (one card, a selection) made the rest of the grid look
        # untouched, which read as "the reset does nothing".
        return _cache_reset.reset_metrics_caches(owner, paths=None)
    except Exception:
        return Refusal(REFUSAL_NO_HANDLER, ctx.targets, "metrics reset failed")


def menu_action_handlers(
    *,
    owner,
    ctx: ActionContext | None,
    on_carry=None,
    on_analyze=None,
    on_find_similar=None,
) -> dict:
    """The card-menu's action callables over ONE resolved context.

    The popup builds the context and only RENDERS the menu; the bodies live
    here so no caller can re-derive scope or backend inside a closure. A
    provided callback (post-#434 contract) still wins and receives the resolved
    ``targets``.
    """
    import logging

    from tabs.image_gallery.use_cases import ai_analyze

    log = logging.getLogger("ImproveImgSLI")
    targets = list(ctx.targets) if ctx is not None else ()

    def _refused(what: str, refusal) -> None:
        if refusal is not None:
            log.debug("%s refused: %s (%s)", what, refusal.reason, refusal.detail)

    def _analyze() -> None:
        try:
            if callable(on_analyze):
                on_analyze(list(targets))
                return
            if ctx is None:
                return
            run = getattr(owner, "analyze", None)
            _refused(
                "analyze",
                run(ctx) if callable(run) else ai_analyze.analyze(owner, ctx),
            )
        except Exception:
            pass

    def _carry() -> None:
        try:
            if callable(on_carry):
                on_carry(list(targets))
                return
            if ctx is not None:
                _refused("carry", carry(owner, ctx))
        except Exception:
            pass

    def _find_similar() -> None:
        try:
            if callable(on_find_similar):
                on_find_similar(list(targets))
                return
            if ctx is not None:
                _refused("find_similar", find_similar(owner, ctx))
        except Exception:
            pass

    def _reset_metrics() -> None:
        if ctx is None:
            return
        try:
            _refused("reset metrics", reset_metrics(owner, ctx))
        except Exception:
            pass

    def _group() -> None:
        if ctx is None:
            return
        try:
            _refused("group", group(owner, ctx))
        except Exception:
            pass

    def _ungroup() -> None:
        if ctx is None:
            return
        try:
            _refused("ungroup", ungroup(owner, ctx))
        except Exception:
            pass

    return {
        "analyze": _analyze,
        "carry": _carry,
        "find_similar": _find_similar,
        "reset_metrics": _reset_metrics,
        "group": _group,
        "ungroup": _ungroup,
    }


__all__ = [
    "carry",
    "find_similar",
    "group",
    "menu_action_handlers",
    "reset_metrics",
    "ungroup",
]
