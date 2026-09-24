"""Selection state for the gallery — plain functions taking the owner.

Orthogonality (design.md:96-99): selection is about *dispatching* (HUD
``Compare → / Analyze / Find similar``, marquee/Ctrl-click, carry via
``events/image_carry.py``) and stays orthogonal to triage mechanics
(``crown``/``rejected``/``series`` about folder quality). HUD lives in
``SelectionHudController`` (``ui/selection_hud.py``, ``BaseFlyout`` pinned
bottom-center group ``gallery_selection``) and is suppressed during S3
(``clean_review`` overlay) via ``FlyoutManager`` group policy. Thin owner
delegates here; widget/controller integration does the coordinator.

Owner shape (duck-typed):
  owner.state.selected_paths: set[Path]
  owner.state.selected_order: list[Path]  (optional, for stable order)
  owner.widget or owner.grid_view: has apply_selection(set[Path]) / rebuild etc.
  owner._selection_hud: optional SelectionHudController with show/hide/update/set_suppressed

No implied lookups — owner and paths are passed explicitly.
"""

from __future__ import annotations

from pathlib import Path


def _selected_set(owner) -> set[Path]:
    sel = getattr(getattr(owner, "state", None), "selected_paths", None)
    if sel is None:
        sel = set()
        try:
            owner.state.selected_paths = sel  # type: ignore[attr-defined]
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
    try:
        owner.state.selected_paths = norm  # type: ignore[attr-defined]
    except Exception:
        pass
    # Keep ordered list if owner tracks it.
    if hasattr(getattr(owner, "state", None), "selected_order"):
        try:
            # Preserve existing order for survivors, append new at end.
            old = list(getattr(owner.state, "selected_order", []) or [])
            old_set = set(Path(x) for x in old)
            new_order: list[Path] = [p for p in old if p in norm]
            for p in paths:
                if p not in old_set:
                    new_order.append(p)
            owner.state.selected_order = new_order  # type: ignore[attr-defined]
        except Exception:
            pass
    # Dispatch AFTER the legacy order update so the action carries fresh order.
    _dispatch_selection(owner, norm)
    _notify_selection_changed(owner, norm)


def _notify_selection_changed(owner, selected: set[Path]) -> None:
    # Grid view / widget.
    for attr in ("grid_view", "widget", "_widget"):
        target = getattr(owner, attr, None)
        if target is not None and hasattr(target, "apply_selection"):
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
    # Selection HUD collaborator.
    hud = getattr(owner, "_selection_hud", None) or getattr(owner, "selection_hud", None)
    if hud is not None:
        try:
            if hasattr(hud, "update"):
                hud.update(len(selected))
            elif hasattr(hud, "set_count"):
                hud.set_count(len(selected))
        except Exception:
            pass
        try:
            if len(selected) > 0 and hasattr(hud, "show"):
                hud.show()
            elif len(selected) == 0 and hasattr(hud, "hide"):
                hud.hide()
        except Exception:
            pass


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
    for attr in ("grid_view", "widget", "_widget"):
        target = getattr(owner, attr, None)
        if target is not None and hasattr(target, "apply_selection"):
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
