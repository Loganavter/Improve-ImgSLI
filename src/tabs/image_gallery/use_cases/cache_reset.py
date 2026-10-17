"""Reset the Image Gallery's measured-metrics caches and re-enter the pipeline.

Backs the card context menu's **Reset metrics cache** entry and the Find
Action / MCP ``gallery.reset-metrics`` descriptor.

Deleting the disk cache files alone is a **no-op**: the Stage-2 measured pass
is gated by an in-memory content fingerprint
(``owner._last_analysis_fingerprint`` — see
``use_cases.proxy_pass._apply_triage_result``) and the AI domain is cache-first
(``services.ai_cache.hydrate_item`` sets ``item._ai_cache_checked`` *before* the
disk read, and ``use_cases.ai_analysis.analyze_item`` short-circuits on
``load_cached_analysis``). A genuine recompute therefore has to clear, in ONE
place:

* the in-memory per-item artifact/metric/analysis state + the local activity
  phase;
* the in-memory proxy decode cache (``services.proxy.clear_proxy_cache``);
* the on-disk AI scorecards (``services.ai_cache``) and the VLM metric-profile
  pins (``services.profile_cache``);
* the stored metric profile (``owner.clear_metric_profile``) and the Stage-2
  fingerprint.

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
    """Drop one item's measured / AI state so the pipeline recomputes it."""
    try:
        item.metrics = {}
        item.artifacts = {}
        item.artifact_maps = {}
        item.analysis = None
        item.analysis_status = AnalysisStatus.NOT_ANALYZED
        item.analysis_error = None
    except Exception:
        logger.debug("metrics reset: item state clear failed", exc_info=True)
    try:
        # ``hydrate_item`` sets this BEFORE the disk read — left True it would
        # short-circuit the cache miss and never re-read.
        item._ai_cache_checked = False
    except Exception:
        pass
    try:
        clear_activity(item, "local")
    except Exception:
        pass


def clear_metrics_caches(owner, *, paths=None) -> dict:
    """Clear the measured-metrics caches (in-memory + disk). Never raises.

    *paths* narrows the per-item clear (the card menu passes its file-manager
    targets); ``None`` means every item of ``owner.state.items`` and a
    whole-directory AI-scorecard sweep (``ai_cache.clear_all``). Returns an
    honest summary: ``{"items": n, "ai_files": n, "profiles": n}``.
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
    return summary


def reset_metrics_caches(owner, *, paths=None) -> dict:
    """Clear the caches, then RE-ENTER the triage rebuild. Never raises.

    The clear alone leaves the already-painted view intact, so re-entering
    ``_start_triage(..., cover_grid=False)`` is what makes the proxy pass
    recompute (the fingerprint gate is now open). A missing folder / controller
    degrades to the clear-only path — the summary then carries
    ``"requeued": False``.
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
