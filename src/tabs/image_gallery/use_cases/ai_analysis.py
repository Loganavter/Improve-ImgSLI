"""AI analyze / judgment-domain + analysis delivery for the Image Gallery (Wave 4).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the VLM analyze entry points and their disk-cache hydration
(``analyze_item*`` / ``reanalyze_*`` / ``hydrate_cached_analysis`` /
``_hydrate_ai_cache``), the judgment-domain authority writer + toolbar switch
(``_set_judgment_domain`` / ``activate_judgment_domain``), the bounded
visible-item trigger (``_run_ai_for_visible``) and the worker delivery tail
(``_begin_analysis`` / ``_apply_ai_phase`` / ``_on_analysis_ready`` /
``_refresh_open_quick_look`` / ``_on_analysis_error``). Those two clusters share
one concern: the AI-domain read (see plan-gallery-ai-backend-owns-quality).
The owner keeps ``_tr``, the Jev ranker cluster, ``_apply_fusion_ranks`` and the
shared primitives (``_find_item`` / ``_tracked`` / ``_pool_start`` / folder
generation discipline); thin delegators keep the method names verbatim.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.models import (
    ActivityPhase,
    AnalysisStatus,
    GalleryItem,
)
from tabs.image_gallery.services.activity import set_activity
from tabs.image_gallery.services.ai_cache import load_cached_analysis
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


def analyze_item_by_path(owner, path: Path) -> None:
    item = owner._find_item(path)
    if item is None:
        return
    owner.analyze_item(item)


def hydrate_cached_analysis(owner, item: GalleryItem) -> bool:
    """Fill ``item`` from the disk cache only (Quick Look pre-read).

    No worker, no settings check — lets the overlay show a cached
    analysis the moment it opens instead of waiting for an Analyze
    click. Refreshes the card when something was hydrated. Never raises.
    """
    try:
        from tabs.image_gallery.services.ai_cache import hydrate_item
    except Exception:
        return False
    try:
        if not hydrate_item(item):
            return False
    except Exception:
        return False
    try:
        owner.widget.refresh_card(item)
    except Exception:
        pass
    return True


def _hydrate_ai_cache(owner, items) -> int:
    """Fill pool items from the AI disk cache on a pool (re)build.

    Closed-tab / re-loaded-folder recovery: the live ``analyze_item``
    path is cache-first, but a pool rebuild (session restore, folder
    open, append) had no such pass, so previously analyzed images came
    back "not analyzed" until some other trigger ran — even though the
    results sat in the disk cache. This pass fills them at rebuild so the
    read is present the moment the pool appears; the metrics-pass settle
    then re-derives only the still-missing scorecards (AI domain only,
    ``_run_ai_on_settle``). Cache-only: no worker, no settings check, no
    API call. Never raises; returns how many items were filled.
    """
    try:
        from tabs.image_gallery.services.ai_cache import hydrate_item
    except Exception:
        return 0
    filled = 0
    for it in list(items or []):
        try:
            if getattr(it, "analysis", None) is not None:
                continue
            if hydrate_item(it):
                filled += 1
        except Exception:
            continue
    return filled


def analyze_item(owner, item: GalleryItem) -> None:
    cached = load_cached_analysis(item.path, item.mtime_ns)
    if cached is not None:
        try:
            from tabs.image_gallery.services.ai_client import _ai_debug

            _ai_debug("analyze cache HIT path=%s (no API call)", item.path)
        except Exception:
            pass
        item.analysis = cached
        item.analysis_status = AnalysisStatus.DONE
        item.analysis_error = None
        owner.widget.refresh_card(item)
        return

    owner._begin_analysis(item)


def reanalyze_item_by_path(owner, path: Path) -> None:
    item = owner._find_item(path)
    if item is None:
        return
    owner.reanalyze_item(item)


def reanalyze_item(owner, item: GalleryItem) -> None:
    """Force a fresh analysis, bypassing the disk cache (Re-analyze).

    Same worker pipeline as :meth:`analyze_item` minus the cache
    short-circuit; completion overwrites the cache entry. Never raises.
    """
    try:
        owner._begin_analysis(item)
    except Exception:
        pass


def _set_judgment_domain(owner, domain: str) -> str:
    """The ONLY writer of the judgment domain (Algorithms vs AI).

    ``owner._judgment_domain`` is the single authority and survives the
    ``GalleryState`` rebuilds done by open_folder / append / clear_to_empty;
    ``state.judgment_domain``/``state.rank_domain`` are read-only projections
    kept for rendering. Returns the normalized value.
    """
    dom = str(domain or "").strip().lower()
    dom = dom if dom in ("algorithms", "ai") else "algorithms"
    owner._judgment_domain = dom
    try:
        setattr(owner.state, "judgment_domain", dom)
        setattr(owner.state, "rank_domain", dom)
    except Exception:
        pass
    return dom


def activate_judgment_domain(owner, domain: str) -> None:
    """Apply the toolbar domain switch (plan-gallery-two-domain-axes).

    Switching to ``ai`` is the switch's actual effect: it lazily analyzes
    the **visible** items (cache-first, in-flight skipped, capped). Not
    configured / no key degrades to the existing per-item error on the cards
    — the control always does something visible, never a silent no-op.
    Switching back to ``algorithms`` only flips the report domain; it never
    cancels in-flight work.
    """
    try:
        from tabs.image_gallery.models import JUDGMENT_DOMAINS

        if str(domain or "").strip().lower() not in tuple(JUDGMENT_DOMAINS):
            domain = "algorithms"
    except Exception:
        domain = "algorithms"
    # Single authoritative setter; state/widget mirror it for rendering.
    dom = _set_judgment_domain(owner, domain)
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
    owner._run_jev_ranks()
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
    for it in picked[: owner._AI_VISIBLE_CAP]:
        try:
            owner.analyze_item(it)
        except Exception:
            continue


# -- analysis delivery --------------------------------------------------------


def _refresh_ranks_visible(owner) -> None:
    """Ask the controller to re-evaluate the rank-pill gate (guarded)."""
    fn = getattr(owner, "_refresh_ranks_visible", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def _begin_analysis(owner, item: GalleryItem) -> None:
    settings = owner._ai_settings_store.load()
    if not settings.enabled or not settings.api_key or not settings.model:
        item.analysis_status = AnalysisStatus.ERROR
        item.analysis_error = owner._tr(
            "image_gallery.errors.not_configured",
            "Configure the AI API key in Settings first.",
        )
        owner.widget.refresh_card(item)
        return

    item.analysis_status = AnalysisStatus.PENDING
    item.analysis_error = None
    set_activity(item, ActivityPhase.QUEUED, "ai")
    owner.widget.refresh_card(item)
    _refresh_ranks_visible(owner)

    try:
        from tabs.image_gallery.services.ai_client import _ai_debug

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
    worker = GenericWorker(
        owner._tracked(analyze_image_sync),
        item.path,
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
        mode=getattr(owner.state, "mode", None),
        metrics=_metrics,
        reasoning_effort=str(getattr(settings, "reasoning_effort", "auto") or "auto"),
        on_phase=bridge.phase.emit,
    )
    gen = owner._folder_gen
    # ``bridge=bridge`` keeps the phase relay alive until the worker reports.
    worker.signals.result.connect(
        lambda result, path=item.path, mtime_ns=item.mtime_ns, g=gen, bridge=bridge: owner._on_analysis_ready(
            path, mtime_ns, result, g
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


def _on_analysis_ready(owner, path: Path, mtime_ns: int, result, gen: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late analysis dropped
    item = owner._find_item(path)
    if item is None:
        return
    # The VLM's result IS the AI-domain read (plan-gallery-ai-backend-owns-
    # quality): no detector merge here — the Algorithms domain keeps reading
    # ``item.metrics`` through ``services.quality_read``.
    # ``save_analysis`` is resolved through the controller module (the seam the
    # gallery tests patch to suppress the disk write).
    from tabs.image_gallery.controller import save_analysis

    save_analysis(path, mtime_ns, result)
    item.analysis = result
    item.analysis_status = AnalysisStatus.DONE
    item.analysis_error = None
    set_activity(item, ActivityPhase.DONE, "ai")
    owner.widget.refresh_card(item)
    # The AI scorecard IS the AI-domain read — rebuild the open overlay's
    # rows/dots in place so they switch to the VLM numbers without a reopen.
    owner._refresh_open_quick_look()
    # A new scorecard changes the Jev ranking vector: coalesce the batch of
    # arrivals into one AI-rank pass (no-op off the AI domain).
    owner._queue_ai_rank_on_settle()
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
    _refresh_ranks_visible(owner)
