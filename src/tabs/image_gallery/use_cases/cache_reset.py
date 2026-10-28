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
  fingerprint. The AI slot's JUDGE answer (the axis set) is the one exception:
  it is re-installed straight after the clear (``_keep_ai_axis_set``), because
  a reset drops results, not the axes — otherwise the next Analyze refuses
  "no_profile" on a folder whose judge named its axes a minute earlier.

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

``reset_metrics_caches`` (the user-facing action) then stops. OWNER DECISION
2026-10-22: the reset ZEROES, it does not re-run (see that function).

**WHOSE cache it is, is the adapter's answer** (ADR 009 wave A4). This module
used to clear sixteen named stores it did not own — ``ai_cache.clear_all()``,
``profile_cache.clear_default_cache()``, ``jev_cache``/``vlm_cache``,
``pairwise_rank.clear_default_cache()``, ``metrics_cache.clear_all()`` — and the
list was wrong in both directions: it never cleared the Ask-AI answer cache
(``controller._ask_cache``, so a paid answer survived every reset), and a cache
added by a backend was invisible to it until someone remembered to edit here.
The measured clears are now ONE registry iteration::

    for backend in registry.iter_backends():
        summary.update(backend.reset())

Each adapter drops what its ``descriptor.cache_namespace`` owns and returns the
counts under the summary fields it publishes (``backends/algorithms/reset.py``,
``backends/ai/reset.py``); the reset advances each adapter's work generation
first, so a pin still in flight is refused by the owning adapter instead of
landing in a store that was just emptied. What stays HERE is what is not a
backend's cache: the per-item measured state, the proxy decode cache, the
in-memory Jev/VLM verdict projections on ``state`` and their header marker, the
profile-selector generation markers, the stored profile slots and the Stage-2
fingerprint.

**The reset is a HARD BARRIER** (owner decision 2026-10-26): the clear advances
two current-work tokens *before* it touches anything — ``_domain_epoch`` (the
judgment-domain token: AI / Jev / profile / series-priority / pairwise) and
``_analysis_epoch`` (the measured-metrics token: Stage-2 proxy, triage, the
per-stage producers). Every such worker snapshots its token at start and drops
its delivery when the token moved, so a result produced before the reset cannot
land afterwards in memory, on disk (``save_analysis`` / ``local_metrics.persist``)
or on a card. The in-flight ledgers (batch, phase markers, stage gate, judge
run, AI queue) are retired in the same step — see
``use_cases/reset_barrier.clear_delivery_ledgers``.

EVERY measurement cache is dropped, INCLUDING the Jev rank pins and the
tie-break briefs (``services.jev_cache`` / ``services.vlm_cache``) on disk and
their in-memory halves (``state.tie_breaks`` / ``state.series_priority`` plus
each item's ``vlm_tie_*`` / ``vlm_brief_*`` fields). The owner's order
(2026-10-22) is literal: the action zeroes all measured state without caveats.
The earlier version deliberately kept them ("their keys change anyway") and the
result read as a partial reset — a pinned rank or brief survived and looked
like a stale measurement.

The scope is the ACTION's, and it comes from the ONE resolver
(``use_cases.action_context.build_context``): a three-card selection zeroes
those three cards. Until 2026-10-27 this module forced the whole pool here
("a per-card reset leaves every other card's numbers in place, which is
indistinguishable from 'nothing happened'", owner report 2026-10-22) — but the
owner's newer report is the opposite experience: "Почему я выделил 3
изображения, а он экшн повесил на все, которые есть в вкладке?" A mass action
that silently widens to every card is the same defect class as
``next(iter(selected_paths))``, only in the other direction. The measured
stores are still swept whole (an adapter owns a namespace keyed by
series/pair/content identity, not by one card's path). The reset therefore
reports TWO scopes: the cards it cleared (``targets``/``pool`` in the result)
and the stores it swept for the WHOLE pool (``stores_scope="global"`` +
``stores``), stated once in log.txt at INFO — "выбрал 2 — обработалось 100"
must be readable from the log, not from this file. The pool-wide form remains
available to maintenance callers as ``clear_metrics_caches(owner)`` with
``paths=None``.

Audit-Meta: pattern=reset-barrier size=535 reason="one reset contract: the two current-work tokens, every in-memory/on-disk clear and the visible re-stamp must happen in ONE order (token first, then clear, then repaint); splitting them lets a delivery land between the steps — the exact defect the barrier removes."
"""

from __future__ import annotations

import logging
from pathlib import Path

from tabs.image_gallery.models import AnalysisStatus
from tabs.image_gallery.services.activity import clear_activity
from tabs.image_gallery.services.rank_badge import KIND_NONE, stamp_badges
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: What a reset sweeps for the WHOLE pool regardless of the action's card scope
#: (each adapter owns a namespace keyed by series/pair/content identity, so it
#: cannot delete "just this card's" rows). Named here once: the summary field
#: and the one INFO log line read the same list, so the two can never drift,
#: and a reader of the result never has to open this module to learn that
#: "2 of 100 cards" does not mean "2 cards' caches".
STORE_SCOPE_NAMES: tuple[str, ...] = (
    "scorecards",
    "metric_profiles",
    "metrics",
    "ranks",
    "pins",
)


def _state_of(owner):
    """The owner's gallery state (``owner.state``, else the widget's ``_state``).

    A controller in production owns ``state``, but the widget itself is a legal
    owner (storeless/live-menu paths) and carries ``_state`` instead — the same
    probe ``_items_of`` delegates to, so the in-memory half of a reset reaches
    the same object the cleared items came from.
    """
    try:
        st = getattr(owner, "state", None)
        if st is not None:
            return st
        widget = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
        if widget is None:
            return None
        return getattr(widget, "_state", None) or getattr(
            getattr(widget, "_controller", None), "state", None
        )
    except Exception:
        return None


def _items_of(owner) -> list:
    """The owner's pool items (``state.items`` first, widget fallback)."""
    try:
        return list(getattr(_state_of(owner), "items", None) or [])
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
        # Engine records + the k-draw scorecards are MEASUREMENTS too: leaving
        # them meant the read path (``analysis.read``) still answered from the
        # old pass after the reset (owner: "метрики остались").
        item.analysis_records = ()
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
        # Stage-3 VLM verdicts + briefs: a tie-break/compare answer is a
        # MEASUREMENT produced by the paid judge, so it goes with the rest.
        # ``vlm_brief_status`` returns to its dataclass default ("none"), not
        # to a "pending" state — the reset leaves nothing measuring.
        item.vlm_tie_result = None
        item.vlm_tie_pending = False
        item.vlm_tie_error = None
        item.vlm_brief = None
        item.vlm_brief_status = "none"
        item.vlm_brief_error = None
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
    (``ui/card/factory.py``), so mutating the items alone leaves the painted view
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


def _gallery_backends() -> tuple:
    """Every composed analysis backend, or ``()`` when the registry is unwired.

    The reset must not raise because an adapter could not be composed (the many
    owner doubles in the suite have no gallery plugin); the engine-side half of
    the reset still runs and the failure is traced.
    """
    try:
        from tabs.image_gallery.backends.composition import register_gallery_backends

        return tuple(register_gallery_backends())
    except Exception:
        logger.debug("metrics reset: backend composition failed", exc_info=True)
        return ()


def _ai_axis_set_snapshot(owner):
    """The AI slot's judge answer, or ``None`` (never raises).

    Read BEFORE the clear: the judge's axis set is a JUDGMENT about which
    dimensions matter, not one of the measurements a reset drops.
    """
    try:
        from tabs.image_gallery.services.metric_profile import (
            DOMAIN_AI,
            profile_for_domain,
        )

        profile = profile_for_domain(_state_of(owner), DOMAIN_AI)
    except Exception:
        logger.debug("metrics reset: AI axis set snapshot failed", exc_info=True)
        return None
    return profile if profile else None


def _keep_ai_axis_set(owner, profile) -> None:
    """Re-install *profile* into the AI slot after a reset cleared the slot.

    Owner rule 2026-10-27: «ручная очистка кеша — это сброс РЕЗУЛЬТАТОВ, а не
    оси». The live consequence of dropping it: 04:00:29 reset → 04:00:30 and
    04:00:37 ``analyze refused: no_profile``, twice, on a folder whose judge had
    named six axes seconds earlier. ``analyze`` needs the axis names to build a
    scorecard at all, so the reset made the AI backend unusable until something
    re-selected a profile — while nothing in the reset path asks the judge again
    (by design: the reset zeroes, it does not re-run).

    The MEASUREMENTS still go (scorecards, metrics, ranks, pins — including the
    on-disk profile pins, so nothing stale is re-served); only the in-memory
    answer of "which axes does this folder's judge read" survives, and the
    selector guards are re-opened, so a later settle may still replace it.
    Never raises.
    """
    if profile is None:
        return
    try:
        from tabs.image_gallery.backends.composition import backend
        from tabs.image_gallery.services.metric_profile import DOMAIN_AI

        backend(DOMAIN_AI).install(_state_of(owner), profile)
    except Exception:
        logger.debug("metrics reset: AI axis set restore failed", exc_info=True)
        return
    try:
        axes = list(getattr(profile, "axis_ids", ()) or ()) + [
            str(getattr(entry, "name", "") or "")
            for entry in (getattr(profile, "axis_entries", ()) or ())
        ]
        logger.debug(
            "[gallery] metrics reset: the judge's axis set kept (source=%s axes=%s) "
            "— a reset clears results, not the axes",
            getattr(profile, "source", "") or "?",
            ",".join(a for a in axes if a) or "-",
        )
    except Exception:
        pass


def clear_metrics_caches(owner, *, paths=None) -> dict:
    """Clear the measured-metrics caches (in-memory + disk). Never raises.

    *paths* narrows the per-item clear (the card menu passes its file-manager
    targets); ``None`` means every item of ``owner.state.items``. The MEASURED
    stores are always swept whole: each adapter owns a namespace keyed by
    series/pair/content identity, not by one card's path, so a scoped delete
    cannot express "drop the pins this card was part of" (the adapter's own
    ``reset`` is the only clear it offers). Returns an honest summary:
    ``{"items": n, "ai_files": n, "profiles": n, "jev_files": n,
    "vlm_files": n, "pairwise_verdicts": n}`` — the cache counts come from the
    adapters that dropped them, the item count from the per-item clear.

    TWO SCOPES, BOTH NAMED (owner report 2026-10-27: "выбрал 2 — обработалось
    100"): ``items`` counts the cards whose visible state was cleared
    (``paths``), while the measured stores are pool-wide by construction. The
    summary therefore also carries ``targets``/``pool`` (the two sizes), the
    target_scope ("targets" or "pool"), stores_scope ("global") and
    ``stores`` (:data:`STORE_SCOPE_NAMES`), and ONE INFO
    line states the same thing in log.txt — otherwise the widening was
    readable only from this docstring.

    Cleared items lose their metric-derived rank state AND their VLM verdict /
    brief fields (see :func:`_clear_item`); the in-memory verdict maps
    (``state.tie_breaks``, ``state.series_priority``) are emptied as well — the
    Jev hint through the controller's own seam, so the per-series attention
    marker is re-stamped too — and the bound cards are re-stamped unranked and
    repainted BEFORE this returns; a reset must look reset immediately, not
    after the async pass repaints.

    A HARD BARRIER: the first action advances both current-work tokens and
    retires the in-flight ledgers (``use_cases.reset_barrier`` /
    :func:`~tabs.image_gallery.use_cases.reset_barrier.clear_delivery_ledgers`),
    so no pre-reset delivery can land after this returns. The adapters' work
    generations are advanced in the same window (``backend.reset()`` below), which
    is what stops a worker-thread PIN — a write that never passes through a
    landing seam — from re-filling a store this call just emptied.
    """
    summary = {
        "items": 0,
        "ai_files": 0,
        "profiles": 0,
        "jev_files": 0,
        "vlm_files": 0,
        "pairwise_verdicts": 0,
    }
    # HARD BARRIER (owner decision 2026-10-26), BEFORE any clear: advance the
    # two current-work tokens and retire the in-flight ledgers. A delivery that
    # races the clear is stale from this line on, and the ledgers it would
    # consult (settled/phase/stage/judge/queue) no longer describe this world.
    from tabs.image_gallery.use_cases import reset_barrier as _reset_barrier

    # Read BEFORE the clear: the judge's axis set survives this reset (see
    # ``_keep_ai_axis_set``) — it is the one thing here that is a JUDGMENT
    # rather than a measurement.
    kept_ai_profile = _ai_axis_set_snapshot(owner)
    _reset_barrier.bump_delivery_epochs(owner)
    _reset_barrier.clear_delivery_ledgers(owner)
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
    # THE TWO SCOPES, recorded before the clear so a caller reads them from the
    # result instead of inferring them: ``targets`` are the cards whose visible
    # state goes, the measured stores below are swept for the whole pool.
    summary["targets"] = len(targets)
    summary["pool"] = len(items)
    summary["target_scope"] = "pool" if paths is None else "targets"
    summary["stores_scope"] = "global"
    summary["stores"] = list(STORE_SCOPE_NAMES)
    for it in targets:
        _clear_item(it)
        summary["items"] += 1

    # In-memory decode cache: the proxy pass re-decodes from scratch. Nobody's
    # judgment lives here (it is decoded pixels), so no adapter owns it.
    try:
        from tabs.image_gallery.services import proxy as _proxy

        _proxy.clear_proxy_cache()
    except Exception:
        logger.debug("metrics reset: proxy cache clear failed", exc_info=True)

    # THE MEASURED CACHES: one iteration, no cache name named here (ADR 009
    # wave A4). Each adapter advances its work generation first and then drops
    # every store its ``cache_namespace`` owns, reporting the counts under the
    # summary fields it publishes — so a cache added by a backend is reset by
    # construction rather than by remembering to edit this function.
    for backend in _gallery_backends():
        try:
            report = backend.reset() or {}
        except Exception:
            logger.debug(
                "metrics reset: backend %r reset failed",
                getattr(getattr(backend, "descriptor", None), "backend_id", "?"),
                exc_info=True,
            )
            continue
        for field, count in dict(report).items():
            try:
                summary[field] = summary.get(field, 0) + int(count or 0)
            except Exception:
                continue

    # The IN-MEMORY halves of the Jev/VLM stores. An open session paints the
    # pinned Jev ordering and the VLM verdicts from ``state`` without reading
    # disk again, so dropping the files alone left the stale measurements on
    # screen until the process restarted — the partial-reset complaint this
    # whole function exists to answer.
    try:
        st = _state_of(owner)
        if st is not None:
            st.tie_breaks = {}
            st.series_priority = {}
    except Exception:
        logger.debug("metrics reset: in-memory verdict clear failed", exc_info=True)
    # The Jev routing hint also paints a per-series-header attention marker, so
    # prefer the controller's own clear seam (it drops the hint AND re-stamps
    # the headers); ``state.series_priority`` above already covers owners that
    # have no such seam.
    try:
        clear_priority = getattr(owner, "_clear_series_priority", None)
        if callable(clear_priority):
            clear_priority()
    except Exception:
        logger.debug("metrics reset: series priority marker clear failed", exc_info=True)
    # The selection profile's generation markers: a reset re-opens the selector
    # for the SAME folder generation (the frozen/consumed guard would otherwise
    # suppress it after the first run). They are owner-side markers, not a
    # backend cache (the adapter owns the profile it produced, not the guard).
    try:
        owner._profile_consumed_gen = None
        owner._profile_settle_pending_gen = None
    except Exception:
        pass

    # Stored profile slots + the Stage-2 skip gate. The slots hold MetricProfiles,
    # not caches, and a profile DERIVED from the dropped measurements (the
    # Algorithms heuristic) must not survive them — it is re-derived a line later
    # by the owning pipeline. The AI slot is re-installed from the snapshot taken
    # above: its axis set is the judge's answer, not a measurement.
    try:
        clear = getattr(owner, "clear_metric_profile", None)
        if callable(clear):
            clear()
    except Exception:
        logger.debug("metrics reset: clear_metric_profile failed", exc_info=True)
    # ...and the judge's AXES come straight back: the measurements are what the
    # user asked to drop, not the answer to "which axes does this folder's
    # judge read". Without it the next Analyze refused "no_profile" (live
    # 04:00:30, right after a manual reset) although nothing was wrong with the
    # AI; with it, the re-entered pass builds scorecards for those same axes.
    _keep_ai_axis_set(owner, kept_ai_profile)
    try:
        owner._last_analysis_fingerprint = None
    except Exception:
        logger.debug("metrics reset: fingerprint clear failed", exc_info=True)

    # Visible reset LAST: the Algorithms slot holds the freshly (mode-derived)
    # offer while the AI slot keeps the judge's own axis set, so the refreshed
    # dots and Quick Look rows read the axis set each backend actually measures,
    # and the cards show the unranked/neutral state the re-entered pass starts
    # from.
    _refresh_cleared_view(owner, targets)
    # THE ONE PLAIN-LOG LINE (INFO — log.txt's default level). The owner's
    # "выбрал 2 — обработалось 100" was only explainable by reading the code:
    # the card count and the pool-wide store sweep were never in the same
    # sentence. Both sizes and the store list are stated here; the gated
    # ``gallery_debug`` line below keeps the per-cache counters for tracing.
    try:
        logger.info(
            "[gallery] metrics reset: %d of %d card(s) cleared (scope=%s); the "
            "measured stores were swept WHOLE — %s (%d scorecard, %d profile, "
            "%d jev, %d vlm, %d pairwise file(s)) — every non-target card keeps "
            "its items but loses those caches",
            len(targets),
            len(items),
            summary["target_scope"],
            "/".join(STORE_SCOPE_NAMES),
            summary["ai_files"],
            summary["profiles"],
            summary["jev_files"],
            summary["vlm_files"],
            summary["pairwise_verdicts"],
        )
    except Exception:
        pass
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(
            "metrics reset: scope=%s items=%d ai_files=%d profiles=%d "
            "jev_files=%d vlm_files=%d",
            "pool" if paths is None else f"{len(targets)} card(s)",
            summary["items"],
            summary["ai_files"],
            summary["profiles"],
            summary["jev_files"],
            summary["vlm_files"],
        )
    except Exception:
        pass
    return summary


def reset_metrics_caches(owner, *, paths=None) -> dict:
    """Clear the caches, then stop. Never raises.

    ``paths`` is the ACTION's scope, passed through verbatim: the menu /
    registry entries hand the resolved ``ActionContext.targets`` here, so a
    three-card selection zeroes three cards. ``paths=None`` (the whole pool) is
    now reached only by an explicit maintenance call — no per-card control
    passes it any more (owner report 2026-10-27: "Почему я выделил 3
    изображения, а он экшн повесил на все, которые есть в вкладке?"; the
    previous version forced ``paths=None`` here, so every entry that had
    correctly resolved a scope threw it away).

    OWNER DECISION 2026-10-22: the action ZEROES, it does not re-run. The
    earlier version re-entered the triage rebuild, so the numbers (and with them
    the AI/ALG marker) came back seconds later — or on the next repaint (opening
    and closing quick look) — which reads exactly like "the reset did not
    work". A reset now leaves an empty, unranked gallery; the ordinary triggers
    (open the folder, Analyze, the folder's next triage) recompute from scratch
    because the Stage-2 fingerprint and every disk cache were dropped.

    ``summary["requeued"]`` is kept for callers and is always ``False``.
    """
    summary = clear_metrics_caches(owner, paths=paths)
    summary["requeued"] = False
    return summary
