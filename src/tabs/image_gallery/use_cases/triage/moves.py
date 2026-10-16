"""Triage move-to-_rejected helpers — thin-owner plain functions.

Split out of ``tabs.image_gallery.use_cases.triage`` (plan-gallery-split-2026-10-17
Part C5). Resolving the target folder and moving rejected files to
``<folder>/_rejected/`` (move-only, never delete).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from core.state_management.gallery_actions import GalleryItemsRemoved

from .compare import _refresh_owner_grid, is_rejected
from .emit import _emit_gallery, _items_of
from .removal import _detach_pool_items

logger = logging.getLogger("ImproveImgSLI")


def resolve_move_folder(owner, rejected: list | None = None) -> Path | None:
    """Folder whose ``_rejected/`` receives the move (single source of truth).

    State folder first; file-drop sessions carry no folder context, so fall
    back to the rejected items' common parent. None when neither resolves
    (the overlay subtitle shows the ``<folder>`` literal in that case).
    """
    try:
        folder = getattr(getattr(owner, "state", None), "folder", None)
    except Exception:
        folder = None
    if folder:
        try:
            return Path(folder)
        except Exception:
            pass
    try:
        parents = {
            str(Path(getattr(it, "path", None)).parent)
            for it in list(rejected or [])
            if getattr(it, "path", None)
        }
    except Exception:
        parents = set()
    if len(parents) == 1:
        try:
            return Path(next(iter(parents)))
        except Exception:
            return None
    return None


def clean_rejected(owner) -> list[dict]:
    """Move rejected files to <folder>/_rejected/ (move-only, never delete).

    Mirrors :func:`remove_paths_from_grid`: the moved items are dropped from
    the local pool (their ``path`` is never rewritten), selection/series are
    pruned, and ONLY ``GalleryItemsRemoved`` is emitted — the ``_rejected/``
    locations are NOT gallery members, so nothing re-renders them. The
    removed item objects ride on the move records so :func:`restore_moves`
    can put the cards back (files + cards). Returns list of move records
    for undo.
    """
    st = getattr(owner, "state", None)
    if st is None:
        return []
    rejected = [it for it in _items_of(owner) if is_rejected(it)]
    if not rejected:
        return []
    folder = resolve_move_folder(owner, rejected)
    if folder is None:
        logger.warning("triage.clean_rejected: no folder")
        return []
    target = folder / "_rejected"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("triage.clean_rejected: mkdir failed %s", target)
        return []
    moves: list[dict] = []
    for it in rejected:
        src = Path(it.path)
        if not src.is_file():
            continue
        dst = target / src.name
        # Avoid overwrite: suffix with counter
        counter = 1
        base_dst = dst
        while dst.exists():
            dst = base_dst.with_name(f"{base_dst.stem}_{counter}{base_dst.suffix}")
            counter += 1
        # Remember the pool slot so Undo can re-insert in order.
        try:
            index = list(getattr(st, "items", []) or []).index(it)
        except Exception:
            index = None
        try:
            shutil.move(str(src), str(dst))
            moves.append(
                {
                    "src": str(dst),
                    "dst": str(src),
                    "path": str(src),
                    "item": it,
                    "index": index,
                }
            )
        except Exception:
            logger.exception("triage.clean_rejected: move failed %s -> %s", src, dst)
    if moves:
        # Drop the moved cards from the local pool (no path rewrite), prune
        # selection/series, then emit ONLY the removal — the _rejected/
        # locations are not gallery members (working-sibling parity with
        # remove_paths_from_grid).
        try:
            target_set = set()
            for m in moves:
                try:
                    target_set.add(Path(m["path"]))
                except Exception:
                    continue
            _detach_pool_items(owner, target_set)
            _emit_gallery(
                owner,
                GalleryItemsRemoved(paths=sorted({str(m["path"]) for m in moves})),
            )
        except Exception:
            logger.debug("triage.clean_rejected: pool removal failed", exc_info=True)
    _refresh_owner_grid(owner)
    logger.debug("triage.clean_rejected: moved %d", len(moves))
    return moves
