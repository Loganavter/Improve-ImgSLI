"""Selection application for the gallery marquee (preview + commit).

Tab-specific end of the shared drag plumbing
(``ui.widgets.shelf.marquee_plumbing``): the geometry that turns a band
rect into gallery paths lives here, together with the gallery preview /
commit / snapshot callbacks bound into :data:`GALLERY_WIRING`. ``marquee``
re-exports the wrapper names, so existing import sites keep working.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect

from sli_ui_toolkit.managers import scaled_px
from ui.widgets.shelf.marquee_plumbing import MarqueeWiring, on_rect_finish as _finish
from ui.widgets.shelf.marquee_plumbing import on_rect_update as _update


def _mdbg(msg: str, *args) -> None:
    """Marquee trace via gallery_debug (env-gated, fail-open)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(msg, *args)
    except Exception:
        pass


def _commit_allowed() -> bool:
    """Elimination gate (bisect, not a feature).

    ``IMGSLI_GALLERY_NO_MARQUEE_COMMIT=1`` keeps gesture + preview alive
    while skipping the commit, to decide whether a selection artifact
    lives in the finish path.
    """
    try:
        from shared.debug_flags import env_flag

        return not bool(env_flag("IMGSLI_GALLERY_NO_MARQUEE_COMMIT"))
    except Exception:
        return True


def _base_snapshot(view) -> set:  # type: ignore[no-untyped-def]
    """Press-time selection: owner state wins, else the view's own."""
    owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
    sel = None
    if owner is not None and hasattr(getattr(owner, "state", None), "selected_paths"):
        sel = getattr(owner.state, "selected_paths", None)
    if sel is None:
        sel = getattr(view, "_selection", None) or getattr(view, "_selection_paths", lambda: set())()
        if callable(sel):
            sel = sel()
    return set(sel) if sel is not None else set()


def _press_preview(view, additive: bool) -> None:  # type: ignore[no-untyped-def]
    """Live preview clear right after band start (non-additive drags)."""
    cb = getattr(view, "_on_marquee_preview", None)
    if callable(cb):
        try:
            cb(set(), bool(additive))
        except Exception:
            pass
    elif not bool(additive):
        try:
            view.apply_selection(set())
        except Exception:
            pass


def _preview(view, paths: set, additive: bool) -> None:  # type: ignore[no-untyped-def]
    """Preview selection while the band is dragging (owner-first)."""
    try:
        import time as _time

        _t_apply_start = _time.perf_counter()
    except Exception:
        _t_apply_start = None  # type: ignore[assignment]
    # Prefer owner's preview helper if view delegates to an owner.
    owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
    if owner is not None:
        # Try commit_preview on owner.
        for mod_name in ("tabs.image_gallery.use_cases.selection",):
            try:
                import importlib

                mod = importlib.import_module(mod_name)
                if hasattr(mod, "commit_preview"):
                    mod.commit_preview(owner, paths, additive=additive)
                    try:
                        import time as _time3

                        _mdbg(
                            "marquee UPDATE-COST apply(owner)=%.1fms",
                            (_time3.perf_counter() - _t_apply_start) * 1000.0,  # type: ignore[operator]
                        )
                    except Exception:
                        pass
                    return
            except Exception:
                pass
    # Fallback: drive view's own selection preview without mutating state.
    base = getattr(view, "_marquee_base", set()) or set()
    try:
        from ui.widgets.shelf.selection import preview_selection

        base_paths = set(Path(p) if not isinstance(p, Path) else p for p in base)
        preview = preview_selection(base_paths, paths, additive=additive)
    except Exception:
        if additive:
            preview = set(base) | set(paths)
        else:
            preview = set(paths)
    # Apply to view without committing to owner state.
    try:
        view.apply_selection(preview)
    except Exception:
        pass
    # Also notify on_marquee_preview hook if view exposes it.
    cb = getattr(view, "_on_marquee_preview", None)
    if callable(cb):
        try:
            cb(paths, additive)
        except Exception:
            pass
    try:
        import time as _time2

        _mdbg(
            "marquee UPDATE-COST apply=%.1fms",
            (_time2.perf_counter() - _t_apply_start) * 1000.0,  # type: ignore[operator]
        )
    except Exception:
        pass


def _commit(view, paths: set, additive: bool) -> None:  # type: ignore[no-untyped-def]
    """Commit selection when the band finishes (empty set clears or keeps)."""
    if not _commit_allowed():
        _mdbg("marquee finish SKIP commit (elimination gate IMGSLI_GALLERY_NO_MARQUEE_COMMIT=1)")
        return
    if not paths:
        if not additive:
            # Empty band with no additive → clear preview? Commit empty only if not additive.
            # Tiny-drag (< min_drag_px on both axes, see toolkit gesture) lands
            # here too — this line distinguishes "shrink to click clears"
            # from "shrink kept (additive)".
            owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
            if owner is not None:
                try:
                    import tabs.image_gallery.use_cases.selection as sel

                    sel.commit(owner, set(), additive=False)
                    _mdbg("marquee finish COMMIT-EMPTY via owner (cleared, non-additive)")
                    return
                except Exception:
                    pass
            try:
                base = getattr(view, "_marquee_base", set()) or set()
                view.apply_selection(set(base))
                _mdbg("marquee finish RESTORE-BASE n=%d (no owner)", len(set(base)))
            except Exception:
                pass
        else:
            _mdbg("marquee finish EMPTY-KEPT (additive, no clear)")
        return
    # Commit via owner if available.
    owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
    if owner is not None:
        try:
            import tabs.image_gallery.use_cases.selection as sel

            sel.commit(owner, paths, additive=additive)
            _mdbg("marquee finish COMMIT via owner paths=%d additive=%s", len(paths), additive)
            return
        except Exception:
            pass
    cb = getattr(view, "_on_marquee_commit", None)
    if callable(cb):
        try:
            cb(paths, additive)
            _mdbg("marquee finish COMMIT via hook paths=%d additive=%s", len(paths), additive)
            return
        except Exception:
            pass
    # Fallback: commit directly on view's selection state if it owns one.
    try:
        current = set(getattr(view, "_selection", set()) or set())
        if additive:
            current = current | set(str(p) for p in paths)
        else:
            current = set(str(p) for p in paths)
        # Normalize to Path if view expects Path.
        norm = set(Path(p) for p in current)
        view.apply_selection(norm)
        # Persist via the controller dispatch — never write owner.state
        # directly. A widget threaded as owner resolves to its attached
        # controller first (fail-open: owners without set_selection skip).
        try:
            triage = owner
            resolve = getattr(owner, "_owner_for_triage", None)
            if callable(resolve):
                try:
                    triage = resolve()
                except Exception:
                    triage = owner
            commit_sel = getattr(triage, "set_selection", None)
            if callable(commit_sel):
                commit_sel(norm)
        except Exception:
            pass
    except Exception:
        pass


GALLERY_WIRING = MarqueeWiring(
    hit_test=lambda view, rect: paths_for_rect(view, rect),
    preview=_preview,
    commit=_commit,
    base_snapshot=_base_snapshot,
    press_preview=_press_preview,
    trace=_mdbg,
    state_trace=lambda line: _mdbg(line),
)


def on_rect_update(view, rect: QRect) -> None:  # type: ignore[no-untyped-def]
    """Preview selection while the band is dragging (shared plumbing)."""
    _update(view, rect, GALLERY_WIRING)


def on_rect_finish(view, rect: QRect) -> None:  # type: ignore[no-untyped-def]
    """Commit selection when the band finishes (shared plumbing)."""
    _finish(view, rect, GALLERY_WIRING)


try:
    from tabs.image_gallery.ui.grid_view import GRID_COLUMNS, GRID_MARGIN, GRID_SPACING, GALLERY_CARD_W, GALLERY_CARD_H
except Exception:
    GRID_COLUMNS = 4
    GRID_MARGIN = 8
    GRID_SPACING = 12
    GALLERY_CARD_W = 160
    GALLERY_CARD_H = 168


def _card_rect_for_index(index: int, *, columns: int, host_width: int) -> QRect:  # noqa: ARG001
    # host_width not needed for fixed 4-col absolute placement, but kept for signature parity.
    card_w = scaled_px(GALLERY_CARD_W)
    card_h = scaled_px(GALLERY_CARD_H)
    stride_x = card_w + scaled_px(GRID_SPACING)
    stride_y = card_h + scaled_px(GRID_SPACING)
    row, col = divmod(int(index), max(1, int(columns)))
    x = scaled_px(GRID_MARGIN) + col * stride_x
    y = scaled_px(GRID_MARGIN) + row * stride_y
    return QRect(x, y, card_w, card_h)


def _card_geometry_rect(view, item, index: int) -> QRect:  # type: ignore[no-untyped-def]
    """Live geometry for *item*'s card — host-local ``QRect`` with grid fallback.

    Tries ``card.geometry()`` first (covers series headers and scaled_px offsets);
    falls back to the fixed-grid ``_card_rect_for_index`` when the card is not
    yet pooled/visible (virtualized or before first layout).
    """
    try:
        # Direct lookup via grid view pool.
        card = None
        for attr in ("card_for", "_card_for"):
            fn = getattr(view, attr, None)
            if callable(fn):
                try:
                    card = fn(getattr(item, "path", item))
                    if card is not None:
                        break
                except Exception:
                    continue
        if card is None:
            mp = getattr(view, "_cards_by_path", None) or getattr(view, "cards_by_path", None)
            if isinstance(mp, dict):
                try:
                    key = str(getattr(item, "path", ""))
                    card = mp.get(key) or mp.get(Path(key))
                except Exception:
                    card = None
        if card is not None:
            try:
                g = card.geometry()
                if g is not None and not g.isEmpty() and g.isValid():
                    # Already host-local (Button parent is items_host); normalize.
                    return QRect(g)
            except Exception:
                pass
            # Try map if card parent != host (edge case).
            try:
                host = getattr(view, "items_host", None)
                if host is not None and card.parentWidget() is not host:
                    tl = card.mapTo(host, card.rect().topLeft()) if hasattr(card, "mapTo") else None
                    if tl is not None:
                        return QRect(tl.x(), tl.y(), scaled_px(GALLERY_CARD_W), scaled_px(GALLERY_CARD_H))
            except Exception:
                pass
    except Exception:
        pass
    # Fallback — fixed grid.
    try:
        columns = getattr(view, "grid_columns", GRID_COLUMNS)
        host = getattr(view, "items_host", None)
        host_w = int(host.width()) if host is not None and hasattr(host, "width") else 0
    except Exception:
        columns = GRID_COLUMNS
        host_w = 0
    return _card_rect_for_index(index, columns=columns, host_width=host_w)


def paths_for_rect(view, rect: QRect) -> set[Path]:  # type: ignore[no-untyped-def]
    """Return gallery paths whose card geometry intersects *rect* (host-local).

    Uses live ``card.geometry()`` per card (header-aware via host layout) with
    fixed-grid fallback for offscreen/pooled cards (``_card_geometry_rect``).
    ``rect`` is host-local from ``MarqueeState``; the band paints in the
    viewport band widget (see ``ui.widgets.shelf.marquee_plumbing``).
    """
    if rect.isEmpty():
        return set()
    items = getattr(view, "_items", None) or getattr(view, "items", None) or []
    # Normalize items to list.
    try:
        items = list(items() if callable(items) else items)  # type: ignore[no-untyped-call]
    except Exception:
        items = list(items)
    if not items:
        return set()
    hit: set[Path] = set()
    for idx, item in enumerate(items):
        geom = _card_geometry_rect(view, item, idx)
        if geom.intersects(rect):
            try:
                p = item.path
                hit.add(Path(p) if not isinstance(p, Path) else p)
            except Exception:
                continue
    return hit


# Back-compat alias used by task description.
def paths_for_marquee_rect(view, rect: QRect) -> set[Path]:  # type: ignore[no-untyped-def]
    return paths_for_rect(view, rect)
