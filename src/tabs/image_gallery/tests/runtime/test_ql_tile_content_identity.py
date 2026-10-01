"""Quick Look tiled single-source renderer — CONTENT-IDENTITY contracts.

Counts, windows, emits, sizes and timing are *not* correctness. A plan that
binds tile ``i``'s screen rect to tile ``j``'s array layer satisfies every one
of those and still shows the wrong pixels. These tests assert the stronger
property

    payload(tile i) == content(i)   for every emitted instance

with a content-aware fake that stores, per array ``(index, layer)``, a
fingerprint of the *image actually uploaded there*. A swapped / neighbor /
stale binding fails because the bytes in the bound layer are the neighbor's,
not the rect's own tile.

The store is a synthetic multi-tile ``TiledPixelStore`` (a distinct solid
colour per ``LIVE_TILE_EXTENT`` region), so each tile's content is
distinguishable and the identity tests are provably not blind (a guard
asserts the per-tile fingerprints are pairwise distinct). No real GPU:
``record_array_draw`` is captured.

This file is additive to W1's ``test_ql_tile_renderer.py`` (plan/instance
shape); it re-asserts identity in terms of what lands in the array.
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


def _fingerprint(image) -> tuple[int, int] | None:
    """Distinct-content fingerprint of one uploaded tile image.

    Each synthetic tile is a solid colour, so two interior samples identify
    it. The apron's 1px border (which duplicates neighbour pixels) is never
    sampled: ``(1, 1)`` and the centre are tile-owned for every index.
    """
    try:
        w, h = int(image.width()), int(image.height())
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return (
        int(image.pixel(min(w - 1, 1), min(h - 1, 1))),
        int(image.pixel(w // 2, h // 2)),
    )


class _ContentResources:
    """CPU-side array stand-in that models the *content* of each layer.

    Mirrors ``TileArrayResourcesBase.upload_tile_to_array`` ordering exactly
    (``mark_resident`` -> ``slot_for`` -> record payload) so instance layers
    resolve through the real service allocator, and additionally records the
    fingerprint of the uploaded image under ``(array_index, layer)``. That is
    what makes a wrong binding observable: the bound layer holds a neighbour's
    fingerprint, not the rect's own.
    """

    def __init__(self) -> None:
        self.array_pipeline = "pipeline"
        self.array_uniform_buffer = _FakeBuffer("ubuf")
        self.array_instance_buffer = _FakeBuffer("ibuf")
        self.array_srb = "srb"
        self.tile_arrays = [_FakeBuffer("array0")]
        self.layer_payload: dict[tuple[int, int], tuple[int, int] | None] = {}
        self.uploads: list = []

    def ensure_array_pipeline(self, target) -> None:
        pass

    def ensure_array_instance_capacity(self, count) -> None:
        pass

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
        array_index, layer = tile_service.slot_for(source_key, index)
        self.layer_payload[(array_index, layer)] = _fingerprint(image)
        self.uploads.append((source_key, index, (array_index, layer)))
        return tile_service.tile_key(source_key, *index)


def _make_renderer(monkeypatch):
    rhi = _FakeRhi()
    renderer = tr.QuickLookTileRenderer(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda _n: "sampler",
        load_shader=lambda _n: object(),
    )
    renderer.resources = _ContentResources()
    renderer._mip_cascade = _FakeMipCascade()
    renderer._vertex_buffer = _FakeBuffer()
    captured: dict = {}

    def _capture(command_buffer, **kwargs):
        captured["instances"] = list(kwargs.get("instances") or [])

    monkeypatch.setattr(tr, "record_array_draw", _capture)
    return renderer, captured


def _distinct_store(width: int, height: int, tile_px: int = 512, offset: int = 0):
    """A TiledPixelStore whose every ``tile_px`` region is a distinct solid
    colour (``offset`` shifts the palette, so two stores at the same size
    carry different content — the stale-generation discriminator)."""
    import numpy as np
    from PIL import Image

    from engine.store.tiled_pixel_store import TiledPixelStore

    arr = np.zeros((height, width, 4), dtype=np.uint8)
    idx = 0
    for top in range(0, height, tile_px):
        for left in range(0, width, tile_px):
            color = (
                (idx * 40 + 10 + offset) % 256,
                (idx * 70 + 30 + offset) % 256,
                (idx * 110 + 50 + offset) % 256,
                255,
            )
            arr[top:top + tile_px, left:left + tile_px, :] = color
            idx += 1
    return TiledPixelStore.from_pil(Image.fromarray(arr, "RGBA"))


def _render(renderer, captured=None, *, fb_w=512, fb_h=512, zoom=1.0, pan=(0.0, 0.0)):
    if captured is not None:
        captured["instances"] = []
    updates = _FakeUpdates()
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: fb_w, height=lambda: fb_h)
    )
    return renderer.render(
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


def _plan(renderer, *, fb_w, fb_h, pan, zoom):
    fit = tr.contain_fit_scale(renderer.store_size(), fb_w, fb_h)
    plan = tr.build_slot_plan_tiles(
        renderer.tile_service, renderer._key, pan, fit, zoom
    )
    return plan


def _tile_fingerprint(store, grid, index):
    from engine.cache.tile_geometry import crop_apron_tile

    region = grid.region_for(*index)
    return _fingerprint(
        crop_apron_tile(store, region.left, region.top, region.right, region.bottom)
    )


def _assert_content_identity(
    renderer, captured, store, *, fb_w, fb_h, pan, zoom
):
    """Every emitted instance must sample the layer holding *its own* tile.

    The expected payload is recomputed from the store's region for the rect's
    plan index — *not* from the service slot lookup the renderer itself used,
    so a renderer that binds a neighbour's slot fails here.
    """
    grid = renderer.tile_service.grid_for(renderer._key)
    plan = _plan(renderer, fb_w=fb_w, fb_h=fb_h, pan=pan, zoom=zoom)
    rect_to_index = {tile.rect: tile.index for tile in plan}
    res = renderer.resources
    seen: set = set()
    for inst in captured["instances"]:
        assert inst.rect1 in rect_to_index, (
            f"instance rect {inst.rect1!r} is not a visible plan tile"
        )
        index = rect_to_index[inst.rect1]
        assert index not in seen, f"duplicate instance for tile {index}"
        seen.add(index)
        expected = _tile_fingerprint(store, grid, index)
        actual = res.layer_payload.get((0, inst.layer1))
        assert actual == expected, (
            f"tile {index} bound layer {inst.layer1} holding {actual!r}, "
            f"expected its own content {expected!r} (neighbour/stale binding)"
        )
    return seen, rect_to_index


# ---------------------------------------------------------------------------
# 1. distinct-content identity
# ---------------------------------------------------------------------------


def test_distinct_content_payload_matches_own_index(monkeypatch):
    store = _distinct_store(1024, 1024)
    renderer, captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        drawn = _render(renderer)
        assert drawn is True
        instances = captured["instances"]
        assert len(instances) == 4

        # Not-blind guard: the four tiles really do carry distinct content.
        grid = renderer.tile_service.grid_for("item.png")
        fps = [_tile_fingerprint(store, grid, idx) for idx in
               [(0, 0), (0, 1), (1, 0), (1, 1)]]
        assert len(set(fps)) == 4, f"fixture not distinct: {fps}"

        seen, _ = _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
        )
        assert seen == {(0, 0), (0, 1), (1, 0), (1, 1)}
        assert len({i.layer1 for i in instances}) == 4
    finally:
        renderer.release()
        store.close()


# ---------------------------------------------------------------------------
# 2. sparse / evicted / stale — fail closed, never a neighbour
# ---------------------------------------------------------------------------


def test_no_resident_tile_draws_nothing(monkeypatch):
    """Empty residency: render draws nothing and emits no instance."""
    store = _distinct_store(1024, 1024)
    renderer, captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        monkeypatch.setattr(
            renderer.tile_service, "select_upload_batch", lambda *_a, **_k: []
        )
        drawn = _render(renderer, captured)
        assert drawn is False
        assert captured.get("instances", []) == []

        # No source at all is also empty, never a stale draw.
        renderer.clear_source()
        assert _render(renderer, captured) is False
        assert captured.get("instances", []) == []
    finally:
        renderer.release()
        store.close()


def test_hole_in_middle_skips_without_neighbor_substitution(monkeypatch):
    """3x3 grid with the centre tile unresident: 8 instances, centre gap."""
    store = _distinct_store(1536, 1536)
    renderer, captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        from engine.cache.tile_geometry import crop_apron_tile

        grid = renderer.tile_service.grid_for("item.png")
        assert (grid.rows, grid.columns) == (3, 3)
        hole = (1, 1)
        for row in range(3):
            for col in range(3):
                if (row, col) == hole:
                    continue
                region = grid.region_for(row, col)
                renderer.resources.upload_tile_to_array(
                    renderer.tile_service, "item.png", (row, col),
                    crop_apron_tile(
                        store, region.left, region.top, region.right, region.bottom
                    ),
                    _FakeUpdates(),
                )
        monkeypatch.setattr(
            renderer.tile_service, "select_upload_batch", lambda *_a, **_k: []
        )
        assert _render(renderer) is True
        seen, _ = _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
        )
        assert hole not in seen
        assert len(seen) == 8
        # The unresident hole's own content appears nowhere.
        hole_fp = _tile_fingerprint(store, grid, hole)
        bound = {renderer.resources.layer_payload[(0, i.layer1)] for i in captured["instances"]}
        assert hole_fp not in bound, "unresident tile's content leaked onto a layer"
    finally:
        renderer.release()
        store.close()


def test_evicted_neighbor_is_skipped_not_substituted(monkeypatch):
    """Evicting one resident tile removes its instance; no neighbour covers it."""
    store = _distinct_store(1024, 1024)
    renderer, captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        from engine.cache.tile_geometry import crop_apron_tile

        grid = renderer.tile_service.grid_for("item.png")
        for index in [(1, 1), (0, 0), (1, 0), (0, 1)]:  # non row-major
            region = grid.region_for(*index)
            renderer.resources.upload_tile_to_array(
                renderer.tile_service, "item.png", index,
                crop_apron_tile(
                    store, region.left, region.top, region.right, region.bottom
                ),
                _FakeUpdates(),
            )
        evicted = (0, 1)
        renderer.tile_service.invalidate_tiles("item.png", {evicted})
        assert not renderer.tile_service.is_resident("item.png", evicted)
        assert renderer.tile_service.slot_for("item.png", evicted) is None

        monkeypatch.setattr(
            renderer.tile_service, "select_upload_batch", lambda *_a, **_k: []
        )
        assert _render(renderer) is True
        instances = captured["instances"]
        assert len(instances) == 3
        seen, _ = _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
        )
        assert evicted not in seen
        evicted_fp = _tile_fingerprint(store, grid, evicted)
        bound = {renderer.resources.layer_payload[(0, i.layer1)] for i in instances}
        assert evicted_fp not in bound, "evicted tile's content resurfaced"
    finally:
        renderer.release()
        store.close()


def test_stale_generation_after_fresh_is_not_sampled(monkeypatch):
    """A fresh source's un-uploaded tiles are gaps, never the old array content."""
    store_a = _distinct_store(1024, 1024, offset=0)
    store_b = _distinct_store(1024, 1024, offset=128)
    renderer, captured = _make_renderer(monkeypatch)
    try:
        # Generation A: upload all four (array layers now hold A's content).
        renderer.set_source("A", store_a)
        assert _render(renderer) is True
        assert len(captured["instances"]) == 4
        stale_a_layers = dict(renderer.resources.layer_payload)
        assert len(stale_a_layers) == 4

        # Generation B: fresh service, but the fake array still holds A's bytes.
        renderer.set_source("B", store_b)
        monkeypatch.setattr(
            renderer.tile_service, "select_upload_batch", lambda *_a, **_k: []
        )
        # Nothing resident for B -> fail closed, never samples A's stale layers.
        assert _render(renderer, captured) is False
        assert captured.get("instances", []) == []

        # Upload exactly one B tile (lands in the fresh allocator's first slot).
        from engine.cache.tile_geometry import crop_apron_tile

        grid_b = renderer.tile_service.grid_for("B")
        only = (1, 1)
        region = grid_b.region_for(*only)
        renderer.resources.upload_tile_to_array(
            renderer.tile_service, "B", only,
            crop_apron_tile(
                store_b, region.left, region.top, region.right, region.bottom
            ),
            _FakeUpdates(),
        )
        assert _render(renderer) is True
        assert len(captured["instances"]) == 1
        seen, _ = _assert_content_identity(
            renderer, captured, store_b, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
        )
        assert seen == {only}
        inst = captured["instances"][0]
        b_fp = _tile_fingerprint(store_b, grid_b, only)
        # The layer holds B's content, and B(1,1) differs from A(1,1) — prove
        # the fixture actually discriminates stale A bytes from fresh B bytes.
        assert renderer.resources.layer_payload[(0, inst.layer1)] == b_fp
        from engine.store.regions import build_uniform_tile_grid

        grid_a = build_uniform_tile_grid(1024, 1024, max_tile_width=512)
        a_fp = _tile_fingerprint(store_a, grid_a, only)
        assert b_fp != a_fp, "fixture: A and B must differ for this test to bite"
    finally:
        renderer.release()
        store_a.close()
        store_b.close()


# ---------------------------------------------------------------------------
# 3. remap — zoom / resize / reopen re-resolve index -> layer, no cross-binding
# ---------------------------------------------------------------------------


def test_remap_zoom_resize_reopen_no_cross_binding(monkeypatch):
    store = _distinct_store(1024, 1024)
    renderer, captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        assert _render(renderer) is True
        seen, _ = _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
        )
        assert seen == {(0, 0), (0, 1), (1, 0), (1, 1)}

        # Zoom into the bottom-right tile only.
        assert _render(renderer, zoom=8.0, pan=(-0.375, -0.375)) is True
        seen, _ = _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=512,
            pan=(-0.375, -0.375), zoom=8.0,
        )
        assert seen == {(1, 1)}, f"zoom remap must re-resolve to one tile, got {seen}"

        # Resize the framebuffer: geometry changes, identity still holds.
        assert _render(renderer, fb_w=512, fb_h=1024) is True
        seen_resize, _ = _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=1024, pan=(0.0, 0.0), zoom=1.0
        )
        assert seen_resize == {(0, 0), (0, 1), (1, 0), (1, 1)}

        # Reopen with a same-size store of different content (a new generation).
        store2 = _distinct_store(1024, 1024, offset=200)
        try:
            renderer.set_source("reopened", store2)
            assert _render(renderer) is True
            seen_reopen, _ = _assert_content_identity(
                renderer, captured, store2, fb_w=512, fb_h=512,
                pan=(0.0, 0.0), zoom=1.0,
            )
            assert seen_reopen == {(0, 0), (0, 1), (1, 0), (1, 1)}
        finally:
            store2.close()
    finally:
        renderer.release()
        store.close()


# ---------------------------------------------------------------------------
# 4. cache / slot keys distinguish tile indices
# ---------------------------------------------------------------------------


def test_slot_and_tile_keys_include_index(monkeypatch):
    store = _distinct_store(1024, 1024)
    renderer, _captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        indices = [(0, 0), (0, 1), (1, 0), (1, 1)]
        keys = {renderer.tile_service.tile_key("item.png", r, c) for r, c in indices}
        assert keys == {("item.png", r, c) for r, c in indices}
        assert len(keys) == 4, "tile keys collapse across indices"

        assert _render(renderer) is True
        slots = {
            renderer.tile_service.slot_for("item.png", index) for index in indices
        }
        assert None not in slots
        assert len(slots) == 4, f"two tiles share an array slot: {slots}"

        alloc_keys = set(renderer.tile_service._slot_allocator._slot_for_key)
        assert alloc_keys == {("item.png", index) for index in indices}, (
            "slot allocator keys must be (source_id, tile index)-shaped"
        )
    finally:
        renderer.release()
        store.close()


# ---------------------------------------------------------------------------
# 5. geometry is data / arrival independent
# ---------------------------------------------------------------------------


def test_plan_geometry_from_store_not_residency(monkeypatch):
    """Visibility/enumeration is full-grid even when only one tile is resident."""
    store = _distinct_store(1024, 1024)
    renderer, captured = _make_renderer(monkeypatch)
    renderer.set_source("item.png", store)
    try:
        from engine.cache.tile_geometry import crop_apron_tile

        grid = renderer.tile_service.grid_for("item.png")
        only = (1, 1)
        region = grid.region_for(*only)
        renderer.resources.upload_tile_to_array(
            renderer.tile_service, "item.png", only,
            crop_apron_tile(
                store, region.left, region.top, region.right, region.bottom
            ),
            _FakeUpdates(),
        )
        monkeypatch.setattr(
            renderer.tile_service, "select_upload_batch", lambda *_a, **_k: []
        )
        # The plan enumerates all four tiles regardless of residency.
        plan = _plan(renderer, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0)
        assert {tile.index for tile in plan} == {(0, 0), (0, 1), (1, 0), (1, 1)}
        # Drawn set is the resident subset; the one instance's rect matches
        # the full-grid position of (1,1), not a first-arrived fit.
        assert _render(renderer) is True
        assert len(captured["instances"]) == 1
        own = next(t for t in plan if t.index == only)
        assert captured["instances"][0].rect1 == own.rect
        _assert_content_identity(
            renderer, captured, store, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
        )
    finally:
        renderer.release()
        store.close()


def test_geometry_and_content_independent_of_arrival_order(monkeypatch):
    """Same size -> same instance geometry; content stays per-index either way."""
    store_a = _distinct_store(1024, 1024, offset=0)
    store_b = _distinct_store(1024, 1024, offset=64)

    renderer_a, captured_a = _make_renderer(monkeypatch)
    renderer_a.set_source("item.png", store_a)
    assert _render(renderer_a) is True
    inst_a = captured_a["instances"]
    _assert_content_identity(
        renderer_a, captured_a, store_a, fb_w=512, fb_h=512, pan=(0.0, 0.0), zoom=1.0
    )

    renderer_b, captured_b = _make_renderer(monkeypatch)
    renderer_b.set_source("item.png", store_b)
    try:
        from engine.cache.tile_geometry import crop_apron_tile

        grid_b = renderer_b.tile_service.grid_for("item.png")
        for index in reversed([(0, 0), (0, 1), (1, 0), (1, 1)]):
            region = grid_b.region_for(*index)
            renderer_b.resources.upload_tile_to_array(
                renderer_b.tile_service, "item.png", index,
                crop_apron_tile(
                    store_b, region.left, region.top, region.right, region.bottom
                ),
                _FakeUpdates(),
            )
        monkeypatch.setattr(
            renderer_b.tile_service, "select_upload_batch", lambda *_a, **_k: []
        )
        assert _render(renderer_b) is True
        inst_b = captured_b["instances"]
        _assert_content_identity(
            renderer_b, captured_b, store_b, fb_w=512, fb_h=512,
            pan=(0.0, 0.0), zoom=1.0,
        )

        shape = lambda insts: {  # noqa: E731
            (round(i.rect1[0], 6), round(i.rect1[1], 6), round(i.rect1[2], 6),
             round(i.rect1[3], 6), round(i.bbox[0], 6), round(i.bbox[1], 6),
             round(i.bbox[2], 6), round(i.bbox[3], 6))
            for i in insts
        }
        assert shape(inst_a) == shape(inst_b), "geometry depends on arrival order"
    finally:
        renderer_a.release()
        renderer_b.release()
        store_a.close()
        store_b.close()
