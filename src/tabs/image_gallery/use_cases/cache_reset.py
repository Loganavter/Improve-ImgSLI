"""Reset the Image Gallery's measured-metrics caches and re-enter the pipeline.

Backs the card context menu's **Reset metrics cache** entry and the Find
Action / MCP ``gallery.reset-metrics`` descriptor.

Deleting the disk cache files alone is a **no-op**: the Stage-2 measured pass
is gated by an in-memory content fingerprint
(``owner._last_analysis_fingerprint`` — see
``use_cases.proxy_pass._apply_triage_result``) and the AI domain is cache-first
(``services.ai_cache.hydrate_item`` memoizes an "already checked" verdict on
the item, scoped to the identity it was earned under, and
``use_cases.ai_analysis.analyze_item`` short-circuits on
``load_cached_analysis``). A genuine recompute therefore has to clear, in ONE
place:

* the in-memory per-item artifact/metric/analysis state + the local activity
  phase;
* the in-memory proxy decode cache (``services.proxy.clear_proxy_cache``);
* the on-disk AI scorecards (``services.ai_cache``) and the VLM metric-profile
  pins (``services.profile_cache``);
* the stored metric profile (``owner.clear_metric_profile``) and the Stage-2
  fingerprint.

The cleared item state includes the **metric-derived rank state** (``rank`` /
``rank_source`` / ``crown_rank`` / ``is_best`` / badge triple), not just the
numbers: a reset asks for a fresh UNRANKED view, so both an automatic
(fusion/jev) rank and an explicit "Make best" pick go — the manual pick is a
rank OVER the old measurements. ``series_id`` / ``provenance_series_id`` /
``rejected`` / ``triage_rejected`` are not metric-derived and survive.

The clear then re-stamps the badges unranked (``rank_badge.stamp_badges(...,
show_rank=False)``) and refreshes the bound cards through the live view
(``refresh_cards``) — otherwise the per-card painted dots
(``_gallery_dot_colors``) and the ★ BEST pill survive on screen even though
the items are already empty (the painted view is not derived from the items
at paint time, it is stamped at build/update time).

``reset_metrics_caches`` then re-enters the rebuild
(``_start_triage(..., cover_grid=False)``) so the pipeline actually recomputes
instead of repainting the already-measured view.

Deliberately NOT touched: ``services.jev_cache`` / ``services.vlm_cache``. Their
keys already include the measured payload / the compared paths+mtimes, so once
the measurements change the stale entries simply MISS — deleting them is
unnecessary work (and would discard still-valid briefs for unchanged inputs).
Do not "fix" this by widening the clear.
"""

from __future__ import annotations

import logging
from pathlib import Path

from tabs.image_gallery.models import AnalysisStatus
from tabs.image_gallery.services.activity import clear_activity
from tabs.image_gallery.services.rank_badge import KIND_NONE, stamp_badges

logger = logging.getLogger("ImproveImgSLI")


def _items_of(owner) -> list:
    """The owner's pool items (``state.items`` first, widget fallback)."""
    try:
        st = getattr(owner, "state", None)
        if st is None:
            widget = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
            if widget is not None:
                st = getattr(widget, "_state", None) or getattr(
                    getattr(widget, "_controller", None), "state", None
                )
        return list(getattr(st, "items", None) or [])
    except Exception:
        return []


def _path_key(item) -> str:
    try:
        return str(getattr(item, "path", ""))
    except Exception:
        return ""


def _clear_item(item) -> None:
    """Drop one item's measured / AI / metric-derived rank state.

    DECISION: a metrics reset is a *reset*, not a cache refresh. Auto ranks
    (``fusion``/``jev``) and a manual "Make best" pick both go — the user
    asked for a fresh unranked view, and a manual pick is a rank over the old
    measurements (leaving ``triage_best`` set would let the next snapshot
    re-freeze it as a manual rank and silently undo the reset). What is NOT
    metric-derived survives: ``series_id`` / ``provenance_series_id`` (group
    identity), ``rejected`` / ``triage_rejected`` (user triage decisions).
    """
    try:
        item.metrics = {}
        item.artifacts = {}
        item.artifact_maps = {}
        item.analysis = None
        item.analysis_status = AnalysisStatus.NOT_ANALYZED
        item.analysis_error = None
        # Metric-derived rank state — see the DECISION above.
        item.rank = None
        item.rank_source = None
        item.crown_rank = None
        item.is_best = False
        item.triage_best = False
        item.triage_rank = None
        item.badge = ""
        item.badge_kind = KIND_NONE
        item.badge_source = ""
    except Exception:
        logger.debug("metrics reset: item state clear failed", exc_info=True)
    try:
        # Both halves of the hydrate memo: the flag AND the identity it was
        # earned under, so the next populate reads the (now deleted) entry
        # instead of short-circuiting on a stale "checked" verdict.
        item._ai_cache_checked = False
        item._ai_cache_checked_identity = None
    except Exception:
        pass
    try:
        clear_activity(item, "local")
    except Exception:
        pass


def _cards_view(owner):
    """The live view that owns the card widgets, or ``None`` (storeless tests).

    Owner is a controller in production (``owner.widget``), but the widget
    itself is also a legal owner (storeless/live-menu paths), so both are
    probed. A bare ``_grid_view`` is the last resort for thin doubles.
    """
    try:
        candidates = (getattr(owner, "widget", None), getattr(owner, "_widget", None), owner)
    except Exception:
        return None
    for cand in candidates:
        if cand is None:
            continue
        try:
            if callable(getattr(cand, "refresh_cards", None)):
                return cand
            grid = getattr(cand, "_grid_view", None)
            if grid is not None and callable(getattr(grid, "refresh_cards", None)):
                return grid
        except Exception:
            continue
    return None


def _source_path_of(owner, view):
    """Current source hub for the badge stamp (identity badge stays visible)."""
    for cand in (owner, view, getattr(owner, "widget", None)):
        if cand is None:
            continue
        try:
            src = getattr(cand, "_source_path", None)
        except Exception:
            src = None
        if src is not None:
            return src
    return None


def _refresh_cleared_view(owner, targets) -> None:
    """Re-stamp the cleared items unranked and repaint their cards.

    The dots and the ★ BEST pill are stamped ON the card at build/update time
    (``ui/card.py``), so mutating the items alone leaves the painted view
    showing the old colours until some unrelated event repaints it. Two
    existing seams, no new render pipeline: the single badge-stamp point
    (``stamp_badges``, ``show_rank=False`` — the ranking is not final after a
    reset) and the view's targeted per-card update (``refresh_cards``, the
    same path a triage tail uses, which recomputes ``_gallery_dot_colors``
    from the now-empty metrics). Never raises.
    """
    try:
        clear_targets = list(targets or [])
    except Exception:
        return
    if not clear_targets:
        return
    view = _cards_view(owner)
    try:
        stamp_badges(clear_targets, _source_path_of(owner, view), show_rank=False)
    except Exception:
        logger.debug("metrics reset: badge re-stamp failed", exc_info=True)
    # The OPEN quick-look report holds its own row set: it must rebuild from the
    # cleared items, or the reset looks like a no-op while the panel still shows
    # the old numbers (owner 2026-10-22: "кэш сброшен, нумерации нет, а метрики
    # остались").
    try:
        refresh_ql = getattr(owner, "_refresh_open_quick_look", None)
        if callable(refresh_ql):
            refresh_ql()
    except Exception:
        logger.debug("metrics reset: quick-look refresh failed", exc_info=True)
    if view is None:
        return
    try:
        view.refresh_cards(clear_targets)
        return
    except Exception:
        logger.debug("metrics reset: batch card refresh failed", exc_info=True)
    for it in clear_targets:
        try:
            view.refresh_card(it)
        except Exception:
            logger.debug("metrics reset: per-card refresh failed", exc_info=True)


def clear_metrics_caches(owner, *, paths=None) -> dict:
    """Clear the measured-metrics caches (in-memory + disk). Never raises.

    *paths* narrows the per-item clear (the card menu passes its file-manager
    targets); ``None`` means every item of ``owner.state.items`` and a
    whole-directory AI-scorecard sweep (``ai_cache.clear_all``). Returns an
    honest summary: ``{"items": n, "ai_files": n, "profiles": n}``.

    Cleared items lose their metric-derived rank state too (see
    :func:`_clear_item`), and the bound cards are re-stamped unranked and
    repainted BEFORE this returns — a reset must look reset immediately, not
    after the async pass repaints.
    """
    summary = {"items": 0, "ai_files": 0, "profiles": 0}
    items = _items_of(owner)
    if paths is None:
        targets = items
    else:
        wanted = set()
        for p in paths or ():
            try:
                wanted.add(str(Path(p)))
            except Exception:
                continue
        targets = [it for it in items if _path_key(it) in wanted]
    for it in targets:
        _clear_item(it)
        summary["items"] += 1

    # In-memory decode cache: the proxy pass re-decodes from scratch.
    try:
        from tabs.image_gallery.services import proxy as _proxy

        _proxy.clear_proxy_cache()
    except Exception:
        logger.debug("metrics reset: proxy cache clear failed", exc_info=True)

    # Disk caches: AI scorecards + the VLM metric-profile pins.
    try:
        from tabs.image_gallery.services import ai_cache as _ai_cache

        if paths is None:
            summary["ai_files"] = int(_ai_cache.clear_all())
        else:
            removed = 0
            for it in targets:
                try:
                    if _ai_cache.clear_cached_analysis(it.path, it.mtime_ns):
                        removed += 1
                except Exception:
                    continue
            summary["ai_files"] = removed
    except Exception:
        logger.debug("metrics reset: ai cache clear failed", exc_info=True)
    try:
        from tabs.image_gallery.services import profile_cache as _profile_cache

        summary["profiles"] = int(_profile_cache.clear_default_cache())
    except Exception:
        logger.debug("metrics reset: profile pin clear failed", exc_info=True)

    # Stored profile + the Stage-2 skip gate.
    try:
        clear = getattr(owner, "clear_metric_profile", None)
        if callable(clear):
            clear()
    except Exception:
        logger.debug("metrics reset: clear_metric_profile failed", exc_info=True)
    try:
        owner._last_analysis_fingerprint = None
    except Exception:
        logger.debug("metrics reset: fingerprint clear failed", exc_info=True)

    # Visible reset LAST: the profile is already dropped, so the refreshed
    # dots use the fresh (mode-derived) axis set, and the cards show the
    # unranked/neutral state the re-entered pass starts from.
    _refresh_cleared_view(owner, targets)
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(
            "metrics reset: scope=%s items=%d ai_files=%d profiles=%d",
            "pool" if paths is None else f"{len(targets)} card(s)",
            summary["items"],
            summary["ai_files"],
            summary["profiles"],
        )
    except Exception:
        pass
    return summary


def reset_metrics_caches(owner, *, paths=None) -> dict:
    """Clear the caches, then RE-ENTER the triage rebuild. Never raises.

    The clear already resets the visible state (unranked badges + neutral
    dots); re-entering ``_start_triage(..., cover_grid=False)`` is what makes
    the proxy pass recompute the numbers (the fingerprint gate is now open).
    A missing folder / controller degrades to the clear-only path — the
    summary then carries ``"requeued": False``.
    """
    summary = clear_metrics_caches(owner, paths=paths)
    summary["requeued"] = False
    try:
        st = getattr(owner, "state", None)
        items = list(getattr(st, "items", None) or [])
        folder = getattr(st, "folder", None)
        start = getattr(owner, "_start_triage", None)
        if items and folder is not None and callable(start):
            start(items, cover_grid=False)
            summary["requeued"] = True
    except Exception:
        logger.debug("metrics reset: triage re-entry failed", exc_info=True)
    return summary
