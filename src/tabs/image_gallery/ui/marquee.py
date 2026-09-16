"""Marquee band-select for the gallery grid.

Mirrors ``tabs/session_picker/recent/marquee.py`` but for the 4-column
gallery grid. Functions take the grid view as first arg and read/write its
``_marquee_gesture``/``_marquee_additive``/``_marquee_base`` state, same as
the session picker pattern.

Public API:
  ensure_marquee_gesture(view) -> MarqueeBandGesture
  paths_for_rect(view, rect) -> set[Path]
  on_rect_update(view, rect)
  on_rect_finish(view, rect)
  event_filter(view, watched, event) -> bool  (host mouse press → start band)
  host_mouse_press(view, event) -> bool

The gesture uses ``MarqueeBandGesture`` + ``MarqueeBandOverlay`` (Wayland-safe
app event filter, no grabMouse) and clips against the scroll viewport.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QMouseEvent

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import MarqueeBandGesture

try:
    from tabs.image_gallery.ui.grid_view import GRID_COLUMNS, GRID_MARGIN, GRID_SPACING, GALLERY_CARD_W, GALLERY_CARD_H
except Exception:
    GRID_COLUMNS = 4
    GRID_MARGIN = 8
    GRID_SPACING = 12
    GALLERY_CARD_W = 160
    GALLERY_CARD_H = 168

try:
    from ui.widgets.shelf.selection import ctrl_held as _ctrl_held  # reuse helper
except Exception:
    def _ctrl_held(mods):  # type: ignore[no-untyped-def]
        return bool(mods & Qt.KeyboardModifier.ControlModifier) or bool(mods & Qt.KeyboardModifier.MetaModifier)


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
    ``rect`` is host-local from ``MarqueeBandGesture``; overlay itself is
    ``MarqueeBandOverlay`` (Wayland-safe, no grabMouse).
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


def ensure_marquee_gesture(view) -> MarqueeBandGesture:  # type: ignore[no-untyped-def]
    """Lazily create (or re-clip) the MarqueeBandGesture for *view*."""
    gesture = getattr(view, "_marquee_gesture", None)
    host = getattr(view, "items_host", None)
    viewport = None
    try:
        viewport = view.scroll_area.viewport()
    except Exception:
        viewport = None
    accent = getattr(view, "_selection_accent", None)
    if gesture is None:
        gesture = MarqueeBandGesture(
            host,
            parent=view,
            clip_widget=viewport,
            on_update=lambda r: on_rect_update(view, r),
            on_finish=lambda r: on_rect_finish(view, r),
        )
        try:
            view._marquee_gesture = gesture  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        try:
            gesture.set_clip_widget(viewport)
        except Exception:
            pass
    if accent is not None:
        try:
            gesture.set_accent(accent)
        except Exception:
            pass
    return gesture


def on_rect_update(view, rect: QRect) -> None:  # type: ignore[no-untyped-def]
    """Preview selection while the band is dragging."""
    paths = paths_for_rect(view, rect)
    additive = bool(getattr(view, "_marquee_additive", False))
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


def on_rect_finish(view, rect: QRect) -> None:  # type: ignore[no-untyped-def]
    """Commit selection when the band finishes."""
    if rect.isEmpty():
        additive = bool(getattr(view, "_marquee_additive", False))
        if not additive:
            # Empty band with no additive → clear preview? Commit empty only if not additive.
            owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
            if owner is not None:
                try:
                    import tabs.image_gallery.use_cases.selection as sel

                    sel.commit(owner, set(), additive=False)
                    return
                except Exception:
                    pass
            try:
                base = getattr(view, "_marquee_base", set()) or set()
                view.apply_selection(set(base))
            except Exception:
                pass
        return
    paths = paths_for_rect(view, rect)
    additive = bool(getattr(view, "_marquee_additive", False))
    # Commit via owner if available.
    owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
    if owner is not None:
        try:
            import tabs.image_gallery.use_cases.selection as sel

            sel.commit(owner, paths, additive=additive)
            return
        except Exception:
            pass
    cb = getattr(view, "_on_marquee_commit", None)
    if callable(cb):
        try:
            cb(paths, additive)
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


def host_mouse_press(view, event: QMouseEvent) -> bool:  # type: ignore[no-untyped-def]
    if event.button() != Qt.MouseButton.LeftButton:
        return False
    host = getattr(view, "items_host", None)
    if host is None:
        return False
    try:
        child = host.childAt(event.position().toPoint())
    except Exception:
        child = None
    if child is not None:
        return False
    try:
        view._marquee_additive = bool(_ctrl_held(event.modifiers()))  # type: ignore[attr-defined]
    except Exception:
        view._marquee_additive = False  # type: ignore[attr-defined]
    # Snapshot base selection.
    try:
        from pathlib import Path as _Path  # noqa: F401
        sel = None
        owner = getattr(view, "_owner", None) or getattr(view, "owner", None)
        if owner is not None and hasattr(getattr(owner, "state", None), "selected_paths"):
            sel = getattr(owner.state, "selected_paths", None)
        if sel is None:
            sel = getattr(view, "_selection", None) or getattr(view, "_selection_paths", lambda: set())()
            if callable(sel):
                sel = sel()
        view._marquee_base = set(sel) if sel is not None else set()  # type: ignore[attr-defined]
    except Exception:
        view._marquee_base = set()  # type: ignore[attr-defined]
    gesture = ensure_marquee_gesture(view)
    try:
        if not gesture.start(event.position().toPoint()):
            return False
    except Exception:
        return False
    # Live preview clear for non-additive.
    cb = getattr(view, "_on_marquee_preview", None)
    if callable(cb):
        try:
            cb(set(), bool(getattr(view, "_marquee_additive", False)))
        except Exception:
            pass
    else:
        # Preview empty band immediately (non-additive clears).
        if not bool(getattr(view, "_marquee_additive", False)):
            try:
                view.apply_selection(set())
            except Exception:
                pass
    return True


def event_filter(view, watched: QObject, event: QEvent) -> bool:  # type: ignore[no-untyped-def]
    host = getattr(view, "items_host", None)
    if watched is host and event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
        return host_mouse_press(view, event)
    return False
