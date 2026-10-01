"""Quick Look tiled single-source view — plan/instance contracts.

Quick Look now draws through the engine's ``SingleImageTiledView``
(``engine.gpu.tiled_image_view``); these tests construct that view directly
and pin the frozen semantics, not its tab-local predecessor:

- ``set_source`` registers the expected rows/cols for the store size;
- one instance per visible tile, each ``layer`` resolved from ITS OWN index
  (a swapped/neighbor binding must fail);
- a visible tile with no slot yet is skipped (fail closed, never a neighbor);
- geometry comes from store size + ``(fb_w, fb_h)``, not upload/arrival order.

No real GPU: the engine view's draw is captured by monkeypatching
``engine.gpu.tiled_image_view.record_array_draw`` and the array resource
owner is a CPU-side fake, while residency still runs through the real
``TileTextureService`` + shared ``realize_specs`` loop.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.gpu.tiled_image_view as tiv
from engine.cache.draw_plans import build_slot_plan_tiles
from engine.gpu.tiled_image_view import (
    SingleImageTiledView,
    TiledImageSource,
    TiledImageView,
    contain_fit_scale,
)


pytest.importorskip("PIL")

_KEY = "item.png"


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


class _NoPrefetch:
    def warm(self, *_a, **_k) -> bool:
        return False


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


def _make_view(monkeypatch, captured):
    rhi = _FakeRhi()
    view = SingleImageTiledView(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda _n: "sampler",
        load_shader=lambda _name: object(),
        name_prefix="ql",
    )
    # Replace GPU owners with fakes; keep the real tile service + shared
    # residency loop so uploads are recorded through the engine seam.
    resources = _FakeResources()
    view.resources = resources
    view._realizer._array_resources = resources
    view._realizer._prefetcher = _NoPrefetch()
    view._mip_cascade = _FakeMipCascade()
    view._vertex_buffer = _FakeBuffer()

    def _capture(command_buffer, **kwargs):
        captured["instances"] = list(kwargs.get("instances") or [])
        captured["uniform_bytes"] = kwargs.get("uniform_bytes")
        captured["pre_begin"] = kwargs.get("pre_begin")

    monkeypatch.setattr(tiv, "record_array_draw", _capture)
    return view, rhi


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


def _render(view, *, fb_w=512, fb_h=512, zoom=1.0, pan=(0.0, 0.0)):
    updates = _FakeUpdates()
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: fb_w, height=lambda: fb_h)
    )
    result = view.render(
        _FakeCmdBuffer(),
        updates=updates,
        target=target,
        clear_color=SimpleNamespace(),
        view=TiledImageView(zoom=zoom, pan=pan, fb_size=(fb_w, fb_h)),
    )
    return result, updates


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_set_source_registers_expected_grid(monkeypatch):
    store = _distinct_store(1024, 1024)
    view, _ = _make_view(monkeypatch, {})
    view.set_source(TiledImageSource(key=_KEY, store=store))
    grid = view.tile_service.grid_for(_KEY)
    assert grid is not None
    assert (grid.rows, grid.columns) == (2, 2)
    assert (grid.total_width, grid.total_height) == (1024, 1024)
    view.clear_source()


def test_render_binds_layer_from_own_index(monkeypatch):
    store = _distinct_store(1024, 1024)
    captured: dict = {}
    view, _ = _make_view(monkeypatch, captured)
    view.set_source(TiledImageSource(key=_KEY, store=store))

    # Upload in a deliberately NON row-major order so a plan that bound
    # layers by upload/arrival order rather than by tile index would fail.
    from engine.cache.tile_geometry import crop_apron_tile

    reverse = [(1, 1), (0, 0), (1, 0), (0, 1)]
    for index in reverse:
        view.resources.upload_tile_to_array(
            view.tile_service, _KEY, index,
            crop_apron_tile(store, index[1] * 512, index[0] * 512,
                            index[1] * 512 + 512, index[0] * 512 + 512),
            _FakeUpdates(),
        )

    result, _uploads = _render(view)
    assert result.drawn is True
    instances = captured["instances"]
    assert len(instances) == 4
    # Every visible tile got its own instance, bound to its own index's layer.
    by_rect = {(round(i.rect1[0], 4), round(i.rect1[1], 4)): i for i in instances}
    assert len(by_rect) == 4
    for tile in build_slot_plan_tiles(
        view.tile_service, _KEY, (0.0, 0.0),
        contain_fit_scale((1024, 1024), 512, 512), 1.0,
    ):
        inst = next(i for i in instances if i.rect1 == tile.rect)
        expected_layer = view.tile_service.slot_for(_KEY, tile.index)[1]
        assert inst.layer1 == expected_layer
    # A swapped/neighbor binding would collapse layers; require all distinct.
    assert len({i.layer1 for i in instances}) == 4
    view.clear_source()


def test_render_uploads_in_non_row_major_order_still_all_visible(monkeypatch):
    store = _distinct_store(1024, 1024)
    captured: dict = {}
    view, _ = _make_view(monkeypatch, captured)
    view.set_source(TiledImageSource(key=_KEY, store=store))
    # No pre-upload: render must upload the visible set itself and draw it.
    result, updates = _render(view)
    assert result.drawn is True
    assert result.covered is True
    assert len(captured["instances"]) == 4
    uploaded_indices = {u[1] for u in view.resources.uploaded}
    assert uploaded_indices == {(0, 0), (0, 1), (1, 0), (1, 1)}
    view.clear_source()


def test_missing_slot_fails_closed_never_neighbor(monkeypatch):
    store = _distinct_store(1024, 1024)
    captured: dict = {}
    view, _ = _make_view(monkeypatch, captured)
    view.set_source(TiledImageSource(key=_KEY, store=store))
    # Mark only ONE tile resident (index (0,0)); the others have no slot.
    from engine.cache.tile_geometry import crop_apron_tile

    only = (0, 0)
    view.resources.upload_tile_to_array(
        view.tile_service, _KEY, only,
        crop_apron_tile(store, 0, 0, 512, 512), _FakeUpdates(),
    )
    # Prevent render from uploading the rest: monkeypatch select_upload_batch.
    monkeypatch.setattr(
        view.tile_service, "select_upload_batch",
        lambda *_a, **_k: [],
    )
    result, _updates = _render(view)
    assert result.drawn is True
    assert result.covered is False
    instances = captured["instances"]
    assert len(instances) == 1
    expected_layer = view.tile_service.slot_for(_KEY, only)[1]
    assert instances[0].layer1 == expected_layer
    # The single instance's rect is the resident tile's own, not a neighbor's.
    plan = build_slot_plan_tiles(
        view.tile_service, _KEY, (0.0, 0.0),
        contain_fit_scale((1024, 1024), 512, 512), 1.0,
    )
    own = next(t for t in plan if t.index == only)
    assert instances[0].rect1 == own.rect
    view.clear_source()


def test_geometry_from_store_size_not_arrival_order(monkeypatch):
    """Same inputs -> same instance set regardless of upload order."""
    store_a = _distinct_store(1024, 1024)
    store_b = _distinct_store(1024, 1024)

    captured_a: dict = {}
    view_a, _ = _make_view(monkeypatch, captured_a)
    view_a.set_source(TiledImageSource(key=_KEY, store=store_a))
    _render(view_a)
    set_a = {
        (round(i.rect1[0], 5), round(i.rect1[1], 5), round(i.bbox[0], 5),
         round(i.bbox[1], 5), round(i.bbox[2], 5), round(i.bbox[3], 5))
        for i in captured_a["instances"]
    }

    captured_b: dict = {}
    view_b, _ = _make_view(monkeypatch, captured_b)
    view_b.set_source(TiledImageSource(key=_KEY, store=store_b))
    # Upload all first in reverse order, then render (no new uploads).
    from engine.cache.tile_geometry import crop_apron_tile

    for index in reversed([(0, 0), (0, 1), (1, 0), (1, 1)]):
        view_b.resources.upload_tile_to_array(
            view_b.tile_service, _KEY, index,
            crop_apron_tile(store_b, index[1] * 512, index[0] * 512,
                            index[1] * 512 + 512, index[0] * 512 + 512),
            _FakeUpdates(),
        )
    _render(view_b)
    set_b = {
        (round(i.rect1[0], 5), round(i.rect1[1], 5), round(i.bbox[0], 5),
         round(i.bbox[1], 5), round(i.bbox[2], 5), round(i.bbox[3], 5))
        for i in captured_b["instances"]
    }
    assert set_a == set_b

    # Geometry derives from store size + framebuffer, not arrival: a second
    # framebuffer size yields different bboxes for the same store.
    captured_c: dict = {}
    view_c, _ = _make_view(monkeypatch, captured_c)
    view_c.set_source(TiledImageSource(key=_KEY, store=store_a))
    _render(view_c, fb_w=800, fb_h=400)
    bbox_c = sorted(
        (round(i.bbox[0], 4), round(i.bbox[1], 4)) for i in captured_c["instances"]
    )
    bbox_a = sorted(
        (round(i.bbox[0], 4), round(i.bbox[1], 4)) for i in captured_a["instances"]
    )
    assert bbox_c != bbox_a
    view_a.clear_source()
    view_b.clear_source()
    view_c.clear_source()


def test_contain_fit_scale_matches_preview_zoom_letterbox():
    # 1000x500 in 800x800: the wide image is height-limited.
    assert contain_fit_scale((1000, 500), 800, 800) == (1.0, 0.5)
    assert contain_fit_scale((500, 1000), 800, 800) == (0.5, 1.0)
    assert contain_fit_scale((0, 0), 800, 800) == (1.0, 1.0)


def test_clear_source_drops_service(monkeypatch):
    view, _ = _make_view(monkeypatch, {})
    view.set_source(TiledImageSource(key=_KEY, store=_distinct_store(1024, 1024)))
    assert view.has_source()
    view.clear_source()
    assert not view.has_source()
    assert view.tile_service is None
