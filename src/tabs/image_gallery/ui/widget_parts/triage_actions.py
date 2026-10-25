"""Triage actions + series-view paint for the gallery widget (plan Part B, Wave 4).

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps same-named one-line
delegators so call sites and tests do not move. Fail-open like the
surrounding widget chrome.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.debug import gallery_debug as _dbg


def _on_keep_best(owner) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        _triage.keep_best_of_series(owner._owner_for_triage())
    except Exception:
        pass


def _on_show_all(owner) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        _triage.show_all(owner._owner_for_triage())
    except Exception:
        pass


def _on_clean_rejected(owner) -> None:
    try:
        # Prefer S3 overlay if rejected items exist.
        _triage_owner = owner._owner_for_triage()
        # Check rejected count.
        n = 0
        try:
            from tabs.image_gallery.use_cases.triage import is_rejected as _is_rejected

            st = getattr(_triage_owner, "state", None) or getattr(owner, "_state", None)
            items = list(getattr(st, "items", []) or []) if st is not None else list(owner._items or [])
            n = sum(1 for it in items if _is_rejected(it))
        except Exception:
            n = 0
        if n > 0:
            owner.show_clean_review(_triage_owner)
        else:
            from tabs.image_gallery.use_cases import triage as _triage

            _triage.clean_rejected(_triage_owner)
    except Exception:
        pass


def _on_compare_finalists(owner) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        _triage.compare_finalists(owner._owner_for_triage())
    except Exception:
        pass


def _series_view_matches(owner, norm_series, prev_mode, prev_source, mode, source) -> bool:
    """True when the painted series view already equals the incoming one.

    Compares ordered cluster membership (path strings), the UNGROUPED
    tail derived from ``owner._items``, object identity per path (fresh
    objects need card refresh, not a skip), plus mode/source (dot
    palette + strip label depend on them). Lets repeat triage over an
    unchanged pool skip the full card recycle.
    """
    try:
        if mode != prev_mode:
            return False
    except Exception:
        return False
    try:
        if str(source) != str(prev_source):
            return False
    except Exception:
        return False
    try:
        gv = getattr(owner, "_grid_view", None)
        if gv is None:
            return False
        cur_clusters = [list(cl) for cl in (getattr(gv, "_series", None) or [])]
        new_clusters = [list(cl) for cl in (norm_series or []) if len(list(cl)) >= 2]
        if len(cur_clusters) != len(new_clusters):
            return False
        try:
            by_path = {}
            for it in (owner._items or []):
                try:
                    by_path[str(it.path)] = it
                except Exception:
                    continue
        except Exception:
            by_path = {}
        for cur_cl, new_cl in zip(cur_clusters, new_clusters):
            try:
                cur_paths = [str(getattr(m, "path", None)) for m in list(cur_cl)]
                new_paths = [str(getattr(m, "path", None)) for m in list(new_cl)]
            except Exception:
                return False
            if cur_paths != new_paths:
                return False
            for m in list(new_cl):
                try:
                    if m is not by_path.get(str(getattr(m, "path", None))):
                        return False
                except Exception:
                    return False
        try:
            cur_members = {p for cl in cur_clusters for p in [str(getattr(m, "path", None)) for m in list(cl)]}
            new_members = {p for cl in new_clusters for p in [str(getattr(m, "path", None)) for m in list(cl)]}
            cur_all = set(by_path)
        except Exception:
            return False
        if cur_members != new_members:
            return False
        if (cur_all - cur_members) != (cur_all - new_members):
            return False
        return True
    except Exception:
        return False


def _rebuild_series_view(owner, norm_series, hub_names, collapsed) -> None:
    """Paint the series-grouped grid (extracted from set_triage)."""
    try:
        if norm_series:
            owner._grid_view.set_series(norm_series, hub_names=hub_names, collapsed=collapsed)
            # Sync collapsed back (grid may have normalized)
            try:
                owner._collapsed = dict(getattr(owner._grid_view, "_collapsed", {}) or collapsed)
            except Exception:
                pass
        else:
            # No series: show UNGROUPED header for all items (real_design.md:59)
            owner._grid_view.set_series([], hub_names=[], collapsed=collapsed)
        # set_scanning hid the grid for S1 — S2 content exists again, show it
        if owner._items or norm_series:
            try:
                if hasattr(owner, "_content_stack"):
                    owner._content_stack.setCurrentWidget(owner._grid_view)
                else:
                    owner._grid_view.show()
            except Exception:
                pass
        # Keep compat dicts in sync after series rebuild
        owner._cards.clear()
        owner._card_labels.clear()
        for it in (owner._items or []):
            card = owner._grid_view.card_for(it.path)
            if card is not None:
                owner._cards[it.path] = card
                owner._card_labels[it.path] = card  # type: ignore[assignment]
        # Re-hook double-click for newly pooled cards
        try:
            owner._install_quick_look_hooks()
        except Exception:
            pass
    except Exception:
        pass


def _refresh_action_states(owner) -> None:
    """Gate Keep best / Compare finalists on live content (fail-open).

    Keep best needs a 2+ survivor cluster (or show-mode, where the
    button reads "Show all"); compare needs 2+ surviving items.
    Anything unresolvable leaves the buttons as-is (never strand a
    live action disabled, never arm a dead one on error).
    """
    try:
        strip = owner.stats_strip
        items = list(getattr(owner, "_items", None) or [])
        series = list(getattr(owner, "_series", None) or [])
    except Exception:
        return

    def _members(cluster):
        if hasattr(cluster, "members"):
            return list(getattr(cluster, "members", None) or [])
        try:
            return list(cluster)
        except Exception:
            return []

    def _alive(members) -> int:
        try:
            from tabs.image_gallery.use_cases.triage import is_rejected as _is_rejected
        except Exception:
            _is_rejected = None  # type: ignore[assignment]
        count = 0
        for m in members or []:
            try:
                if _is_rejected is None or not _is_rejected(m):
                    count += 1
            except Exception:
                count += 1
        return count

    try:
        keep_mode = str(getattr(strip, "_keep_mode", "keep") or "keep")
    except Exception:
        keep_mode = "keep"
    try:
        keep = keep_mode.strip().lower().startswith("show") or any(
            _alive(_members(cl)) >= 2 for cl in series if len(_members(cl)) >= 2
        )
    except Exception:
        return
    try:
        compare = _alive(items) >= 2
    except Exception:
        return
    try:
        strip.set_action_states(keep_best=keep, compare_finalists=compare)
    except Exception:
        pass


def set_triage(owner, series, mode, source) -> None:
    """Stage 2: update stats strip + series-grouped grid.

    *series* — list of clusters (each ≥2) as ``list[list[GalleryItem]]``
    or ``list[Series]``. Singles are derived as items not in any cluster
    and shown under an ``UNGROUPED`` tail. *mode* is ``fidelity`` |
    ``camera`` | ``batch_synthetic`` and *source* is the hub/source file
    for fidelity mode.
    """
    norm_series: list[list] = []
    try:
        if series is None:
            norm_series = []
        else:
            for entry in list(series):
                # Accept Series dataclass (has .members) or plain list.
                if hasattr(entry, "members"):
                    members = list(getattr(entry, "members") or [])
                else:
                    members = list(entry) if isinstance(entry, (list, tuple)) else [entry]
                if members:
                    norm_series.append(members)
    except Exception:
        norm_series = []

    # Sorting is a VIEW property: re-apply the toolbar's CURRENT sort on every
    # (re)build, not only when the combo changes. A fresh folder/list used to
    # ignore the selected sort until the user toggled it (owner report
    # 2026-10-22). Idempotent — ``_on_sort_changed`` sorts, then calls here.
    try:
        from tabs.image_gallery.ui.widget_parts import view_prefs as _vp

        _keyfunc = _vp.sort_keyfunc(owner, _vp.current_sort_text(owner))
        if _keyfunc is not None:
            norm_series = _vp.sort_series(owner, norm_series, _keyfunc)
            try:
                _members = {str(it.path) for cl in norm_series for it in cl}
            except Exception:
                _members = set()
            try:
                _tail = [
                    it for it in list(owner._items or ())
                    if str(getattr(it, "path", "")) not in _members
                ]
            except Exception:
                _tail = []
            try:
                owner._items = [it for cl in norm_series for it in cl] + _vp.sort_items(
                    owner, _tail, _keyfunc
                )
            except Exception:
                pass
    except Exception:
        pass
    try:
        owner._series = list(norm_series)
    except Exception:
        owner._series = []
    try:
        prev_mode = owner._mode
    except Exception:
        prev_mode = None
    try:
        prev_source = owner._source_path
    except Exception:
        prev_source = None
    owner._mode = mode
    try:
        owner._source_path = Path(source) if source is not None else None
    except Exception:
        owner._source_path = None
    # Single source of truth for the display badge: compute it ONCE here
    # (triage/mode/source all converge in set_triage) so every surface
    # renders item.badge verbatim and never re-derives it.
    try:
        from tabs.image_gallery.services.rank_badge import stamp_badges

        _all_items = list(owner._items or [])
        for _cluster in norm_series:
            _all_items.extend(_cluster)
        stamp_badges(_all_items, owner._source_path, show_rank=bool(getattr(owner, "_ranks_visible", True)))
    except Exception:
        pass
    try:
        view_unchanged = owner._series_view_matches(
            norm_series, prev_mode, prev_source, mode, source
        )
    except Exception:
        view_unchanged = False

    # Stats strip — "40 images · 7 series · 33 redundant" synced with grid (real_design §2.3)
    try:
        filtered = [cl for cl in norm_series if len(cl) >= 2]
        series_cnt = len(filtered)
        try:
            member_paths = {str(it.path) for cl in filtered for it in cl}
        except Exception:
            member_paths = set()
        # Total synced: prefer grid contents (series+ungrouped) over stale _items
        if filtered:
            try:
                # ungrouped from _items or derived
                if owner._items:
                    ungrouped_cnt = sum(1 for it in owner._items if str(it.path) not in member_paths)
                else:
                    ungrouped_cnt = 0
                total = sum(len(cl) for cl in filtered) + int(ungrouped_cnt)
            except Exception:
                total = len(owner._items) if isinstance(owner._items, list) else sum(len(cl) for cl in filtered)
        else:
            total = len(owner._items) if isinstance(owner._items, list) else 0
            ungrouped_cnt = total  # all ungrouped when no series
            # but spec expects UNGROUPED · N header, so series 0
        redundant = max(0, int(total) - int(series_cnt) - int(ungrouped_cnt)) if total else 0
        # When total from _items mismatches series (e.g. _items 1 but series 2), recompute total from series
        try:
            series_total = sum(len(cl) for cl in filtered) + int(ungrouped_cnt)
            if series_total > total:
                total = series_total
                redundant = max(0, int(total) - int(series_cnt) - int(ungrouped_cnt))
        except Exception:
            pass
        # Live rejected count
        rejected_n = 0
        try:
            from tabs.image_gallery.use_cases.triage import is_rejected as _is_rejected

            rejected_n = sum(1 for it in (owner._items or []) if _is_rejected(it))
        except Exception:
            pass
        owner.stats_strip.set_stats(total, series_cnt, redundant)
        owner.stats_strip.set_rejected_count(rejected_n)
        try:
            from tabs.image_gallery.use_cases.triage import should_show_all as _should_show_all

            groups = [cl for cl in (filtered or []) if len(cl) >= 2]
            if not groups:
                # Flat fallback: group grid items by series_id.
                try:
                    from tabs.image_gallery.use_cases.triage import _flat_series_groups

                    groups = _flat_series_groups(owner._items or [])
                except Exception:
                    groups = []
            owner.stats_strip.set_keep_mode(
                "show" if _should_show_all(owner._items or [], groups) else "keep"
            )
        except Exception:
            pass
        owner.stats_strip.set_mode(str(mode or "fidelity"), owner._source_path)
        owner.stats_strip.show()
    except Exception:
        pass
    try:
        owner._refresh_action_states()
    except Exception:
        pass

    # Hub names + collapsed for grid_view (A1 parity: SERIES i · hub · n VARIANTS ▼)
    hub_names = owner._compute_series_hub_names(norm_series)

    # Ensure collapsed dict persists
    try:
        collapsed = dict(getattr(owner, "_collapsed", {}) or {})
    except Exception:
        collapsed = {}

    # Series-grouped grid — headers only for clusters ≥2, singles under UNGROUPED tail.
    # Identical re-triage (append/change that moved nothing) skips the
    # full recycle: stats above already synced, cards are current.
    if view_unchanged:
        _dbg("set_triage skip rebuild: view identical")
        _dbg("view-cycle triage series=%d → skip (identical)", len([cl for cl in norm_series if len(cl) >= 2]))
    else:
        _dbg(
            "view-cycle triage series=%d → rebuild",
            len([cl for cl in norm_series if len(cl) >= 2]),
        )
        try:
            owner._rebuild_series_view(norm_series, hub_names, collapsed)
        except Exception:
            pass
    # No setStyleSheet — painter pipeline owns visuals.
    # Mark triage done (S2) — toolbar ✓
    try:
        owner.set_triage_done()
    except Exception:
        pass


def show_clean_review(owner, _triage_owner=None) -> None:
    """Open S3 clean review overlay (TopLevelInWindowOverlay + Toast Undo)."""
    try:
        from tabs.image_gallery.ui.clean_review import CleanReviewOverlay

        actual_owner = _triage_owner if _triage_owner is not None else owner._owner_for_triage()
        # Ensure overlay exists. Owner travels via constructor / show_for
        # (both take owner) — never re-poked afterwards (G2 contract).
        _ctx = getattr(owner, "_context", None)
        _tr = getattr(_ctx, "_tr", None) if _ctx is not None else None
        overlay = getattr(owner, "_clean_overlay", None)
        if overlay is None:
            parent = owner.window() or owner
            overlay = CleanReviewOverlay(parent, actual_owner, translate=_tr)
            owner._clean_overlay = overlay
        elif _tr is not None:
            # Created before a language switch: re-apply the current tr.
            try:
                overlay.retranslate(_tr)
            except Exception:
                pass
        overlay.show_for(actual_owner)
    except Exception:
        pass


# -- judge-run continue affordance (board 2026-10-24) -------------------------
# A call ceiling stops ONE AI pass and parks the cards it refused
# (``use_cases/judge_budget``). The catalogue row lives in
# ``use_cases/registration.judge_continue_descriptor``; the strip's button reads
# the SAME two controller attributes through these functions, so the visible and
# catalogue affordances cannot disagree.


def _triage_controller(owner):
    """The object the judge-run flag is read from (attached controller, or owner).

    ``_owner_for_triage`` is the widget's documented resolver (attached
    controller first, itself when unattached) — never a parent walk.
    """
    resolver = getattr(owner, "_owner_for_triage", None)
    if callable(resolver):
        try:
            resolved = resolver()
        except Exception:
            resolved = None
        if resolved is not None:
            return resolved
    return owner


def _judge_continue_state(owner) -> tuple[bool, int]:
    """``(available, parked)`` read from the controller ledger — never a copy.

    Same predicate/count the catalogue row uses, so a click here and Find
    Action cannot disagree about whether a run is parked.
    """
    ctrl = _triage_controller(owner)
    try:
        if not bool(getattr(ctrl, "judge_run_continue_available", False)):
            return False, 0
        parked = int(getattr(ctrl, "judge_run_parked_count", 0) or 0)
    except Exception:
        return False, 0
    return True, max(0, parked)


def _on_continue_judge(owner) -> None:
    """Click target of the strip's continue button: run the registered action.

    Dispatched by ID through ``use_cases.registration.run_action`` so the
    visible control and Find Action run the SAME handler — which owns the
    "nothing parked" refusal and never starts a fresh pass.
    """
    try:
        from tabs.image_gallery.use_cases import registration as _registration

        _registration.run_action(_triage_controller(owner), "gallery.continue-judge")
    except Exception:
        pass
