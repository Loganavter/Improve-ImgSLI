"""BaseImagesPass hooks into the shared TileTextureService for oversized
slots (docs/dev/TILED_RENDERING_DESIGN.md pattern, reused from
image_compare)."""

from types import SimpleNamespace

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.host_texture_cache import HostTextureUploadCache
from shared.rendering.tile_texture_service import TileTextureService
from tabs.multi_compare.scene.passes.base_images import BaseImagesPass
from tabs.multi_compare.scene.tile_geometry import build_slot_draw_plan


def test_build_slot_draw_plan_single_tile_is_identity_rect():
    service = TileTextureService(max_tile_extent=2048)
    service.register_source(1, (512, 512))

    items = build_slot_draw_plan(service, 1, pan_offset=(0.0, 0.0), fit_scale=(1.0, 1.0), zoom=1.0)

    assert len(items) == 1
    assert items[0].tile_key == 1
    assert items[0].tile_rect == (0.0, 0.0, 1.0, 1.0)


def test_build_slot_draw_plan_splits_oversized_slot_into_visible_tiles():
    service = TileTextureService(max_tile_extent=2048)
    grid = service.register_source(1, (4096, 2048))
    assert (grid.rows, grid.columns) == (1, 2)

    # Zoomed and panned so the visible uv range (0.15..0.35) sits entirely
    # inside the left tile (tile boundary at uv 0.5).
    items = build_slot_draw_plan(
        service, 1, pan_offset=(0.25, 0.0), fit_scale=(1.0, 1.0), zoom=5.0
    )

    tile_keys = {item.tile_key for item in items}
    assert tile_keys == {(1, 0, 0)}


class _FakeStageFlag:
    VertexStage = 1
    FragmentStage = 2


class _FakeBinding:
    StageFlag = _FakeStageFlag

    @staticmethod
    def uniformBuffer(*args):
        return ("uniform", args)

    @staticmethod
    def sampledTexture(*args):
        return ("texture", args)


class _FakeTexture:
    def __init__(self, size):
        self.size = size
        self.destroyed = False

    def create(self):
        return True

    def destroy(self):
        self.destroyed = True


class _FakeSrb:
    def __init__(self):
        self.destroyed = False

    def setBindings(self, bindings):
        self.bindings = bindings

    def create(self):
        return True

    def destroy(self):
        self.destroyed = True


class _FakeBuffer:
    def create(self):
        return True


class _FakeRhi:
    def newTexture(self, _fmt, size):
        return _FakeTexture(size)

    def newShaderResourceBindings(self):
        return _FakeSrb()

    def newBuffer(self, *_args, **_kwargs):
        return _FakeBuffer()


class _FakeUpdates:
    def __init__(self):
        self.uploads = []

    def uploadTexture(self, texture, image):
        self.uploads.append((texture, image))


def test_oversized_slot_lazily_uploads_only_visible_tiles(monkeypatch):
    from tabs.multi_compare.scene.passes import base_images as base_images_module

    monkeypatch.setattr(base_images_module, "QRhiShaderResourceBinding", _FakeBinding)

    render_pass = BaseImagesPass()
    host = SimpleNamespace()
    renderer = SimpleNamespace(
        rhi=_FakeRhi(),
        sampler=object(),
        tile_service=TileTextureService(max_tile_extent=64),
        host=host,
    )

    store = TiledPixelStore.from_pil(Image.new("RGBA", (128, 64), (0, 0, 0, 255)))
    try:
        render_pass.queue_upload(1, store)
        updates = _FakeUpdates()
        render_pass.apply_pending_texture_ops(renderer, updates)

        grid = renderer.tile_service.grid_for(1)
        assert (grid.rows, grid.columns) == (1, 2)
        assert render_pass.slot_textures == {}
        assert render_pass.slot_pixel_sources[1] is store

        layer = SimpleNamespace(
            slot_id=1,
            rect_fb=(0.0, 0.0, 100.0, 100.0),
            fit_x=1.0,
            fit_y=1.0,
            zoom=5.0,
            pan_x=0.25,
            pan_y=0.0,
        )
        ctx = SimpleNamespace(projected_layers=[layer])
        render_pass._realize_tile_residency(renderer, ctx, updates)

        assert set(render_pass.slot_textures) == {(1, 0, 0), (1, 0, 1)}
        cache = getattr(host, "_host_texture_upload_cache", None)
        assert isinstance(cache, HostTextureUploadCache)
        assert cache.entries
    finally:
        store.close()


def test_host_cache_evicts_when_over_budget():
    host = SimpleNamespace()
    renderer = SimpleNamespace(host=host)
    render_pass = BaseImagesPass()
    cache = render_pass._host_cache(renderer)
    from PySide6.QtGui import QImage

    big = QImage(512, 512, QImage.Format.Format_RGBA8888)
    per = big.sizeInBytes()
    cache.store("slot_a", big)
    cache.store("slot_b", big)
    cache.evict_over_budget({"slot_a"}, budget_bytes=per)
    assert "slot_a" in cache.entries
    assert "slot_b" not in cache.entries
