"""Popup builder for the gallery card context menu.

Right-click on a card opens a standard toolkit ``ContextMenu`` under the
cursor (``popup_at(QCursor.pos())``). The menu merges two groups:

1. Selection section (ex-HUD flyout: Analyze / Find similar) — shown only
   when a non-empty selection exists. No "clear selection" entry by design
   — deselect is Esc, menus offer actions ON the set.
2. Per-card actions mirroring the hover capsule: Make best / Reject /
   Remove from view (+ Make source, every mode), plus the manual
   grouping pair — Ungroup (dissolve into the tail) and Group (pin the
   menu-rule targets into a brand-new series; multi-select only, hidden
   when the selection is already exactly one whole series) — and the
   maintenance entry Reset metrics cache (drop the measured caches and
   re-run the pass; no confirm/undo, the recompute is the feedback).
   Make best / Reject / Remove from view apply to the whole selection when
   the clicked card is selected (file-manager rule), else to the clicked
   card alone.
   The Reject entry tracks state: all targets rejected → "Unreject",
   otherwise "Reject".
   "Remove from view" drops the card from the grid (file on disk
   stays); selection actions never touch the grid — hence the
   separator between the sections.

Compare/Move were removed from this menu (carry flows live in the stats strip
and keyboard paths; carrying to another tab is drag-only). Split out of
``ui/card/context_menu.py`` per the module→package split
(``plan-gallery-split-2026-10-17``).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from tabs.image_gallery.icons import Icon
from tabs.image_gallery.ui.card.context_actions import (
    _ctx_make_best,
    _ctx_remove,
    _ctx_set_source,
    _ctx_toggle_reject,
)
from tabs.image_gallery.ui.card.menu_track import track_open_menu
from tabs.image_gallery.use_cases import gallery_actions

from .icons import _menu_icon
from .predicates import (
    _is_source,
    _selection_label,
    _targets_all_rejected,
    _targets_any_grouped,
    _targets_are_single_series,
)
from .translator import _resolve_menu_translator, _t

def _require_target_callback(name: str, cb) -> None:
    """Fail closed: a scope callback must accept the resolved targets list.

    The menu owns scope, so a zero-arg callable (the bypass this contract
    removes) raises at menu-build time, never gets called with no arguments.
    Un-introspectable callables (C builtins) are trusted, not rejected.
    """
    if not callable(cb):
        raise TypeError(f"{name} must be callable and take the resolved targets")
    try:
        signature = inspect.signature(cb)
    except (TypeError, ValueError):
        return
    try:
        signature.bind([])
    except TypeError as exc:
        raise ValueError(
            f"{name} must accept the resolved targets (one positional argument); "
            "the menu resolves the scope — a zero-arg callback would pick its own"
        ) from exc


def popup_gallery_card_context_menu(  # type: ignore[no-untyped-def]
    card,
    owner,
    path: Path,
    global_pos=None,
    mode=None,
    *,
    selection_count: int | None = None,
    on_carry=None,
    on_analyze=None,
    on_find_similar=None,
    on_ask_ai=None,
    translate=None,
):
    """Popup toolkit ``ContextMenu`` for gallery card at *global_pos*.

    THE SCOPE IS THE MENU'S: resolved ONCE through
    ``use_cases.action_context.build_context`` (the ONE builder) and handed to
    ``on_analyze(targets)`` / ``on_carry(targets)`` / ``on_find_similar(targets)``
    (``targets: list[Path]``). A callback says HOW to act, never WHICH cards:
    a zero-arg callable raises ``ValueError`` instead of being called with no
    arguments (the old ``if callable(cb): cb(); return`` shape let a production
    closure re-derive its own scope — ``next(iter(selected_paths))`` — and
    analyze one arbitrary card of a six-card selection, owner report 2026-10-20).
    ``on_ask_ai(scope_kind)`` keeps its string: the Ask AI flyout owns its own
    scope line and reads the set itself when it opens (also with no selection).

    The context carries the backend too: Analyze on the ``algorithms`` domain
    re-measures, Analyze on ``ai`` runs the VLM — the handler cannot re-decide.
    """
    # Fail closed before anything is built, and OUTSIDE the handlers'
    # fail-soft ``except Exception`` where this TypeError used to vanish.
    for _cb_name, _cb in (("on_carry", on_carry), ("on_analyze", on_analyze),
                          ("on_find_similar", on_find_similar)):
        if _cb is not None:
            _require_target_callback(_cb_name, _cb)

    # THE context of this menu: resolved once, here, through the ONE builder,
    # and shared by the labels and every action (callback or default) — they
    # cannot disagree about which cards (or which backend) are in play. Built
    # OUTSIDE the swallowing try: an invalid judgment domain is a named
    # refusal, never a menu that silently loses its scope.
    from tabs.image_gallery.use_cases import action_context, action_scope

    ctx = (
        action_context.build_context(
            owner,
            origin=action_context.ORIGIN_MENU,
            card_path=path,
            action_id="gallery.card.analyze",
        )
        if owner is not None
        else None
    )
    targets = list(ctx.targets) if ctx is not None else []
    # "Make source" is its own rule (one card, or a named refusal). Resolving it
    # here — from the SAME table the registry row uses — is what keeps the menu
    # and Find Action from answering differently (rule 8): a multi-selection
    # hides the entry, it never silently picks the clicked card.
    source_scope = (
        action_scope.resolve_scope(owner, "gallery.card.set_source", card_path=path)
        if owner is not None
        else None
    )

    from tabs.image_gallery.debug import gallery_debug as _dbg
    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

    _dbg_on = _dbg_enabled()
    if _dbg_on:
        _dbg(
            "card menu begin path=%s has_pos=%s owner=%s",
            path,
            global_pos is not None,
            type(owner).__name__ if owner is not None else "None",
        )
    try:
        from sli_ui_toolkit.widgets import (
            ContextMenu,
            ContextMenuAction,
            ContextMenuSection,
            ContextMenuSeparator,
        )

        # The header counts the RESOLVED targets, not the selection mirror: the
        # slot is the authority (``action_scope.selected_paths``), so a stale
        # mirror can no longer print "2 selected" over a one-card scope.
        # The selection SECTION is gated by whether anything is selected (a
        # right-click on an unselected card resolves to that card but is not a
        # selection), while its title counts the context's targets.
        # ``selection_count`` stays as a fallback for a caller that has no owner.
        try:
            selection_size = (
                len(action_scope.selected_paths(owner))
                if owner is not None
                else (int(selection_count) if selection_count is not None else 0)
            )
        except Exception:
            selection_size = int(selection_count) if selection_count is not None else 0
        n = len(targets) if ctx is not None else selection_size
        has_selection = selection_size > 0
        has_analyze = on_analyze is not None or owner is not None
        # Resolve the translator from the widget tree (page ``install_translator``
        # root) or the owner — call sites no longer need to thread ``translate=``.
        tr = _resolve_menu_translator(card, owner, translate)

        # THE scope of this menu was resolved ONCE above (the ActionContext)
        # and is shared by the labels and every action. The bodies live in
        # ``use_cases.gallery_actions`` so no closure here can re-derive scope
        # or backend — the menu only renders.
        handlers = gallery_actions.menu_action_handlers(
            owner=owner,
            ctx=ctx,
            on_carry=on_carry,
            on_analyze=on_analyze,
            on_find_similar=on_find_similar,
        )

        def _open_ask_ai_now(scope_kind: str) -> None:
            # Ask AI keeps a kind string instead of the resolved targets: the
            # flyout owns its scope line ("Selection (N)" / the card), applies
            # with no selection at all, and reads the set itself when it opens.
            try:
                if callable(on_ask_ai):
                    on_ask_ai(scope_kind)
                    return
                fn = getattr(owner, "open_ask_ai", None)
                if callable(fn):
                    fn(scope_kind, card, path)
            except Exception:
                pass

        def _do_ask_ai(scope_kind: str) -> None:
            # The context menu is an in-window registered flyout, so the Ask AI
            # flyout's manager sequenced-cycle opt-in
            # (``AskAiFlyout.wait_for_close_before_show``) waits for the menu to
            # close and replays this show — no app-side close/open chain needed.
            _open_ask_ai_now(scope_kind)

        ask_ai_label = _t(tr, "image_gallery.ask_ai.action", "AI…")
        entries: list = []
        if has_selection:
            sel_actions = [
                ContextMenuAction(
                    "gallery.selection.analyze",
                    _t(tr, "image_gallery.selection.analyze", "Analyze"),
                    icon=_menu_icon(Icon.ANALYZE),
                    enabled=has_analyze,
                    text_key="image_gallery.selection.analyze",
                ),
                ContextMenuAction(
                    "gallery.selection.find_similar",
                    _t(tr, "image_gallery.selection.find_similar", "Find similar"),
                    icon=_menu_icon("compare.svg"),
                    text_key="image_gallery.selection.find_similar",
                ),
                ContextMenuAction(
                    "gallery.selection.ask_ai",
                    ask_ai_label,
                    icon=_menu_icon(Icon.AI),
                    text_key="image_gallery.ask_ai.action",
                ),
            ]
            entries.append(ContextMenuSection(entries=tuple(sel_actions), title=_selection_label(tr, n)))
            entries.append(ContextMenuSeparator())

        # Reject label follows state: all targets rejected → Unreject
        # (mixed → Reject, matching the uniform apply direction).
        _menu_targets = targets
        _all_rejected = _targets_all_rejected(owner, _menu_targets)
        _reject_key = (
            "image_gallery.card.unreject" if _all_rejected else "image_gallery.card.reject"
        )
        _reject_label = _t(tr, _reject_key, "Unreject" if _all_rejected else "Reject")
        per_card: list = []
        # Ask AI on the clicked card alone — only when there is no selection,
        # so it never competes with the selection-scoped entry above.
        if not has_selection:
            per_card.append(
                ContextMenuAction(
                    "gallery.ask_ai",
                    ask_ai_label,
                    icon=_menu_icon(Icon.AI),
                    text_key="image_gallery.ask_ai.action",
                )
            )
        per_card.extend(
            [
                ContextMenuAction(
                    "gallery.make_best",
                    _t(tr, "image_gallery.card.make_best", "Make best"),
                    icon=_menu_icon("star.svg"),
                    text_key="image_gallery.card.make_best",
                ),
                ContextMenuAction(
                    "gallery.reject",
                    _reject_label,
                    icon=_menu_icon("close.svg"),
                    text_key=_reject_key,
                ),
            ]
        )
        per_card.append(
            ContextMenuAction(
                "gallery.remove",
                _t(tr, "image_gallery.card.remove", "Remove from view"),
                # Non-destructive: "remove from view" only drops the card from
                # the grid (files stay on disk, list-mode parity) — no danger
                # red on the label/icon.
                icon=_menu_icon("delete"),
                text_key="image_gallery.card.remove",
            )
        )
        # Maintenance: drop the measured-metrics caches and re-run the pass.
        # NOT destructive of user work (nothing authored is lost — the
        # recompute IS the feedback), so no confirm dialog / undo, mirroring
        # the series-header ``gallery.series.reset`` item.
        per_card.append(
            ContextMenuAction(
                "gallery.reset_metrics",
                _t(
                    tr,
                    "image_gallery.card.reset_metrics_cache",
                    "Reset metrics cache",
                ),
                icon=_menu_icon("undo.svg"),
                text_key="image_gallery.card.reset_metrics_cache",
            )
        )
        # Explicit path to UNGROUPED when no tail section exists to drop
        # onto (drop fallback covers the tail only while visible).
        # Hidden for all-UNGROUPED targets (nothing to dissolve).
        if _targets_any_grouped(owner, _menu_targets):
            per_card.append(
                ContextMenuAction(
                    "gallery.ungroup",
                    _t(tr, "image_gallery.card.ungroup", "Ungroup"),
                    icon=_menu_icon("unlink.svg"),
                    text_key="image_gallery.card.ungroup",
                )
            )
        # Reverse path: pin the menu-rule targets into a brand-new manual
        # series. Multi-select only (≥2 targets), and never for a complete
        # series on its own (already one group — regrouping is a no-op).
        # Sits next to Ungroup, same per-card section; plain "Group" like
        # the plain "Ungroup" (no counts in this menu's per-card labels).
        if len(_menu_targets) >= 2 and not _targets_are_single_series(owner, _menu_targets):
            per_card.append(
                ContextMenuAction(
                    "gallery.group",
                    _t(tr, "image_gallery.card.group", "Group"),
                    icon=_menu_icon("link.svg"),
                    text_key="image_gallery.card.group",
                )
            )
        entries.extend(per_card)
        # "Make source" is available in every mode: in camera/batch the click
        # switches to fidelity and re-runs the fidelity pass
        # (on_quick_set_source -> select_mode + _start_fidelity_analysis).
        # Context-dependent: hidden when the clicked card is ALREADY the source
        # (setting it again is a no-op) and when the resolved scope is not
        # exactly one card (rule 8 — the registry refuses the same input).
        source_refused = bool(source_scope is not None and source_scope.refused)
        if not source_refused and not _is_source(owner, path):
            entries.append(
                ContextMenuAction(
                    "gallery.set_as_source",
                    _t(tr, "image_gallery.card.make_source", "Make source"),
                    icon=_menu_icon("check.svg"),
                    text_key="image_gallery.card.make_source",
                )
            )
        def _on_triggered(action_id: str, _data: object) -> None:
            # Every body receives the context the menu already resolved: no
            # closure here may re-derive a scope (that is how the "two cards
            # selected, a hundred processed" class of bug came back).
            try:
                if action_id == "gallery.selection.analyze":
                    handlers["analyze"]()
                elif action_id == "gallery.selection.find_similar":
                    handlers["find_similar"]()
                elif action_id == "gallery.selection.ask_ai":
                    _do_ask_ai("selection")
                elif action_id == "gallery.ask_ai":
                    _do_ask_ai("card")
                elif action_id == "gallery.make_best":
                    _ctx_make_best(owner, path, targets)
                elif action_id == "gallery.reject":
                    _ctx_toggle_reject(owner, path, targets)
                elif action_id == "gallery.remove":
                    _ctx_remove(owner, path, targets)
                elif action_id == "gallery.reset_metrics":
                    handlers["reset_metrics"]()
                elif action_id == "gallery.ungroup":
                    handlers["ungroup"]()
                elif action_id == "gallery.group":
                    handlers["group"]()
                elif action_id == "gallery.set_as_source":
                    _ctx_set_source(
                        owner,
                        path,
                        list(source_scope.targets) if source_scope is not None else None,
                    )
            except Exception:
                pass

        # Parent the popup to the CARD (a content widget), never the
        # MainWindow: a Qt.Popup whose QWidget parent is the top-level breaks
        # compositing for the whole window on Wayland/XWayland (in-window
        # translucency turns black, e.g. toasts; every fresh QRhiWidget mint
        # then fails -> Quick Look dead). Mirrors MC (canvas parent) and IC
        # (unified-flyout parent); MC's interaction.py carries the same
        # warning for menu_parent=MainWindow. See
        # inv-2026-10-06-ql-rhi-menu-first.
        source = card
        pos = global_pos
        if pos is None:
            try:
                from PySide6.QtGui import QCursor

                pos = QCursor.pos()
            except Exception:
                pos = None
        # Menu through the app manager: it owns the surface policy
        # (``surface="in_window"`` — a child overlay, no native xdg_popup
        # teardown before the Ask AI flyout shows) and the outside-close /
        # keyed-reopen bookkeeping. Never a flyout competing with the capsule.
        try:
            from tabs.image_gallery.ui.card.marquee_snapshot import marquee_snapshot
            from ui.context_menu.manager import open_context_menu_entries

            if _dbg_on:
                _dbg(
                    "card menu popup path=%s n=%s marquee=%s",
                    path, n, marquee_snapshot(owner, card),
                )
            # The manager's app-wide RMB policy is ``surface="in_window"`` (a
            # plain child widget, no native popup teardown for the Ask AI
            # sequence). A child widget is clipped to its parent's rectangle,
            # so parenting to the card itself cut the menu down to a sliver at
            # the card's edge (2026-10-17 card-menu-size). Parent the overlay
            # to the card's window instead — NOT a Qt.Popup, so the Wayland
            # "popup parented to the top-level" trap above does not apply.
            _parent = None
            try:
                _parent = card.window()
            except Exception:
                _parent = None
            _open_kwargs = {}
            if _parent is not None and _parent is not card:
                _open_kwargs["menu_parent"] = _parent
            menu = open_context_menu_entries(
                source_widget=source or card,
                global_pos=pos,
                entries=tuple(entries),
                key=("gallery-card", str(path), n),
                on_triggered=_on_triggered,
                **_open_kwargs,
            )
            if menu is not None:
                # Labels are localized when the entries are built (``_t``
                # above), like every other context menu in the app. Do NOT bind
                # a translator to the shown menu: ``retranslate`` ->
                # ``_relayout_widths`` -> ``adjustSize`` ran while the show-time
                # fade had the container hidden and collapsed the menu to a
                # sliver (card-menu-collapse, 2026-10-17).
                if _dbg_on:
                    try:
                        _dbg(
                            "card menu opened path=%s marquee=%s",
                            path, marquee_snapshot(owner, card),
                        )
                    except Exception:
                        pass
                track_open_menu(card, menu, owner)
                return
        except Exception:
            if _dbg_on:
                _dbg("card menu manager open raised path=%s", path, exc_info=True)
            pass
        # Fallback: direct popup (same surface the manager would use).
        try:
            menu = ContextMenu(source, entries=tuple(entries), on_triggered=_on_triggered, surface="popup")
        except TypeError:
            menu = ContextMenu(source, entries=tuple(entries), on_triggered=_on_triggered)
        try:
            menu.flyout_group = "context_menu"  # type: ignore[attr-defined]
        except Exception:
            pass
        if pos is not None:
            try:
                menu.popup_at(pos)
                track_open_menu(card, menu, owner)
                return
            except Exception:
                if _dbg_on:
                    _dbg("card menu popup_at raised path=%s", path, exc_info=True)
                pass
        # Last resort: anchor-aligned dropdown.
        try:
            from sli_ui_toolkit.widgets import popup_context_menu_for_anchor

            _anchor_menu = popup_context_menu_for_anchor(
                source or card, card, tuple(entries), on_triggered=_on_triggered
            )
            track_open_menu(card, _anchor_menu, owner)
        except Exception:
            if _dbg_on:
                _dbg("card menu fallback-anchor raised path=%s", path, exc_info=True)
            try:
                menu.show()
            except Exception:
                pass
    except Exception:
        if _dbg_on:
            _dbg("card menu outer raised path=%s", path, exc_info=True)
        pass
