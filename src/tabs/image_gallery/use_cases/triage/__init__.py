"""Stage 2 triage helpers — keep best / clean rejected / compare finalists.

Package split of the former ``use_cases/triage.py`` (plan-gallery-split-2026-10-17
Part C5): each submodule owns one concern, all bodies stay plain
functions-taking-owner, and this ``__init__`` re-exports the full surface so
``from tabs.image_gallery.use_cases.triage import X`` and
``triage.X`` keep working unchanged.

Thin-owner helpers: plain functions taking the owner (controller or widget).
No implied lookups — owner and paths are passed explicitly.

These helpers work on the current GalleryItem flags (rejected, triage_best,
etc.) and are wired to StatsStrip signals. Series resolution goes through
the sole ``_series_of`` implementation in :mod:`triage.provenance`.
"""

from __future__ import annotations

# Toolkit usage per S3 spec: scaled_px + ThemeManager tokens (no QSS) — ensure
# provenance logic respects theme scaling where UI consumes it (clean_review).
# No direct ThemeManager.get_color calls (contracts forbid outside theme infra)
# — keep import for token awareness only, no runtime call.
try:
    from sli_ui_toolkit.managers import scaled_px as _scaled_px  # noqa: F401

    ThemeManager = None  # type: ignore  # placeholder for token palette (Button variants own visuals)
    scaled_px = _scaled_px  # type: ignore
except Exception:
    scaled_px = lambda x: int(x)  # type: ignore
    ThemeManager = None  # type: ignore

from .compare import (
    _flat_series_groups,
    _is_rejected,
    _refresh_owner_grid,
    compare_finalists,
    is_keep_best_done,
    is_rejected,
    keep_best_of_series,
    should_show_all,
    show_all,
)
from .crown import keep_best, make_best, set_rejected_paths, toggle_reject
from .emit import (
    _emit_gallery,
    _emit_rank_snapshot,
    _items_of,
    _mtime_of,
    _resolve_state,
    _transact_gallery,
)
from .moves import clean_rejected, resolve_move_folder
from .provenance import (
    _series_of,
    _sync_provenance_from_series,
    ensure_provenance_series_ids,
)
from .removal import (
    _detach_pool_items,
    _reinsert_pool_item,
    remove_from_grid,
    remove_paths_from_grid,
    restore_moves,
)

__all__ = [
    "_detach_pool_items",
    "_emit_gallery",
    "_emit_rank_snapshot",
    "_flat_series_groups",
    "_is_rejected",
    "_items_of",
    "_mtime_of",
    "_refresh_owner_grid",
    "_reinsert_pool_item",
    "_resolve_state",
    "_series_of",
    "_sync_provenance_from_series",
    "_transact_gallery",
    "clean_rejected",
    "compare_finalists",
    "ensure_provenance_series_ids",
    "is_keep_best_done",
    "is_rejected",
    "keep_best",
    "keep_best_of_series",
    "make_best",
    "remove_from_grid",
    "remove_paths_from_grid",
    "resolve_move_folder",
    "restore_moves",
    "set_rejected_paths",
    "should_show_all",
    "show_all",
    "toggle_reject",
]

# Ensure provenance fields are present on GalleryItem (Stage 2 safety model)
# The model file already defines rejected/is_best/crown_rank/provenance_series_id.
