"""The gallery's analyze entry points — ONE context, one pipeline.

Extracted from ``ai_analysis`` (same wave, file-size policy): the analyze
surface grew when point and mass processing were unified, so it now lives here
and ``ai_analysis`` imports it back for its callers (``hydrate_*`` / delivery /
``_run_ai_for_visible``). The split is by concern, not by behavior: this module
owns *what runs*, ``ai_analysis`` owns *what the result means*.

Every entry takes an ``ActionContext`` (targets + backend + mode/profile/effort)
and loops ``ctx.targets`` internally — a point action is a one-element context.
``AiSettings`` is read for credentials/transport and the cache identity only;
no code here chooses a backend.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import AnalysisStatus, GalleryItem
from tabs.image_gallery.services.ai_cache import (
    analysis_cache_identity,
    load_cached_analysis,
)
from tabs.image_gallery.services.ai_client import _ai_debug
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_AI,
    REFUSAL_EMPTY_SCOPE,
    REFUSAL_NO_ITEMS,
    REFUSAL_NOT_CONFIGURED,
    ActionContext,
    Refusal,
    point_context,
)
from tabs.image_gallery.use_cases.profile_select import active_profile


def _stamp_profile_consumed(owner) -> None:
    """Freeze the folder generation's profile — ONE call, right before a payload.

    Deferred import: ``controller`` imports this module's callers lazily, so a
    module-level import here would be a cycle (mirrors
    ``ai_analysis._begin_analysis``'s deferred controller import). The rule
    itself lives on the controller (``_mark_profile_consumed``); this forwarder
    exists so the payload-build site names what it is doing.

    Plan-gallery-ai-judgement P2: this is the fact the freeze was always about —
    "a request was built" — not "the analyze entry was reached". A run whose
    every card is a disk-cache HIT builds no payload and must stay unfrozen so
    the paid VLM axis-set answer can still be applied to it.
    """
    from tabs.image_gallery.controller import _stamp_profile_consumed as _stamp

    _stamp(owner)


def _item_for(owner, path: Path):
    """The pool item for *path* (owner ``_find_item``, else a state scan)."""
    finder = getattr(owner, "_find_item", None)
    if callable(finder):
        try:
            item = finder(path)
        except Exception:
            item = None
        if item is not None:
            return item
    try:
        items = list(getattr(getattr(owner, "state", None), "items", None) or ())
    except Exception:
        items = []
    for item in items:
        try:
            if Path(getattr(item, "path")) == Path(path):
                return item
        except Exception:
            continue
    return None


def _items_for(owner, ctx: ActionContext):
    """Context targets → pool items (missing targets are skipped, never faked)."""
    found = []
    for path in ctx.targets:
        item = _item_for(owner, path)
        if item is not None:
            found.append(item)
    return found


def _load_settings(owner):
    """AiSettings for credentials/transport — never for a backend choice."""
    return owner._ai_settings_store.load()  # action-context: credentials-only


def _is_configured(settings) -> bool:
    return bool(
        getattr(settings, "enabled", False)
        and getattr(settings, "api_key", "")
        and getattr(settings, "model", "")
    )


def _mark_not_configured(owner, items) -> None:
    default = "Configure the AI API key in Settings first."
    for item in items:
        try:
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = owner._tr("image_gallery.errors.not_configured", default)
            owner.widget.refresh_card(item)
        except Exception:
            continue


def analysis_identity_for(owner, *, ctx: ActionContext | None = None) -> dict:  # type: ignore[no-untyped-def]
    """The AI disk-cache identity for one call configuration.

    The single seam for every cache touch (analyze / Quick Look hydrate / pool
    rebuild): model + base_url + mode + the active profile's axes + reasoning
    effort. Without them a scorecard cached under another backend is served
    after a Settings switch (queue id
    ``task-gallery-ai-cache-backend-key-2026-10-20``); ``api_key`` is never part
    of it. Never raises (a broken settings store degrades to misses).

    With *ctx* the identity uses THE ACTION's parameters. Without one the caller
    is a display-only pre-read (Quick Look open, pool rebuild) where no action
    exists yet — that path reads the current view configuration, which is a
    read of the same values the next action would carry, not a backend choice.
    """
    try:
        settings = owner._ai_settings_store.load()  # action-context: identity (model/base_url)
    except Exception:
        settings = None
    if ctx is not None:
        mode, profile, effort = ctx.mode, ctx.profile, ctx.effort
    else:
        state = getattr(owner, "state", None)
        try:
            mode = getattr(state, "mode", None) if state is not None else None
        except Exception:
            mode = None
        try:
            profile = active_profile(state) if state is not None else None
        except Exception:
            profile = None
        effort = None
    return analysis_cache_identity(
        settings, mode=mode, profile=profile, reasoning_effort=effort
    )


def analyze(owner, ctx: ActionContext) -> Refusal | None:
    """Analyze every ``ctx.targets`` card on ``ctx.backend``.

    ONE entry for point and mass processing: a point action is a one-element
    context and takes this exact path. Returns a named :class:`Refusal` when
    nothing can run (empty scope / no pool items / AI not configured / no
    algorithms pipeline); otherwise ``None``.
    """
    if not isinstance(ctx, ActionContext):
        raise TypeError("analyze() requires an ActionContext")
    if ctx.is_empty:
        return Refusal(REFUSAL_EMPTY_SCOPE, (), "no targets were resolved")
    if ctx.backend == BACKEND_AI:
        return _analyze_ai(owner, ctx)
    return _analyze_algorithms(owner, ctx)


def _analyze_ai(owner, ctx: ActionContext) -> Refusal | None:
    settings = _load_settings(owner)
    if not _is_configured(settings):
        # A NAMED per-target error — never a switch to algorithms.
        items = _items_for(owner, ctx)
        _mark_not_configured(owner, items)
        return Refusal(
            REFUSAL_NOT_CONFIGURED,
            ctx.targets,
            "the AI backend is selected but its settings are not configured",
        )
    items = _items_for(owner, ctx)
    if not items:
        return Refusal(REFUSAL_NO_ITEMS, ctx.targets, "no resolved target is in the pool")
    identity = analysis_identity_for(owner, ctx=ctx)
    for item in items:
        cached = load_cached_analysis(item.path, item.mtime_ns, identity)
        if cached is not None:
            try:
                _ai_debug("analyze cache HIT path=%s (no API call)", item.path)
            except Exception:
                pass
            item.analysis = cached
            item.analysis_status = AnalysisStatus.DONE
            item.analysis_error = None
            owner.widget.refresh_card(item)
            continue
        try:
            # Per-target isolation: one failing card never aborts the context
            # (same contract the old per-path loop in the menu upheld).
            #
            # P2 (plan-gallery-ai-judgement J3): THIS is where a request payload
            # is built — a MISS, under this generation's profile. Freeze the
            # profile here, never on the analyze entry: a HIT above builds no
            # request, so a cache-only run must not freeze anything.
            _stamp_profile_consumed(owner)
            owner._begin_analysis(ctx, item)
        except Exception:
            continue
    return None


def _analyze_algorithms(owner, ctx: ActionContext) -> Refusal | None:
    """Re-run the deterministic measured pass for the context targets."""
    items = _items_for(owner, ctx)
    if not items:
        return Refusal(REFUSAL_NO_ITEMS, ctx.targets, "no resolved target is in the pool")
    try:
        source = getattr(getattr(owner, "state", None), "source_path", None)
    except Exception:
        source = None
    start = getattr(owner, "_start_proxy_analysis", None)
    if not callable(start):
        return Refusal(
            REFUSAL_NO_ITEMS, ctx.targets, "owner has no algorithms analysis pipeline"
        )
    start(items, source, ctx.mode)
    return None


def reanalyze(owner, ctx: ActionContext) -> Refusal | None:
    """Force a fresh analysis of ``ctx.targets`` (Re-analyze).

    Same pipeline as :func:`analyze` minus the AI disk-cache short-circuit
    (algorithms re-measures the same way). Never fabricates a scope.
    """
    if not isinstance(ctx, ActionContext):
        raise TypeError("reanalyze() requires an ActionContext")
    if ctx.is_empty:
        return Refusal(REFUSAL_EMPTY_SCOPE, (), "no targets were resolved")
    if ctx.backend != BACKEND_AI:
        return _analyze_algorithms(owner, ctx)
    settings = _load_settings(owner)
    if not _is_configured(settings):
        items = _items_for(owner, ctx)
        _mark_not_configured(owner, items)
        return Refusal(
            REFUSAL_NOT_CONFIGURED,
            ctx.targets,
            "the AI backend is selected but its settings are not configured",
        )
    items = _items_for(owner, ctx)
    if not items:
        return Refusal(REFUSAL_NO_ITEMS, ctx.targets, "no resolved target is in the pool")
    for item in items:
        try:
            # P2: a reanalyze MISSES by definition (no cache read), so this is a
            # payload-build site too — the freeze must be stamped here, not on
            # the entry (plan-gallery-ai-judgement J3).
            _stamp_profile_consumed(owner)
            owner._begin_analysis(ctx, item)
        except Exception:
            continue
    return None


# -- deprecated thin adapters (other call sites / tests) ----------------------
# These keep the old names working. They build an EXPLICIT point context and
# take the same ``analyze``/``reanalyze`` path — they are not a second way to
# process, and they cannot widen the scope.


def analyze_item_by_path(owner, path: Path) -> Refusal | None:
    """Deprecated: use ``analyze(owner, ctx)`` with ``targets=(path,)``."""
    return analyze(owner, point_context(owner, path))


def analyze_item(owner, item: GalleryItem) -> Refusal | None:
    """Deprecated: use ``analyze(owner, ctx)`` with ``targets=(item.path,)``."""
    return analyze(owner, point_context(owner, item.path))


def reanalyze_item_by_path(owner, path: Path) -> Refusal | None:
    """Deprecated: use ``reanalyze(owner, ctx)`` with ``targets=(path,)``."""
    return reanalyze(owner, point_context(owner, path))


def reanalyze_item(owner, item: GalleryItem) -> Refusal | None:
    """Deprecated: use ``reanalyze(owner, ctx)`` with ``targets=(item.path,)``."""
    return reanalyze(owner, point_context(owner, item.path))


