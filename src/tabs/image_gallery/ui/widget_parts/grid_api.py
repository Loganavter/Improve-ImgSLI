"""Grid API + series-view restore + card refresh for the gallery widget (plan Part B, Wave 3).

Audit-Meta: pattern=thin-owner-target size=exempt reason="grid API bodies extracted verbatim from ImageGalleryWidget (plan-gallery-split-2026-10-17 Part B Wave 3) - one widget-glue surface, splitting further would be a helpers bag"

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps same-named one-line
delegators so call sites and tests do not move. Fail-open like the
surrounding widget chrome.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.models import GalleryItem


def set_folder_label(owner, folder: Path) -> None:
    owner._folder_label.setText(str(folder))


def rebuild_grid(owner, items: list[GalleryItem]) -> None:
    had_items = bool(owner._items)
    # Snapshot the active series view — the flat rebuild below clears
    # grid_view._series (headers). Every triage action funnels through
    # here (toggle/make-best/keep-best/remove), so without a re-apply
    # any of them flattens the SERIES grouping.
    saved_series = None
    pre_paths: set[str] = set()
    try:
        gv = getattr(owner, "_grid_view", None)
        if gv is not None and getattr(gv, "_series", None) is not None:
            saved_series = (
                list(gv._series),
                list(getattr(gv, "_hub_names", []) or []),
                dict(getattr(gv, "_collapsed", {}) or {}),
            )
    except Exception:
        saved_series = None
    try:
        for it in (owner._items or []):
            pre_paths.add(str(getattr(it, "path", None)))
    except Exception:
        pass
    # Append fast-path: pure pool growth with a live series view keeps
    # every painted card/header in place (no flat teardown + restore —
    # that demolished headers twice per drop). New cards land in the
    # UNGROUPED tail via grid_view.append_new_cards; the imminent
    # background triage regroups once if clustering actually moved them.
    # Strict order check: old pool must appear first and unchanged
    # (reorders still take the full path).
    try:
        gv_fast = getattr(owner, "_grid_view", None)
        # Also allow the flat (pre-triage) case: a pure pool growth with
        # no live series view yet must still group the fresh card(s)
        # immediately (append_new_cards promotes the flat pool to one
        # UNGROUPED section) — bug 2, first-drop grouping delay.
        if pre_paths and (items or []):
            try:
                new_paths = [str(getattr(it, "path", None)) for it in list(items)]
                old_paths = [str(getattr(it, "path", None)) for it in list(owner._items or [])]
            except Exception:
                new_paths, old_paths = [], []
            if (
                len(new_paths) > len(old_paths)
                and gv_fast is not None
                and getattr(gv_fast, "_rebuild_pending", None) is None
                and [p for p in new_paths if p in set(old_paths)] == list(old_paths)
            ):
                try:
                    old_set = set(old_paths)
                    fresh = [it for it in list(items) if str(getattr(it, "path", None)) not in old_set]
                except Exception:
                    fresh = []
                if fresh:
                    owner._items = list(items)
                    _dbg(
                        "view-cycle rebuild n=%d append-fast-path new=%d",
                        len(owner._items),
                        len(fresh),
                    )
                    try:
                        gv_fast.append_new_cards(fresh)
                    except Exception:
                        gv_fast = None
                    if gv_fast is not None:
                        try:
                            for it in fresh:
                                card = gv_fast.card_for(it.path)
                                if card is not None:
                                    owner._cards[it.path] = card
                                    owner._card_labels[it.path] = card  # type: ignore[assignment]
                        except Exception:
                            pass
                        # Fresh cards are content-current from acquire;
                        # tooltips only (no sweep: selection untouched).
                        try:
                            for item in fresh:
                                owner._refresh_tooltip(item)
                        except Exception:
                            pass
                        try:
                            owner._install_quick_look_hooks()
                        except Exception:
                            pass
                        return
    except Exception:
        pass
    owner._items = list(items)
    try:
        owner._refresh_action_states()
    except Exception:
        pass
    _dbg("rebuild_grid n=%d branch=%s", len(owner._items), "empty" if not items else "grid")
    _dbg(
        "view-cycle rebuild n=%d saved_series=%s pre=%d",
        len(owner._items),
        "yes" if saved_series is not None else "no",
        len(pre_paths),
    )
    if not items:
        if had_items:
            # Emptied by removals (reject/Space/Delete) — files stay on
            # disk, so the pick-a-folder message would mislead.
            try:
                owner._empty_state.set_empty_message(owner._empty_view_text)
            except Exception:
                pass
            empty_text = owner._empty_view_text
        else:
            try:
                owner._empty_state.restore_empty_message()
            except Exception:
                pass
            empty_text = owner._empty_text
        owner._empty_state.set_state("empty")
        try:
            if hasattr(owner, "_content_stack"):
                owner._content_stack.setCurrentWidget(owner._empty_state)
            else:
                owner._empty_state.show()
                owner._grid_view.hide()
        except Exception:
            pass
        # Compat shim only (never in a layout — show() would pin it at
        # (0,0) over the corner). S0 visuals belong to _empty_state.
        owner._empty_label.setText(empty_text)
        owner._empty_label.hide()
        try:
            owner._grid_view.rebuild_grid([])
        except Exception:
            pass
        return
    owner._empty_state.set_state("ready")
    owner._empty_label.hide()
    try:
        if hasattr(owner, "_content_stack"):
            owner._content_stack.setCurrentWidget(owner._grid_view)
        else:
            owner._empty_state.hide()
            owner._grid_view.show()
    except Exception:
        pass
    try:
        try:
            owner._grid_view.rebuild_grid(
                items,
                paint_selection=saved_series is None,
                flat_ungrouped=saved_series is None,
            )
        except TypeError:
            # Legacy doubles predate the paint_selection kwarg.
            owner._grid_view.rebuild_grid(items)
    except Exception:
        pass
    # Keep compat dicts in sync with grid_view's pool
    owner._cards.clear()
    owner._card_labels.clear()
    for it in items:
        card = owner._grid_view.card_for(it.path)
        if card is not None:
            owner._cards[it.path] = card
            # card is Button, not QLabel — store dummy for refresh compatibility
            owner._card_labels[it.path] = card  # type: ignore[assignment]

    # Re-apply the series view snapshotted above (if clusters survive).
    # The restore paints via set_series when it acts (returns True) —
    # only a non-restored flat grid needs the post-build paint below.
    restored = False
    if saved_series is not None:
        try:
            restored = bool(owner._restore_series_view(saved_series, pre_paths=pre_paths))
        except Exception:
            restored = False
    if not restored:
        owner._refresh_rebuilt_cards(items, sweep=True)
        # Hook double-click → quick look (restored views hook inside).
        try:
            owner._install_quick_look_hooks()
        except Exception:
            pass


def _restore_series_view(owner, saved, pre_paths=None) -> bool:
    """Re-apply a series view snapshot taken before the flat rebuild.

    Clusters are pruned to current membership (removals); clusters
    shrinking below 2 members fall out — ``set_series`` lands their
    survivors in the UNGROUPED tail. When every cluster dissolved but
    items remain from the same pool (pure removal, e.g. deleted a
    whole group), survivors get an explicit UNGROUPED view instead of
    hanging header-less. A wholly new pool (folder switch — every
    alive path is new) also lands under one UNGROUPED section, so a
    fresh folder never paints nameless while triage runs.

    Returns True when the view was (re)painted via set_series.
    """
    try:
        series, hub_names, collapsed = saved
    except Exception:
        return
    alive: set[str] = set()
    for it in (owner._items or []):
        try:
            alive.add(str(it.path))
        except Exception:
            continue
    kept: list = []
    kept_hubs: list = []
    for idx, cl in enumerate(list(series or [])):
        try:
            members = [m for m in list(cl) if str(getattr(m, "path", None)) in alive]
        except Exception:
            continue
        if len(members) >= 2:
            kept.append(members)
            try:
                if idx < len(hub_names):
                    kept_hubs.append(hub_names[idx])
            except Exception:
                pass
    if not kept:
        # Every cluster dissolved. Same-pool removals (no brand-new
        # paths) → explicit UNGROUPED so survivors don't hang without
        # a series; replacement pool (folder switch) → stay flat.
        try:
            alive_paths = {str(getattr(it, "path", None)) for it in (owner._items or [])}
        except Exception:
            alive_paths = set(alive)
        if not alive_paths:
            _dbg("view-cycle restore dissolved pool=empty → empty-state")
            return False
        try:
            pre = set(pre_paths or set())
        except Exception:
            pre = set()
        try:
            added = set(alive_paths) - set(pre)
        except Exception:
            added = set()
        if added:
            _dbg("view-cycle restore dissolved added=%d → UNGROUPED (replacement pool)", len(added))
            try:
                owner._grid_view.set_series([], hub_names=[], collapsed={})
            except Exception:
                return False
            try:
                owner._series = []
            except Exception:
                pass
            return True
        _dbg("view-cycle restore dissolved same-pool → UNGROUPED n=%d", len(alive_paths))
        try:
            owner._grid_view.set_series([], hub_names=[], collapsed={})
        except Exception:
            return False
        try:
            owner._series = []
        except Exception:
            pass
        try:
            owner._stats_sync_after_dissolve()
        except Exception:
            pass
        try:
            owner._cards.clear()
            owner._card_labels.clear()
            for it in (owner._items or []):
                card = owner._grid_view.card_for(it.path)
                if card is not None:
                    owner._cards[it.path] = card
                    owner._card_labels[it.path] = card  # type: ignore[assignment]
        except Exception:
            pass
        try:
            for item in (owner._items or []):
                owner._refresh_tooltip(item)
        except Exception:
            pass
        try:
            owner._install_quick_look_hooks()
        except Exception:
            pass
        return True
    try:
        owner._series = [list(cl) for cl in kept]
    except Exception:
        pass
    try:
        collapsed = {int(k): bool(v) for k, v in dict(collapsed or {}).items() if 0 <= int(k) < len(kept)}
    except Exception:
        collapsed = {}
    _dbg("rebuild_grid restore series clusters=%d", len(kept))
    _dbg("view-cycle restore kept=%d alive=%d → set_series", len(kept), len(alive))
    try:
        owner._grid_view.set_series(kept, hub_names=kept_hubs, collapsed=collapsed)
    except Exception:
        return False
    try:
        owner._collapsed = dict(getattr(owner._grid_view, "_collapsed", {}) or collapsed)
    except Exception:
        pass
    # set_series recycled cards again — re-sync compat dicts (mirrors set_triage).
    try:
        owner._cards.clear()
        owner._card_labels.clear()
        for it in (owner._items or []):
            card = owner._grid_view.card_for(it.path)
            if card is not None:
                owner._cards[it.path] = card
                owner._card_labels[it.path] = card  # type: ignore[assignment]
    except Exception:
        pass
    # set_series already swept selection once — tooltips only (no O(N²)).
    try:
        for item in (owner._items or []):
            owner._refresh_tooltip(item)
    except Exception:
        pass
    try:
        owner._install_quick_look_hooks()
    except Exception:
        pass
    return True


def _sample_view_frame(owner) -> None:
    """TEMP-DIAG: log the painted signature on change (see __init__)."""
    try:
        gv = getattr(owner, "_grid_view", None)
        if gv is None:
            return
        try:
            cur = owner._content_stack.currentWidget()
            stack = type(cur).__name__
        except Exception:
            stack = "?"
        try:
            series = getattr(gv, "_series", None)
            series_n = None if series is None else len(series)
        except Exception:
            series_n = "?"
        try:
            headers = [(h, bool(h.isVisible())) for h in list(getattr(gv, "_series_headers", []) or [])]
            n_hdr_vis = sum(1 for _, v in headers if v)
        except Exception:
            n_hdr_vis = "?"
        try:
            cards = list(getattr(gv, "_cards_by_path", {}).values())
            n_cards_vis = sum(1 for c in cards if bool(c.isVisible()))
            n_cards = len(cards)
        except Exception:
            n_cards_vis, n_cards = "?", "?"
        sig = f"stack={stack} series={series_n} headers={n_hdr_vis} cards={n_cards_vis}/{n_cards}"
        if sig != getattr(owner, "_view_frame_sig", None):
            owner._view_frame_sig = sig
            _dbg("view-frame %s", sig)
    except Exception:
        pass


def _stats_sync_after_dissolve(owner) -> None:
    """Sync the stats strip after all series dissolved to UNGROUPED.

    The strip otherwise keeps showing the pre-removal series count
    next to a grid that has no SERIES headers left.
    """
    try:
        total = len(list(owner._items or []))
    except Exception:
        return
    try:
        owner.stats_strip.set_stats(int(total), 0, 0)
    except Exception:
        pass


def set_series_attention(owner, series_ids) -> None:
    """Forward the cross-series routing hint to the grid (series-header marker).

    Additive: it never changes a card, its rank or the selection.
    """
    try:
        owner._grid_view.set_series_attention(series_ids)
    except Exception:
        pass


def set_rank_provenance(owner, source: str | None = None, *, domain: str | None = None) -> None:
    """Show which ranker produced the series ranks (stats-strip chip).

    *source* is a ``rank_source`` token (``fusion``/``jev``/``manual``); when
    absent, *domain* ("algorithms"|"ai") picks the label. The strip hides the
    chip when neither is known (never a fabricated ranker).
    """
    try:
        owner.stats_strip.set_rank_provenance(source, domain=domain)
    except Exception:
        pass


def refresh_card(owner, item: GalleryItem) -> None:
    # Re-stamp the display badge (rank/source may have changed since the
    # last triage) before the card renders it — same single computation.
    try:
        from tabs.image_gallery.services.rank_badge import stamp_badges

        stamp_badges([item], getattr(owner, "_source_path", None))
    except Exception:
        pass
    # Delegate to grid_view (Button region update)
    try:
        owner._grid_view.refresh_card(item)
    except Exception:
        pass
    # Also handle legacy QLabel thumb path if present (for tests that inspect thumb)
    thumb = owner._card_labels.get(item.path)
    # If thumb is actually a Button, grid_view already handled pixmap; no QLabel logic needed.
    # Keep tooltip logic for Button cards
    owner._refresh_tooltip(item)


def _refresh_tooltip(owner, item: GalleryItem) -> None:
    """Sync the card tooltip for *item* (no content update, no sweep)."""
    try:
        card = owner._cards.get(item.path) or owner._grid_view.card_for(item.path)
    except Exception:
        return
    if card is not None:
        try:
            # Single line: the full file name (the analysis second line was
            # removed — a hover tooltip must not add extra lines).
            card.setToolTip(str(item.name))
        except Exception:
            pass


def _refresh_rebuilt_cards(owner, items, *, sweep: bool) -> None:
    """Post-(re)build paint without the O(N²) sweep cascade.

    Content is already current from the acquire/update pass — only
    tooltips (stale on pool-recycled cards) plus a single selection
    sweep. Replaces per-item ``refresh_card`` loops, each of which
    re-swept selection over the whole grid.
    """
    try:
        for item in list(items or []):
            owner._refresh_tooltip(item)
    except Exception:
        pass
    if sweep:
        try:
            owner._grid_view.apply_selection(None)
        except Exception:
            pass


def refresh_cards(owner, items) -> None:
    """Batch passthrough to ``grid_view.refresh_cards`` (single selection sweep).

    Falls back to per-card refresh when the grid view predates the batch
    API (tests with stubbed grid views). Single-card semantics (incl.
    the legacy tooltip tail) live in ``refresh_card``.
    """
    try:
        from tabs.image_gallery.services.rank_badge import stamp_badges

        stamp_badges(list(items or []), getattr(owner, "_source_path", None))
    except Exception:
        pass
    try:
        batch = getattr(owner._grid_view, "refresh_cards", None)
        if callable(batch):
            batch(items)
            return
    except Exception:
        pass
    try:
        for item in list(items or []):
            owner.refresh_card(item)
    except Exception:
        pass


def sync_source_badge(owner, source) -> None:
    """Move the SOURCE badge the instant the source changes.

    A source change is a pure badge move, so it must not be chained to
    the heavy comparison pass: ``stamp_badges`` is cheap (no decode, no
    Qt) and only the two affected cards — the previous and the new
    source — need a repaint. The background fidelity pass then re-stamps
    everything in ``set_triage`` when it lands. Without this, pressing
    "Make source" showed the old badge until every item had been
    compared against the new source.
    """
    try:
        try:
            old = getattr(owner, "_source_path", None)
        except Exception:
            old = None
        try:
            new = Path(source) if source is not None else None
        except Exception:
            new = None
        try:
            owner._source_path = new
        except Exception:
            pass
        from tabs.image_gallery.services.rank_badge import stamp_badges

        items: list = []
        try:
            items.extend(list(owner._items or []))
        except Exception:
            pass
        try:
            for cluster in getattr(owner, "_series", None) or []:
                items.extend(list(cluster))
        except Exception:
            pass
        stamp_badges(items, new)
        want = {str(p) for p in (old, new) if p is not None}
        if not want:
            return
        changed = []
        seen: set[str] = set()
        for item in items:
            try:
                key = str(getattr(item, "path", ""))
            except Exception:
                continue
            if key in want and key not in seen:
                seen.add(key)
                changed.append(item)
        if changed:
            owner.refresh_cards(changed)
    except Exception:
        pass


def set_card_visible(owner, path: Path, visible: bool) -> None:
    try:
        owner._grid_view.set_card_visible(path, visible)
    except Exception:
        pass
    card = owner._cards.get(path)
    if card is not None:
        try:
            card.setVisible(visible)
        except Exception:
            pass
