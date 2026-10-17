"""Series headers, hub naming, rename and live retranslate for the gallery widget.

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps same-named one-line
delegators so call sites and tests do not move. Fail-open like the
surrounding widget chrome.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ImproveImgSLI")


def _tr_ui(owner, key: str, default: str) -> str:
    """Gallery i18n lookup for widget-level strings (fail-open to default)."""
    ctx = getattr(owner, "_context", None)
    if ctx is None:
        return default
    try:
        return ctx._tr(key, default)
    except Exception:
        return default


def _retranslate_overlays(owner) -> None:
    """Refresh the lazily-created overlays on a live language switch.

    Reuses this widget's context translator (same ``tr`` the toolbar and
    stats strip got at construction). No-op while an overlay has not been
    created yet — the next ``show_*`` builds it with the current tr.
    """
    ctx = getattr(owner, "_context", None)
    tr = getattr(ctx, "_tr", None) if ctx is not None else None
    for attr in ("_clean_overlay", "_quick_look_overlay"):
        overlay = getattr(owner, attr, None)
        if overlay is None:
            continue
        try:
            overlay.retranslate(tr)
        except Exception:
            pass


def _retranslate_chrome(owner) -> None:
    """Re-render every gallery-owned string on a live language switch.

    The toolbar/stats strip captured ``translate`` at construction and
    their ``retranslate()`` hooks were never wired; the series headers and
    cards capture theirs per render. Re-applies all three in place — no
    teardown, selection/scroll/focus preserved (the grid reuses header and
    card widgets). Fail-open per surface.
    """
    owner._retranslate_overlays()
    for attr in ("toolbar", "stats_strip"):
        widget = getattr(owner, attr, None)
        if widget is None:
            continue
        try:
            widget.retranslate()
        except Exception:
            pass
    try:
        gv = getattr(owner, "_grid_view", None)
        if gv is not None:
            gv.retranslate_headers()
    except Exception:
        pass


def _series_names_map(owner) -> dict:
    """Session custom-name map (series_id → name); lazily created."""
    names = getattr(owner, "_series_names", None)
    if not isinstance(names, dict):
        names = {}
        owner._series_names = names
    return names


def _compute_series_hub_names(owner, norm_series) -> list:
    """Per-series header names (``SERIES i · <hub> · n VARIANTS``).

    Hub = rank-1 member's file name uppercased, unless a session rename
    override exists for the cluster's stable ``series_id`` (override wins
    verbatim; the header upper-cases it for display).
    """
    names_map = owner._series_names_map()
    hub_names: list = []
    try:
        for cl in [c for c in (norm_series or []) if len(c) >= 2]:
            hub_item = None
            try:
                ranked = sorted(cl, key=lambda it: int(getattr(it, "rank", 999) or 999))
                hub_item = ranked[0] if ranked else cl[0]
            except Exception:
                hub_item = cl[0] if cl else None
            hub = None
            if hub_item is not None:
                try:
                    hub = Path(hub_item.path).name.upper()
                except Exception:
                    hub = str(getattr(hub_item, "name", "")).upper() or None
            sid = None
            try:
                for m in cl:
                    _s = getattr(m, "series_id", None)
                    if _s:
                        sid = str(_s)
                        break
            except Exception:
                sid = None
            if sid and names_map.get(sid):
                hub = str(names_map[sid])
            hub_names.append(hub)
    except Exception:
        hub_names = []
    return hub_names


def _on_series_context_menu(
    owner, index, anchor, member_paths, label, series_id=None, global_pos=None
) -> None:
    """Series-header right-click → toolkit ``ContextMenu``.

    Ask AI / Rename / Delete over the whole series, then the manual-series
    tools (Reset / Re-cluster) as the tail. Popup surface via the app
    manager — parented to the header Button (a content widget), never the
    MainWindow (Wayland compositing trap; see the card menu).
    """
    paths = tuple(member_paths or ())
    _triage_owner = owner._owner_for_triage()

    def _open_ask_ai_now() -> None:
        try:
            fn = getattr(_triage_owner, "open_ask_ai_for_series", None)
            if callable(fn):
                fn(index, anchor, paths, str(label or ""))
        except Exception:
            pass

    def _do_ask_ai() -> None:
        # The context menu is an in-window registered flyout; the Ask AI
        # flyout's manager sequenced-cycle opt-in waits for it to close,
        # then replays the show — no app-side close/open chain needed.
        _open_ask_ai_now()

    def _do_rename() -> None:
        try:
            owner._rename_series(series_id, label)
        except Exception:
            pass

    def _do_delete() -> None:
        try:
            from tabs.image_gallery.use_cases import triage as _triage

            if len(paths) > 1:
                _triage.remove_paths_from_grid(_triage_owner, paths)
            elif paths:
                _triage.remove_from_grid(_triage_owner, paths[0])
        except Exception:
            pass

    def _do_reset() -> None:
        try:
            fn = getattr(_triage_owner, "reset_series_overrides", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    def _do_recluster() -> None:
        try:
            fn = getattr(_triage_owner, "recluster_series", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    try:
        from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator
    except Exception:
        return

    try:
        from tabs.image_gallery.icons import Icon as _GalleryIcon
    except Exception:
        _GalleryIcon = None  # type: ignore[assignment]
    has_reset = callable(getattr(_triage_owner, "reset_series_overrides", None))
    has_recluster = callable(getattr(_triage_owner, "recluster_series", None))
    entries: list = [
        ContextMenuAction(
            "gallery.series.ask_ai",
            owner._tr_ui("image_gallery.series.ask_ai", "Ask AI"),
            icon=getattr(_GalleryIcon, "AI", None),
        ),
        ContextMenuAction(
            "gallery.series.rename",
            owner._tr_ui("image_gallery.series.rename", "Rename"),
            icon="text_filename.svg",
            enabled=bool(series_id),
        ),
        ContextMenuAction(
            "gallery.series.delete",
            owner._tr_ui("image_gallery.series.delete", "Delete"),
            icon="delete",
            danger=True,
        ),
    ]
    tail: list = []
    if has_reset:
        tail.append(
            ContextMenuAction(
                "gallery.series.reset",
                owner._tr_ui("image_gallery.series.reset", "Reset manual series"),
                icon="undo.svg",
            )
        )
    if has_recluster:
        tail.append(
            ContextMenuAction(
                "gallery.series.recluster",
                owner._tr_ui("image_gallery.series.recluster", "Re-cluster series"),
                icon="sync.svg",
            )
        )
    if tail:
        entries.append(ContextMenuSeparator())
        entries.extend(tail)

    def _on_triggered(action_id: str, _data: object) -> None:
        if action_id == "gallery.series.ask_ai":
            _do_ask_ai()
        elif action_id == "gallery.series.rename":
            _do_rename()
        elif action_id == "gallery.series.delete":
            _do_delete()
        elif action_id == "gallery.series.reset":
            _do_reset()
        elif action_id == "gallery.series.recluster":
            _do_recluster()

    source = anchor if anchor is not None else owner
    pos = global_pos
    if pos is None:
        try:
            from PySide6.QtGui import QCursor

            pos = QCursor.pos()
        except Exception:
            pos = None
    try:
        from ui.context_menu.manager import open_context_menu_entries

        open_context_menu_entries(
            source_widget=source,
            global_pos=pos,
            entries=tuple(entries),
            key=("gallery-series", int(index), str(series_id or "")),
            on_triggered=_on_triggered,
        )
    except Exception:
        logger.debug("series header context menu failed", exc_info=True)


def _rename_series(owner, series_id, label) -> None:
    """Prompt for a session-only custom series name and repaint headers."""
    sid = str(series_id) if series_id else ""
    if not sid:
        return
    try:
        from tabs.host_helpers import AppTextInputDialog
    except Exception:
        return
    names = owner._series_names_map()
    current = names.get(sid) or str(label or "")
    title = owner._tr_ui("image_gallery.series.rename_title", "Rename series")
    prompt = owner._tr_ui("image_gallery.series.rename_prompt", "Series name")
    try:
        parent = owner.window() or owner
    except Exception:
        parent = owner
    value, ok = AppTextInputDialog.get_text(parent, title, prompt, current)
    if not ok:
        return
    name = str(value or "").strip()
    if name:
        names[sid] = name
    else:
        names.pop(sid, None)  # empty → fall back to the derived hub name
    owner._refresh_series_names()


def _refresh_series_names(owner) -> None:
    """Repaint series headers with the current custom names (no teardown)."""
    try:
        norm_series = list(owner._series or [])
    except Exception:
        return
    try:
        collapsed = dict(owner._collapsed or {})
    except Exception:
        collapsed = {}
    try:
        owner._rebuild_series_view(
            norm_series, owner._compute_series_hub_names(norm_series), collapsed
        )
    except Exception:
        logger.debug("series rename repaint failed", exc_info=True)
