"""AI analyze / judgment-domain + analysis delivery for the Image Gallery (Wave 4).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one analysis delivery + domain + re-analyze-offer concern over the owner; the offer shares the same action context and the same scorecard state as delivery"

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the analysis DELIVERY + domain cluster: cache hydration
(``hydrate_cached_analysis`` / ``_hydrate_ai_cache``), the judgment-domain
authority writer + toolbar switch (``_set_judgment_domain`` /
``activate_judgment_domain``), the bounded visible-item trigger
(``_run_ai_for_visible``) and the worker delivery tail (``_begin_analysis`` /
``_apply_ai_phase`` / ``_on_analysis_ready`` / ``_refresh_open_quick_look`` /
``_on_analysis_error``). The analyze ENTRY points (``analyze`` / ``reanalyze``
and the deprecated point adapters) live in ``use_cases/ai_analyze.py`` and are
re-exported here for their callers (file-size policy, same wave).
The owner keeps ``_tr``, the Jev ranker cluster, ``_apply_fusion_ranks`` and the
shared primitives (``_find_item`` / ``_tracked`` / ``_pool_start`` / folder
generation discipline); thin delegators keep the method names verbatim.

EVERY actionable entry takes an ``ActionContext`` (``use_cases.action_context``):
targets, backend, mode, profile and reasoning effort travel as arguments, so
nothing here re-decides which cards or which backend. In particular
``_begin_analysis`` reads ``AiSettings`` for credentials (api_key / base_url /
model) and nothing else, and an invalid domain is a named ``ValueError`` — never
a silent switch to ``algorithms`` (queue id
``task-gallery-action-context-2026-10-20``).

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.models import (
    JUDGMENT_DOMAINS,
    ActivityPhase,
    AnalysisStatus,
    GalleryItem,
)
from tabs.image_gallery.services.activity import set_activity
from tabs.image_gallery.services.ai_cache import analysis_cache_identity
from tabs.image_gallery.services.ai_client import (
    _ai_debug,
    AiAuthError,
    AiClientError,
    AiNetworkError,
    AiRateLimitError,
    AiResponseError,
    AiTruncatedError,
    analyze_image_sync,
)
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_AI,
    ORIGIN_ACTION,
    ActionContext,
    context_for_paths,
    current_backend,
)
from tabs.image_gallery.use_cases.analysis_batch import begin as _ai_batch_begin
from tabs.image_gallery.use_cases.analysis_batch import end as _ai_batch_end
from tabs.image_gallery.use_cases.analysis_batch import (
    dispatch_terminal_rank as _dispatch_terminal_rank,
)
from tabs.image_gallery.use_cases.ai_analyze import (  # re-exported for callers
    _is_configured,
    _load_settings,
    _mark_not_configured,
    analysis_identity_for,
    analyze,  # noqa: F401 — re-exported for the controller delegators
    analyze_item,  # noqa: F401 — deprecated point adapter
    analyze_item_by_path,  # noqa: F401 — deprecated point adapter
    reanalyze,  # noqa: F401 — re-exported for the controller delegators
    reanalyze_item,  # noqa: F401 — deprecated point adapter
    reanalyze_item_by_path,  # noqa: F401 — deprecated point adapter
)

logger = logging.getLogger("ImproveImgSLI")


_ERROR_KEYS = {
    # AiTruncatedError FIRST — it subclasses AiResponseError, and the mapping
    # loop breaks on the first isinstance match.
    AiTruncatedError: (
        "image_gallery.errors.truncated",
        "The AI answer was cut off at the token limit — raise the reasoning "
        "effort or answer budget in Settings.",
    ),
    AiAuthError: ("image_gallery.errors.auth", "Authentication failed — check your API key."),
    AiRateLimitError: ("image_gallery.errors.rate_limit", "Rate limited — try again later."),
    AiNetworkError: ("image_gallery.errors.network", "Network error while contacting the AI API."),
    AiResponseError: ("image_gallery.errors.parse", "Could not parse the AI response."),
}


# -- AI analyze ---------------------------------------------------------------


def hydrate_cached_analysis(
    owner, item: GalleryItem, *, ctx: ActionContext | None = None
) -> bool:
    """Fill ``item`` from the disk cache only (Quick Look pre-read).

    No worker, no settings check — lets the overlay show a cached
    analysis the moment it opens instead of waiting for an Analyze
    click. Identity-scoped: only a scorecard cached under the CURRENT
    configuration is shown, so another backend's read is never
    resurrected. Refreshes the card when something was hydrated. Never
    raises.
    """
    try:
        from tabs.image_gallery.services.ai_cache import hydrate_item
    except Exception:
        return False
    try:
        if not hydrate_item(item, analysis_identity_for(owner, ctx=ctx)):
            return False
    except Exception:
        return False
    try:
        owner.widget.refresh_card(item)
    except Exception:
        pass
    return True


def _hydrate_ai_cache(owner, items, *, ctx: ActionContext | None = None) -> int:
    """Fill pool items from the AI disk cache on a pool (re)build.

    Closed-tab / re-loaded-folder recovery: the live ``analyze`` path is
    cache-first, but a pool rebuild (session restore, folder open, append) had
    no such pass, so previously analyzed images came back "not analyzed" until
    some other trigger ran — even though the results sat in the disk cache.
    This pass fills them at rebuild so the read is present the moment the pool
    appears; the metrics-pass settle then re-derives only the still-missing
    scorecards (AI domain only, ``_run_ai_on_settle``). Cache-only: no worker,
    no settings check, no API call. Identity-scoped: the pass builds ONE
    identity for the current AI configuration and hydrates only entries cached
    under it, so a backend switch cannot resurrect the previous backend's reads
    on restore. Never raises; returns how many items were filled.
    """
    try:
        from tabs.image_gallery.services.ai_cache import hydrate_item
    except Exception:
        return 0
    identity = analysis_identity_for(owner, ctx=ctx)
    filled = 0
    for it in list(items or []):
        try:
            if getattr(it, "analysis", None) is not None:
                continue
            if hydrate_item(it, identity):
                filled += 1
        except Exception:
            continue
    return filled


def _require_domain(domain: str) -> str:
    """Normalize a judgment domain or refuse with a named error.

    THERE IS NO COERCION. The pre-fix writers mapped anything unknown (a typo,
    an empty toolbar value, a failed read) to ``"algorithms"`` — a silent
    backend switch after the user picked AI.
    """
    dom = str(domain or "").strip().lower()
    if dom not in tuple(JUDGMENT_DOMAINS):
        raise ValueError(
            f"invalid judgment domain {domain!r}; expected one of "
            f"{tuple(JUDGMENT_DOMAINS)!r}"
        )
    return dom


def _set_judgment_domain(owner, domain: str) -> str:
    """The ONLY writer of the judgment domain (Algorithms vs AI).

    ``owner._judgment_domain`` is the single authority and survives the
    ``GalleryState`` rebuilds done by open_folder / append / clear_to_empty;
    ``state.judgment_domain``/``state.rank_domain`` are read-only projections
    kept for rendering. Invalid input raises (no coercion); returns the
    normalized value.
    """
    dom = _require_domain(domain)
    owner._judgment_domain = dom
    try:
        setattr(owner.state, "judgment_domain", dom)
        setattr(owner.state, "rank_domain", dom)
    except Exception:
        pass
    return dom


def activate_judgment_domain(owner, domain: str) -> None:
    """Apply the toolbar domain switch (plan-gallery-two-domain-axes).

    An invalid domain raises ``ValueError`` BEFORE anything is changed: a
    failed switch must not leave the domain on algorithms (the pre-fix body
    coerced unknown input to ``algorithms``).

    Switching to ``ai`` is the switch's actual effect: it lazily analyzes
    the **visible** items (cache-first, in-flight skipped, capped). Not
    configured / no key degrades to the existing per-item error on the cards
    — the control always does something visible, never a silent no-op.
    Switching back to ``algorithms`` only flips the report domain; it never
    cancels in-flight work.
    """
    # Single authoritative setter; state/widget mirror it for rendering.
    dom = _set_judgment_domain(owner, _require_domain(domain))

    # An EXPLICIT domain switch re-opens the rank stage: switching back to AI
    # must re-apply the pinned Jev rank (cache-first, no second HTTP) even
    # though the same fingerprint already completed for this folder
    # generation (the Algorithms switch re-derived the ranks to fusion in
    # between). The settled-pass trigger does NOT invalidate, so a second
    # settle over unchanged inputs stays a no-op.
    try:
        gate = getattr(owner, "_stage_gate", None)
        if gate is not None:
            gate.invalidate()
    except Exception:
        logger.debug("domain switch stage-gate invalidate failed", exc_info=True)
    # WHY Jev did / did not run: the domain switch is the only trigger for
    # the AI ranker (algorithms ⇒ no Jev call at all). Same IMGSLI_AI_DEBUG key.
    _ai_debug("judgment domain -> %s (%s)", dom, "Jev on" if dom == "ai" else "Jev off")
    # The open quick-look report/dots are domain-scoped: re-render them for
    # the new domain (VLM read ↔ detectors) without a reopen. (getattr keeps
    # this safe on the fake controllers the domain-switch tests drive.)
    refresh_ql = getattr(owner, "_refresh_open_quick_look", None)
    if callable(refresh_ql):
        refresh_ql()
    # Card dots are domain-scoped too — repaint every card for the new read.
    try:
        items = list(getattr(owner.state, "items", None) or [])
        refresh_cards = getattr(owner.widget, "refresh_cards", None)
        if callable(refresh_cards) and items:
            refresh_cards(items)
        else:
            refresh_card = getattr(owner.widget, "refresh_card", None)
            if callable(refresh_card):
                for it in items:
                    refresh_card(it)
    except Exception:
        logger.debug("domain switch card refresh failed", exc_info=True)
    if dom != "ai":
        # Back to Algorithms: re-derive the deterministic fusion rank (a
        # Jev rank is only in effect while the AI domain owns the rank).
        try:
            owner._apply_fusion_ranks(getattr(owner.state, "series", None))
        except Exception:
            logger.debug("domain switch rank re-derive failed", exc_info=True)
        owner._clear_series_priority()
        return
    owner._run_ai_for_visible()
    # The terminal ranker, guarded by the batch ledger: a switch that started
    # analyses waits for the LAST one instead of ranking a partial matrix
    # (plan-gallery-ai-judgement P3-A). A cache-only switch (nothing in flight)
    # dispatches here and now.
    _dispatch_terminal_rank(owner)
    owner._run_series_priority()


def _run_ai_for_visible(owner) -> None:
    """Analyze the currently-visible, not-yet-analyzed items (bounded)."""
    try:
        vis = getattr(owner.widget, "visible_paths", None)
        paths = vis() if callable(vis) else None
    except Exception:
        paths = None
    try:
        keys = {str(p) for p in (paths or [])}
    except Exception:
        keys = set()
    picked: list = []
    try:
        items = list(getattr(owner.state, "items", None) or [])
    except Exception:
        items = []
    for it in items:
        try:
            if keys and str(it.path) not in keys:
                continue
            status = getattr(it, "analysis_status", None)
            if status in (AnalysisStatus.DONE, AnalysisStatus.PENDING):
                continue
        except Exception:
            continue
        picked.append(it)
    if not keys:
        # Viewport not laid out yet — bound instead of flooding.
        picked = picked[: owner._AI_VISIBLE_CAP]
    picked = picked[: owner._AI_VISIBLE_CAP]
    if not picked:
        return
    ctx = context_for_paths(owner, (it.path for it in picked), origin=ORIGIN_ACTION)
    run = getattr(owner, "analyze", None)
    if callable(run):
        run(ctx)
    else:
        analyze(owner, ctx)


# -- analysis delivery --------------------------------------------------------


def _refresh_ranks_visible(owner) -> None:
    """Ask the controller to re-evaluate the rank-pill gate (guarded)."""
    fn = getattr(owner, "_refresh_ranks_visible", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def _begin_analysis(owner, ctx: ActionContext, item: GalleryItem) -> None:
    """Start ONE AI worker for *item* under *ctx*.

    The backend is an ARGUMENT: this function never chooses one (an
    ``algorithms`` context here is a programming error, raised — not a switch).
    ``AiSettings`` is read for credentials/transport only (api_key, base_url,
    model); mode/profile/effort come from *ctx*.
    """
    if not isinstance(ctx, ActionContext):
        raise TypeError("_begin_analysis() requires an ActionContext")
    if ctx.backend != BACKEND_AI:
        raise ValueError(
            f"_begin_analysis is the AI analyzer; ctx.backend={ctx.backend!r}"
        )
    settings = _load_settings(owner)
    if not _is_configured(settings):
        _mark_not_configured(owner, [item])
        return

    item.analysis_status = AnalysisStatus.PENDING
    item.analysis_error = None
    set_activity(item, ActivityPhase.QUEUED, "ai")
    owner.widget.refresh_card(item)
    _refresh_ranks_visible(owner)
    # plan-gallery-ai-judgement P3-A / D1.1: this build opens a slot in the
    # matrix. The terminal Jev call is dispatched when the LAST slot closes.
    _ai_batch_begin(owner)

    try:
        _ai_debug(
            "analyze MISS -> API call path=%s model=%s base_url=%s",
            item.path,
            settings.model,
            settings.base_url,
        )
    except Exception:
        pass

    # Local (Algorithms-domain) numbers ride along as CONTEXT; the AI
    # returns its own per-axis scorecard (the AI-domain read).
    try:
        _metrics = dict(getattr(item, "metrics", None) or {})
    except Exception:
        _metrics = {}
    from tabs.image_gallery.controller import _ActivityPhaseBridge

    bridge = _ActivityPhaseBridge(lambda phase, it=item: owner._apply_ai_phase(it, phase))
    mode = ctx.mode
    profile = ctx.profile
    # Snapshot the identity of THIS request: the result may arrive after the
    # user switched Settings, and it must be stored under the configuration
    # that actually produced it (a save under the current one would hand a
    # model-A scorecard to model B on the next hit).
    identity = analysis_cache_identity(
        settings, mode=mode, profile=profile, reasoning_effort=ctx.effort
    )
    worker = GenericWorker(
        owner._tracked(analyze_image_sync),
        item.path,
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
        mode=mode,
        profile=profile,
        metrics=_metrics,
        reasoning_effort=str(ctx.effort or "auto"),
        on_phase=bridge.phase.emit,
        # Sampling (plan P3-D): k draws per card, ONE unless the user declared a
        # larger `sample_count`; the trace states the cost.
        samples=int(getattr(settings, "sample_count", 1) or 1),
        temperature=float(getattr(settings, "sampling_temperature", 0.0) or 0.0),
        seed=int(getattr(settings, "sampling_seed", 0) or 0),
    )
    gen = owner._folder_gen
    # ``bridge=bridge`` keeps the phase relay alive until the worker reports.
    # The module function is called directly (the controller forwarder is pure
    # delegation but does not carry the request identity, and controller.py is
    # outside this task's scope): the identity must survive the worker hop.
    worker.signals.result.connect(
        lambda result, path=item.path, mtime_ns=item.mtime_ns, g=gen, bridge=bridge, identity=identity: _on_analysis_ready(
            owner, path, mtime_ns, result, g, identity=identity
        )
    )
    worker.signals.error.connect(
        lambda err, path=item.path, g=gen, bridge=bridge: owner._on_analysis_error(path, err, g)
    )
    set_activity(item, ActivityPhase.CLAIMED, "ai")
    owner.widget.refresh_card(item)
    owner._pool_start(worker, None)


def _apply_ai_phase(owner, item: GalleryItem, phase: str) -> None:
    """UI-thread sink for worker phase emits; drops phases of stale items."""
    if owner._find_item(item.path) is not item:
        return
    set_activity(item, phase, "ai")
    owner.widget.refresh_card(item)


def _on_analysis_ready(owner, path: Path, mtime_ns: int, result, gen: int | None = None, identity: dict | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late analysis dropped
    item = owner._find_item(path)
    if item is None:
        return
    # The VLM's result IS the AI-domain read (plan-gallery-ai-backend-owns-
    # quality): no detector merge here — the Algorithms domain keeps reading
    # ``item.metrics`` through ``services.quality_read``.
    # ``save_analysis`` is resolved through the controller module (the seam the
    # gallery tests patch to suppress the disk write). The identity is the one
    # snapshotted when the request was built; ``None`` (the controller forwarder
    # path) falls back to the current configuration rather than writing an
    # unverifiable entry.
    from tabs.image_gallery.controller import save_analysis

    if identity is None:
        identity = analysis_identity_for(owner)
    save_analysis(path, mtime_ns, result, identity)
    item.analysis = result
    item.analysis_status = AnalysisStatus.DONE
    item.analysis_error = None
    set_activity(item, ActivityPhase.DONE, "ai")
    owner.widget.refresh_card(item)
    # The AI scorecard IS the AI-domain read — rebuild the open overlay's
    # rows/dots in place so they switch to the VLM numbers without a reopen.
    owner._refresh_open_quick_look()
    # plan-gallery-ai-judgement P3-A / D1.1: NO per-arrival rank trigger. Jev is
    # the terminal calculator — one call per series, at the settle of the
    # matrix. This arrival only closes the batch; the LAST one dispatches.
    _ai_batch_end(owner)
    _dispatch_terminal_rank(owner)
    _refresh_ranks_visible(owner)


def _refresh_open_quick_look(owner) -> None:
    """Rebuild the open quick-look report rows + dots for the current domain.

    The report is domain-scoped (``services.quality_read``); a domain switch
    or a fresh analysis must re-render it in place, not on reopen.
    """
    try:
        ql = getattr(owner.widget, "_quick_look_overlay", None)
        if ql is None:
            return
        item = getattr(ql, "_current_item", None)
        if item is None:
            return
        if hasattr(ql, "refresh_metrics"):
            ql.refresh_metrics(item)
        if hasattr(ql, "refresh_artifacts"):
            ql.refresh_artifacts(item)
    except Exception:
        logger.debug("quick-look domain refresh failed", exc_info=True)


def _on_analysis_error(owner, path: Path, error_info, gen: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return
    item = owner._find_item(path)
    if item is None:
        return
    exctype, value, _tb = error_info
    message = None
    for error_cls, (key, default) in _ERROR_KEYS.items():
        if isinstance(value, error_cls) or (
            isinstance(exctype, type) and issubclass(exctype, error_cls)
        ):
            message = owner._tr(key, default)
            break
    if message is None and isinstance(value, AiClientError):
        message = str(value)
    item.analysis_status = AnalysisStatus.ERROR
    item.analysis_error = message or str(value)
    set_activity(item, ActivityPhase.ERROR, "ai")
    owner.widget.refresh_card(item)
    # A failed card does not change the ranking vector, but it DOES close its
    # slot in the batch: the remaining analyses still settle the matrix (a card
    # with no score is what `rank_completeness` reports as partial — the series
    # is then refused, not ranked on the missing member).
    _ai_batch_end(owner)
    _dispatch_terminal_rank(owner)
    _refresh_ranks_visible(owner)


# -- re-analyze offer after an AI-settings change ------------------------------
#
# Owner decision (2026-10-20): the AI settings now name a PROVIDER, and
# switching one changes the cache identity (model / base_url / profile /
# effort / mode) every existing scorecard was produced under. Applying such a
# change therefore asks ONCE, in a modal, which existing analyses to redo —
# scopes visible / selection / all, plus "not now" — and runs the SAME action
# path any other re-analyze takes (``ActionContext`` + ``reanalyze``). There is
# no bespoke loop here: the offer only resolves targets.

REANALYZE_SCOPE_VISIBLE = "visible"
REANALYZE_SCOPE_SELECTION = "selection"
REANALYZE_SCOPE_ALL = "all"
REANALYZE_SCOPES: tuple[str, ...] = (
    REANALYZE_SCOPE_VISIBLE,
    REANALYZE_SCOPE_SELECTION,
    REANALYZE_SCOPE_ALL,
)

_REANALYZE_TITLE_KEY = "image_gallery.settings.reanalyze_title"
_REANALYZE_BODY_KEY = "image_gallery.settings.reanalyze_body"
_REANALYZE_VISIBLE_KEY = "image_gallery.settings.reanalyze_visible"
_REANALYZE_SELECTION_KEY = "image_gallery.settings.reanalyze_selection"
_REANALYZE_ALL_KEY = "image_gallery.settings.reanalyze_all"
_REANALYZE_NOT_NOW_KEY = "image_gallery.settings.reanalyze_not_now"

_REANALYZE_TITLE_DEFAULT = "AI settings changed"
_REANALYZE_BODY_DEFAULT = (
    "The existing analyses were made with the previous AI configuration. "
    "Re-analyze them now? Re-analysis calls the API again and may cost money."
)
_REANALYZE_VISIBLE_DEFAULT = "Visible images"
_REANALYZE_SELECTION_DEFAULT = "Selected images"
_REANALYZE_ALL_DEFAULT = "All analyzed images"
_REANALYZE_NOT_NOW_DEFAULT = "Not now"


def _owner_tr(owner, key: str, default: str) -> str:
    """Resolve *key* through the owner's ``_tr``, failing open to *default*."""
    translate = getattr(owner, "_tr", None)
    if not callable(translate):
        return default
    try:
        value = translate(key, default)
    except TypeError:
        return default
    except Exception:
        return default
    if isinstance(value, str) and value and value != key:
        return value
    return default


def analyzed_items(owner) -> list[GalleryItem]:
    """Pool items that already carry an analysis (the offer's subject)."""
    try:
        items = list(getattr(getattr(owner, "state", None), "items", None) or ())
    except Exception:
        return []
    out: list[GalleryItem] = []
    for item in items:
        try:
            if getattr(item, "analysis", None) is not None:
                out.append(item)
        except Exception:
            continue
    return out


def reanalyze_targets(owner, scope: str) -> tuple[Path, ...]:
    """The ``ActionContext`` targets for one offer scope — analyzed items only.

    ``visible`` reads the viewport (``widget.visible_paths``), ``selection``
    the ONE selection source (``action_scope.selected_paths``), ``all`` the
    pool order. A scope that resolves to nothing returns ``()`` — the caller
    no-ops instead of widening to "everything".
    """
    analyzed = analyzed_items(owner)
    if not analyzed:
        return ()
    ordered = tuple(item.path for item in analyzed)
    if scope == REANALYZE_SCOPE_ALL:
        return ordered
    keys: set[str] = set()
    if scope == REANALYZE_SCOPE_VISIBLE:
        try:
            visible = getattr(getattr(owner, "widget", None), "visible_paths", None)
            keys = {str(p) for p in (visible() if callable(visible) else visible or ())}
        except Exception:
            keys = set()
    elif scope == REANALYZE_SCOPE_SELECTION:
        try:
            from tabs.image_gallery.use_cases import action_scope

            keys = {str(p) for p in action_scope.selected_paths(owner)}
        except Exception:
            keys = set()
    if not keys:
        return ()
    return tuple(path for path in ordered if str(path) in keys)


def _ask_reanalyze_scope(owner, *, parent=None) -> str:
    """Ask which analyses to redo; returns a scope token or "" for "not now".

    Uses the shared ``AppMessageDialog`` (same chrome/CSD as the large-drop
    guard). Its three action buttons carry the three scopes; the explicit
    "Not now" is a fourth surface button AND the window-close/Esc path, so a
    dismissed dialog can never be read as "re-analyze everything".
    """
    from tabs.host_helpers import AppMessageDialog, MessageKind

    dialog = AppMessageDialog(
        parent,
        kind=MessageKind.QUESTION,
        title=_owner_tr(owner, _REANALYZE_TITLE_KEY, _REANALYZE_TITLE_DEFAULT),
        text=_owner_tr(owner, _REANALYZE_BODY_KEY, _REANALYZE_BODY_DEFAULT),
        ok_text=_owner_tr(owner, _REANALYZE_VISIBLE_KEY, _REANALYZE_VISIBLE_DEFAULT),
        dont_ask_text=_owner_tr(
            owner, _REANALYZE_SELECTION_KEY, _REANALYZE_SELECTION_DEFAULT
        ),
        cancel_text=_owner_tr(owner, _REANALYZE_ALL_KEY, _REANALYZE_ALL_DEFAULT),
    )
    chosen = {"scope": ""}

    def _pick(scope: str):
        def _apply() -> None:
            chosen["scope"] = scope

        return _apply

    # The button handlers are connected in addition to the dialog's own
    # accept/reject: the scope is recorded before ``exec`` returns, and a plain
    # window close (no button) leaves it empty = "not now".
    try:
        dialog._ok_button.clicked.connect(_pick(REANALYZE_SCOPE_VISIBLE))
        dialog._dont_ask_button.clicked.connect(_pick(REANALYZE_SCOPE_SELECTION))
        dialog._cancel_button.clicked.connect(_pick(REANALYZE_SCOPE_ALL))
    except Exception:
        return ""
    try:
        from PySide6.QtCore import Qt
        from sli_ui_toolkit.widgets import Button

        actions = dialog._ok_button.parentWidget()
        not_now = Button(
            text=_owner_tr(owner, _REANALYZE_NOT_NOW_KEY, _REANALYZE_NOT_NOW_DEFAULT),
            variant="surface",
            parent=actions,
        )
        not_now.clicked.connect(dialog.reject)
        actions.layout().addWidget(
            not_now,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
    except Exception:
        logger.debug("re-analyze offer: no explicit 'not now' button", exc_info=True)
    dialog.exec()
    scope = chosen["scope"]
    return scope if scope in REANALYZE_SCOPES else ""


def reanalyze_after_settings_change(owner, ctx: ActionContext) -> None:
    """Run the standard re-analyze entry for one offer context."""
    run = getattr(owner, "reanalyze", None)
    if callable(run):
        run(ctx)
        return
    reanalyze(owner, ctx)


def offer_reanalysis(
    owner,
    *,
    old_identity,
    new_identity,
    parent=None,
    show_scope=None,
    reanalyze_fn=None,
) -> dict | None:
    """Offer to re-analyze existing results after an AI-settings change.

    Fires only when the applied identity CHANGED, the pool holds analyses, and
    the gallery is ranking through the AI backend (a re-analysis of an AI
    scorecard in the algorithms domain would silently re-measure instead).

    Returns ``{"scope": str, "targets": tuple[Path, ...]}`` when the user picked
    a scope (targets may be empty — nothing matched, so nothing ran), else
    ``None``. Re-analysis goes through ``ActionContext`` + the owner's
    ``reanalyze``; ``show_scope`` / ``reanalyze_fn`` are the test seams.
    """
    if not isinstance(old_identity, dict) or not isinstance(new_identity, dict):
        return None
    try:
        if dict(old_identity) == dict(new_identity):
            return None
    except Exception:
        return None
    if not analyzed_items(owner):
        return None
    try:
        if current_backend(owner) != BACKEND_AI:
            return None
    except Exception:
        return None
    ask = show_scope if callable(show_scope) else _ask_reanalyze_scope
    try:
        scope = str(ask(owner, parent=parent) or "").strip().lower()
    except TypeError:
        scope = ""
    except Exception:
        logger.debug("re-analyze offer: scope dialog failed", exc_info=True)
        scope = ""
    if scope not in REANALYZE_SCOPES:
        return None
    targets = reanalyze_targets(owner, scope)
    if targets:
        run = reanalyze_fn if callable(reanalyze_fn) else reanalyze_after_settings_change
        ctx = context_for_paths(owner, targets, origin=ORIGIN_ACTION)
        try:
            run(owner, ctx)
        except Exception:
            logger.debug("re-analyze after settings change failed", exc_info=True)
    return {"scope": scope, "targets": targets}

