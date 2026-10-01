"""Quick Look tiled single-source renderer — plan/instance contracts.

No real GPU: the tile-array resources and mip cascade are faked, and
``record_array_draw`` is captured so the built instances can be inspected.
Uses a synthetic multi-tile ``TiledPixelStore`` (a distinct solid color per
tile region) big enough to force a >1x1 grid.

Asserts the frozen semantics:
- ``set_source`` registers the expected rows/cols for the store size;
- one instance per visible tile, each ``layer`` resolved from ITS OWN index
  (a swapped/neighbor binding must fail);
- a visible tile with no slot yet is skipped (fail closed, never a neighbor);
- geometry comes from store size + ``(fb_w, fb_h)``, not upload/arrival order.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tabs.image_gallery.ui.quick_look import tile_renderer as tr


pytest.importorskip("PIL")


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class _FakeBuffer:
    def __init__(self, name: str = "") -> None:
        self._name = name

    def setName(self, _n) -> None:
        pass

    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        pass


class _FakeClipMatrix:
    def data(self):
        return tuple(float(i) for i in range(16))


class _FakeRhi:
    def clipSpaceCorrMatrix(self):
        return _FakeClipMatrix()

    def newBuffer(self, *_a, **_k):
        return _FakeBuffer()

    def nextResourceUpdateBatch(self):
        return _FakeUpdates()


class _FakeUpdates:
    def __init__(self) -> None:
        self.uploads: list = []
        self.writes: list = []

    def uploadTexture(self, tex, desc) -> None:
        self.uploads.append((tex, desc))

    def updateDynamicBuffer(self, buffer, offset, data) -> None:
        self.writes.append((buffer, offset, data))

    def generateMips(self, tex) -> None:
        pass


class _FakeCmdBuffer:
    def __init__(self) -> None:
        self.resource_updates = 0

    def resourceUpdate(self, batch) -> None:
        self.resource_updates += 1


class _FakeMipCascade:
    def __init__(self) -> None:
        self.released = 0

    def release(self) -> None:
        self.released += 1

    def generate_all_dirty_mips(self, *_a, **_k):
        return {}


class _FakeResources:
    """Faithful-enough CPU-side stand-in: records uploads and updates the
    real tile service's residency/slot bookkeeping exactly as
    ``TileArrayResourcesBase.upload_tile_to_array`` would, so instance layers
    resolve through the service's own slot allocator."""

    def __init__(self) -> None:
        self.array_pipeline = "pipeline"
        self.array_uniform_buffer = _FakeBuffer("ubuf")
        self.array_instance_buffer = _FakeBuffer("ibuf")
        self.array_srb = "srb"
        self.tile_arrays = [_FakeBuffer("array0")]
        self.pipeline_targets: list = []
        self.capacities: list = []
        self.uploaded: list = []

    def ensure_array_pipeline(self, target) -> None:
        self.pipeline_targets.append(target)

    def ensure_array_instance_capacity(self, count) -> None:
        self.capacities.append(count)

    def ensure_array_srb(self, sampler_name):
        return "srb"

    def release(self) -> None:
        pass

    def upload_tile_to_array(
        self, tile_service, source_key, index, image, updates, dirty_layers=None
    ):
        tile_service.mark_resident(
            source_key, index, image.width() * image.height() * 4,
            (image.width(), image.height()),
        )
        self.uploaded.append((source_key, index))
        return index


def _make_renderer(monkeypatch, captured):
    rhi = _FakeRhi()
    renderer = tr.QuickLookTileRenderer(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda _n: "sampler",
        load_shader=lambda _name: object(),
    )
    # Replace GPU owners with fakes; keep the real tile service.
    renderer.resources = _FakeResources()
    renderer._mip_cascade = _FakeMipCascade()
    renderer._vertex_buffer = _FakeBuffer()

    def _capture(command_buffer, **kwargs):
        captured["instances"] = list(kwargs.get("instances") or [])
        captured["uniform_bytes"] = kwargs.get("uniform_bytes")
        captured["pre_begin"] = kwargs.get("pre_begin")

    monkeypatch.setattr(tr, "record_array_draw", _capture)
    return renderer, rhi


def _distinct_store(width: int, height: int, tile_px: int = 512):
    """A TiledPixelStore whose every ``tile_px`` region is a distinct solid
    color, so a wrong (neighbor) layer binding would be visible as wrong
    content."""
    from PIL import Image

    from engine.store.tiled_pixel_store import TiledPixelStore

    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    px = img.load()
    idx = 0
    for top in range(0, height, tile_px):
        for left in range(0, width, tile_px):
            color = ((idx * 40 + 10) % 256, (idx * 70 + 30) % 256, (idx * 110 + 50) % 256, 255)
            for y in range(top, min(top + tile_px, height)):
                for x in range(left, min(left + tile_px, width)):
                    px[x, y] = color
            idx += 1
    return TiledPixelStore.from_pil(img)


def _render(renderer, *, fb_w=512, fb_h=512, zoom=1.0, pan=(0.0, 0.0), target=None):
    updates = _FakeUpdates()
    target = target or SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: fb_w, height=lambda: fb_h)
    )
    drawn = renderer.render(
        _FakeCmdBuffer(),
        updates=updates,
        target=target,
        clear_color=SimpleNamespace(),
        zoom=zoom,
        pan_x=pan[0],
        pan_y=pan[1],
        fb_w=fb_w,
        fb_h=fb_h,
    )
    return drawn, updates


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_set_source_registers_expected_grid():
    store = _distinct_store(1024, 1024)
    rhi = _FakeRhi()
    renderer = tr.QuickLookTileRenderer(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda _n: "sampler",
        load_shader=lambda _n: object(),
    )
    renderer.set_source("item.png", store)
    grid = renderer.grid()
    assert grid is not None
    assert (grid.rows, grid.columns) == (2, 2)
    assert (grid.total_width, grid.total_height) == (1024, 1024)
    renderer.release()


def test_render_binds_layer_from_own_index(monkeypatch):
    store = _distinct_store(1024, 1024)
    captured: dict = {}
    renderer, _ = _make_renderer(monkeypatch, captured)
    renderer.set_source("item.png", store)

    # Upload in a deliberately NON row-major order so a plan that bound
    # layers by upload/arrival order rather than by tile index would fail.
    from engine.cache.tile_geometry import crop_apron_tile

    reverse = [(1, 1), (0, 0), (1, 0), (0, 1)]
    for index in reverse:
        renderer.resources.upload_tile_to_array(
            renderer.tile_service, "item.png", index,
            crop_apron_tile(store, index[1] * 512, index[0] * 512,
                            index[1] * 512 + 512, index[0] * 512 + 512),
            _FakeUpdates(),
        )

    drawn, _uploads = _render(renderer)
    assert drawn is True
    instances = captured["instances"]
    assert len(instances) == 4
    # Every visible tile got its own instance, bound to its own index's layer.
    by_rect = {(round(i.rect1[0], 4), round(i.rect1[1], 4)): i for i in instances}
    assert len(by_rect) == 4
    for tile in tr.build_slot_plan_tiles(
        renderer.tile_service, "item.png", (0.0, 0.0),
        tr.contain_fit_scale((1024, 1024), 512, 512), 1.0,
    ):
        inst = next(i for i in instances if i.rect1 == tile.rect)
        expected_layer = renderer.tile_service.slot_for("item.png", tile.index)[1]
        assert inst.layer1 == expected_layer
    # A swapped/neighbor binding would collapse layers; require all distinct.
    assert len({i.layer1 for i in instances}) == 4
    renderer.release()


def test_render_uploads_in_non_row_major_order_still_all_visible(monkeypatch):
    store = _distinct_store(1024, 1024)
    captured: dict = {}
    renderer, _ = _make_renderer(monkeypatch, captured)
    renderer.set_source("item.png", store)
    # No pre-upload: render must upload the visible set itself and draw it.
    drawn, updates = _render(renderer)
    assert drawn is True
    assert len(captured["instances"]) == 4
    uploaded_indices = {u[1] for u in renderer.resources.uploaded}
    assert uploaded_indices == {(0, 0), (0, 1), (1, 0), (1, 1)}
    renderer.release()


def test_missing_slot_fails_closed_never_neighbor(monkeypatch):
    store = _distinct_store(1024, 1024)
    captured: dict = {}
    renderer, _ = _make_renderer(monkeypatch, captured)
    renderer.set_source("item.png", store)
    # Mark only ONE tile resident (index (0,0)); the others have no slot.
    from engine.cache.tile_geometry import crop_apron_tile

    only = (0, 0)
    renderer.resources.upload_tile_to_array(
        renderer.tile_service, "item.png", only,
        crop_apron_tile(store, 0, 0, 512, 512), _FakeUpdates(),
    )
    # Prevent render from uploading the rest: monkeypatch select_upload_batch.
    monkeypatch.setattr(
        renderer.tile_service, "select_upload_batch",
        lambda *_a, **_k: [],
    )
    drawn, _updates = _render(renderer)
    assert drawn is True
    instances = captured["instances"]
    assert len(instances) == 1
    expected_layer = renderer.tile_service.slot_for("item.png", only)[1]
    assert instances[0].layer1 == expected_layer
    # The single instance's rect is the resident tile's own, not a neighbor's.
    plan = tr.build_slot_plan_tiles(
        renderer.tile_service, "item.png", (0.0, 0.0),
        tr.contain_fit_scale((1024, 1024), 512, 512), 1.0,
    )
    own = next(t for t in plan if t.index == only)
    assert instances[0].rect1 == own.rect
    renderer.release()


def test_geometry_from_store_size_not_arrival_order(monkeypatch):
    """Same inputs -> same instance set regardless of upload order."""
    store_a = _distinct_store(1024, 1024)
    store_b = _distinct_store(1024, 1024)

    captured_a: dict = {}
    renderer_a, _ = _make_renderer(monkeypatch, captured_a)
    renderer_a.set_source("item.png", store_a)
    _render(renderer_a)
    set_a = {
        (round(i.rect1[0], 5), round(i.rect1[1], 5), round(i.bbox[0], 5),
         round(i.bbox[1], 5), round(i.bbox[2], 5), round(i.bbox[3], 5))
        for i in captured_a["instances"]
    }

    captured_b: dict = {}
    renderer_b, _ = _make_renderer(monkeypatch, captured_b)
    renderer_b.set_source("item.png", store_b)
    # Upload all first in reverse order, then render (no new uploads).
    from engine.cache.tile_geometry import crop_apron_tile

    for index in reversed([(0, 0), (0, 1), (1, 0), (1, 1)]):
        renderer_b.resources.upload_tile_to_array(
            renderer_b.tile_service, "item.png", index,
            crop_apron_tile(store_b, index[1] * 512, index[0] * 512,
                            index[1] * 512 + 512, index[0] * 512 + 512),
            _FakeUpdates(),
        )
    _render(renderer_b)
    set_b = {
        (round(i.rect1[0], 5), round(i.rect1[1], 5), round(i.bbox[0], 5),
         round(i.bbox[1], 5), round(i.bbox[2], 5), round(i.bbox[3], 5))
        for i in captured_b["instances"]
    }
    assert set_a == set_b

    # Geometry derives from store size + framebuffer, not arrival: a second
    # framebuffer size yields different bboxes for the same store.
    captured_c: dict = {}
    renderer_c, _ = _make_renderer(monkeypatch, captured_c)
    renderer_c.set_source("item.png", store_a)
    _render(renderer_c, fb_w=800, fb_h=400)
    bbox_c = sorted(
        (round(i.bbox[0], 4), round(i.bbox[1], 4)) for i in captured_c["instances"]
    )
    bbox_a = sorted(
        (round(i.bbox[0], 4), round(i.bbox[1], 4)) for i in captured_a["instances"]
    )
    assert bbox_c != bbox_a
    renderer_a.release()
    renderer_b.release()
    renderer_c.release()


def test_contain_fit_scale_matches_preview_zoom_letterbox():
    # 1000x500 in 800x800: the wide image is height-limited.
    assert tr.contain_fit_scale((1000, 500), 800, 800) == (1.0, 0.5)
    assert tr.contain_fit_scale((500, 1000), 800, 800) == (0.5, 1.0)
    assert tr.contain_fit_scale((0, 0), 800, 800) == (1.0, 1.0)


def test_clear_source_drops_service():
    rhi = _FakeRhi()
    renderer = tr.QuickLookTileRenderer(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda _n: "sampler",
        load_shader=lambda _n: object(),
    )
    renderer.set_source("item.png", _distinct_store(1024, 1024))
    assert renderer.has_source()
    renderer.clear_source()
    assert not renderer.has_source()
    assert renderer.tile_service is None
    renderer.release()
