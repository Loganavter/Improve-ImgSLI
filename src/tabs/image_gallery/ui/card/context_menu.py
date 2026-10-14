"""Context menu for gallery card — per-card + selection actions (toolkit ContextMenu).
Audit-Meta: pattern=qdialog-wiring size=exempt reason="one card-menu builder — entry list + per-card context gating (source/reject/group) + monochrome icon tinting share one menu contract; action bodies live in context_actions.py"

Right-click on a card opens a standard toolkit ``ContextMenu`` under the
cursor (``popup_at(QCursor.pos())``). The menu merges two groups:

1. Selection section (ex-HUD flyout: Analyze / Find similar) — shown only
   when a non-empty selection exists. No "clear selection" entry by design
   — deselect is Esc, menus offer actions ON the set.
2. Per-card actions mirroring the hover capsule: Make best / Reject /
   Remove from view (+ Make source, every mode), plus the manual
   grouping pair — Ungroup (dissolve into the tail) and Group (pin the
   menu-rule targets into a brand-new series; multi-select only, hidden
   when the selection is already exactly one whole series).
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
    _ctx_set_source,
    _ctx_toggle_reject,
    _ctx_ungroup,
)
from tabs.image_gallery.ui.card.menu_track import track_open_menu


def _t(translate, key: str, default: str) -> str:
    if translate is None:
        return default
    try:
        return translate(key, default)
    except Exception:
        try:
            return translate(key)  # type: ignore[call-arg]
        except Exception:
            return default


def _selection_count(owner) -> int:
    try:
        sel = getattr(getattr(owner, "state", None), "selected_paths", None)
        if sel is None:
            return 0
        return len(sel)
    except Exception:
        return 0


def _targets_are_single_series(owner, targets) -> bool:
    """True when *targets* are exactly one whole live series (fail-open False).

    Grouping a complete series would pin it onto a fresh id and rebuild
    for nothing — the menu hides Group in that case (Ungroup stays: it
    dissolves). Reads controller ``state.series`` plus the grid mirror
    (``_grid_view._series`` clusters); the UNGROUPED tail is not a series.
    """
    try:
        tset = {str(p) for p in (targets or [])}
    except Exception:
        return False
    if len(tset) < 2:
        return False
    try:
        candidates: list = []
        try:
            st = getattr(owner, "state", None)
            if st is not None and getattr(st, "series", None):
                candidates.extend(list(st.series or []))
        except Exception:
            pass
        try:
            gv = getattr(owner, "_grid_view", None)
            if gv is not None and getattr(gv, "_series", None):
                candidates.extend(list(gv._series or []))
        except Exception:
            pass
        for entry in candidates:
            try:
                if hasattr(entry, "members"):
                    members = list(getattr(entry, "members", None) or [])
                elif isinstance(entry, (list, tuple)):
                    members = list(entry)
                else:
                    continue
                if len(members) >= 2 and {str(getattr(m, "path", None)) for m in members} == tset:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _targets_any_grouped(owner, targets) -> bool:
    """True unless every target is positively UNGROUPED (fail-open True).

    Hides Ungroup for an all-UNGROUPED set (nothing to dissolve — the
    move path would no-op). Targets missing from the known pool (storeless
    doubles) keep the old visible behavior; only a positively-known
    all-ungrouped set hides the entry. Mirrors ``_targets_all_rejected``.
    """
    try:
        tset = {str(t) for t in (targets or [])}
        if not tset:
            return False
        from tabs.image_gallery.use_cases import triage as _triage

        pool: dict[str, bool] = {}
        for it in _triage._items_of(owner):
            try:
                pool[str(Path(it.path))] = getattr(it, "series_id", None) is not None
            except Exception:
                continue
        if any(t not in pool for t in tset):
            return True
        return any(pool[t] for t in tset)
    except Exception:
        return True


def _targets_all_rejected(owner, targets) -> bool:
    """True when every target card is currently rejected (fail-open False).

    Drives the Reject/Unreject label; mirrors the uniform direction in
    ``_ctx_toggle_reject`` (all rejected → unreject, else reject).
    """
    try:
        if not targets:
            return False
        from tabs.image_gallery.use_cases import triage as _triage

        flags: dict[str, bool] = {}
        for it in _triage._items_of(owner):
            try:
                flags[str(Path(it.path))] = bool(
                    getattr(it, "rejected", getattr(it, "triage_rejected", False))
                )
            except Exception:
                continue
        return bool(targets) and all(flags.get(str(t), False) for t in targets)
    except Exception:
        return False


def _selection_label(translate, n: int) -> str:
    if n <= 0:
        return _t(translate, "image_gallery.selection.none", "No selection")
    if n == 1:
        return _t(translate, "image_gallery.selection.one", "1 selected")
    raw = _t(translate, "image_gallery.selection.many", "{n} selected")
    try:
        if "{n}" in raw:
            return raw.format(n=n)
        return f"{n} selected"
    except Exception:
        return f"{n} selected"


def _is_source(owner, path) -> bool:
    """True when the clicked card is already the series source (fail-open False)."""
    try:
        p = str(Path(path))
    except Exception:
        return False
    try:
        st = getattr(owner, "state", None)
        src = getattr(st, "source_path", None) if st is not None else None
        if src is not None:
            return str(Path(src)) == p
    except Exception:
        pass
    try:
        from tabs.image_gallery.services.rank_badge import KIND_SOURCE
        from tabs.image_gallery.use_cases import triage as _triage

        for it in _triage._items_of(owner):
            if str(Path(getattr(it, "path", ""))) == p:
                return str(getattr(it, "badge_kind", "")) == KIND_SOURCE
    except Exception:
        pass
    return False


def _menu_icon(name):  # type: ignore[no-untyped-def]
    """Resolve a menu icon tinted to the row-text theme color (monochrome family).

    The toolkit paints ``ContextMenuAction.icon`` verbatim, so icons from
    mixed sources (brand-blue ``ai.svg``, black ``compare.svg``, white
    ``delete``/``star``/``check``) rendered as a rainbow in one menu. Tinting
    them all to ``dialog.text`` — the same color the row paints its label with
    — makes the menu one monochrome family that tracks the theme. Fail-open:
    returns *name* unchanged on any error (the toolkit then resolves it as
    before).
    """
    try:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
        from sli_ui_toolkit.icons import resolve_icon
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), "dialog.text")
        if c is None:
            return name
        col = c if isinstance(c, QColor) else QColor(c)
        base = resolve_icon(name)
        if base is None or base.isNull():
            return name
        pm = base.pixmap(QSize(64, 64))
        if pm.isNull():
            return name
        out = QPixmap(pm.size())
        try:
            out.setDevicePixelRatio(pm.devicePixelRatio())
        except Exception:
            pass
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        try:
            painter.drawPixmap(0, 0, pm)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(out.rect(), col)
        finally:
            painter.end()
        return QIcon(out)
    except Exception:
        return name


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

        ask_ai_label = _t(translate, "image_gallery.ask_ai.action", "AI…")
        entries: list = []
        if has_selection:
            sel_actions = [
                ContextMenuAction(
                    "gallery.selection.analyze",
                    _t(translate, "image_gallery.selection.analyze", "Analyze"),
                    icon=_menu_icon(Icon.ANALYZE),
                    enabled=has_analyze,
                ),
                ContextMenuAction(
                    "gallery.selection.find_similar",
                    _t(translate, "image_gallery.selection.find_similar", "Find similar"),
                    icon=_menu_icon("compare.svg"),
                ),
                ContextMenuAction(
                    "gallery.selection.ask_ai",
                    ask_ai_label,
                    icon=_menu_icon(Icon.AI),
                ),
            ]
            entries.append(ContextMenuSection(entries=tuple(sel_actions), title=_selection_label(translate, n)))
            entries.append(ContextMenuSeparator())

        # Reject label follows state: all targets rejected → Unreject
        # (mixed → Reject, matching the uniform apply direction).
        _menu_targets = _action_targets(owner, path)
        _reject_label = (
            _t(translate, "image_gallery.card.unreject", "Unreject")
            if _targets_all_rejected(owner, _menu_targets)
            else _t(translate, "image_gallery.card.reject", "Reject")
        )
        per_card: list = []
        # Ask AI on the clicked card alone — only when there is no selection,
        # so it never competes with the selection-scoped entry above.
        if not has_selection:
            per_card.append(ContextMenuAction("gallery.ask_ai", ask_ai_label, icon=Icon.AI))
        per_card.extend(
            [
                ContextMenuAction(
                    "gallery.make_best",
                    _t(translate, "image_gallery.card.make_best", "Make best"),
                    icon=_menu_icon("star.svg"),
                ),
                ContextMenuAction(
                    "gallery.reject",
                    _reject_label,
                    icon=_menu_icon("close.svg"),
                ),
            ]
        )
        per_card.append(
            ContextMenuAction(
                "gallery.remove",
                _t(translate, "image_gallery.card.remove", "Remove from view"),
                # Non-destructive: "remove from view" only drops the card from
                # the grid (files stay on disk, list-mode parity) — no danger
                # red on the label/icon.
                icon=_menu_icon("delete"),
            )
        )
        # Explicit path to UNGROUPED when no tail section exists to drop
        # onto (drop fallback covers the tail only while visible).
        # Hidden for all-UNGROUPED targets (nothing to dissolve).
        if _targets_any_grouped(owner, _menu_targets):
            per_card.append(
                ContextMenuAction(
                    "gallery.ungroup",
                    _t(translate, "image_gallery.card.ungroup", "Ungroup"),
                    icon=_menu_icon("unlink.svg"),
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
                    _t(translate, "image_gallery.card.group", "Group"),
                    icon=_menu_icon("link.svg"),
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
                    _t(translate, "image_gallery.card.make_source", "Make source"),
                    icon=_menu_icon("check.svg"),
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
        # Popup surface via the app manager (real Qt.Popup top-level, above
        # UnifiedFlyout) — never an in-window flyout competing with the capsule.
        try:
            from tabs.image_gallery.ui.card.marquee_snapshot import marquee_snapshot
            from ui.context_menu.manager import open_context_menu_entries

            if _dbg_on:
                _dbg(
                    "card menu popup path=%s n=%s marquee=%s",
                    path, n, marquee_snapshot(owner, card),
                )
            menu = open_context_menu_entries(
                source_widget=source or card,
                global_pos=pos,
                entries=tuple(entries),
                key=("gallery-card", str(path), n),
                on_triggered=_on_triggered,
            )
            if menu is not None:
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



