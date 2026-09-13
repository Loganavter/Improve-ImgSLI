"""Carry selected images to a workspace tab via ImageCarryService / EventBus.

Plain function taking the owner; no implied lookups — owner, paths, and
services are resolved explicitly from owner attributes or via direct imports.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ImproveImgSLI")


def _selected_paths(owner) -> list[Path]:
    state = getattr(owner, "state", None)
    if state is None:
        return []
    sel = getattr(state, "selected_paths", None) or set()
    out: list[Path] = []
    for p in sel:
        try:
            out.append(Path(p) if not isinstance(p, Path) else p)
        except Exception:
            continue
    # Preserve selected_order if available for stable dispatch order.
    order = getattr(state, "selected_order", None)
    if order:
        order_map = {Path(x) if not isinstance(x, Path) else x: i for i, x in enumerate(order)}
        try:
            out.sort(key=lambda x: order_map.get(x, 10**9))
        except Exception:
            pass
    return out


def _dispatch_via_image_carry(paths: list[Path], *, pixmap=None) -> bool:
    """Try ImageCarryService.begin / begin_image_carry."""
    try:
        from events.image_carry import begin_image_carry, ImageCarryService  # noqa: F401

        # Prefer the convenience helper which resolves singleton and preview.
        try:
            ok = begin_image_carry(paths, pixmap=pixmap)
            if ok:
                return True
        except Exception:
            logger.debug("carry: begin_image_carry failed", exc_info=True)

        # Fallback: direct singleton begin with explicit paths.
        try:
            svc = ImageCarryService.get_instance()
            return bool(svc.begin(paths, pixmap=pixmap))
        except Exception:
            logger.debug("carry: ImageCarryService.get_instance/begin failed", exc_info=True)
    except Exception:
        logger.debug("carry: ImageCarryService import failed", exc_info=True)
    return False


def _dispatch_via_event_bus(owner, paths: list[Path]) -> bool:
    """Fallback: emit via owner's EventBus if available (not primary path)."""
    bus = None
    for attr in ("event_bus", "_event_bus", "bus"):
        bus = getattr(owner, attr, None)
        if bus is not None:
            break
    if bus is None:
        # Try to resolve from main window / context if owner holds it.
        ctx = getattr(owner, "_context", None) or getattr(owner, "context", None)
        if ctx is not None:
            bus = getattr(ctx, "event_bus", None)
    if bus is None or not hasattr(bus, "emit"):
        return False
    try:
        # Generic payload — listeners on workspace switch can pick it up.
        # We avoid a hard dependency on a specific Event type; try common ones.
        from core.events import Event  # noqa: F401

        # Use a lightweight dict-like event if available; otherwise no-op.
        # Emit a simple custom event carrying paths.
        class GalleryCarryRequested:  # minimal duck-typed Event
            def __init__(self, paths):  # type: ignore[no-untyped-def]
                self.paths = paths

        bus.emit(GalleryCarryRequested(paths))
        return True
    except Exception:
        logger.debug("carry: EventBus emit failed", exc_info=True)
        return False


def find_similar_selected(owner, *, threshold: float = 0.15) -> bool:  # type: ignore[no-untyped-def]
    """Stub for “Find similar” — semantic search for images similar to selection.

    Prepared HUD API: ``SelectionHudController`` wires ``Find similar`` → this.
    Widget/controller integration (coordinator) will handle actual filtering
    (embedding/phash nearest neighbours, threshold) and selection update.
    Currently a stub that validates selection and returns ``False`` so callers
    can degrade gracefully; logs at debug level.

    Returns ``True`` only when a future implementation actually selects similar
    items; ``False`` otherwise (no selection or not yet implemented).
    """
    paths = _selected_paths(owner)
    if not paths:
        logger.debug("find_similar_selected: no selection")
        return False
    # Stub — no embedding search yet; coordinator will override.
    logger.debug("find_similar_selected: stub — %d selected, threshold=%s (not implemented)", len(paths), threshold)
    # Optionally notify that feature is pending (no state change).
    return False


def carry_selected(owner, *, pixmap=None) -> bool:  # type: ignore[no-untyped-def]
    """Dispatch selected images to the workspace carry flow.

    Returns True if a carry was started (preview ghost shown or drop scheduled),
    False if nothing selected or dispatch failed.
    """
    paths = _selected_paths(owner)
    if not paths:
        logger.debug("carry_selected: no selection")
        return False

    # Verify files still exist (filtered out missing mover may still be selected).
    existing = [p for p in paths if p.is_file()]
    if not existing:
        logger.warning("carry_selected: no existing files in selection")
        return False

    # If no pixmap supplied, try to use first item's thumbnail.
    if pixmap is None:
        state = getattr(owner, "state", None)
        items = getattr(state, "items", None) or []
        by_path = {Path(it.path): it for it in items if hasattr(it, "path")}
        first = existing[0]
        item = by_path.get(first)
        if item is not None and getattr(item, "thumbnail", None) is not None:
            try:
                from PySide6.QtGui import QPixmap  # noqa: F401

                thumb = item.thumbnail
                if thumb is not None and not thumb.isNull():
                    pixmap = thumb
            except Exception:
                pixmap = None

    if _dispatch_via_image_carry(existing, pixmap=pixmap):
        logger.debug("carry_selected: dispatched via ImageCarryService (%d paths)", len(existing))
        return True

    if _dispatch_via_event_bus(owner, existing):
        logger.debug("carry_selected: dispatched via EventBus (%d paths)", len(existing))
        return True

    logger.warning("carry_selected: dispatch failed — no ImageCarryService/EventBus available")
    return False
