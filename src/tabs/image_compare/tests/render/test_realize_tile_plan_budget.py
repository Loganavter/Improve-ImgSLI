"""Budgeted progressive tile upload (docs/dev/rendering/tile-rendering-system.md
"Planned: budgeted progressive tile upload"): realize_tile_plan must not
upload every missing tile in one call once a source spans multiple tiles --
only up to TILE_UPLOAD_BUDGET_PER_CALL, with the rest picked up on a
follow-up call against the same (self-correcting) target set.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources


def _tps(image: Image.Image, tmp_path) -> TiledPixelStore:
    return TiledPixelStore.from_pil(image, tmp_dir=str(tmp_path))


def _widget(*, stored0, update_calls: list):
    state = SimpleNamespace(
        _pending_texture_uploads=[],
        _images_uploaded=[False, False],
        _texture_upload_cache=OrderedDict(),
        _qimage_by_uid_cache=OrderedDict(),
        _stored_pil_images=[None, None],
        _stored_image_ids=None,
        _source_pil_images=[None, None],
        _source_image_ids=None,
        _source_images_ready=False,
        _shader_letterbox_mode=False,
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _inner_content_rect_px=None,
        _clip_overlays_to_content_rect=False,
        _host_texture_upload_cache=None,
    )
    widget = SimpleNamespace(
        runtime_state=state,
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        width=lambda: 800,
        height=lambda: 600,
        update=lambda: update_calls.append(1),
    )
    from tabs.image_compare.canvas.texture_parts.base_images import upload_pil_images

    upload_pil_images(widget, stored0, stored0, shader_letterbox=True)
    return widget


def _resources():
    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    resources.upload_whole = MagicMock()
    return resources


def test_first_call_uploads_at_most_the_budget(tmp_path, monkeypatch):
    # Exercises the budget-truncation logic itself, independent of whatever
    # TILE_UPLOAD_BUDGET_PER_CALL production tuning happens to be (64 at
    # LIVE_TILE_EXTENT=512's ~1MB/tile -- see tile_constants.py) -- a small
    # local budget keeps this test's fixture image small.
    from shared.rendering import residency as residency_module

    local_budget = 2
    monkeypatch.setattr(
        residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", local_budget
    )
    # 1200x800 at max_tile_extent=512 -> 3 cols x 2 rows = 6 tiles, well
    # above local_budget.
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )
    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )

    grid = tile_service.grid_for("stored_0")
    assert grid.rows * grid.columns > local_budget
    resident = {
        index
        for index in tile_service.visible_tiles("stored_0")
        if tile_service.is_resident("stored_0", index)
    }
    assert len(resident) == local_budget
    # Tiles remain outstanding -> caller must self-schedule another paint.
    assert update_calls, "expected widget.update() to fire another frame"


def test_remaining_tiles_upload_on_a_follow_up_call(tmp_path, monkeypatch):
    from shared.rendering import residency as residency_module

    local_budget = 2
    monkeypatch.setattr(
        residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", local_budget
    )
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )
    total_tiles = None
    resident_counts = []
    for _ in range(10):
        resources.residency.realize_tile_plan(
            tile_service, widget, ("stored_0", "stored_1"), base_image, updates
        )
        grid = tile_service.grid_for("stored_0")
        total_tiles = grid.rows * grid.columns
        resident = {
            index
            for index in tile_service.visible_tiles("stored_0")
            if tile_service.is_resident("stored_0", index)
        }
        resident_counts.append(len(resident))
        if len(resident) == total_tiles:
            break

    assert resident_counts[0] == local_budget
    assert resident_counts[-1] == total_tiles
    # Strictly progressive: each call adds tiles until everything is resident.
    assert resident_counts == sorted(resident_counts)


def test_time_budget_stops_upload_before_count_budget(tmp_path, monkeypatch):
    """docs/dev/rendering/tile-rendering-system.md "Planned: time-boxed
    upload budget": the wall-clock check must be able to stop a call before
    even TILE_UPLOAD_BUDGET_PER_CALL tiles are uploaded, if the clock says
    the per-call time budget is already spent."""
    from shared.rendering import tile_upload_budget as residency_module

    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )

    # First call: establishes the deadline. Second+ calls (checked before
    # every tile upload attempt): already past it -> zero tiles upload even
    # though TILE_UPLOAD_BUDGET_PER_CALL would normally allow some.
    clock = iter([0.0] + [1000.0] * 100)
    monkeypatch.setattr(residency_module.time, "monotonic", lambda: next(clock))

    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )

    resident = {
        index
        for index in tile_service.visible_tiles("stored_0")
        if tile_service.is_resident("stored_0", index)
    }
    assert resident == set()
    assert update_calls, "expected widget.update() to fire another frame"


def test_shared_deadline_does_not_starve_a_later_key_of_its_first_tile(
    tmp_path, monkeypatch
):
    """The per-call time budget is shared across every key (stored_0,
    stored_1, ...), not per-key -- a large source's first tile crop+upload
    can alone consume the whole budget. If that meant a later key got zero
    tiles this call, the two compared images could go multiple calls
    without ever having a co-resident tile at the same index, which is
    exactly what the array-path draw plan (``build_array_draw_plan``)
    requires before it draws anything -- so the canvas would render fully
    blank for as long as one side's uploads kept outpacing the other's.
    Each key must therefore get at least one tile through per call
    regardless of what an earlier key already spent, as long as the budget
    wasn't already blown before this call even started (that case stays
    covered by ``test_time_budget_stops_upload_before_count_budget``)."""
    from shared.rendering import tile_upload_budget as residency_module

    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )

    # Deadline is fresh (not already exhausted) at call start, but every
    # check from then on reports it blown -- as if stored_0's own uploads
    # alone ate the whole per-call time budget.
    clock = iter([0.0, 0.001] + [1000.0] * 100)
    monkeypatch.setattr(residency_module.time, "monotonic", lambda: next(clock))

    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )

    resident_0 = {
        index
        for index in tile_service.visible_tiles("stored_0")
        if tile_service.is_resident("stored_0", index)
    }
    resident_1 = {
        index
        for index in tile_service.visible_tiles("stored_1")
        if tile_service.is_resident("stored_1", index)
    }
    assert resident_0, "stored_0 (first key) should get its guaranteed first tile"
    assert resident_1, "stored_1 must not be starved of its own first tile"


def test_extra_protect_keys_survives_eviction_without_being_in_this_calls_pairs(
    tmp_path, monkeypatch
):
    """docs/dev/rendering/tile-array-atlas-plan.md Phase 2 fallback-LOD
    finding: a previous LOD level's tiles, kept around only via
    ``extra_protect_keys`` (not part of this call's ``texture_keys``/
    ``diff_key`` pairs at all), must survive ``evict_over_budget`` even
    under budget pressure that would otherwise reclaim them -- this is what
    lets ``RhiCanvasRenderer`` redraw the old level as a fallback while the
    new level's tiles are still uploading, instead of a blank frame."""
    from tabs.image_compare.canvas.rhi_renderer import residency as residency_module

    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )

    # A fallback source ("stale_0") with one already-resident tile, entirely
    # outside this call's own (stored_0, stored_1) pairs.
    tile_service.register_source("stale_0", (512, 512))
    tile_service.mark_resident("stale_0", (0, 0), byte_size=1024)

    # Tiny budget: without protection, evict_over_budget would reclaim
    # everything not in this call's own protected_by_key.
    monkeypatch.setattr(residency_module, "_TILE_CACHE_BUDGET_BYTES", 1)

    resources.residency.realize_tile_plan(
        tile_service,
        widget,
        ("stored_0", "stored_1"),
        base_image,
        updates,
        extra_protect_keys=("stale_0",),
    )

    assert tile_service.is_resident("stale_0", (0, 0))


def test_same_slot_image_swap_rekeys_old_content_instead_of_dropping_it(
    tmp_path,
):
    """docs/dev/rendering/qrhi-gotchas.md same-slot-swap finding: texture
    keys like "stored_0" are stable slot labels, not per-image identity --
    loading a new, differently-sized image into an already-loaded side
    reuses the same key. Before this fix, the re-register branch called
    ``tile_service.register_source(key, ...)`` straight away, which resets
    residency bookkeeping for that key and silently drops every
    already-uploaded tile the instant the new image's grid disagrees with
    the old one -- before a single tile of the new image has uploaded, so
    the screen goes fully blank and refills tile-by-tile instead of the new
    content progressively replacing the old. ``realize_tile_plan`` must
    instead move the old content to a fresh key (``rekey_source``) and
    report the mapping via ``last_rekeyed_keys``, so a caller can keep
    drawing it as a fallback while the reused key's new content fills in."""
    from tabs.image_compare.canvas.texture_parts.base_images import (
        upload_pil_images,
    )

    store1 = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store1, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )

    # First pass(es): fully realize the original image's residency.
    for _ in range(10):
        resources.residency.realize_tile_plan(
            tile_service, widget, ("stored_0", "stored_1"), base_image, updates
        )
        grid = tile_service.grid_for("stored_0")
        resident = {
            index
            for index in tile_service.visible_tiles("stored_0")
            if tile_service.is_resident("stored_0", index)
        }
        if len(resident) == grid.rows * grid.columns:
            break
    assert resident, "expected the original image to have resident tiles"

    # Swap "stored_0" to a differently-sized image without changing the key
    # -- the same thing update_comparison_if_needed's real callers do on an
    # image replacement.
    store2 = _tps(Image.new("RGBA", (2000, 1000), "red"), tmp_path)
    upload_pil_images(widget, store2, store1, shader_letterbox=True)

    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )

    rekeyed = resources.residency.last_rekeyed_keys
    assert "stored_0" in rekeyed
    prev_key = rekeyed["stored_0"]

    # The old content is still fully there under its new key -- nothing was
    # dropped, only relabeled.
    assert tile_service.resident_tiles(prev_key) == resident
    old_grid = tile_service.grid_for(prev_key)
    assert (old_grid.total_width, old_grid.total_height) == (1200, 800)

    # "stored_0" itself now points at the new image's own grid, tracked
    # independently of the rekeyed old content.
    new_grid = tile_service.grid_for("stored_0")
    assert (new_grid.total_width, new_grid.total_height) == (2000, 1000)


def test_same_size_image_swap_also_rekeys_old_content(tmp_path):
    """Follow-up to the size-mismatch case above: two compared images can
    happen to share the exact same pixel resolution, in which case
    ``grid.total_width``/``total_height`` never disagree across a swap and
    the size check alone never re-fires. Before this fix that meant
    ``is_resident`` stayed true for every already-uploaded index forever
    (``plan_key_upload`` only uploads indices that *aren't* resident), so
    the old image's tiles were never replaced except by incidental LRU
    eviction -- a persistent, patchwork mix of old and new content instead
    of a clean transition, matching the user's live report even after the
    size-mismatch fix above landed (docs/dev/rendering/qrhi-gotchas.md
    same-slot-swap finding, same-size follow-up). Tracking the live
    source's own ``image_uid()`` alongside the size check catches this
    too."""
    from tabs.image_compare.canvas.texture_parts.base_images import (
        upload_pil_images,
    )

    store1 = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget = _widget(stored0=store1, update_calls=update_calls)
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )

    for _ in range(10):
        resources.residency.realize_tile_plan(
            tile_service, widget, ("stored_0", "stored_1"), base_image, updates
        )
        grid = tile_service.grid_for("stored_0")
        resident = {
            index
            for index in tile_service.visible_tiles("stored_0")
            if tile_service.is_resident("stored_0", index)
        }
        if len(resident) == grid.rows * grid.columns:
            break
    assert resident, "expected the original image to have resident tiles"

    # Same pixel size, different content -- the size check alone would miss
    # this entirely.
    store2 = _tps(Image.new("RGBA", (1200, 800), "red"), tmp_path)
    assert store2.size == store1.size
    upload_pil_images(widget, store2, store1, shader_letterbox=True)

    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )

    rekeyed = resources.residency.last_rekeyed_keys
    assert "stored_0" in rekeyed
    prev_key = rekeyed["stored_0"]
    # The old content survives intact under its own key -- nothing was
    # silently dropped, only relabeled -- and "stored_0" was re-registered
    # (its residency bookkeeping reset) for the new content rather than
    # left pointing at the old image's already-uploaded tiles: the grid
    # object identity changes even though its dimensions don't.
    assert tile_service.resident_tiles(prev_key) == resident
    assert tile_service.grid_for("stored_0") is not tile_service.grid_for(prev_key)


def test_upload_source_rekeys_old_multi_tile_content_before_reregistering():
    """docs/dev/rendering/qrhi-gotchas.md same-slot-swap SSIM follow-up:
    upload_source (the *eager* whole-image/diff-role upload path -- used
    for e.g. the SSIM diff texture, which is queued via
    queue_texture_upload rather than lazily resolved through
    realize_tile_plan) used to call ``tile_service.register_source(key,
    ...)`` unconditionally on every call, wiping a multi-tile grid's
    residency the instant a new image landed, well before a single new
    tile of it uploaded (realize_tile_plan lazily fills multi-tile grids
    in over several frames). It must instead rekey the old content first,
    exactly like realize_tile_plan's lazy TiledPixelStore path -- this is
    what let the *previous* diff stay visible across an image swap instead
    of vanishing while the new one recomputes."""
    from PySide6.QtGui import QImage

    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()

    # First upload: registers a multi-tile grid. Mark every tile resident,
    # as realize_tile_plan would have done over earlier frames.
    image1 = QImage(1024, 1024, QImage.Format.Format_RGBA8888)
    image1.fill(0)
    resources.upload_source(tile_service, "diff", image1, updates)
    grid = tile_service.grid_for("diff")
    assert grid.rows * grid.columns > 1
    resident = set()
    for row in range(grid.rows):
        for col in range(grid.columns):
            tile_service.mark_resident(
                "diff", (row, col), byte_size=1024, content_size=(512, 512)
            )
            resident.add((row, col))

    # Second upload: a new diff image lands under the same "diff" key.
    image2 = QImage(1024, 1024, QImage.Format.Format_RGBA8888)
    image2.fill(255)
    resources.upload_source(tile_service, "diff", image2, updates)

    rekeyed = resources.residency.last_rekeyed_keys
    assert "diff" in rekeyed
    prev_key = rekeyed["diff"]
    # Old content survives intact under its own key.
    assert tile_service.resident_tiles(prev_key) == resident
    # "diff" itself was reset for the new content.
    assert tile_service.resident_tiles("diff") == set()
