"""Carry selected images to a workspace tab via ImageCarryService.

Plain function taking the owner; no implied lookups — owner, paths, and
services are resolved explicitly from owner attributes or via direct imports.
ImageCarryService is the only dispatch path (no EventBus fallback).
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.image_extensions import is_loadable_image_path
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _selected_paths(owner) -> list[Path]:
    """Current selection, ordered — delegated to ``use_cases.action_scope``.

    The slot/mirror read and its ordering live in ONE place now
    (``action_scope.selected_paths``); this name stays as the carry-local
    alias its callers (``carry_selected`` / ``find_similar_selected``) use.
    """
    from tabs.image_gallery.use_cases import action_scope

    return action_scope.selected_paths(owner)


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


def find_similar_selected(owner, *, threshold: float = 0.15) -> bool:  # type: ignore[no-untyped-def]
    """DEPRECATED selection adapter — the action surface passes an ActionContext.

    Use ``use_cases.gallery_actions.find_similar(owner, ctx)``. This name stays
    for the pre-context callers (and the parity stub contract) and reads the
    selection through ``action_scope`` (the ONE read), never set iteration.

    Intentional placeholder for “Find similar” — semantic search for images
    similar to selection (parity plan non-goal: context-menu item stays a stub).
    Currently a stub that validates selection and returns ``False`` so callers
    can degrade gracefully; logs at debug level.
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
    """DEPRECATED selection adapter — the action surface passes an ActionContext.

    Use ``use_cases.gallery_actions.carry(owner, ctx)`` (menu) for an explicit
    target set. This name stays for the keyboard/drag call sites, whose scope
    IS the selection (read once through ``action_scope``).

    Returns True if a carry was started (preview ghost shown or drop scheduled),
    False if nothing selected or dispatch failed.
    """
    paths = _selected_paths(owner)
    if not paths:
        logger.debug("carry_selected: no selection")
        return False

    # B3: seam predicate (accepted-extension ∧ is_file) — an is_file-only
    # filter would carry a surviving non-image file into workspace tabs.
    existing = [p for p in paths if is_loadable_image_path(p)]
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

    logger.warning("carry_selected: dispatch failed — no ImageCarryService available")
    return False
