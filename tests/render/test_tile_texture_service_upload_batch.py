"""select_upload_batch: nearest-first, budget-truncated tile selection.

Pure-Python unit tests for the budgeted progressive tile upload design
(docs/dev/rendering/tile-rendering-system.md "Planned: budgeted progressive
tile upload") -- no Qt/GPU needed, TileTextureService never touches a GPU
texture itself.
"""

from shared.rendering.tile_texture_service import TileTextureService


def _service(width=3 * 1024, height=1024, max_tile_extent=1024):
    service = TileTextureService(max_tile_extent=max_tile_extent)
    service.register_source("src", (width, height))
    return service


def test_returns_all_missing_when_under_budget():
    service = _service()
    missing = {(0, 0), (0, 1)}
    batch = service.select_upload_batch("src", missing, None, budget=5)
    assert set(batch) == missing


def test_empty_missing_or_zero_budget_returns_nothing():
    service = _service()
    assert service.select_upload_batch("src", set(), (0, 0, 100, 100), 5) == []
    assert service.select_upload_batch("src", {(0, 0)}, (0, 0, 100, 100), 0) == []


def test_nearest_to_visible_rect_center_wins_under_budget():
    # 3 tiles in a row, each 1024px wide: (0,0)=[0,1024) (0,1)=[1024,2048)
    # (0,2)=[2048,3072). Center the visible rect on tile (0,1); with a
    # budget of 1, only the nearest tile should be selected.
    service = _service()
    missing = {(0, 0), (0, 1), (0, 2)}
    visible_rect = (1024.0, 0.0, 2048.0, 1024.0)
    batch = service.select_upload_batch("src", missing, visible_rect, budget=1)
    assert batch == [(0, 1)]


def test_budget_truncates_in_nearest_first_order():
    service = _service()
    missing = {(0, 0), (0, 1), (0, 2)}
    # Visible rect centered near tile (0,2) -- nearest-first order should be
    # (0,2), (0,1), (0,0).
    visible_rect = (2048.0, 0.0, 3072.0, 1024.0)
    batch = service.select_upload_batch("src", missing, visible_rect, budget=2)
    assert batch == [(0, 2), (0, 1)]


def test_unregistered_source_falls_back_to_deterministic_order():
    service = TileTextureService()
    missing = {(1, 0), (0, 0)}
    batch = service.select_upload_batch("unknown", missing, None, budget=1)
    assert batch == [(0, 0)]


def test_does_not_mark_anything_resident():
    service = _service()
    missing = {(0, 0), (0, 1)}
    service.select_upload_batch("src", missing, (1024.0, 0.0, 2048.0, 1024.0), budget=1)
    assert not service.is_resident("src", (0, 0))
    assert not service.is_resident("src", (0, 1))


def test_equal_distance_ties_break_by_index_not_set_hash_order():
    """Tiles equidistant from the visible-rect center (common -- e.g. a full
    ring one step out) must resolve in a fixed (row, col) order, not the
    hash-based iteration order of the `missing` set. A missing tie-break
    made the fill order look random from call to call even though each
    individual call was internally deterministic -- see docs/dev/rendering/
    tile-rendering-system.md. `budget` is kept below `len(missing)` so this
    exercises the distance-sorted path (the `len(missing) <= budget` fast
    path in `select_upload_batch` returns everything unsorted, which is
    fine there since every tile uploads in the same call regardless of
    order)."""
    service = _service(width=5 * 1024, height=3 * 1024, max_tile_extent=1024)
    # Center tile is (1, 2); the 4 orthogonal neighbors are all equidistant,
    # plus one far-away tile that must always lose to all four.
    missing = {(0, 2), (1, 1), (1, 3), (2, 2), (0, 0)}
    visible_rect = (2048.0, 1024.0, 3072.0, 2048.0)
    batch = service.select_upload_batch("src", missing, visible_rect, budget=4)
    assert batch == [(0, 2), (1, 1), (1, 3), (2, 2)]
    # Re-running against a differently-ordered-but-equal set must still
    # produce the same result.
    same_missing_rebuilt = set()
    for index in [(0, 0), (2, 2), (1, 3), (1, 1), (0, 2)]:
        same_missing_rebuilt.add(index)
    assert (
        service.select_upload_batch("src", same_missing_rebuilt, visible_rect, budget=4)
        == batch
    )