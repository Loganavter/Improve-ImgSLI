"""TileTextureService texture-array slot allocator (Phase 1 of
docs/dev/rendering/tile-array-atlas-plan.md) -- pure Python, no GPU.

Maps (source_id, tile index) to (array_index, layer) slots inside one or
more fixed-capacity texture arrays, with free-list reuse on eviction.
"""

from shared.rendering.tile_texture_service import TileTextureService


def _service(max_array_size=2, width=3 * 1024, height=1024, max_tile_extent=1024):
    service = TileTextureService(
        max_tile_extent=max_tile_extent, max_array_size=max_array_size
    )
    service.register_source("src", (width, height))
    return service


def test_never_uploaded_index_has_no_slot():
    service = _service()
    assert service.slot_for("src", (0, 0)) is None


def test_mark_resident_allocates_a_slot():
    service = _service()
    service.mark_resident("src", (0, 0), byte_size=100)
    slot = service.slot_for("src", (0, 0))
    assert slot == (0, 0)


def test_slots_fill_current_array_before_opening_a_new_one():
    service = _service(max_array_size=2)
    service.mark_resident("src", (0, 0), byte_size=100)
    service.mark_resident("src", (0, 1), byte_size=100)
    service.mark_resident("src", (0, 2), byte_size=100)
    assert service.slot_for("src", (0, 0)) == (0, 0)
    assert service.slot_for("src", (0, 1)) == (0, 1)
    # array 0's free-list is exhausted (max_array_size=2) -- a second array
    # texture opens for the third tile.
    assert service.slot_for("src", (0, 2)) == (1, 0)


def test_evict_over_budget_frees_slot_for_reuse_before_opening_a_new_array():
    service = _service(max_array_size=2)
    service.mark_resident("src", (0, 0), byte_size=100)
    service.mark_resident("src", (0, 1), byte_size=100)
    service.touch("src", (0, 1))  # keep (0,1) more recently used than (0,0)

    evicted = service.evict_over_budget(protected={}, budget_bytes=100)
    assert evicted == [("src", (0, 0))]
    assert service.slot_for("src", (0, 0)) is None

    # A newly-uploaded tile reuses the freed (0,0) slot instead of opening a
    # second array texture.
    service.mark_resident("src", (0, 2), byte_size=100)
    assert service.slot_for("src", (0, 2)) == (0, 0)


def test_repeated_mark_resident_keeps_the_same_slot():
    service = _service()
    service.mark_resident("src", (0, 0), byte_size=100)
    first = service.slot_for("src", (0, 0))
    service.mark_resident("src", (0, 0), byte_size=200)
    assert service.slot_for("src", (0, 0)) == first


def test_invalidate_source_frees_all_its_slots():
    service = _service(max_array_size=2)
    service.mark_resident("src", (0, 0), byte_size=100)
    service.mark_resident("src", (0, 1), byte_size=100)
    service.invalidate_source("src")

    service.register_source("src", (3 * 1024, 1024))
    service.mark_resident("src", (0, 0), byte_size=100)
    # Freed slots are reused before a new array opens.
    assert service.slot_for("src", (0, 0)) in {(0, 0), (0, 1)}


def test_invalidate_tiles_frees_the_slot():
    service = _service(max_array_size=2)
    service.mark_resident("src", (0, 0), byte_size=100)
    service.mark_resident("src", (0, 1), byte_size=100)

    service.invalidate_tiles("src", {(0, 0)})
    assert service.slot_for("src", (0, 0)) is None
    assert service.slot_for("src", (0, 1)) == (0, 1)

    service.mark_resident("src", (0, 2), byte_size=100)
    assert service.slot_for("src", (0, 2)) == (0, 0)
