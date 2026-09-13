"""Preview-baseline joint hold vs host-cache eviction.

``TileResidencyRealizer.realize_tile_plan`` keeps a swapped-out preview's GPU
tiles alive via ``extra_protect_keys`` (``_preview_stash``) until both halves
have complete tile replacement. The host-side QImage behind that fallback
must survive the same call's ``evict_texture_upload_cache_over_budget`` too
-- including calls made for a *different* role pair: the magnifier's
``source_*`` residency call shares the realizer and the host cache with the
main ``stored_*`` call, so its eviction pass (protected only by its own
pairs) can drop the held baseline while the GPU hold is still active.
Neither progressive re-crop nor post-context-loss ``restore_texture_uploads``
(which re-queues from the host cache) can then bring the fallback back.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image
from PySide6.QtGui import QImage

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources
from tabs.image_compare.canvas.texture_parts.upload_queue import (
    touch_texture_upload_cache,
)


def _tps(image: Image.Image, tmp_path) -> TiledPixelStore:
    return TiledPixelStore.from_pil(image, tmp_dir=str(tmp_path))


def _preview(w: int, h: int) -> QImage:
    image = QImage(w, h, QImage.Format.Format_RGBA8888)
    image.fill(2)
    return image


def _widget(update_calls: list):
    state = SimpleNamespace(
        _pending_texture_uploads=[],
        _images_uploaded=[False, False],
        _texture_upload_cache=OrderedDict(),
        _qimage_by_uid_cache=OrderedDict(),
        _stored_pil_images=[None, None],
        _source_pil_images=[None, None],
        _source_images_ready=False,
        _diff_source_pil_image=None,
        _host_texture_upload_cache=None,
        _shader_letterbox_mode=False,
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _inner_content_rect_px=None,
        _clip_overlays_to_content_rect=False,
    )
    return SimpleNamespace(
        runtime_state=state,
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        width=lambda: 800,
        height=lambda: 600,
        update=lambda: update_calls.append(1),
    )


def _resources():
    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    resources.upload_whole = MagicMock()
    return resources


def _base_image():
    return SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )


def _swap_to_store_hold(tmp_path, monkeypatch):
    """Frame 1 (previews) + frame 2 (stored_0 swapped to a store).

    Returns (widget, resources, tile_service) with an active preview hold
    on ``stored_0`` whose new content is still incomplete (starved upload
    budget), i.e. the joint hold must still be engaged on both sides.
    """
    from shared.rendering import residency as shared_residency_module

    monkeypatch.setattr(shared_residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", 2)
    update_calls: list = []
    widget = _widget(update_calls)
    widget.runtime_state._stored_pil_images = [_preview(1200, 800), _preview(1200, 800)]
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    updates = MagicMock()
    base_image = _base_image()

    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )
    assert touch_texture_upload_cache(widget, "stored_0") is not None

    widget.runtime_state._stored_pil_images[0] = _tps(
        Image.new("RGBA", (1600, 1200), "blue"), tmp_path
    )
    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), base_image, updates
    )
    assert "stored_0" in resources.residency._preview_stash, (
        "preview->store swap must engage the joint preview hold"
    )
    return widget, resources, tile_service


def test_held_preview_baseline_survives_foreign_pair_eviction(tmp_path, monkeypatch):
    """A magnifier-style call for another role pair must not evict the held
    preview baseline's host QImage while its GPU hold is still active."""
    from tabs.image_compare.canvas.rhi_renderer import residency as residency_module

    widget, resources, _tile_service = _swap_to_store_hold(tmp_path, monkeypatch)

    # Foreign-pair call (magnifier source_* roles, no sources of its own --
    # still runs the shared host-cache eviction pass at the end).
    monkeypatch.setattr(residency_module, "_HOST_TEXTURE_CACHE_BUDGET_BYTES", 1)
    resources.residency.realize_tile_plan(
        _tile_service,
        widget,
        ("source_0", "source_1"),
        _base_image(),
        MagicMock(),
        capture_uv_rect=(0.0, 0.0, 1.0, 1.0),
    )

    assert "stored_0" in resources.residency._preview_stash
    assert touch_texture_upload_cache(widget, "stored_0") is not None, (
        "held preview baseline's host QImage must survive a foreign-pair "
        "eviction pass while the joint hold is active"
    )


def test_preview_hold_releases_once_both_halves_complete(tmp_path, monkeypatch):
    """The joint hold is 'until BOTH halves have complete tile replacement':
    once the pair's new content is fully resident the hold must release
    instead of pinning stale stash tiles (and their host images) forever."""
    from shared.rendering import residency as shared_residency_module

    widget, resources, tile_service = _swap_to_store_hold(tmp_path, monkeypatch)

    # Full budget: the swapped store (12 tiles at 512px extent) completes
    # this frame on both halves.
    monkeypatch.setattr(
        shared_residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", 64
    )
    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), _base_image(), MagicMock()
    )

    assert "stored_0" not in resources.residency._preview_stash, (
        "preview hold must release once both halves' new content is resident"
    )
