"""TiledPixelStore must reach GPU without magnifier / display-cache nudge."""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources
from tabs.image_compare.canvas.texture_parts.base_images import upload_pil_images


def _tps(image: Image.Image, tmp_path) -> TiledPixelStore:
    return TiledPixelStore.from_pil(image, tmp_dir=str(tmp_path))


def _widget(*, stored0, stored1=None):
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
        update=lambda: None,
    )
    stored1 = stored1 if stored1 is not None else stored0
    upload_pil_images(
        widget,
        stored0,
        stored1,
        shader_letterbox=True,
    )
    return widget


def test_upload_pil_images_marks_tiled_store_ready_without_host_qimage(tmp_path):
    store = _tps(Image.new("RGBA", (64, 64), "red"), tmp_path)
    widget = _widget(stored0=store)
    assert widget.runtime_state._images_uploaded == [True, True]
    assert widget.runtime_state._pending_texture_uploads == []


def test_realize_tile_plan_uploads_single_tile_tiled_pixel_store(tmp_path):
    store = _tps(Image.new("RGBA", (128, 96), "blue"), tmp_path)
    widget = _widget(stored0=store)
    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    tile_service = __import__(
        "shared.rendering.tile_texture_service", fromlist=["TileTextureService"]
    ).TileTextureService(max_tile_extent=512)
    updates = MagicMock()
    resources.upload_whole = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )
    resources.realize_tile_plan(
        tile_service,
        widget,
        ("stored_0", "stored_1"),
        base_image,
        updates,
    )

    assert resources.upload_whole.call_count >= 1
    tile_key = tile_service.tile_key("stored_0", 0, 0)
    assert tile_service.is_resident("stored_0", (0, 0))
    uploaded_key = resources.upload_whole.call_args_list[0].args[0]
    assert uploaded_key == tile_key


def test_realize_source_tiles_for_magnifier_when_canvas_uses_stored(tmp_path):
    """Magnifier samples source_* at zoom <= 1; those tiles must still upload.

    After the all-TiledPixelStore refactor, source textures skip eager upload.
    Realizing only stored_* (canvas at zoom 1) left magnifier binding the
    transparent placeholder. Regress: realizing source keys must mark them
    resident under the same key MagnifierPass resolves (1×1 → source_id).
    """
    display = Image.new("RGBA", (64, 48), "gray")
    source = _tps(Image.new("RGBA", (256, 192), "green"), tmp_path)
    widget = _widget(stored0=display)
    widget.runtime_state._source_pil_images = [source, source]
    widget.runtime_state._source_images_ready = True

    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    tile_service = __import__(
        "shared.rendering.tile_texture_service", fromlist=["TileTextureService"]
    ).TileTextureService(max_tile_extent=512)
    updates = MagicMock()
    resources.upload_whole = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        use_hires=False,
    )

    # Canvas path: only stored — sources stay cold.
    resources.realize_tile_plan(
        tile_service,
        widget,
        ("stored_0", "stored_1"),
        base_image,
        updates,
    )
    assert not tile_service.is_resident("source_0", (0, 0))

    # Magnifier path: realize source keys even though use_hires is false.
    resources.realize_tile_plan(
        tile_service,
        widget,
        ("source_0", "source_1"),
        base_image,
        updates,
        diff_key=None,
    )
    assert tile_service.is_resident("source_0", (0, 0))
    assert tile_service.is_resident("source_1", (0, 0))
    assert tile_service.tile_key("source_0", 0, 0) == "source_0"
    uploaded_keys = [call.args[0] for call in resources.upload_whole.call_args_list]
    assert "source_0" in uploaded_keys
    assert "source_1" in uploaded_keys


def test_realize_tile_plan_reregisters_stale_grid_when_source_grows(tmp_path):
    """Stale 1×1 grid after a larger TiledPixelStore lands must not stick.

    Otherwise zoom>1 (use_hires) crops only the old top-left window and
    stretches it as the full image.
    """
    small_dir = tmp_path / "small"
    large_dir = tmp_path / "large"
    small_dir.mkdir()
    large_dir.mkdir()
    small = _tps(Image.new("RGBA", (64, 48), "red"), small_dir)
    large = _tps(Image.new("RGBA", (1200, 800), "blue"), large_dir)
    widget = _widget(stored0=Image.new("RGBA", (64, 48), "gray"))
    widget.runtime_state._source_pil_images = [small, small]
    widget.runtime_state._source_images_ready = True

    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    tile_service = __import__(
        "shared.rendering.tile_texture_service", fromlist=["TileTextureService"]
    ).TileTextureService(max_tile_extent=512)
    updates = MagicMock()
    resources.upload_whole = MagicMock()
    resources._evict_stale_tiles = MagicMock()

    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=2.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )

    resources.realize_tile_plan(
        tile_service,
        widget,
        ("source_0", "source_1"),
        base_image,
        updates,
    )
    stale = tile_service.grid_for("source_0")
    assert stale is not None
    assert (stale.total_width, stale.total_height) == (64, 48)
    assert stale.rows == 1 and stale.columns == 1

    widget.runtime_state._source_pil_images = [large, large]
    resources.realize_tile_plan(
        tile_service,
        widget,
        ("source_0", "source_1"),
        base_image,
        updates,
    )
    grid = tile_service.grid_for("source_0")
    assert grid is not None
    assert (grid.total_width, grid.total_height) == (1200, 800)
    assert grid.rows > 1 or grid.columns > 1
    resources._evict_stale_tiles.assert_called()
