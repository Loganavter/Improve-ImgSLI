"""Selection application for the gallery marquee (preview + commit).

Split out of ``ui/marquee.py`` per CODE_PATTERNS (gesture vs selection
seam): the gesture (press/ensure/filter) lives in ``marquee``, everything
that turns a band rect into selection state lives here. ``marquee``
re-exports both names, so existing import sites keep working.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect

from sli_ui_toolkit.managers import scaled_px

def _mdbg(msg: str, *args) -> None:
    """Marquee trace via gallery_debug (env-gated, fail-open)."""
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(msg, *args)
    except Exception:
        pass


def on_rect_update(view, rect: QRect) -> None:  # type: ignore[no-untyped-def]
    """Preview selection while the band is dragging.

    Coalescing: the gesture emits per mousemove (100+/s unthrottled) but
    most moves do not change membership. Recomputing paths is O(items)
    and re-applying repaints changed cards — so when the normalized hit
    set + additive flag match the last dispatched update, only the band
    visual (already set by the gesture) moves and this returns early.
    The signature resets on every new press (see ``host_mouse_press``),
    and ``on_rect_finish`` always recomputes, so a mid-drag layout shift
    can delay one preview frame at most, never a commit.
    """
    try:
        import time as _time

        _t_hit_start = _time.perf_counter()
    except Exception:
        _t_hit_start = None  # type: ignore[assignment]
    # Band visual (viewport space, over cards) + scroll-corrected content
    # rect for hit-testing — the two never diverge by construction.
    try:
        viewport_rect, rect = band_rects(view, rect)
    except Exception:
        viewport_rect = rect
    try:
        band = band_widget(view)
        if band is not None:
            band.set_band(viewport_rect)
    except Exception:
        pass
    paths = paths_for_rect(view, rect)
    try:
        _t_hit_ms = (_time.perf_counter() - _t_hit_start) * 1000.0  # type: ignore[operator]
        _t_apply_start = _time.perf_counter()
    except Exception:
        _t_hit_ms = -1.0
        _t_apply_start = None  # type: ignore[assignment]
    additive = bool(getattr(view, "_marquee_additive", False))
    try:
        sig = (frozenset(str(p) for p in paths), additive)
    except Exception:
        sig = None
    if sig is not None and getattr(view, "_marquee_last_update_sig", None) == sig:
        try:
            _mdbg("marquee UPDATE-skip identical membership")
        except Exception:
            pass
        return
    try:
        view._marquee_last_update_sig = sig  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        _mdbg(
            "marquee UPDATE rect=(%d,%d %dx%d) paths=%d additive=%s hit=%.1fms",
            rect.x(), rect.y(), rect.width(), rect.height(),
            len(paths), additive, _t_hit_ms,
        )
    except Exception:
        pass
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


def on_rect_finish(view, rect: QRect) -> None:  # type: ignore[no-untyped-def]
    """Commit selection when the band finishes."""
    try:
        band = band_widget(view)
        if band is not None:
            band.set_active(False)
    except Exception:
        pass
    # Compensate only real bands: empty (tiny-finish) rects must stay empty
    # so the clear path below still triggers.
    if not rect.isEmpty():
        try:
            _, rect = band_rects(view, rect)
        except Exception:
            pass
    try:
        _mdbg(
            "marquee FINISH rect=(%d,%d %dx%d) empty=%s additive=%s",
            rect.x(),
            rect.y(),
            rect.width(),
            rect.height(),
            rect.isEmpty(),
            bool(getattr(view, "_marquee_additive", False)),
        )
    except Exception:
        pass
    try:
        from shared.debug_flags import env_flag

        if bool(env_flag("IMGSLI_GALLERY_NO_MARQUEE_COMMIT")):
            _mdbg("marquee finish SKIP commit (elimination gate IMGSLI_GALLERY_NO_MARQUEE_COMMIT=1)")
            return
    except Exception:
        pass
    if rect.isEmpty():
        additive = bool(getattr(view, "_marquee_additive", False))
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
    paths = paths_for_rect(view, rect)
    additive = bool(getattr(view, "_marquee_additive", False))
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
        # Also persist to owner's state if view has owner attr.
        if owner is not None and hasattr(getattr(owner, "state", None), "selected_paths"):
            try:
                owner.state.selected_paths = norm  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        pass


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
    host's own paint pass (``MarqueeHost``).
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
