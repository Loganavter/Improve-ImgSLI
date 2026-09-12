"""Contract: tile sizing constants stay consistent across host and GPU layers.

Closes docs/dev/TODO.md P2 "Host vs GPU tile sizes": one GPU live tile must
cover a whole number of host pixel tiles, and every module that re-exports a
tile constant must alias shared.rendering.tile_constants, not fork the value.
"""

from core.constants import AppConstants
from shared.rendering import tile_constants


def test_gpu_tile_divisible_by_host_tile():
    assert tile_constants.LIVE_TILE_EXTENT % tile_constants.PIXEL_TILE_SIZE == 0
    assert tile_constants.DEFAULT_TILE_EXTENT % tile_constants.PIXEL_TILE_SIZE == 0


def test_apron_sane():
    assert 0 < tile_constants.TILE_APRON_PX < tile_constants.PIXEL_TILE_SIZE
    assert tile_constants.TILE_RESIDENCY_MARGIN >= 0


def test_app_constants_mirror():
    # core cannot import shared.rendering (layering), so the value is
    # duplicated in AppConstants and pinned here.
    assert AppConstants.PIXEL_TILE_SIZE == tile_constants.PIXEL_TILE_SIZE


def test_reexports_alias_tile_constants():
    from shared.rendering import tile_geometry, tile_texture_service
    from tabs.image_compare.canvas.rhi_renderer import resources
    from tabs.multi_compare.scene import resources as mc_resources

    assert tile_geometry._TILE_APRON_PX == tile_constants.TILE_APRON_PX
    assert tile_geometry._TILE_RESIDENCY_MARGIN == tile_constants.TILE_RESIDENCY_MARGIN
    assert tile_texture_service.DEFAULT_TILE_EXTENT == tile_constants.DEFAULT_TILE_EXTENT
    assert resources._LIVE_TILE_EXTENT == tile_constants.LIVE_TILE_EXTENT
    assert mc_resources.SLOT_LIVE_TILE_EXTENT == tile_constants.LIVE_TILE_EXTENT