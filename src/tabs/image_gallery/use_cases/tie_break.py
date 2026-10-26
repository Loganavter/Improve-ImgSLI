"""Stage-3 VLM tie-break + compare briefs for the Image Gallery (Wave 4).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the selective VLM tie-break for a series' measured-fusion
top-2 (``_is_tie`` / ``run_tie_break_if_needed`` / ``_apply_tie_break_result``)
and the compare-brief result apply tail (``_apply_brief_result``). The VLM runs
via ``GenericWorker`` (never UI-blocking), is cached (``vlm_cache``) and degrades
silent-but-visible when unresolved. The owner keeps the shared primitives
(``_find_item`` / ``_pool_start`` / ``_is_current_folder_gen`` / ``_folder_gen``
/ ``TIE_EPSILON``); thin delegators keep the method names verbatim.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.controller import TIE_EPSILON
from tabs.image_gallery.models import GalleryItem
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _is_tie(owner, a: GalleryItem, b: GalleryItem, epsilon: float = TIE_EPSILON) -> bool:
    """Local-metric epsilon check for top-2 tie-break eligibility."""
    try:
        da = a.metrics.get("embedding_dist_to_centroid")
        db = b.metrics.get("embedding_dist_to_centroid")
        if da is not None and db is not None:
            return abs(float(da) - float(db)) < epsilon
        # Fallback: sharpness / ssim deltas
        for key in ("sharpness", "ssim", "artifact_score"):
            va = a.metrics.get(key)
            vb = b.metrics.get(key)
            if va is not None and vb is not None:
                try:
                    av, bv = float(va), float(vb)
                    denom = max(abs(av), abs(bv), 1e-6)
                    if abs(av - bv) / denom < epsilon * 2:
                        return True
                except Exception:
                    continue
        # No metrics → conservative: treat rank-1 vs rank-2 as tie candidate if phash close?
        # Use hamming of phash if available
        pa = a.metrics.get("phash")
        pb = b.metrics.get("phash")
        if isinstance(pa, int) and isinstance(pb, int):
            ham = bin(int(pa) ^ int(pb)).count("1")
            if ham <= 4:
                return True
        return False
    except Exception:
        return False


def _tie_break_still_owned(owner, epoch) -> bool:
    """True while the AI domain that scheduled this verdict still owns the tab.

    A live domain switch has no cancellation API; the epoch is the token (see
    ``use_cases/ai_analysis.domain_epoch``). A verdict that arrives after the
    switch must not crown a card under Algorithms. The decision itself is the
    ONE shared gate (``ai_analysis._epoch_is_current``).
    """
    try:
        from tabs.image_gallery.use_cases.ai_analysis import _epoch_is_current

        return _epoch_is_current(owner, epoch)
    except Exception:
        return True


def run_tie_break_if_needed(owner, series) -> None:
    """Stage 3: selective VLM tie-break for top-2 when local metrics within epsilon.

    *series* may be a ``Series`` dataclass (has .members) or plain list[GalleryItem].
    Sets badge ``AI tie-break…`` pending on both candidates until resolved;
    degrades silent-but-visible if unresolved (badge cleared, local ranking kept).
    Uses ``GenericWorker`` (never UI-blocking), cached via ``vlm_cache`` (hash paths+mtime).
    """
    try:
        members = list(getattr(series, "members", series) or [])
    except Exception:
        return
    if len(members) < 2:
        return
    # The VLM tie-break is AI-domain work. The Algorithms backend must emit ZERO
    # VLM requests (owner ask 2026-10-22) — measured live: with Algorithms
    # selected, merely opening a near-duplicate folder fired one tie_break_sync
    # POST because the only gate here was "AI settings configured".
    try:
        from tabs.image_gallery.use_cases.ai_analysis import domain_epoch

        epoch = domain_epoch(owner)
    except Exception:
        epoch = None
    if not _tie_break_still_owned(owner, epoch):
        try:
            from tabs.image_gallery.services.ai_client.prompt import _ai_debug

            _ai_debug("tie-break skipped: not the AI judgment domain (no VLM call)")
        except Exception:
            pass
        return
    # Candidates come from the MEASURED FUSION order (not the old centroid
    # distance/rank): the VLM tie-break is additive on top of the
    # Algorithms rank, so its top-2 must be the fusion top-2.
    try:
        from tabs.image_gallery.services.rank_fusion import rank_series as _rank

        fusion = _rank(members, mode=getattr(owner.state, "mode", None))
    except Exception:
        fusion = {}

    def _sort_key(it: GalleryItem):
        try:
            r = fusion.get(str(getattr(it, "path", "")))
        except Exception:
            r = None
        try:
            rk = int(r) if r is not None else 1 << 30
        except Exception:
            rk = 1 << 30
        try:
            return (rk, str(getattr(it, "path", "")))
        except Exception:
            return (rk, "")

    sorted_members = sorted(members, key=_sort_key)
    top2 = sorted_members[:2]
    if len(top2) < 2:
        return
    a, b = top2[0], top2[1]
    if not owner._is_tie(a, b):
        return

    # Use existing analyze_image_sync only via VLM targeted path — tie-break needs 2 images.
    settings = owner._ai_settings_store.load()
    from tabs.image_gallery.services.vlm import set_vlm_max_edge

    set_vlm_max_edge(settings.vlm_max_edge_px)
    # Owner rule 2026-10-26: the AI backend is selected, so an unusable
    # configuration is an ERROR on the cards, not a "silent degrade" that leaves
    # the tie ordered by the local numbers as if the model had answered.
    if not settings.enabled or not settings.api_key or not settings.model:
        logger.warning("tie-break: AI is not configured — marking the pair ERROR")
        try:
            from tabs.image_gallery.services.activity import ActivityPhase, set_activity

            for item in (a, b):
                set_activity(item, ActivityPhase.ERROR, "ai")
            owner.widget.refresh_card(a)
            owner.widget.refresh_card(b)
        except Exception:
            logger.debug("tie-break error paint failed", exc_info=True)
        return

    # Resolve source path for fidelity mode (if available) — needed early for cache key source_mtime
    source = getattr(owner.state, "source_path", None)
    try:
        source = Path(source) if source is not None else None
    except Exception:
        source = None
    # source_mtime for vlm_cache key (design parity: hash(paths+mtime+source_mtime))
    source_mtime: int | None = None
    if source is not None:
        try:
            si = owner._find_item(source)
            if si is not None:
                source_mtime = int(getattr(si, "mtime_ns", 0) or 0) or None
            else:
                source_mtime = int(Path(source).stat().st_mtime_ns)
        except Exception:
            source_mtime = None

    # Check cache first (key = hash(paths+mtime+source_mtime))
    try:
        from tabs.image_gallery.services.vlm_cache import load_cached_tie_break, save_tie_break
    except Exception:
        load_cached_tie_break = None  # type: ignore
        save_tie_break = None  # type: ignore

    if load_cached_tie_break is not None:
        try:
            cached = load_cached_tie_break(a.path, a.mtime_ns, b.path, b.mtime_ns, source_mtime)
            if cached is not None:
                owner._apply_tie_break_result(a, b, cached)
                return
        except Exception:
            logger.debug("tie-break cache load failed", exc_info=True)

    # Badge pending on both candidates
    for it in top2:
        it.vlm_tie_pending = True
        it.vlm_tie_error = None
        try:
            owner.widget.refresh_card(it)
        except Exception:
            pass

    from tabs.image_gallery.services.vlm import tie_break_sync

    worker = GenericWorker(
        tie_break_sync,
        a.path,
        b.path,
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model,
        source=source,
    )

    def _on_result(result, a_path=a.path, b_path=b.path, a_mtime=a.mtime_ns, b_mtime=b.mtime_ns, _src_mtime=source_mtime, gen=owner._folder_gen):
        if not owner._is_current_folder_gen(gen):
            return  # folder switched mid-VLM — late tie-break dropped
        if not _tie_break_still_owned(owner, epoch):
            return  # the user left the AI domain — the verdict must not land
        try:
            if save_tie_break is not None:
                save_tie_break(a_path, a_mtime, b_path, b_mtime, result, _src_mtime)
        except Exception:
            logger.debug("tie-break cache save failed", exc_info=True)
        # Find current items (may have been refreshed)
        item_a = owner._find_item(a_path)
        item_b = owner._find_item(b_path)
        if item_a is None or item_b is None:
            return
        owner._apply_tie_break_result(item_a, item_b, result)

    def _on_error(error_info, top2_paths=(a.path, b.path), gen=owner._folder_gen):
        if not owner._is_current_folder_gen(gen):
            return
        logger.debug("tie-break worker error: %r", error_info, exc_info=True)
        # Silent-but-visible degrade: clear pending badge, keep local ranking
        for p in top2_paths:
            it = owner._find_item(p)
            if it is not None:
                it.vlm_tie_pending = False
                # keep vlm_tie_error visible as tooltip but not badge
                try:
                    exctype, value, _tb = error_info
                    it.vlm_tie_error = str(value)[:200] if value is not None else "tie-break unresolved"
                except Exception:
                    it.vlm_tie_error = "tie-break unresolved"
                try:
                    owner.widget.refresh_card(it)
                except Exception:
                    pass

    worker.signals.result.connect(_on_result)
    worker.signals.error.connect(_on_error)
    owner._pool_start(worker, None)


def _series_is_ranked_by_jev(owner, *items) -> bool:
    """True when the terminal Jev ranker owns this series' ordering.

    P3-A: Jev is the terminal calculator, so its rank-1 member is the ONE card
    allowed to wear BEST. A tie-break verdict that lands afterwards (or a stale
    crown that survived) must not add a second one — the owner saw two
    "★ ЛУЧШЕЕ" cards at once (2026-10-22). The verdict stays visible as
    information (``state.tie_breaks`` + ``vlm_tie_result``), never as a crown.
    """
    seen = list(items or ())
    try:
        seen.extend(list(getattr(getattr(owner, "state", None), "items", None) or ()))
    except Exception:
        pass
    for it in seen:
        try:
            if str(getattr(it, "rank_source", "") or "") == "jev":
                return True
        except Exception:
            continue
    return False


def _apply_tie_break_result(owner, a: GalleryItem, b: GalleryItem, result) -> None:
    """Apply VLM winner: mark winner is_best/crown_rank, clear pending badges."""
    if not _tie_break_still_owned(owner, None):
        # Direct callers (tests, an old queued callback) get the same rule as the
        # worker path: the Algorithms domain never receives a VLM crown.
        return
    if _series_is_ranked_by_jev(owner, a, b):
        # ONE crown per series: the terminal ranker already marked its winner.
        # Keep the verdict (hover/state) but do not touch is_best/crown_rank.
        try:
            owner.state.tie_breaks[
                str(getattr(a, "series_id", None) or getattr(b, "series_id", None) or f"{a.path}:{b.path}")
            ] = result
        except Exception:
            pass
        for it in (a, b):
            try:
                it.vlm_tie_result = result
                it.vlm_tie_pending = False
                it.vlm_tie_error = None
                owner.widget.refresh_card(it)
            except Exception:
                pass
        try:
            from tabs.image_gallery.services.ai_client.prompt import _ai_debug

            _ai_debug("tie-break verdict recorded, crown left to the Jev rank")
        except Exception:
            pass
        return
    try:
        winner_str = str(getattr(result, "winner_path", ""))
        loser_str = str(getattr(result, "loser_path", ""))
        # Resolve which of a,b is winner by path equality (resolve-aware)
        def _matches(item: GalleryItem, s: str) -> bool:
            try:
                return str(item.path.resolve()) == s or str(item.path) == s
            except Exception:
                return str(item.path) == s

        winner = a if _matches(a, winner_str) else (b if _matches(b, winner_str) else a)
        loser = b if winner is a else a
        # Additive crown: the VLM verdict overlays ``crown_rank``/``is_best``
        # on top of the fusion rank (#N is crown_rank ?? rank in
        # ``rank_badge``). ``rank`` stays the measured-fusion number — the
        # AI hint never fabricates a measured rank.
        try:
            winner.is_best = True
            winner.crown_rank = 1
            winner.vlm_tie_result = result
        except Exception:
            pass
        try:
            loser.is_best = False
            loser.crown_rank = 2
            loser.vlm_tie_result = result
        except Exception:
            pass
        for it in (a, b):
            it.vlm_tie_pending = False
            it.vlm_tie_error = None
            try:
                owner.widget.refresh_card(it)
            except Exception:
                pass
        # Persist in state
        try:
            key = getattr(a, "series_id", None) or getattr(b, "series_id", None) or f"{a.path}:{b.path}"
            owner.state.tie_breaks[str(key)] = result
        except Exception:
            pass
    except Exception:
        logger.debug("apply tie-break failed", exc_info=True)
        for it in (a, b):
            try:
                it.vlm_tie_pending = False
                owner.widget.refresh_card(it)
            except Exception:
                pass


def _apply_brief_result(owner, pa: Path, pb: Path, result, gen: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late brief dropped
    try:
        # Persist in state (one per pair)
        try:
            key = f"{Path(pa).resolve()}:{Path(pb).resolve()}"
            if str(Path(pa).resolve()) > str(Path(pb).resolve()):
                key = f"{Path(pb).resolve()}:{Path(pa).resolve()}"
            owner.state.briefs[key] = result
        except Exception:
            pass
        for p in (pa, pb):
            it = owner._find_item(p)
            if it is not None:
                it.vlm_brief = result
                it.vlm_brief_status = "done"
                it.vlm_brief_error = None
                try:
                    owner.widget.refresh_card(it)
                except Exception:
                    pass
    except Exception:
        logger.debug("apply brief failed", exc_info=True)
