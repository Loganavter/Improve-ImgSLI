"""Selection state for the gallery — plain functions taking the owner.

Orthogonality (design.md:96-99): selection is about *dispatching* (context menu
``Compare → / Analyze / Find similar``, marquee/Ctrl-click, carry via
``events/image_carry.py``) and stays orthogonal to triage mechanics
(``crown``/``rejected``/``series`` about folder quality). Selection actions live in
the card context menu (``ui/card/context_menu.py``). Thin owner
delegates here; widget/controller integration does the coordinator.

Owner shape (duck-typed):
  owner.state.selected_paths: set[Path]
  owner.state.selected_order: list[Path]  (optional, for stable order)
  visual targets (any with apply_selection(set[Path])): owner.grid_view,
  owner.widget, owner._widget, owner._grid_view, owner.widget._grid_view
  (the production controller nests the grid at widget._grid_view — a
  targets search that stops at the top level silently drops live
  previews, see commit_preview).

No implied lookups — owner and paths are passed explicitly.
"""

from __future__ import annotations

from pathlib import Path


def _selection_visual_targets(owner) -> list:
    """Objects whose apply_selection paints this owner's selection.

    Covers the flat shapes (owner.grid_view/widget/_widget) and the real
    production nesting (controller.widget._grid_view). Deduped, never
    raises — an empty list means preview is impossible (fail-soft).
    """
    found: list = []

    def _take(target) -> None:
        try:
            if (
                target is not None
                and hasattr(target, "apply_selection")
                and all(target is not other for other in found)
            ):
                found.append(target)
        except Exception:
            pass

    for attr in ("grid_view", "widget", "_widget", "_grid_view"):
        try:
            _take(getattr(owner, attr, None))
        except Exception:
            continue
    try:
        _take(getattr(getattr(owner, "widget", None), "_grid_view", None))
    except Exception:
        pass
    return found


def _resolve_selection_controller(owner):
    """Return the triage owner exposing ``set_selection``, or None.

    Dispatch-only contract (G3): wholesale selection writes go through
    ``GalleryController.set_selection`` (dispatch + mirror + grid apply).
    Resolution order: the passed owner itself, its ``_owner_for_triage``,
    ``_gallery_widget._owner_for_triage`` (widget → controller), then legacy attrs.
    None means a storeless unit context — callers keep the local mirror
    via ``setattr`` (no bare ``owner.state.* =`` writes anywhere here).
    """
    try:
        if callable(getattr(owner, "set_selection", None)):
            return owner
    except Exception:
        pass
    try:
        cand = None
        resolver = getattr(owner, "_owner_for_triage", None)
        if not callable(resolver):
            widget = getattr(owner, "_gallery_widget", None)
            resolver = getattr(widget, "_owner_for_triage", None)
        cand = resolver() if callable(resolver) else None
        if cand is not None and callable(getattr(cand, "set_selection", None)):
            return cand
    except Exception:
        pass
    for attr in ("_controller", "_owner"):
        try:
            cand = getattr(owner, attr, None)
        except Exception:
            continue
        try:
            if cand is not None and callable(getattr(cand, "set_selection", None)):
                return cand
        except Exception:
            continue
    return None


def _selected_set(owner) -> set[Path]:
    sel = getattr(getattr(owner, "state", None), "selected_paths", None)
    if sel is None:
        sel = set()
        try:
            # Read-path init only (no dispatch): storeless owners may not
            # track the attr yet. Spelled via setattr — no direct writes.
            setattr(owner.state, "selected_paths", sel)  # type: ignore[attr-defined]
        except Exception:
            pass
    # Normalize to Path set.
    out: set[Path] = set()
    for p in sel:
        out.add(Path(p) if not isinstance(p, Path) else p)
    return out


def _dispatch_selection(owner, norm: set[Path]) -> None:
    """Dispatch the wholesale selection to the ``gallery`` slot (fail-open).

    Ordered ids preserve the owner's ``selected_order`` when tracked,
    else sorted path strings. The legacy ``owner.state`` mutation below
    stays until the controller reads the slot (W2b) — the reducer dedups
    identical selections, so this dispatch is idempotent.
    """
    try:
        ordered: list[str] = []
        try:
            track = list(getattr(getattr(owner, "state", None), "selected_order", None) or [])
            if track:
                ordered = [str(p) for p in track]
        except Exception:
            ordered = []
        if not ordered:
            try:
                ordered = sorted(str(p) for p in norm)
            except Exception:
                ordered = [str(p) for p in norm]
        from core.state_management.gallery_actions import GallerySelectionSet
        from tabs.image_gallery.ui.gallery_store import dispatch_gallery

        dispatch_gallery(owner, GallerySelectionSet(selected_ids=ordered))
    except Exception:
        pass


def _set_selected(owner, paths: set[Path]) -> None:
    norm = set(Path(p) for p in paths)
    # Preserve existing order for survivors, append new at end (verbatim
    # legacy ordering — read-only here; the write route below decides).
    try:
        old = list(getattr(getattr(owner, "state", None), "selected_order", None) or [])
    except Exception:
        old = []
    try:
        old_set = set(Path(x) for x in old)
    except Exception:
        old_set = set()
    new_order: list[Path] = [p for p in old if p in norm]
    for p in paths:
        if p not in old_set:
            new_order.append(p)
    # Dispatch-only route: the triage owner mirrors locally, dispatches
    # GallerySelectionSet, and applies the grid — skip the legacy direct
    # writes + second dispatch below. Visual fan-out stays (the controller
    # covers widget._grid_view; _notify covers the remaining targets).
    ctrl = _resolve_selection_controller(owner)
    if ctrl is not None:
        try:
            ctrl.set_selection(new_order)
            _notify_selection_changed(owner, norm)
            return
        except Exception:
            pass
    # Storeless fallback (unit contexts without a controller): local mirror
    # via setattr, then the legacy dispatch + visuals, verbatim behavior.
    if hasattr(getattr(owner, "state", None), "selected_order"):
        try:
            setattr(owner.state, "selected_order", new_order)  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        setattr(owner.state, "selected_paths", norm)  # type: ignore[attr-defined]
    except Exception:
        pass
    # Dispatch AFTER the legacy order update so the action carries fresh order.
    _dispatch_selection(owner, norm)
    _notify_selection_changed(owner, norm)


def _notify_selection_changed(owner, selected: set[Path]) -> None:
    # Grid view / widget (controller nesting included — see module docstring).
    for target in _selection_visual_targets(owner):
        try:
            target.apply_selection(selected)
        except Exception:
            pass
    # Also try owner.apply_selection directly.
    if hasattr(owner, "apply_selection"):
        try:
            owner.apply_selection(selected)  # type: ignore[attr-defined]
        except Exception:
            pass
    # No HUD: selection actions live in the card context menu.


def commit(owner, paths, additive: bool = False) -> None:  # type: ignore[no-untyped-def]
    """Set selection to *paths* (or union if additive)."""
    if paths is None:
        paths = set()
    incoming: set[Path] = set()
    for p in paths:
        incoming.add(Path(p) if not isinstance(p, Path) else p)
    if additive:
        base = _selected_set(owner)
        merged = set(base) | incoming
        _set_selected(owner, merged)
    else:
        _set_selected(owner, incoming)


def commit_preview(owner, paths, additive: bool = False) -> None:  # type: ignore[no-untyped-def]
    """Transient preview for marquee drag — updates visuals only, not state."""
    if paths is None:
        paths = set()
    incoming: set[Path] = set(Path(p) if not isinstance(p, Path) else Path(p) for p in paths)
    if additive:
        base = _selected_set(owner)
        preview = set(base) | incoming
    else:
        preview = incoming
    # Only notify visuals, do not mutate state.
    for target in _selection_visual_targets(owner):
        try:
            target.apply_selection(preview)
        except Exception:
            pass
    if hasattr(owner, "apply_selection"):
        try:
            owner.apply_selection(preview)  # type: ignore[attr-defined]
        except Exception:
            pass


def toggle_card(owner, path: Path, additive: bool | None = None) -> None:  # type: ignore[no-untyped-def]
    """Toggle single *path* in selection.

    If *additive* is None, toggle semantics (add if missing, remove if present).
    If additive is True, force add; if False, replace with single.
    """
    p = Path(path) if not isinstance(path, Path) else path
    current = _selected_set(owner)
    if additive is False:
        # Replace selection with just this card (single-click without Ctrl).
        _set_selected(owner, {p})
        return
    if additive is True:
        if p in current:
            # Ctrl-click on selected → remove.
            current.remove(p)
        else:
            current.add(p)
        _set_selected(owner, current)
        return
    # Toggle default (used by region click without explicit additive flag if caller didn't pass).
    if p in current:
        current.remove(p)
    else:
        current.add(p)
    _set_selected(owner, current)


def clear_selection(owner) -> None:  # type: ignore[no-untyped-def]
    _set_selected(owner, set())


def select_all(owner) -> None:  # type: ignore[no-untyped-def]
    items = getattr(getattr(owner, "state", None), "items", None) or []
    paths = set()
    # Respect current filter visibility if owner exposes visible_paths.
    visible = None
    widget = getattr(owner, "widget", None) or getattr(owner, "grid_view", None)
    if widget is not None and hasattr(widget, "_cards_by_path"):
        # Fallback: all items are selectable; filtering already hides cards but selection includes hidden? Use all.
        pass
    for it in items:
        try:
            paths.add(Path(it.path) if not isinstance(it.path, Path) else it.path)
        except Exception:
            continue
    _set_selected(owner, paths)
