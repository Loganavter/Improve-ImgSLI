"""AI analyze / judgment-domain + analysis delivery for the Image Gallery (Wave 4).
Audit-Meta: pattern=thin-owner-target size=exempt reason="one analysis delivery + domain + re-analyze-offer concern over the owner; the offer shares the same action context and the same scorecard state as delivery"

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the analysis DELIVERY + domain cluster: cache hydration
(``hydrate_cached_analysis`` / ``_hydrate_ai_cache``), the judgment-domain
authority writer + toolbar switch (``_set_judgment_domain`` /
``activate_judgment_domain``), the bounded visible-item trigger
(``_run_ai_for_visible``), the worker delivery tail (``_begin_analysis`` /
``_apply_ai_phase`` / ``_on_analysis_ready`` / ``_refresh_open_quick_look`` /
``_on_analysis_error``) and the pairwise refinement of the AI domain's order
(``start_pairwise_refinement`` / ``_on_pairwise_ready``, off the GUI thread on
the SAME pool as the judge; refused off the AI domain) and its terminal-rank
trigger (``dispatch_pairwise_refinement``). The analyze ENTRY points (``analyze`` /
``reanalyze`` and the deprecated point adapters) live in
``use_cases/ai_analyze.py`` and are re-exported here for their callers
(file-size policy, same wave).
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
import time
from functools import partial
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
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
# Judge-run budget (bodies in ``use_cases/judge_budget.py``): the estimate, the
# per-run call ceiling and the run-level 429 parking live in their own
# use_cases module (file-size policy); this module consumes the three helpers
# its own call sites need and nothing else.
from tabs.image_gallery.use_cases.judge_budget import (
    _park_rate_limited_card,
    _release_judge_call,
    _reserve_judge_call,
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
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


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


#: GUI-thread budget for ONE hydrate batch. The settle runs this pass right
#: after the metrics land — i.e. exactly while the user is scrolling a folder
#: whose cards just appeared. One disk read + JSON parse per item is cheap, a
#: large folder is not, and the pass used to run the whole list in one event-loop
#: turn. Over budget it continues on the next turn instead of holding the loop.
#: Deliberately NOT a worker: the settle tails must not rank before the reads
#: are in, and a left-behind item is filled by the cache-first HIT in
#: ``analyze()`` (``use_cases/ai_analyze.py:183``) on the same turn, so the
#: bounded batch keeps the ordering while shortening the stall.
_HYDRATE_BUDGET_MS = 8.0


def _hydrate_ai_cache(
    owner, items, *, ctx: ActionContext | None = None, budget_ms: float | None = None
) -> int:
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
    on restore. Never raises; returns how many items were filled so far.

    ``budget_ms`` bounds one GUI-thread batch (default
    ``_HYDRATE_BUDGET_MS``); the remainder is resumed on the next event-loop
    turn and dropped when the folder generation moved meanwhile. At least one
    item always runs per batch, so a tight budget cannot starve the pass.
    """
    try:
        from tabs.image_gallery.services.ai_cache import hydrate_item
    except Exception:
        return 0
    identity = analysis_identity_for(owner, ctx=ctx)
    try:
        budget = _HYDRATE_BUDGET_MS if budget_ms is None else max(0.0, float(budget_ms))
    except (TypeError, ValueError):
        budget = _HYDRATE_BUDGET_MS
    try:
        gen = int(getattr(owner, "_folder_gen", 0) or 0)
    except Exception:
        gen = 0
    filled_total = [0]

    def _repaint(filled_items: list) -> None:
        # A hydrated item is a NEW read for every surface: the card's dots and
        # its AI/ALG marker are derived at update time, and the open quick-look
        # report holds a row set. Without this repaint the data was present but
        # the view showed the pre-hydration state until an unrelated event
        # (owner 2026-10-22: the marker appeared only after opening and closing
        # quick look; the same staleness read as "reset did nothing").
        try:
            owner.widget.refresh_cards(filled_items)
        except Exception:
            for it in filled_items:
                try:
                    owner.widget.refresh_card(it)
                except Exception:
                    pass
        try:
            refresh_ql = getattr(owner, "_refresh_open_quick_look", None)
            if callable(refresh_ql):
                refresh_ql()
        except Exception:
            logger.debug("hydrate: quick-look refresh failed", exc_info=True)

    def _batch(pending: list) -> None:
        deadline = time.monotonic() + budget / 1000.0
        filled_items: list = []
        rest: list = []
        for index, it in enumerate(pending):
            # ``index`` 0 always runs: a zero budget must not degenerate into an
            # endless chain of single-item event-loop turns.
            if index and time.monotonic() >= deadline:
                rest = pending[index:]
                break
            try:
                if getattr(it, "analysis", None) is not None:
                    continue
                if hydrate_item(it, identity):
                    filled_total[0] += 1
                    filled_items.append(it)
            except Exception:
                continue
        if filled_items:
            _repaint(filled_items)
        if not rest:
            return
        if QCoreApplication.instance() is None:
            # No event loop to come back to (headless unit call): finish now —
            # the bound is a GUI-latency fix, not a throughput one.
            _batch(rest)
            return
        QTimer.singleShot(0, lambda: _resume(rest))

    def _resume(rest: list) -> None:
        try:
            if int(getattr(owner, "_folder_gen", 0) or 0) != gen:
                return  # folder switched: the rest belongs to a dead pool
        except Exception:
            return
        _batch(rest)

    _batch(list(items or []))
    return filled_total[0]


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


def domain_epoch(owner) -> int:
    """The controller's judgment-domain epoch (the AI work's cancellation token).

    ``owner._domain_epoch`` advances every time the toolbar actually changes the
    domain. Work scheduled under a different epoch belongs to a backend the user
    has left: it must neither be sent nor applied (measured live 2026-10-22:
    four VLM POSTs went out after a switch back to Algorithms, and a late Jev
    outcome re-crowned the series under Algorithms).
    """
    try:
        return int(getattr(owner, "_domain_epoch", 0) or 0)
    except Exception:
        return 0


def analysis_epoch(owner) -> int:
    """The owner's measured-metrics epoch (the RESET's cancellation token).

    ``owner._analysis_epoch`` advances on every ``cache_reset.clear_metrics_caches``
    — a reset is a hard barrier: a result produced before it must not land after
    it (memory, disk, card). ``_domain_epoch`` covers the judgment-backed work
    (AI / Jev / profile); Stage-2 proxy chunks, triage and the per-stage metric
    producers have no domain, so they snapshot THIS token in their worker
    closure and compare it at landing. Created lazily (``getattr`` default) so
    the many owner doubles keep working.
    """
    try:
        return int(getattr(owner, "_analysis_epoch", 0) or 0)
    except Exception:
        return 0


def _analysis_epoch_is_current(owner, epoch: int | None) -> bool:
    """True when *epoch* still describes the live measured-metrics pass.

    ``epoch=None`` is an unversioned caller (a direct call in a legacy test or
    a double that never owned the ledger): treated as current, the same rule
    ``_epoch_is_current`` applies to its own ``epoch=None``. This is the ONE
    place the reset barrier is decided for non-domain work.
    """
    if epoch is None:
        return True
    return analysis_epoch(owner) == int(epoch)


def _epoch_is_current(owner, epoch: int | None, *, domain: str | None = "ai") -> bool:
    """True when *epoch* still describes the live judgment domain.

    ``epoch=None`` means an unversioned caller (a fake controller in a legacy
    test): it is treated as current so nothing that never knew about the epoch
    starts failing. An owner without ``_judgment_domain`` is a legacy double
    that never owned the authority — also current. This is the ONE place the
    analysis-domain gate is decided (contract G10: no ad-hoc domain comparisons
    at call sites).
    """
    if epoch is not None and domain_epoch(owner) != int(epoch):
        return False
    if domain is None:
        return True
    try:
        live = getattr(owner, "_judgment_domain", None)
    except Exception:
        live = None
    if live is None:
        return True
    return str(live).strip().lower() == domain


def _set_judgment_domain(owner, domain: str) -> str:
    """The ONLY writer of the judgment domain (Algorithms vs AI).

    ``owner._judgment_domain`` is the single authority and survives the
    ``GalleryState`` rebuilds done by open_folder / append / clear_to_empty;
    ``state.judgment_domain``/``state.rank_domain`` are read-only projections
    kept for rendering. Invalid input raises (no coercion); returns the
    normalized value. Every call bumps ``owner._domain_epoch`` — the toolbar
    suppresses a same-domain emit, so a call here is an explicit (re)activation
    and cancelling the previous epoch's queued work is the correct semantics.
    """
    dom = _require_domain(domain)
    try:
        owner._domain_epoch = int(getattr(owner, "_domain_epoch", 0) or 0) + 1
    except Exception:
        pass
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
        # NO pairwise pass here: the A/B refinement is AI work and runs only
        # while the AI domain owns the order (owner decision 2026-10-26). The
        # Algorithms backend must issue ZERO network calls, so this switch's
        # explicit trigger is gone — the terminal-rank tail of the AI domain
        # (:func:`dispatch_pairwise_refinement`) is the ONE production trigger.
        return
    # Owner rule 2026-10-26 (measured live, 07:05): the AXIS SET must be the
    # judge's, so the analysis may not start on the heuristic profile and freeze
    # it — ``_mark_profile_consumed`` then makes the selector skip ("frozen for
    # gen N"), and the folder keeps sharpness/exposure/clipping/... forever. Ask
    # for the profile FIRST; its single release resumes the analysis tail
    # (``_resume_settle_after_profile`` → ``_run_ai_on_settle``). When the profile
    # is already resolved (vlm pin / consumed / no selector) nothing is pending
    # and the analysis runs here, exactly as before.
    kick = getattr(owner, "_run_profile_select_on_settle", None)
    if callable(kick):
        try:
            kick()
        except Exception:
            logger.debug("profile kick on the AI switch failed", exc_info=True)
    try:
        pending = getattr(owner, "_profile_settle_pending_gen", None)
        deferred = pending is not None and int(pending) == int(
            getattr(owner, "_folder_gen", -1)
        )
    except Exception:
        deferred = False
    if deferred:
        _ai_debug(
            "domain switch: the analysis waits for the axis profile (gen=%s)",
            getattr(owner, "_folder_gen", "?"),
        )
        return
    # Cache-first, never re-derive: items that already carry a scorecard (any
    # backend's cached read) are skipped by ``_run_ai_for_visible``; only a card
    # the AI has never seen is analyzed. A switch must not re-run the other
    # backend, but it must still produce the AI read on a first switch.
    try:
        owner._run_ai_for_visible(cache_only=False)
    except TypeError:
        owner._run_ai_for_visible()
    # The terminal ranker, guarded by the batch ledger: a switch that started
    # analyses waits for the LAST one instead of ranking a partial matrix
    # (plan-gallery-ai-judgement P3-A). A cache-only switch (nothing in flight)
    # dispatches here and now.
    _dispatch_terminal_rank(owner)
    owner._run_series_priority()


# -- pairwise refinement of a near-tie top set (board 2026-10-25) -------------
#
# The pointwise judge cannot order near-identical variants (54-68% order flips
# across draws), so ``use_cases/pairwise_rank`` asks A/B in both orders and
# derives an order from complete comparisons. This is the WIRING: when a
# pointwise order has just been applied to the live series, a series whose
# top-set spread is inside the near-tie threshold may refine it.
#
# Why here and not per scoring arrival: the pass needs the pointwise ORDER
# (its top-N is the displayed order), which only exists once the ranks are
# applied. The pairwise pass is the AI backend's own refinement (owner decision
# 2026-10-26): it runs only while the AI domain owns the order
# (:func:`dispatch_pairwise_refinement` and :func:`start_pairwise_refinement`
# both refuse off it), and the Algorithms backend never schedules it.
#
# ONE trigger site, AFTER the pointwise order is in place: the TERMINAL-RANK
# tail (``analysis_batch.dispatch_terminal_rank`` →
# :func:`dispatch_pairwise_refinement`), which the AI domain reaches from the
# settle of an analysis batch and from the toolbar switch to ``ai``. The old
# explicit trigger on the switch back to Algorithms was removed with the owner
# decision — that switch must not cause a network call.
#
# The trigger is NOT inside ``_apply_fusion_ranks``: that primitive is how THIS
# pass applies its own result (``pairwise_order=`` forwards into
# ``rank_series``), so a trigger there would re-enter itself on every apply —
# one pass per apply, forever. The trigger sits one level above it, on the
# fact "the pointwise ranking settled for this folder generation".
#
# ONE pass per (folder generation, series), single-flight: the slot is claimed
# before the worker is scheduled and released by its result/error/finish
# handler, and a folder switch drops the closed generation's slots exactly like
# the analysis batch (``analysis_batch.begin``/``end``) — so a stale in-flight
# pass can neither block the new folder nor apply across it.
#
# Threading: the blocking A/B requests run on the SAME pool the pointwise judge
# uses (``owner._tracked`` + ``owner._pool_start`` + ``GenericWorker``) — no
# second executor, no QThread, and the GUI thread never waits for the provider.
# The gates that cost nothing (flag off / < 2 measured / decided) are decided
# BEFORE a worker exists (``pairwise_rank.precheck``), so a skipped series
# cannot even occupy a pool slot.
#
# Fail open, always to the pointwise order: a refused reservation, an
# unavailable client, a transport/parse failure or an exception on the worker
# leaves every rank exactly as it was — a pairwise failure never cancels,
# retries or mutates the pointwise results and never becomes a card error.


def _pairwise_error(owner, exc_name: str, *, detail: str = "") -> None:
    """Trace the fail-open path (pointwise order kept, nothing marked failed)."""
    _ai_debug(
        "judge_pairwise.skip reason=error exc=%s detail=%s order_kept=pointwise",
        exc_name,
        detail or "none",
    )


def _pairwise_trace_once(owner, line: str, *args) -> None:
    """Emit a per-run trace line at most once (one run = one folder generation).

    The disabled gate is evaluated per series, on every domain switch and on
    every terminal-rank tail; the contract is ONE line per run, not one per
    series/switch/arrival.
    """
    try:
        gen = int(getattr(owner, "_folder_gen", 0) or 0)
    except Exception:
        gen = 0
    try:
        seen = getattr(owner, "_pairwise_skip_gen", None)
        if seen is not None and int(seen) == gen:
            return
    except Exception:
        pass
    _ai_debug(line, *args)
    try:
        owner._pairwise_skip_gen = gen
    except Exception:
        pass


def _pairwise_series_key(entry, members) -> str:
    """Identity of ONE series for the single-flight slot.

    ``Series.id`` is the regroup identity (stable across a re-apply of the same
    group); a double/legacy entry without one falls back to its member paths,
    which is the same identity the pass would be scheduled over.
    """
    try:
        sid = getattr(entry, "id", None)
        if sid:
            return f"id:{sid}"
    except Exception:
        pass
    try:
        return "members:" + "|".join(
            sorted(str(getattr(m, "path", "")) for m in members or ())
        )
    except Exception:
        return f"entry:{id(entry)}"


def _pairwise_slots(owner) -> dict:
    """The in-flight registry: ``{folder generation: {series key, ...}}``.

    An owner attribute (the same style as ``_pairwise_skip_gen`` /
    ``_pairwise_order_paths``): one run's slots die with it, and a folder
    generation never inherits the previous one's (see :func:`_pairwise_claim`).
    A double that cannot hold attributes simply never claims, i.e. it keeps the
    pre-single-flight behaviour.
    """
    slots = getattr(owner, "_pairwise_inflight", None)
    if isinstance(slots, dict):
        return slots
    slots = {}
    try:
        owner._pairwise_inflight = slots
    except Exception:
        pass
    return slots


def _pairwise_claim(owner, gen: int, key: str) -> bool:
    """Claim the ``(gen, series)`` slot; False when a pass is already in flight.

    The FIRST claim of a new folder generation drops the previous generation's
    slots — the same rule as ``analysis_batch.begin``/``end``: a pass scheduled
    for a folder the user has left must not block the new folder's series, and
    its late result is dropped by ``_on_pairwise_ready`` on its own.
    """
    try:
        g = int(gen)
    except (TypeError, ValueError):
        g = 0
    slots = _pairwise_slots(owner)
    keys = slots.get(g)
    if keys is None:
        slots.clear()
        keys = set()
        slots[g] = keys
    if key in keys:
        return False
    keys.add(key)
    return True


def _pairwise_release(owner, gen, key) -> None:
    """Free the ``(gen, series)`` slot after the pass reported (never raises)."""
    if key is None:
        return
    try:
        g = int(gen if gen is not None else 0)
    except (TypeError, ValueError):
        return
    slots = _pairwise_slots(owner)
    keys = slots.get(g)
    if not keys:
        return
    keys.discard(key)
    if not keys:
        slots.pop(g, None)


def _series_members(owner, entry) -> list:
    """Members of one series entry (the owner's reader, else ``entry.members``)."""
    try:
        resolve = getattr(owner, "_section_members", None)
        if callable(resolve):
            return list(resolve(entry) or ())
    except Exception:
        pass
    try:
        return list(getattr(entry, "members", None) or ())
    except Exception:
        return []


def start_pairwise_refinement(owner, *, series=None, judge=None) -> bool:
    """Refine the AI domain's near-tie order with A/B comparisons (never blocking).

    AI domain ONLY (owner decision 2026-10-26): the pairwise pass is VLM work
    refining a VLM order, so it belongs to the AI backend. Off that domain it
    returns False BEFORE reading settings, building a client, claiming a slot or
    touching the pool — the Algorithms backend issues zero network calls
    (``_epoch_is_current`` is the ONE domain gate, contract G10).

    Returns True when at least one comparison pass was scheduled. *judge* is the
    test seam (a scripted callable); ``None`` builds the production one from the
    settings row — credentials only, no request.
    """
    # Gate 0, before anything else: the live domain owns this pass. Under
    # ``algorithms`` there is nothing of the model's to refine — the fusion rank
    # is the deterministic backend's own measured result.
    if not _epoch_is_current(owner, None, domain="ai"):
        _ai_debug(
            "judge_pairwise.skip reason=domain domain=algorithms order_kept=pointwise"
        )
        return False
    try:
        gen = int(getattr(owner, "_folder_gen", 0) or 0)
    except Exception:
        gen = 0
    epoch = domain_epoch(owner)
    try:
        mode = getattr(getattr(owner, "state", None), "mode", None)
    except Exception:
        mode = None
    # Pairwise is a CAPABILITY, not a shared feature (ADR 009 A3): the pass is
    # VLM work that spends per compared pair, so the request goes to the AI
    # adapter's descriptor instead of assuming every backend can refine a
    # near-tie order. Asking the Algorithms adapter the same question is
    # ``CapabilityNotDeclared`` (``pairwise_backend("algorithms")``) — the
    # refusal is a typed answer, not a convention this call site re-checks.
    try:
        from tabs.image_gallery.backends.composition import pairwise_backend
        from tabs.image_gallery.backends.errors import BackendContractError
        from tabs.image_gallery.services.metric_profile import DOMAIN_AI

        adapter = pairwise_backend(DOMAIN_AI)
    except BackendContractError:
        _ai_debug(
            "judge_pairwise.skip reason=capability order_kept=pointwise "
            "(backend did not declare pairwise)"
        )
        return False
    try:
        profile = adapter.load_profile(getattr(owner, "state", None))
    except Exception:
        profile = None
    if profile is None:
        # No profile-free door for the AI domain (free-axes W4 / ADR 009 A3):
        # this pass ranks the judge's axes, and the local mode mapping is not a
        # profile of this backend — there is no axis set to compare, so nothing
        # is scheduled. The typed `NoProfileYet` is the fusion's own answer
        # (`rank_series(domain="ai")`); this use case translates it into "not
        # ready" exactly like the Jev/priority paths do, with a trace line.
        _ai_debug("judge_pairwise.skip reason=no-profile order_kept=pointwise")
        return False

    try:
        settings = _load_settings(owner)
    except Exception as exc:
        _pairwise_error(owner, type(exc).__name__, detail="settings load failed")
        return False
    if settings is None:
        _pairwise_error(owner, "SettingsUnavailable", detail="no AiSettings row")
        return False

    # Gate 1, before anything else: the flag is the user's opt-in (Settings → AI
    # → "Refine near-ties pairwise"), OFF by default — so this is the normal
    # path: no worker, no call, ONE trace line per run.
    if not bool(getattr(settings, "pairwise_enabled", False)):
        _pairwise_trace_once(
            owner,
            "judge_pairwise.skip reason=disabled enabled=False order_kept=pointwise",
        )
        return False

    from tabs.image_gallery.services.rank_fusion import rank_series
    from tabs.image_gallery.use_cases.pairwise_rank import (
        build_client_judge,
        precheck,
        run_pairwise_pass,
    )

    client = judge
    if client is None:
        # Judge for this row, or None when the row names no usable provider: an
        # unavailable client is the ERROR path (fail open), never a crash.
        try:
            client = build_client_judge(settings, mode=mode, profile=profile)
        except Exception as exc:
            _pairwise_error(owner, type(exc).__name__, detail="judge build failed")
            return False
    if client is None:
        _pairwise_error(owner, "ProviderUnavailable", detail="AI row not usable")
        return False

    pool = getattr(owner, "_pool_start", None)
    if not callable(pool):
        return False
    try:
        groups = list(
            series
            if series is not None
            else (getattr(owner.state, "series", None) or ())
        )
    except Exception:
        groups = []
    try:
        cap = int(getattr(owner, "_AI_VISIBLE_CAP", 0) or 0) or 4
    except Exception:
        cap = 4
    tracked = getattr(owner, "_tracked", None)
    scheduled = 0
    for entry in groups:
        if scheduled >= cap:
            break
        members = _series_members(owner, entry)
        if not members:
            continue
        try:
            pointwise = rank_series(members, mode=mode, profile=profile, domain=DOMAIN_AI)
        except Exception:
            continue
        # FREE gates (off / too_small / unmeasured / decided), traced by the
        # library itself: a skipped series never gets a pool slot.
        skip = precheck(
            owner,
            members,
            pointwise_ranks=pointwise,
            settings=settings,
            mode=mode,
            profile=profile,
            domain=DOMAIN_AI,
        )
        if skip is not None:
            continue
        # Single-flight per (folder generation, series): the terminal-rank tail
        # re-enters this on every settled batch and every metrics settle, so
        # without the slot a pass already comparing these members would be
        # scheduled again by the next trigger (the verdict cache would make it
        # free, not harmless).
        key = _pairwise_series_key(entry, members)
        if not _pairwise_claim(owner, gen, key):
            continue

        def _job(_members=members, _pointwise=pointwise, _client=client):
            return run_pairwise_pass(
                owner,
                _members,
                pointwise_ranks=_pointwise,
                mode=mode,
                profile=profile,
                domain=DOMAIN_AI,
                settings=settings,
                judge=_client,
            )

        worker = GenericWorker(tracked(_job) if callable(tracked) else _job)
        worker.signals.result.connect(
            lambda order, g=gen, e=epoch, m=mode, k=key: _on_pairwise_ready(
                owner, order, gen=g, epoch=e, mode=m, series_key=k
            )
        )
        worker.signals.error.connect(
            lambda err, g=gen, e=epoch, k=key: _on_pairwise_error(
                owner, err, gen=g, epoch=e, series_key=k
            )
        )
        # A job that reports no ``result`` would otherwise hold the slot for the
        # rest of the run; ``finished`` always fires, and the release is
        # idempotent (the result/error handlers may already have freed it).
        worker.signals.finished.connect(lambda g=gen, k=key: _pairwise_release(owner, g, k))
        try:
            pool(worker, None)
        except Exception:
            _pairwise_release(owner, gen, key)
            _pairwise_error(owner, "PoolStartFailed", detail="worker not scheduled")
            continue
        scheduled += 1
    return scheduled > 0


def dispatch_pairwise_refinement(owner) -> bool:
    """Start the pass from the terminal-rank tail — AI domain ONLY.

    ``analysis_batch.dispatch_terminal_rank`` calls this once the batch has
    settled (its own ``pending()`` refusal is the "the matrix is complete"
    gate) and after the ranker ran. The pass refines the ORDER OF THE DOMAIN
    THAT OWNS IT: the VLM pairwise comparison is AI work (owner decision
    2026-10-26), so the order it refines and applies is the AI domain's. Before
    that decision this tail ran under ``algorithms`` and spent judge calls on
    the deterministic fusion order — the "AI work under Algorithms" leak.

    Three gates, all free (no worker, no HTTP), in this order:

    * the AI domain OWNS the order — under ``algorithms`` the displayed order
      is the measured fusion rank and no comparison may be built, scheduled or
      sent (:func:`_epoch_is_current` is the ONE domain gate, contract G10);
    * the measurements pass SETTLED for the current folder generation — the
      same finality stamp ``_apply_fusion_ranks`` uses to mark a winner. Before
      it, the members carry no measured quality and the pass could only answer
      too_small; the settle itself re-enters here (``_run_jev_on_settle`` runs
      after the fusion re-derive), so nothing is lost by refusing;
    * whatever :func:`start_pairwise_refinement` decides (flag, client,
      near-tie, budget) — the pass never raises into the rank path and never
      blocks: :func:`_pairwise_error` is the fail-open seam.

    Returns True when at least one comparison pass was scheduled.
    """
    if not _epoch_is_current(owner, None, domain="ai"):
        _ai_debug("judge_pairwise.skip reason=domain order_kept=pointwise")
        return False
    try:
        settled = int(getattr(owner, "_metrics_settled_gen", -1)) == int(
            getattr(owner, "_folder_gen", 0) or 0
        )
    except Exception:
        settled = False
    if not settled:
        _ai_debug(
            "judge_pairwise.skip reason=not-settled order_kept=pointwise"
        )
        return False
    try:
        return bool(start_pairwise_refinement(owner))
    except Exception as exc:
        _pairwise_error(owner, type(exc).__name__, detail="pairwise trigger failed")
        return False


def _remember_pairwise_paths(owner, paths: tuple[str, ...], gen: int) -> tuple[str, ...]:
    """Accumulate the applied pairwise orders of ONE run (several series).

    Each series produces its own order; ``_apply_fusion_ranks`` re-derives every
    group on every apply, so the union must be kept — otherwise the last
    finished series would silently drop the refinement of the others.
    """
    try:
        seen = getattr(owner, "_pairwise_order_gen", None)
        current: list[str] = []
        if seen is not None and int(seen) == int(gen):
            current = [str(path) for path in (getattr(owner, "_pairwise_order_paths", ()) or ())]
        merged = tuple(dict.fromkeys(current + [str(path) for path in paths]))
        owner._pairwise_order_gen = int(gen)
        owner._pairwise_order_paths = merged
        return merged
    except Exception:
        return paths


def _on_pairwise_ready(
    owner, order, *, gen=None, epoch=None, mode=None, series_key=None
) -> None:
    """Apply a finished pass through the ONE rank primitive (ranks only)."""
    # Free the single-flight slot FIRST: every path below (stale gen, moved
    # domain, unused order, applied order) ends this pass, and a slot left
    # behind would silently disable refinement for the rest of the run.
    _pairwise_release(owner, gen, series_key)
    if gen is not None:
        try:
            if not owner._is_current_folder_gen(gen):
                _ai_debug("judge_pairwise dropped: folder changed while in flight")
                return
        except Exception:
            pass
    if not _epoch_is_current(owner, epoch, domain="ai"):
        _ai_debug("judge_pairwise dropped: judgment domain changed while in flight")
        return
    reason = str(getattr(order, "reason", "") or "")
    if not bool(getattr(order, "applied", False)):
        # A transport/parse failure reaches here as an UNRESOLVED comparison set
        # (the library never defaults a winner from a silent judge). The gates
        # that legitimately skip (disabled/too_small/unmeasured/decided) and the
        # ceiling refusal already traced themselves.
        if reason == "incomplete":
            _pairwise_error(
                owner, "IncompleteComparison", detail="unanswered presentation"
            )
        elif reason == "not-configured":
            _pairwise_error(owner, "ProviderUnavailable", detail="judge unavailable")
        return
    order_paths = tuple(getattr(order, "order_paths", ()) or ())
    if len(order_paths) < 2:
        return
    try:
        live = getattr(owner.state, "series", None)
    except Exception:
        live = None
    merged = _remember_pairwise_paths(owner, order_paths, gen if gen is not None else 0)
    try:
        owner._apply_fusion_ranks(live, mode=mode, pairwise_order=merged)
    except Exception as exc:
        _pairwise_error(owner, type(exc).__name__, detail="rank apply failed")
        return
    _ai_debug(
        "judge_pairwise.apply pairs=%d calls=%d cached=%d order=%s",
        len(getattr(order, "verdicts", ()) or ()),
        int(getattr(order, "calls", 0) or 0),
        int(getattr(order, "cached", 0) or 0),
        " > ".join(order_paths),
    )


def _on_pairwise_error(owner, error_info, *, gen=None, epoch=None, series_key=None) -> None:
    """Worker exception → fail open; the pointwise ranks are never touched."""
    _pairwise_release(owner, gen, series_key)
    if gen is not None:
        try:
            if not owner._is_current_folder_gen(gen):
                return
        except Exception:
            pass
    try:
        exc_type = error_info[0] if error_info else None
    except Exception:
        exc_type = None
    name = getattr(exc_type, "__name__", None) or type(exc_type).__name__
    _pairwise_error(owner, str(name), detail="comparison pass raised")


def _scope_log_line(scope, picked: int) -> str:
    """The switch/settle's ONE plain-log line, cap and drop count included.

    ``Scope.reason`` already names ``action=``/``kind=``/``n=``/``source=`` and,
    on the capped visible branch, ``cap=``/``available=``. It used to reach
    ``logger.debug`` only, so log.txt at the default INFO level said nothing
    about a 12-of-20 pass — the "выбрал 100 — те же 12, молча" half of the
    2026-10-27 report. The DROPPED count is stated here rather than left as
    subtraction for the reader; the resolver owns the numbers, this function
    only spells them out.
    """
    reason = str(getattr(scope, "reason", "") or "")
    cap = available = None
    for token in reason.split():
        if token.startswith("cap="):
            try:
                cap = int(token[len("cap=") :])
            except ValueError:
                cap = None
        elif token.startswith("available="):
            try:
                available = int(token[len("available=") :])
            except ValueError:
                available = None
    line = f"picked={picked} {reason}".strip()
    if cap and available is not None and available > cap:
        line = f"{line} dropped={available - cap} (cap={cap} of available={available})"
    return line


def _run_ai_for_visible(owner, *, cache_only: bool = False) -> None:
    """Analyze the AI tail's scope: THE SELECTION, else the capped viewport.

    Rule 7 (owner report 2026-10-27: *"и наоборот"* — a hundred cards selected,
    twelve analyzed): the switch/settle used to analyze ``visible ∩ 12``
    regardless of the selection. The scope now comes from the ONE resolver
    (``action_scope``, kind selection_else_visible): the selection wins when
    it is non-empty, otherwise the viewport is analyzed up to the owner's cap.
    The cap is never silent — ``Scope.reason`` carries ``cap=``/``available=``,
    :func:`_scope_log_line` adds the drop count, and that line is logged at
    INFO so log.txt states it without ``--debug``. An unlaid-out grid with no
    selection is a refusal instead of a fail-open to the pool.

    ``cache_only`` is the DOMAIN-SWITCH path: switching backends must not spend
    a new request on metrics the other backend already produced (owner order
    2026-10-22). It hydrates the disk cache for the picked items and returns —
    live analysis belongs to the folder's settle / an explicit analyze, not to
    flipping a switch.
    """
    from tabs.image_gallery.use_cases import action_scope

    scope = action_scope.resolve_scope(owner, "gallery.domain.switch")
    if scope.refused or not scope.targets:
        logger.info("[gallery] AI pass: nothing to do — %s", _scope_log_line(scope, 0))
        return
    keys = {str(p) for p in scope.targets}
    picked: list = []
    try:
        items = list(getattr(owner.state, "items", None) or [])
    except Exception:
        items = []
    for it in items:
        try:
            if str(it.path) not in keys:
                continue
            status = getattr(it, "analysis_status", None)
            if status in (AnalysisStatus.DONE, AnalysisStatus.PENDING):
                continue
        except Exception:
            continue
        picked.append(it)
    if not picked:
        logger.info(
            "[gallery] AI pass: nothing left to analyze — %s",
            _scope_log_line(scope, 0),
        )
        return
    logger.info("[gallery] AI pass: %s", _scope_log_line(scope, len(picked)))
    if cache_only:
        hydrate = getattr(owner, "_hydrate_ai_cache", None)
        try:
            if callable(hydrate):
                hydrate(picked)
            else:
                _hydrate_ai_cache(owner, picked)
        except Exception:
            logger.debug("domain switch: cache-only hydrate failed", exc_info=True)
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
    # A queued flush can run after the toolbar already left the AI domain (the
    # switch is asynchronous): never open a batch slot for work the user has
    # switched away from.
    if not _epoch_is_current(owner, None):
        _ai_debug("analyze skipped: judgment domain is not ai")
        return
    settings = _load_settings(owner)
    if not _is_configured(settings):
        _mark_not_configured(owner, [item])
        return
    # The user's VLM upload edge is ALSO the per-card payload ceiling (defect B2:
    # the setting reached only the tie-break / Ask-AI paths, so a card shipped
    # full-resolution bytes — measured 9.29 MB for one 2400-px PNG, three times
    # per card at ``sample_count`` = 3). Cheap: an int on a worker-shared
    # module global, read by ``ai_client.request.resolve_wire_max_edge``.
    try:
        from tabs.image_gallery.services.vlm import set_vlm_max_edge

        set_vlm_max_edge(settings.vlm_max_edge_px)
    except Exception:
        logger.debug("VLM wire edge apply failed", exc_info=True)

    # Run budget (board 2026-10-24): the estimate was stated when the run began;
    # here the hard ceiling is enforced per card (a card costs ``sample_count``
    # calls, so the stop lands on a whole card). A refused card is NOT sent and
    # is NOT an error: it stays analyzable and sits on the run's continue list.
    if not _reserve_judge_call(owner, item, settings):
        try:
            set_activity(item, ActivityPhase.WAITING, "ai")
            owner.widget.refresh_card(item)
        except Exception:
            pass
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
    # The domain epoch THIS request belongs to: checked again immediately before
    # the worker runs (the last gate before the network call — ``_run_ai_for_visible``
    # queues many workers in one turn, so a switch can land between scheduling and
    # sending, measured live 2026-10-22) and once more when the reply arrives.
    epoch = domain_epoch(owner)
    worker = GenericWorker(
        owner._tracked(partial(_send_if_current, owner, epoch)),
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
        samples=int(getattr(settings, "sample_count", 3) or 3),
        temperature=float(getattr(settings, "sampling_temperature", 0.0) or 0.0),
        seed=int(getattr(settings, "sampling_seed", 0) or 0),
    )
    gen = owner._folder_gen
    # ``bridge=bridge`` keeps the phase relay alive until the worker reports.
    # The module function is called directly (the controller forwarder is pure
    # delegation but does not carry the request identity, and controller.py is
    # outside this task's scope): the identity must survive the worker hop.
    worker.signals.result.connect(
        lambda result, path=item.path, mtime_ns=item.mtime_ns, g=gen, bridge=bridge, identity=identity, e=epoch: _on_analysis_ready(
            owner, path, mtime_ns, result, g, identity=identity, epoch=e
        )
    )
    worker.signals.error.connect(
        lambda err, path=item.path, g=gen, bridge=bridge, e=epoch: _on_analysis_error(
            owner, path, err, g, epoch=e
        )
    )
    set_activity(item, ActivityPhase.CLAIMED, "ai")
    owner.widget.refresh_card(item)
    owner._pool_start(worker, None)


def _apply_ai_phase(owner, item: GalleryItem, phase: str) -> None:
    """UI-thread sink for worker phase emits; drops phases of stale items."""
    if owner._find_item(item.path) is not item:
        return
    # A repeated phase is not a content change: k draws each emit ``waiting``, and
    # every ``refresh_card`` re-runs the grid's selection sweep — on the same GUI
    # thread a wheel notch is served from (measured 2026-10-22, the CPU half of
    # the scroll contention). ``set_activity`` still refreshes the phase TTL, and
    # the pulse driver repaints the pill on its own tick, so only the redundant
    # full-card refresh is dropped.
    if not set_activity(item, phase, "ai"):
        return
    owner.widget.refresh_card(item)


def _send_if_current(owner, epoch: int, path: Path, **kwargs):
    """The LAST gate before the network call.

    ``_run_ai_for_visible`` queues many workers in one turn; a toolbar switch can
    land between scheduling and sending (measured live 2026-10-22: four VLM POSTs
    went out AFTER the switch back to Algorithms). The worker runs this wrapper,
    so the epoch is re-checked on the worker thread immediately before the
    request is built.

    It is also the run-level admission seam (board 2026-10-24): the provider
    gate (:func:`scheduler.await_ai_queue`) blocks this WORKER while a 429 has
    paused the whole run, and :class:`scheduler.ai_provider_slot` caps how many
    requests are actually in flight at the configured ``judge_concurrency``
    (never ``os.cpu_count()``).
    """
    if not _epoch_is_current(owner, epoch):
        _ai_debug("analyze cancelled before send: judgment domain changed path=%s", path)
        return None
    from tabs.image_gallery.use_cases.scheduler import ai_provider_slot, await_ai_queue

    if await_ai_queue(owner):
        _ai_debug("send resumed after a rate-limit pause path=%s", path)
        # A pause can outlive the domain that queued this card.
        if not _epoch_is_current(owner, epoch):
            return None
    with ai_provider_slot():
        return analyze_image_sync(path, **kwargs)


def _cancel_pending_analysis(owner, path: Path) -> None:
    """Release a batch slot whose AI work was cancelled by a domain switch.

    The item goes back to NOT_ANALYZED (no error, no scorecard) so a later
    switch back to AI retries it cache-first. Never dispatches the terminal
    rank — the domain the user returned to owns the ordering.
    """
    item = None
    try:
        item = owner._find_item(path)
    except Exception:
        item = None
    if item is not None:
        try:
            if getattr(item, "analysis_status", None) == AnalysisStatus.PENDING:
                item.analysis_status = AnalysisStatus.NOT_ANALYZED
                item.analysis_error = None
                set_activity(item, ActivityPhase.IDLE, "ai")
                owner.widget.refresh_card(item)
        except Exception:
            logger.debug("cancelled analysis cleanup failed", exc_info=True)
    _ai_batch_end(owner)
    _refresh_ranks_visible(owner)
    _release_judge_call(owner)


def _on_analysis_ready(owner, path: Path, mtime_ns: int, result, gen: int | None = None, identity: dict | None = None, epoch: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late analysis dropped
    if result is None:
        # The pre-send gate refused (the domain changed before the payload was
        # built): nothing was sent, nothing to apply.
        _cancel_pending_analysis(owner, path)
        return
    if not _epoch_is_current(owner, epoch):
        # The reply belongs to a backend the user has left: it must not reach the
        # cache, the card, or the rank (measured live 2026-10-22).
        _ai_debug(
            "analysis dropped: judgment domain changed while in flight (epoch=%s)",
            epoch,
        )
        _cancel_pending_analysis(owner, path)
        return
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
    _release_judge_call(owner)


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


def _on_analysis_error(owner, path: Path, error_info, gen: int | None = None, epoch: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return
    if not _epoch_is_current(owner, epoch):
        # A failure of work that belonged to the previous backend is not a fact
        # about the current one: no error card under Algorithms.
        _cancel_pending_analysis(owner, path)
        return
    item = owner._find_item(path)
    if item is None:
        return
    exctype, value, _tb = error_info
    # Run-level 429 (board 2026-10-24): ONE rate-limited request pauses the
    # whole queue and the card is re-queued after the pause — it never becomes
    # an error on the first 429 (the transport already retried in-thread).
    if isinstance(value, AiRateLimitError) or (
        isinstance(exctype, type) and issubclass(exctype, AiRateLimitError)
    ):
        if _park_rate_limited_card(owner, item, value):
            _refresh_ranks_visible(owner)
            return
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
    _release_judge_call(owner)


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
        # The viewport read is the ONE scope mechanism (kind ``visible``): it
        # intersects the filter and REFUSES an unlaid-out grid instead of
        # failing open to the pool (rule 5).
        try:
            from tabs.image_gallery.use_cases import action_scope

            visible_scope = action_scope.resolve_scope(owner, "gallery.reanalyze.visible")
            keys = {str(p) for p in visible_scope.targets}
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

