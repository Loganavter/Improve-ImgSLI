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

Compare actions were removed from this menu (no Compare → / ⇄ Compare):
carry flows live in the stats strip / keyboard paths, not here.
Move was removed as well — carrying to another tab is drag-only (press-move
past the drag threshold on a card starts the QDrag; drop onto a workspace
tab delivers it).

Split out of ``ui/card/context_menu.py`` per the module→package split
(``plan-gallery-split-2026-10-17``); the entry point body moved verbatim.
"""

from __future__ import annotations

import time
from pathlib import Path

from tabs.image_gallery.icons import Icon
from tabs.image_gallery.ui.card.context_actions import (
    _action_targets,
    _ctx_group,
    _ctx_make_best,
    _ctx_remove,
    _ctx_reset_metrics,
    _ctx_set_source,
    _ctx_toggle_reject,
    _ctx_ungroup,
)
from tabs.image_gallery.ui.card.menu_track import track_open_menu

from .icons import _menu_icon
from .predicates import (
    _is_source,
    _selection_count,
    _selection_label,
    _targets_all_rejected,
    _targets_any_grouped,
    _targets_are_single_series,
)
from .translator import _bind_menu_translator, _resolve_menu_translator, _t


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

    Selection callbacks default to the gallery use-cases resolved from
    *owner* when not given explicitly (so existing ``_on_card_context``
    call sites keep working).
    """
    from tabs.image_gallery.debug import gallery_debug as _dbg
    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_enabled

    _dbg_on = _dbg_enabled()
    _t0 = time.perf_counter() if _dbg_on else 0.0
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

        n = int(selection_count) if selection_count is not None else _selection_count(owner)
        has_selection = n > 0
        has_analyze = on_analyze is not None or owner is not None
        # Resolve the translator from the widget tree (page ``install_translator``
        # root) or the owner — call sites no longer need to thread ``translate=``.
        tr = _resolve_menu_translator(card, owner, translate)

        def _do_carry() -> None:
            try:
                if callable(on_carry):
                    on_carry()
                    return
                from tabs.image_gallery.use_cases import carry as _carry

                _carry.carry_selected(owner)
            except Exception:
                pass

        def _do_analyze() -> None:
            try:
                if callable(on_analyze):
                    on_analyze()
                    return
                sel = getattr(getattr(owner, "state", None), "selected_paths", None) or set()
                if sel:
                    p = next(iter(sel))
                    owner.analyze_item_by_path(p)  # type: ignore[attr-defined]
            except Exception:
                pass

        def _do_find_similar() -> None:
            try:
                if callable(on_find_similar):
                    on_find_similar()
                    return
                from tabs.image_gallery.use_cases.carry import find_similar_selected

                find_similar_selected(owner)
            except Exception:
                pass

        def _open_ask_ai_now(scope_kind: str) -> None:
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
        _menu_targets = _action_targets(owner, path)
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
        # Context-dependent: hidden when the clicked card is ALREADY the
        # source (setting it again is a no-op).
        if not _is_source(owner, path):
            entries.append(
                ContextMenuAction(
                    "gallery.set_as_source",
                    _t(tr, "image_gallery.card.make_source", "Make source"),
                    icon=_menu_icon("check.svg"),
                    text_key="image_gallery.card.make_source",
                )
            )
        def _on_triggered(action_id: str, _data: object) -> None:
            try:
                if action_id == "gallery.selection.analyze":
                    _do_analyze()
                elif action_id == "gallery.selection.find_similar":
                    _do_find_similar()
                elif action_id == "gallery.selection.ask_ai":
                    _do_ask_ai("selection")
                elif action_id == "gallery.ask_ai":
                    _do_ask_ai("card")
                elif action_id == "gallery.make_best":
                    _ctx_make_best(owner, path)
                elif action_id == "gallery.reject":
                    _ctx_toggle_reject(owner, path)
                elif action_id == "gallery.remove":
                    _ctx_remove(owner, path)
                elif action_id == "gallery.reset_metrics":
                    _ctx_reset_metrics(owner, path)
                elif action_id == "gallery.ungroup":
                    _ctx_ungroup(owner, path)
                elif action_id == "gallery.group":
                    _ctx_group(owner, path)
                elif action_id == "gallery.set_as_source":
                    _ctx_set_source(owner, path)
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
                translator=tr,
                **_open_kwargs,
            )
            if menu is not None:
                # The translator is bound by the manager BEFORE the popup is
                # shown (see ContextMenuManager.open_entries): a post-show bind
                # ran retranslate -> adjustSize while the fade hid the menu's
                # container and collapsed it (card-menu-collapse, 2026-10-17).
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
        _bind_menu_translator(menu, tr)
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
            _bind_menu_translator(_anchor_menu, tr)
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
