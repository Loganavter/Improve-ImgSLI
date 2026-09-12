from __future__ import annotations

from shared.image_processing.regions import UniformTileGrid, build_uniform_tile_grid
from shared.rendering.tile_constants import DEFAULT_TILE_EXTENT
from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled

__all__ = ["DEFAULT_TILE_EXTENT", "TileIndex", "TileTextureService"]

TileIndex = tuple[int, int]


TileSlot = tuple[int, int]  # (array_index, layer)

# Conservative default: below the smallest `TextureArraySizeMax` observed
# across supported backends (see docs/dev/rendering/tile-array-atlas-plan.md
# Phase 0 -- OpenGL and Vulkan both measured 2048 locally). Callers that know
# the real backend limit (via `rhi.resourceLimit(QRhi.ResourceLimit
# .TextureArraySizeMax)`) should pass it explicitly.
DEFAULT_MAX_ARRAY_SIZE = 2048


class _TileSlotAllocator:
    """Maps arbitrary hashable keys to `(array_index, layer)` slots inside
    one or more fixed-capacity texture arrays, with free-list reuse so a
    freed layer is handed out again before a new array is opened.

    Pure bookkeeping -- never creates or destroys a GPU texture; that is
    the caller's job (see docs/dev/rendering/tile-array-atlas-plan.md
    Phase 1/2)."""

    def __init__(self, max_array_size: int) -> None:
        self._max_array_size = max(1, int(max_array_size))
        self._slot_for_key: dict[object, TileSlot] = {}
        self._free_slots: list[TileSlot] = []
        self._next_layer_in_current_array = 0
        self._array_count = 1

    def slot_for(self, key: object) -> TileSlot | None:
        return self._slot_for_key.get(key)

    def allocate(self, key: object) -> TileSlot:
        existing = self._slot_for_key.get(key)
        if existing is not None:
            return existing
        if self._free_slots:
            slot = self._free_slots.pop()
        else:
            if self._next_layer_in_current_array >= self._max_array_size:
                self._array_count += 1
                self._next_layer_in_current_array = 0
            slot = (self._array_count - 1, self._next_layer_in_current_array)
            self._next_layer_in_current_array += 1
        self._slot_for_key[key] = slot
        return slot

    def free(self, key: object) -> TileSlot | None:
        slot = self._slot_for_key.pop(key, None)
        if slot is not None:
            self._free_slots.append(slot)
        return slot

    def rekey(self, old_key: object, new_key: object) -> None:
        """Renames an already-allocated slot's key without freeing it --
        the GPU layer keeps whatever content it holds. See
        ``TileTextureService.rekey_source``."""
        slot = self._slot_for_key.pop(old_key, None)
        if slot is not None:
            self._slot_for_key[new_key] = slot


def _tile_indices_with_margin(grid, visible_indices, margin: int) -> set[TileIndex]:
    target: set[TileIndex] = set()
    for row, col in visible_indices:
        for delta_row in range(-margin, margin + 1):
            for delta_col in range(-margin, margin + 1):
                candidate_row = row + delta_row
                candidate_col = col + delta_col
                if 0 <= candidate_row < grid.rows and 0 <= candidate_col < grid.columns:
                    target.add((candidate_row, candidate_col))
    return target


class TileTextureService:
    """Owns, per registered source_id, one UniformTileGrid, the set of tile
    indices currently resident as GPU textures, and the LRU/byte-budget
    state used to decide what to evict. A normal image ends up with a 1x1
    grid whose single tile key is the source_id itself (so existing
    per-image upload/cache-restore call sites need no changes for the N=1
    case); a >max_tile_extent image gets an NxM grid instead.

    This service decides *which* tile indices should be resident/evicted;
    it never creates, uploads to, or destroys a GPU texture itself -- that's
    the caller's job (e.g. a compare tab's own ``canvas/rhi_renderer/
    resources.py``), driven by what ``resolve_visible_tiles``/
    ``evict_over_budget`` return. Keeping GPU calls out of this class is
    what makes it unit-testable with plain Python objects, and is why it
    lives at the shared rendering level rather than under any one tab --
    any canvas (the compare tabs, ...) that needs to render
    images larger than one GPU texture can reuse it as-is."""

    def __init__(
        self,
        *,
        max_tile_extent: int = DEFAULT_TILE_EXTENT,
        max_array_size: int = DEFAULT_MAX_ARRAY_SIZE,
    ) -> None:
        self._max_tile_extent = max(1, int(max_tile_extent))
        self._grids: dict[object, UniformTileGrid] = {}
        self._resident: dict[object, set[TileIndex]] = {}
        # LRU state for byte-budget eviction, keyed by (source_id, tile
        # index). Populated only for multi-tile grids -- see
        # resolve_visible_tiles/mark_resident, driven from the caller's
        # GPU resource manager.
        self._tile_byte_sizes: dict[tuple[object, TileIndex], int] = {}
        self._tile_last_used: dict[tuple[object, TileIndex], int] = {}
        self._tile_use_counter = 0
        # Content pixel size at upload time, keyed like _tile_byte_sizes
        # (docs/dev/rendering/tile-array-atlas-plan.md Phase 2) -- lets a
        # renderer's draw-plan builder compute a texture-array tile's
        # content-scale (contentPx / arrayLayerPx) without needing to ask the
        # GPU resource owner, which this service is deliberately decoupled
        # from (see class docstring).
        self._tile_content_size: dict[tuple[object, TileIndex], tuple[int, int]] = {}
        # Texture-array slot allocator (docs/dev/rendering/
        # tile-array-atlas-plan.md Phase 1). Keyed the same as
        # `_tile_byte_sizes`/`_tile_last_used` -- (source_id, index).
        self._slot_allocator = _TileSlotAllocator(max_array_size)

    def register_source(
        self, source_id: object, image_size: tuple[int, int]
    ) -> UniformTileGrid:
        width, height = image_size
        grid = build_uniform_tile_grid(
            width, height, max_tile_width=self._max_tile_extent
        )
        self._grids[source_id] = grid
        self.reset_source(source_id)
        return grid

    def reset_source(self, source_id: object) -> None:
        """Drops residency/LRU bookkeeping for ``source_id`` (its grid, if
        any, is left untouched -- callers registering a new grid call this
        via ``register_source``). Used when a source's image is replaced, so
        stale residency/byte-size entries from the old image don't leak into
        eviction decisions for the new one."""
        self._resident[source_id] = set()
        for cache_key in [
            cache_key for cache_key in self._tile_byte_sizes if cache_key[0] == source_id
        ]:
            self._tile_byte_sizes.pop(cache_key, None)
            self._tile_last_used.pop(cache_key, None)
            self._tile_content_size.pop(cache_key, None)
            self._slot_allocator.free(cache_key)

    def rekey_source(self, old_source_id: object, new_source_id: object) -> None:
        """Moves every piece of bookkeeping (grid, residency, LRU/byte-size
        state, and array-slot assignment) from ``old_source_id`` to
        ``new_source_id`` with no GPU work and no change to any tile's
        residency/content -- only the key callers look it up by changes.

        Used when a slot's underlying source is replaced by a differently
        shaped one but keeps the *same* identity the caller's draw-plan code
        already uses for it (e.g. multi_compare's ``sid``, reused verbatim
        for both a small preview image and the real full-resolution image
        that replaces it): plain ``register_source(old_source_id, ...)``
        would call ``reset_source`` and instantly drop the old image's
        already-uploaded tiles from residency, with no fallback-LOD-style
        "draw old under new until covered" available to bridge the gap --
        the existing ``last_good_key`` mechanism only fires on a genuine key
        *identity* change, and is blind to a same-key content swap. Calling
        this first lets the caller keep the old content reachable under a
        distinct fallback key (protected from eviction, drawable as a
        fallback) before reusing the original id for the new source."""
        grid = self._grids.pop(old_source_id, None)
        if grid is not None:
            self._grids[new_source_id] = grid
        resident = self._resident.pop(old_source_id, None)
        if resident is not None:
            self._resident[new_source_id] = resident
        for cache_key in [
            cache_key for cache_key in self._tile_byte_sizes if cache_key[0] == old_source_id
        ]:
            _, index = cache_key
            new_cache_key = (new_source_id, index)
            self._tile_byte_sizes[new_cache_key] = self._tile_byte_sizes.pop(cache_key)
            self._tile_last_used[new_cache_key] = self._tile_last_used.pop(cache_key, 0)
            content_size = self._tile_content_size.pop(cache_key, None)
            if content_size is not None:
                self._tile_content_size[new_cache_key] = content_size
            self._slot_allocator.rekey(cache_key, new_cache_key)

    def grid_for(self, source_id: object) -> UniformTileGrid | None:
        return self._grids.get(source_id)

    def tile_key(self, source_id: object, row: int, col: int) -> object:
        grid = self._grids.get(source_id)
        if grid is not None and grid.rows == 1 and grid.columns == 1:
            return source_id
        return (source_id, row, col)

    def visible_tiles(
        self,
        source_id: object,
        image_space_rect: tuple[float, float, float, float] | None = None,
    ) -> set[TileIndex]:
        """Tile indices intersecting ``image_space_rect`` (left, top, right,
        bottom) in source-image pixel space, or every tile in the grid when
        no rect is given (export-style "whole image" consumers, and Phase 0's
        live draw loop, which does not yet do viewport-driven partial
        residency — that lands in Phase 2)."""
        grid = self._grids.get(source_id)
        if grid is None:
            return set()
        if image_space_rect is None:
            return {(row, col) for row, col, _ in grid.iter_regions()}
        left, top, right, bottom = image_space_rect
        # Direct math instead of iterating all tiles: compute which
        # (row, col) indices could intersect the rect without iterating
        # the full grid. For a 20k×20k image with 512px tiles, this goes
        # from O(1600 iterations) to O(1 computation).
        row_min = max(0, int(top / grid.tile_height))
        row_max = min(grid.rows - 1, int((bottom - 1) / grid.tile_height))
        col_min = max(0, int(left / grid.tile_width))
        col_max = min(grid.columns - 1, int((right - 1) / grid.tile_width))
        return {(row, col) for row in range(row_min, row_max + 1) for col in range(col_min, col_max + 1)}

    def resolve_visible_tiles(
        self,
        source_id: object,
        visible_rect: tuple[float, float, float, float] | None,
        margin: int = 0,
    ) -> set[TileIndex]:
        """Visible + margin ring, grid-clipped."""
        grid = self._grids.get(source_id)
        if grid is None:
            return set()
        visible = self.visible_tiles(source_id, visible_rect)
        if margin <= 0:
            return visible
        return _tile_indices_with_margin(grid, visible, margin)

    def select_upload_batch(
        self,
        source_id: object,
        missing: set[TileIndex],
        visible_rect: tuple[float, float, float, float] | None,
        budget: int,
    ) -> list[TileIndex]:
        """Orders ``missing`` by distance from ``visible_rect``'s center
        (nearest first -- the tile under the user's focus point fills in
        before edge tiles, mirroring GIMP's inside-out perceived fill) and
        truncates to ``budget``. Pure selection: does not mark anything
        resident or touch a GPU texture -- the caller uploads the returned
        tiles and calls ``mark_resident`` itself, same as before this
        method existed. Tiles left out of the returned batch stay in the
        caller's own ``target``/``missing`` computation and are naturally
        reconsidered on the next call -- no separate pending queue needed."""
        if budget <= 0 or not missing:
            return []
        if len(missing) <= budget:
            return list(missing)
        grid = self._grids.get(source_id)
        if grid is None or visible_rect is None:
            return sorted(missing)[:budget]
        left, top, right, bottom = visible_rect
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0

        def _distance(index: TileIndex) -> float:
            row, col = index
            if row < 0 or row >= grid.rows or col < 0 or col >= grid.columns:
                return float("inf")
            region = grid.region_for(row, col)
            tile_x = (region.left + region.right) / 2.0
            tile_y = (region.top + region.bottom) / 2.0
            return (tile_x - center_x) ** 2 + (tile_y - center_y) ** 2

        # `missing` is a set, so its iteration order is hash-based, not
        # spatial; ties in `_distance` (common -- e.g. every tile one ring
        # out from center is equidistant) would otherwise resolve in that
        # hash order, which looks like a random fill instead of a stable
        # sweep. `index` (row, col) as a tie-break makes equal-distance
        # tiles fill in a fixed, reading-order sequence run to run.
        return sorted(missing, key=lambda index: (_distance(index), index))[:budget]

    def is_resident(self, source_id: object, index: TileIndex) -> bool:
        return index in self._resident.get(source_id, ())

    def resident_tiles(self, source_id: object) -> set[TileIndex]:
        """Copy of the currently-resident indices for ``source_id`` (empty
        if unregistered/never uploaded). Used by callers that need to
        protect a source's existing tiles from eviction without driving any
        new residency decision for it this call (e.g. a fallback LOD level
        kept alive while its replacement's tiles are still loading -- see
        ``RhiResources.realize_tile_plan``'s ``extra_protect_keys``)."""
        return set(self._resident.get(source_id, ()))

    def mark_resident(
        self,
        source_id: object,
        index: TileIndex,
        byte_size: int,
        content_size: tuple[int, int] | None = None,
    ) -> None:
        """Records ``index`` as resident with its byte cost, bumps its LRU
        timestamp. Caller calls this only after the actual GPU texture
        upload succeeded -- this service tracks the *decision*, never
        performs the upload itself. ``content_size`` (uploaded pixel
        width/height, before any array-layer padding) is only needed by
        texture-array callers -- see ``content_size_for``."""
        self._resident.setdefault(source_id, set()).add(index)
        cache_key = (source_id, index)
        self._tile_byte_sizes[cache_key] = byte_size
        self._tile_use_counter += 1
        self._tile_last_used[cache_key] = self._tile_use_counter
        self._slot_allocator.allocate(cache_key)
        if content_size is not None:
            self._tile_content_size[cache_key] = content_size

    def slot_for(self, source_id: object, index: TileIndex) -> TileSlot | None:
        """`(array_index, layer)` for a resident tile, or `None` if
        ``index`` was never uploaded (never had `mark_resident` called)."""
        return self._slot_allocator.slot_for((source_id, index))

    def content_size_for(
        self, source_id: object, index: TileIndex
    ) -> tuple[int, int] | None:
        """Uploaded content pixel size for an array-resident tile (see
        ``mark_resident``'s ``content_size``), or ``None`` if unknown/not an
        array tile."""
        return self._tile_content_size.get((source_id, index))

    def touch(self, source_id: object, index: TileIndex) -> None:
        """Bumps LRU timestamp for an index that was already resident and
        stayed in this frame's visible+margin ring."""
        cache_key = (source_id, index)
        if cache_key not in self._tile_byte_sizes:
            return
        self._tile_use_counter += 1
        self._tile_last_used[cache_key] = self._tile_use_counter

    def evict_over_budget(
        self, protected: dict[object, set[TileIndex]], budget_bytes: int
    ) -> list[tuple[object, TileIndex]]:
        """Returns the (source_id, index) pairs to evict, least-recently-used
        first, never selecting anything in ``protected``. Also removes them
        from internal residency/LRU bookkeeping. Does NOT touch any GPU
        texture -- caller destroys the corresponding GPU textures."""
        total_bytes = sum(self._tile_byte_sizes.values())
        if total_bytes <= budget_bytes:
            return []
        if tile_dump_enabled():
            log_tile_event(
                "evict_over_budget.triggered",
                total_bytes=total_bytes,
                budget_bytes=budget_bytes,
                protected_keys=[str(k) for k in protected],
                resident_count=len(self._tile_byte_sizes),
            )
        evictable = sorted(
            (
                cache_key
                for cache_key in self._tile_byte_sizes
                if cache_key[1] not in protected.get(cache_key[0], ())
            ),
            key=lambda cache_key: self._tile_last_used.get(cache_key, 0),
        )
        evicted: list[tuple[object, TileIndex]] = []
        for cache_key in evictable:
            if total_bytes <= budget_bytes:
                break
            source_id, index = cache_key
            resident = self._resident.get(source_id)
            if resident is not None:
                resident.discard(index)
            total_bytes -= self._tile_byte_sizes.pop(cache_key, 0)
            self._tile_last_used.pop(cache_key, None)
            self._tile_content_size.pop(cache_key, None)
            self._slot_allocator.free(cache_key)
            if tile_dump_enabled():
                log_tile_event(
                    "evict_over_budget.evicted",
                    source_key=str(source_id),
                    index=list(index),
                )
            evicted.append(cache_key)
        return evicted

    def invalidate_source(self, source_id: object) -> None:
        self._grids.pop(source_id, None)
        self._resident.pop(source_id, None)
        for cache_key in [
            cache_key for cache_key in self._tile_byte_sizes if cache_key[0] == source_id
        ]:
            self._tile_byte_sizes.pop(cache_key, None)
            self._tile_last_used.pop(cache_key, None)
            self._tile_content_size.pop(cache_key, None)
            self._slot_allocator.free(cache_key)

    def invalidate_tiles(self, source_id: object, tile_indices: set[TileIndex]) -> None:
        resident = self._resident.get(source_id)
        if resident is not None:
            resident.difference_update(tile_indices)
        for index in tile_indices:
            cache_key = (source_id, index)
            self._tile_byte_sizes.pop(cache_key, None)
            self._tile_last_used.pop(cache_key, None)
            self._tile_content_size.pop(cache_key, None)
            self._slot_allocator.free(cache_key)
