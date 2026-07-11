from __future__ import annotations

from shared.image_processing.regions import UniformTileGrid, build_uniform_tile_grid

from .tile_geometry import _tile_indices_with_margin

# Phase 0 default (docs/dev/TILED_RENDERING_DESIGN.md). Deliberately not the
# eventual 2048/4096 target tile size yet: the base quad draw loop only
# proves the N=1 abstraction in Phase 0 (16384px guard is still in force
# upstream), and per-tile fragment-shader clipping/seam handling for N>1
# is Phase 1/2 work. Callers that need the real 16384px-safe ceiling should
# pass max_tile_extent=query_max_texture_size(...) explicitly.
DEFAULT_TILE_EXTENT = 16384

TileIndex = tuple[int, int]


class TileTextureService:
    """Owns, per registered source_id, one UniformTileGrid, the set of tile
    indices currently resident as GPU textures, and the LRU/byte-budget
    state used to decide what to evict. A normal image ends up with a 1x1
    grid whose single tile key is the source_id itself (so existing
    per-image upload/cache-restore call sites need no changes for the N=1
    case); a >max_tile_extent image gets an NxM grid instead.

    This service decides *which* tile indices should be resident/evicted;
    it never creates, uploads to, or destroys a QRhiTexture itself --
    that's ``rhi_renderer/resources.py``'s job, driven by what
    ``resolve_visible_tiles``/``evict_over_budget`` return. Keeping GPU
    calls out of this class is what makes it unit-testable with plain
    Python objects (see the ``_grid``-based tests)."""

    def __init__(self, *, max_tile_extent: int = DEFAULT_TILE_EXTENT) -> None:
        self._max_tile_extent = max(1, int(max_tile_extent))
        self._grids: dict[object, UniformTileGrid] = {}
        self._resident: dict[object, set[TileIndex]] = {}
        # LRU state for byte-budget eviction, keyed by (source_id, tile
        # index). Populated only for multi-tile grids -- see
        # resolve_visible_tiles/mark_resident, driven from
        # rhi_renderer/resources.py.
        self._tile_byte_sizes: dict[tuple[object, TileIndex], int] = {}
        self._tile_last_used: dict[tuple[object, TileIndex], int] = {}
        self._tile_use_counter = 0

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
        return {
            (row, col)
            for row, col, region in grid.iter_regions()
            if region.left < right
            and region.right > left
            and region.top < bottom
            and region.bottom > top
        }

    def resolve_visible_tiles(
        self,
        source_id: object,
        visible_rect: tuple[float, float, float, float] | None,
        margin: int = 0,
    ) -> set[TileIndex]:
        """Visible + margin ring, grid-clipped. Replaces the free function
        ``_tile_indices_with_margin`` composed with ``visible_tiles()``."""
        grid = self._grids.get(source_id)
        if grid is None:
            return set()
        visible = self.visible_tiles(source_id, visible_rect)
        if margin <= 0:
            return visible
        return _tile_indices_with_margin(grid, visible, margin)

    def is_resident(self, source_id: object, index: TileIndex) -> bool:
        return index in self._resident.get(source_id, ())

    def mark_resident(self, source_id: object, index: TileIndex, byte_size: int) -> None:
        """Records ``index`` as resident with its byte cost, bumps its LRU
        timestamp. Caller (``rhi_renderer/resources.py``) calls this only
        after the actual QRhiTexture upload succeeded -- this service tracks
        the *decision*, never performs the upload itself."""
        self._resident.setdefault(source_id, set()).add(index)
        cache_key = (source_id, index)
        self._tile_byte_sizes[cache_key] = byte_size
        self._tile_use_counter += 1
        self._tile_last_used[cache_key] = self._tile_use_counter

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
        from internal residency/LRU bookkeeping. Does NOT touch any
        QRhiTexture -- caller destroys the corresponding GPU textures."""
        total_bytes = sum(self._tile_byte_sizes.values())
        if total_bytes <= budget_bytes:
            return []
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

    def invalidate_tiles(self, source_id: object, tile_indices: set[TileIndex]) -> None:
        resident = self._resident.get(source_id)
        if resident is not None:
            resident.difference_update(tile_indices)
