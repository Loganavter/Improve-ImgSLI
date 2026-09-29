"""Context menu for gallery card — per-card + selection actions (toolkit ContextMenu).

Right-click on a card opens a standard toolkit ``ContextMenu`` under the
cursor (``popup_at(QCursor.pos())``). The menu merges two groups:

1. Selection section (ex-HUD flyout: Clear / Analyze / Find similar /
   Compare →) — shown only when a non-empty selection exists.
2. Per-card actions mirroring the hover capsule: Make best / Reject /
   Compare (+ Set as source in fidelity mode).
"""

from __future__ import annotations

import time
from pathlib import Path


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


def popup_gallery_card_context_menu(  # type: ignore[no-untyped-def]
    card,
    owner,
    path: Path,
    global_pos=None,
    mode=None,
    *,
    selection_count: int | None = None,
    on_clear=None,
    on_carry=None,
    on_analyze=None,
    on_find_similar=None,
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

        # Resolve mode: explicit > card attribute > owner state.
        _mode = mode
        if _mode is None:
            try:
                _mode = getattr(card, "_gallery_mode", None)
            except Exception:
                _mode = None
        if _mode is None and owner is not None:
            try:
                st = getattr(owner, "state", None)
                _mode = getattr(st, "mode", None) if st is not None else getattr(owner, "_mode", None)
            except Exception:
                pass
        try:
            ms = str(_mode.value).lower() if hasattr(_mode, "value") else str(_mode).lower() if _mode is not None else ""
        except Exception:
            ms = ""
        include_source = ms == "fidelity"

        n = int(selection_count) if selection_count is not None else _selection_count(owner)
        has_selection = n > 0
        has_analyze = on_analyze is not None or owner is not None

        def _do_clear() -> None:
            try:
                if callable(on_clear):
                    on_clear()
                    return
                from tabs.image_gallery.use_cases import selection as _sel

                _sel.clear_selection(owner)
            except Exception:
                pass

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

        entries: list = []
        if has_selection:
            sel_actions = [
                ContextMenuAction(
                    "gallery.selection.clear",
                    _t(translate, "image_gallery.selection.clear", "Clear"),
                ),
                ContextMenuAction(
                    "gallery.selection.analyze",
                    _t(translate, "image_gallery.selection.analyze", "Analyze"),
                    enabled=has_analyze,
                ),
                ContextMenuAction(
                    "gallery.selection.find_similar",
                    _t(translate, "image_gallery.selection.find_similar", "Find similar"),
                ),
                ContextMenuAction(
                    "gallery.selection.compare",
                    _t(translate, "image_gallery.selection.compare", "Compare →"),
                ),
            ]
            entries.append(ContextMenuSection(entries=tuple(sel_actions), title=_selection_label(translate, n)))
            entries.append(ContextMenuSeparator())

        entries.extend(
            [
                ContextMenuAction(
                    "gallery.make_best",
                    "★ Make best",
                ),
                ContextMenuAction(
                    "gallery.reject",
                    "✕ Reject",
                ),
                ContextMenuAction(
                    "gallery.compare",
                    "⇄ Compare",
                ),
                ContextMenuAction(
                    "gallery.remove",
                    "Delete",
                    icon="delete",
                    danger=True,
                ),
            ]
        )
        if include_source:
            entries.append(
                ContextMenuAction(
                    "gallery.set_as_source",
                    "Set as source",
                )
            )

        def _on_triggered(action_id: str, _data: object) -> None:
            try:
                if action_id == "gallery.selection.clear":
                    _do_clear()
                elif action_id == "gallery.selection.analyze":
                    _do_analyze()
                elif action_id == "gallery.selection.find_similar":
                    _do_find_similar()
                elif action_id == "gallery.selection.compare":
                    _do_carry()
                elif action_id == "gallery.make_best":
                    _ctx_make_best(owner, path)
                elif action_id == "gallery.reject":
                    _ctx_toggle_reject(owner, path)
                elif action_id == "gallery.compare":
                    _ctx_compare(owner, path)
                elif action_id == "gallery.remove":
                    _ctx_remove(owner, path)
                elif action_id == "gallery.set_as_source":
                    _ctx_set_source(owner, path)
            except Exception:
                pass

        source = card.window() if card is not None and hasattr(card, "window") else card
        if source is None:
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
                _track_open_menu(card, menu, owner)
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
                _track_open_menu(card, menu, owner)
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
            _track_open_menu(card, _anchor_menu, owner)
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


def _track_open_menu(card, menu, owner=None) -> None:
    """Keep the card hover highlight while its context menu is open.

    The popup takes the mouse, so the card gets a Leave that would clear
    the underline. The hover filter skips the hide while the tracked menu
    is visible (see ``_CardHoverFilter``); on hide we restore the highlight
    and drop the (possibly stale) reference.

    ``owner`` is passed through (grid cards carry no ``_gallery_owner`` —
    the pool builds them without one) so hide-time traces can resolve the
    marquee gesture the same way the open-time trace does.
    """
    try:
        if card is None or menu is None:
            return
        try:
            card._gallery_open_menu = menu  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.card.hover import _show_card_hover_underline

            _show_card_hover_underline(card)
        except Exception:
            pass
        try:
            about = getattr(menu, "aboutToHide", None)
            if about is not None and hasattr(about, "connect"):
                try:
                    _menu_owner = owner if owner is not None else getattr(card, "_gallery_owner", None)
                except Exception:
                    _menu_owner = None

                def _on_menu_hidden(c=card, m=menu, o=_menu_owner) -> None:
                    try:
                        if getattr(c, "_gallery_open_menu", None) is m:
                            c._gallery_open_menu = None  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        from tabs.image_gallery.debug import gallery_debug as _dbg2
                        from tabs.image_gallery.ui.card.marquee_snapshot import marquee_snapshot as _snap

                        _dbg2("card menu hidden marquee=%s", _snap(o, c))
                    except Exception:
                        pass
                    try:
                        from tabs.image_gallery.ui.card.hover import (
                            _show_card_hover_underline as _show,
                        )

                        _show(c)
                    except Exception:
                        pass

                about.connect(_on_menu_hidden)
        except Exception:
            pass
    except Exception:
        pass


def _ctx_make_best(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        _triage.make_best(owner, path)
    except Exception:
        pass


def _ctx_toggle_reject(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.use_cases import triage as _triage

        _dbg("reject clicked path=%s owner=%s", path, type(owner).__name__)
        try:
            result = _triage.toggle_reject(owner, path)
        except Exception:
            _dbg("reject toggle_reject raised path=%s", path, exc_info=True)
            return
        _dbg("reject toggle_reject returned %r path=%s", result, path)
    except Exception:
        pass


def _ctx_compare(owner, path: Path) -> None:
    try:
        from tabs.image_gallery.use_cases import carry as _carry

        # Select path then carry.
        try:
            if hasattr(owner, "state") and hasattr(owner.state, "selected_paths"):
                owner.state.selected_paths.add(Path(path))
        except Exception:
            pass
        _carry.carry_selected(owner)
    except Exception:
        pass


def _ctx_remove(owner, path: Path) -> None:
    """Delete card from the grid (file on disk stays; list-mode parity)."""
    try:
        from tabs.image_gallery.use_cases import triage as _triage

        _triage.remove_from_grid(owner, path)
    except Exception:
        pass


def _ctx_set_source(owner, path: Path) -> None:
    """Fidelity only: set selected image as source hub (used by IconActionFlyout & ContextMenu)."""
    try:
        from pathlib import Path as _P

        p = _P(path)
        # Controller / widget state
        st = getattr(owner, "state", None)
        if st is not None:
            try:
                st.source_path = p
            except Exception:
                pass
        # Widget mirrors _source_path and stats strip chip
        w = getattr(owner, "widget", None)
        candidates = [w, owner]
        # Also try window's gallery widget
        try:
            win = None
            for cand in candidates:
                if cand is not None and hasattr(cand, "window"):
                    try:
                        win = cand.window()
                        if win is not None:
                            candidates.append(win)
                        break
                    except Exception:
                        pass
        except Exception:
            pass
        for cand in candidates:
            if cand is None:
                continue
            try:
                if hasattr(cand, "_source_path"):
                    cand._source_path = p  # type: ignore
            except Exception:
                pass
            try:
                if hasattr(cand, "stats_strip") and hasattr(cand.stats_strip, "set_mode"):
                    # Reuse mode from state
                    mode_val = getattr(st, "mode", None) if st is not None else getattr(cand, "_mode", None)
                    cand.stats_strip.set_mode(str(mode_val or "fidelity"), p)  # type: ignore
            except Exception:
                pass
            try:
                if hasattr(cand, "_grid_view") and hasattr(cand._grid_view, "_mode"):
                    # Grid stores mode; no direct update needed
                    pass
            except Exception:
                pass
        # Try generic helper (quick_look_hooks) as fallback
        try:
            from tabs.image_gallery.ui import quick_look_hooks as _qlh

            _qlh.on_quick_set_source(owner, p)
        except Exception:
            pass
    except Exception:
        pass
