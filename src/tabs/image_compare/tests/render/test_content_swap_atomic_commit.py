"""Content-replacement atomicity regression (user report: visible per-tile
redraw / patchwork mix of old and new content during a preview->store flip
or a same-slot image swap).

The mechanism: ``RhiCanvasRenderer._resolve_fallback_plan`` must treat a
genuine content replacement as atomic -- every non-resident region of the
new content keeps drawing the OLD content until the new content's
current-view tiles are all resident, then the whole draw plan flips over in
one frame -- via ``resolve_fallback_lod``'s ``atomic`` mode. Two signals
identify a content swap vs. a plain LOD/pyramid-level churn:

1. A rekeyed old-content marker in the fallback baseline. The lazy
   TiledPixelStore path produces ``("_content_stash", ...)`` keys
   (``residency._rekey_or_restore``), the eager whole-image path produces
   ``("_prev_content", ...)`` keys (``residency.rekey_stale_content``).
   Only the ``_prev_content`` form used to be detected, so same-slot lazy
   swaps ran in progressive (mixed-frame) mode.

2. A source identity change (``source_changed``): the preview->store flip
   re-registers the store under a fresh ``LevelKey`` and rekeys nothing,
   so its fallback baseline (the plain old bare slot keys) carries no
   marker at all. ``self._content_swap_active`` persists that one-frame
   fact for the whole transition.

Each scenario drives ``_resolve_fallback_plan`` frame by frame with a real
``TileTextureService`` (no QRhi needed -- the method owns all fallback
decision state except ``self._last_good_*``, which the test mirrors the
way render() does), asserting on the produced draw plan's bound layers:
old-content layers only (no new-tile mix, full coverage) until every
current-view tile of the new content is resident, then a single-frame
commit.
"""

from types import SimpleNamespace

from shared.rendering.lod import LevelKey
from shared.rendering.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.rhi_renderer.draw_plan import (
    _covered_fraction,
    _to_common_space,
    build_array_draw_plan,
)
from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer


def _base_image():
    return SimpleNamespace(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
    )


def _register_full(tile_service, key, size):
    """Registers ``key``'s grid and marks every tile resident -- a fully
    drawable content baseline (e.g. the preview tier before the flip)."""
    grid = tile_service.register_source(key, size)
    for row in range(grid.rows):
        for col in range(grid.columns):
            tile_service.mark_resident(
                key, (row, col), byte_size=1024, content_size=(512, 512)
            )


def _mark_budgeted(tile_service, key, indices):
    """Simulates one frame's budgeted upload of ``indices`` (realize_tile_plan
    uploads at most TILE_UPLOAD_BUDGET_PER_CALL tiles per frame)."""
    for index in indices:
        tile_service.mark_resident(
            key, index, byte_size=1024, content_size=(512, 512)
        )


def _visible_new_tiles(tile_service, key):
    return tile_service.visible_tiles(key)


def _layers(tile_service, key):
    """All array layers bound by ``key``'s resident tiles (side-agnostic --
    used to tell old-content items from new-content items in a plan)."""
    return {
        tile_service.slot_for(key, index)[1]
        for index in tile_service.resident_tiles(key)
    }


def _plan_binds_only(tile_service, plan, old_keys, new_keys):
    """True iff every item in ``plan`` binds old-content layers on both
    sides -- i.e. no new-content tile appears in the draw plan at all."""
    old_layers = set()
    for key in old_keys:
        old_layers |= _layers(tile_service, key)
    new_layers = set()
    for key in new_keys:
        new_layers |= _layers(tile_service, key)
    for item in plan:
        if item.layer1 in new_layers or item.layer2 in new_layers:
            return False
        if item.layer1 not in old_layers or item.layer2 not in old_layers:
            return False
    return True


def _covered_visible_fraction(plan, base_image):
    """GAP_DETECTED-style coverage of the visible rect by the plan's items
    (docs/dev/rendering/tile-rendering-system.md Fallback-LOD: coverage must
    be computed from items actually bound, which is all ``plan`` holds)."""
    unit = (0.0, 0.0, 1.0, 1.0)
    letterbox1 = tuple(base_image.letterbox1)
    letterbox2 = tuple(base_image.letterbox2)
    covered1 = _covered_fraction(
        unit,
        [_to_common_space(item.rect1, letterbox1) for item in plan],
    )
    covered2 = _covered_fraction(
        unit,
        [_to_common_space(item.rect2, letterbox2) for item in plan],
    )
    return min(covered1, covered2)


def test_preview_to_store_flip_is_atomic_and_commits_in_one_frame():
    """The preview->store flip: the preview tier (bare slot keys, 1x1
    grids) is fully resident; the flip commits the store under fresh
    LevelKeys with a 6-tile grid each, uploading 2 tiles/frame. Every frame
    of the transition must draw ONLY the old preview content (no new-tile
    mix, no blank regions), and the flip to the store must happen in a
    single frame once its current-view tiles are all resident."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()

    # Old content: the preview tier under the bare slot keys.
    _register_full(tile_service, "stored_0", (512, 512))
    _register_full(tile_service, "stored_1", (512, 512))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None

    # New content: the store under LevelKeys -- 1500x1024 -> 3x2 = 6 tiles.
    new_keys = (LevelKey("stored_0", 1), LevelKey("stored_1", 1))
    for key in new_keys:
        tile_service.register_source(key, (1500, 1024))
    new_grid = tile_service.grid_for(new_keys[0])
    all_new_tiles = {
        (row, col) for row in range(new_grid.rows) for col in range(new_grid.columns)
    }

    # The flip frame itself already uploaded the first budgeted batch
    # (realize_tile_plan runs before the fallback decision in render()).
    _mark_budgeted(tile_service, new_keys[0], [(0, 0), (0, 1)])
    _mark_budgeted(tile_service, new_keys[1], [(0, 0), (0, 1)])

    transition_frames = 0
    promoted = False
    for _ in range(10):
        more_pending = any(
            sum(
                1
                for index in _visible_new_tiles(tile_service, key)
                if tile_service.is_resident(key, index)
            )
            < len(all_new_tiles)
            for key in new_keys
        )
        current_plan = build_array_draw_plan(
            tile_service,
            new_keys,
            base_image,
            diff_key=None,
            sampler_name="linear",
        )
        new_last_good, plan = renderer._resolve_fallback_plan(
            tile_service=tile_service,
            texture_keys=new_keys,
            diff_source_key=None,
            base_image=base_image,
            sampler_name="linear",
            viewport_zoom=None,
            viewport_offset=None,
            main_more_pending=more_pending,
            current_array_plan=current_plan,
            source_changed=(transition_frames == 0),
            rekeyed={},
        )
        renderer._last_good_texture_keys, renderer._last_good_diff_key = (
            new_last_good if new_last_good is not None else (None, None)
        )

        if more_pending:
            # Mid-transition: the whole screen must be the OLD preview --
            # no new-store tile may appear, and there must be no blank
            # region (fallback covers every non-resident new tile).
            assert not promoted
            assert plan, "atomic transition must never draw a blank frame"
            assert _plan_binds_only(
                tile_service, plan, ("stored_0", "stored_1"), new_keys
            ), (
                f"frame {transition_frames}: new-store tile leaked into the "
                f"draw plan while the store was still uploading -- patchwork "
                f"mix, not an atomic swap"
            )
            assert _covered_visible_fraction(plan, base_image) >= 0.999, (
                f"frame {transition_frames}: uncovered region during the "
                f"flip transition"
            )
        else:
            # Single-frame commit: the moment every current-view tile is
            # resident, the plan is the new content only, and the fallback
            # baseline promotes to the new keys.
            assert not _plan_binds_only(
                tile_service, plan, ("stored_0", "stored_1"), new_keys
            ), "promoted frame must not keep drawing the old preview"
            assert new_last_good == (new_keys, None)
            assert not renderer._content_swap_active
            promoted = True
            break
        transition_frames += 1
        _mark_budgeted(tile_service, new_keys[0], [(0, 2), (1, 0)])
        _mark_budgeted(tile_service, new_keys[1], [(0, 2), (1, 0)])
        if transition_frames == 1:
            _mark_budgeted(tile_service, new_keys[0], [(1, 1), (1, 2)])
            _mark_budgeted(tile_service, new_keys[1], [(1, 1), (1, 2)])

    assert promoted, "flip never committed"
    assert transition_frames == 1, (
        f"expected 1 upload-budget frame + 1 commit frame, got "
        f"{transition_frames}"
    )


def test_same_slot_lazy_swap_stash_marker_is_atomic():
    """A same-slot store swap (both contents lazy TiledPixelStores): the
    residency realizer rekeys the old content to a ``("_content_stash", ...)``
    marker key. The marker must be recognized as a content swap (the
    ``_prev_content``-only check used to miss it), so mid-transition frames
    draw the old content only -- never a mix of new and old tiles."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()

    # Old content fully resident under the slot keys.
    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (512, 512))
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = None

    # The swap rekeys stored_0's old content to a stash marker and
    # re-registers the same slot key for the new content (partially
    # uploaded this frame, as realize_tile_plan would leave it).
    stash_key = ("_content_stash", "stored_0", 7)
    tile_service.rekey_source("stored_0", stash_key)
    tile_service.register_source("stored_0", (2000, 1000))
    _mark_budgeted(tile_service, "stored_0", [(0, 0), (0, 1)])
    rekeyed = {"stored_0": stash_key}

    current_plan = build_array_draw_plan(
        tile_service,
        ("stored_0", "stored_1"),
        base_image,
        diff_key=None,
        sampler_name="linear",
    )
    assert current_plan, "new content has uploaded at least one tile"

    new_last_good, plan = renderer._resolve_fallback_plan(
        tile_service=tile_service,
        texture_keys=("stored_0", "stored_1"),
        diff_source_key=None,
        base_image=base_image,
        sampler_name="linear",
        viewport_zoom=None,
        viewport_offset=None,
        main_more_pending=True,
        current_array_plan=current_plan,
        source_changed=True,
        rekeyed=rekeyed,
    )

    assert _plan_binds_only(
        tile_service, plan, (stash_key, "stored_1"), ("stored_0",)
    ), (
        "mid-swap frame mixed new content tiles with the old-content "
        "fallback -- the _content_stash marker was not treated as atomic"
    )
    assert _covered_visible_fraction(plan, base_image) >= 0.999
    assert new_last_good == ((stash_key, "stored_1"), None)
    assert renderer._content_swap_active


def test_same_slot_swap_commits_in_one_frame_once_resident():
    """Continuation of the same-slot swap: once every current-view tile of
    the new content is resident, the whole draw plan flips over in one
    frame (promotion), even while the stash marker is still the baseline."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()

    _register_full(tile_service, "stored_0", (1200, 800))
    _register_full(tile_service, "stored_1", (512, 512))
    stash_key = ("_content_stash", "stored_0", 7)
    tile_service.rekey_source("stored_0", stash_key)
    new_grid = tile_service.register_source("stored_0", (2000, 1000))
    for row in range(new_grid.rows):
        for col in range(new_grid.columns):
            tile_service.mark_resident(
                "stored_0", (row, col), byte_size=1024, content_size=(512, 512)
            )
    renderer._last_good_texture_keys = (stash_key, "stored_1")
    renderer._last_good_diff_key = None
    renderer._content_swap_active = True

    current_plan = build_array_draw_plan(
        tile_service,
        ("stored_0", "stored_1"),
        base_image,
        diff_key=None,
        sampler_name="linear",
    )
    new_last_good, plan = renderer._resolve_fallback_plan(
        tile_service=tile_service,
        texture_keys=("stored_0", "stored_1"),
        diff_source_key=None,
        base_image=base_image,
        sampler_name="linear",
        viewport_zoom=None,
        viewport_offset=None,
        main_more_pending=False,
        current_array_plan=current_plan,
        source_changed=False,
        rekeyed={},
    )

    assert new_last_good == (("stored_0", "stored_1"), None)
    assert not renderer._content_swap_active
    assert not _plan_binds_only(tile_service, plan, (stash_key, "stored_1"), ("stored_0",))
    assert _covered_visible_fraction(plan, base_image) >= 0.999


def test_lod_level_churn_stays_progressive():
    """Regression guard: a plain LOD/pyramid-level transition (same source,
    coarser -> finer LevelKey) must NOT become atomic -- the finer level's
    tiles keep revealing progressively over the coarser level's resident
    tiles, and ``_content_swap_active`` stays False throughout."""
    renderer = RhiCanvasRenderer()
    tile_service = TileTextureService(max_tile_extent=512)
    base_image = _base_image()

    coarse = (LevelKey("stored_0", 2), LevelKey("stored_1", 2))
    fine = (LevelKey("stored_0", 1), LevelKey("stored_1", 1))
    for key in coarse:
        _register_full(tile_service, key, (600, 600))
    for key in fine:
        tile_service.register_source(key, (1200, 800))
    renderer._last_good_texture_keys = coarse
    renderer._last_good_diff_key = None

    # Fine level partially uploaded this frame.
    _mark_budgeted(tile_service, fine[0], [(0, 0), (0, 1)])
    _mark_budgeted(tile_service, fine[1], [(0, 0), (0, 1)])

    current_plan = build_array_draw_plan(
        tile_service,
        fine,
        base_image,
        diff_key=None,
        sampler_name="linear",
    )
    assert current_plan, "the fine level has resident tiles this frame"

    new_last_good, plan = renderer._resolve_fallback_plan(
        tile_service=tile_service,
        texture_keys=fine,
        diff_source_key=None,
        base_image=base_image,
        sampler_name="linear",
        viewport_zoom=None,
        viewport_offset=None,
        main_more_pending=True,
        current_array_plan=current_plan,
        source_changed=False,
        rekeyed={},
    )

    # Progressive reveal preserved: the partially-uploaded fine level IS in
    # the plan alongside the coarse fallback, and nothing was flagged as a
    # content swap.
    assert _plan_binds_only(tile_service, plan, coarse, fine) is False
    assert any(
        item.layer1 in _layers(tile_service, fine[0])
        or item.layer2 in _layers(tile_service, fine[1])
        for item in plan
    )
    assert not renderer._content_swap_active
    assert new_last_good == (coarse, None)