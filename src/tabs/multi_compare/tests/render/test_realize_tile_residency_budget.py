"""Budgeted progressive tile upload for multi_compare (docs/dev/rendering/
tile-rendering-system.md "Planned: budgeted progressive tile upload"):
_realize_tile_residency must not upload every missing tile in one call once
a slot spans multiple tiles -- only up to TILE_UPLOAD_BUDGET_PER_CALL, with
the rest picked up on a follow-up call against the same target set.
"""

from types import SimpleNamespace

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.tile_texture_service import TileTextureService
from tabs.multi_compare.scene.passes.base_images import BaseImagesPass


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

    def setName(self, _name):
        pass


class _FakeSrb:
    def setBindings(self, bindings):
        self.bindings = bindings

    def create(self):
        return True

    def destroy(self):
        pass


class _FakeBuffer:
    def create(self):
        return True


class _FakeRhi:
    def newTexture(self, _fmt, size):
        return _FakeTexture(size)

    def newTextureArray(self, _fmt, _array_size, size, _sample_count, _flags):
        return _FakeTexture(size)

    def newShaderResourceBindings(self):
        return _FakeSrb()

    def newBuffer(self, *_args, **_kwargs):
        return _FakeBuffer()


class _FakeUpdates:
    def uploadTexture(self, texture, image):
        pass


def _setup(monkeypatch, *, max_tile_extent=256):
    from tabs.multi_compare.scene.passes import slot_resources as slot_resources_module

    monkeypatch.setattr(
        slot_resources_module, "QRhiShaderResourceBinding", _FakeBinding
    )

    render_pass = BaseImagesPass()
    update_calls: list = []
    host = SimpleNamespace(update=lambda: update_calls.append(1))
    renderer = SimpleNamespace(
        rhi=_FakeRhi(),
        sampler=object(),
        tile_service=TileTextureService(max_tile_extent=max_tile_extent),
        host=host,
    )
    store = TiledPixelStore.from_pil(Image.new("RGBA", (1200, 800), (0, 0, 0, 255)))
    render_pass.queue_upload(1, store)
    updates = _FakeUpdates()
    render_pass.apply_pending_texture_ops(renderer, updates)

    layer = SimpleNamespace(
        slot_id=1,
        rect_fb=(0.0, 0.0, 100.0, 100.0),
        fit_x=1.0,
        fit_y=1.0,
        zoom=1.0,
        pan_x=0.0,
        pan_y=0.0,
    )
    ctx = SimpleNamespace(projected_layers=[layer])
    return render_pass, renderer, ctx, updates, store, update_calls


def test_first_call_uploads_at_most_the_budget(monkeypatch):
    # Exercises the budget-truncation logic itself, independent of whatever
    # TILE_UPLOAD_BUDGET_PER_CALL production tuning happens to be (64 at
    # LIVE_TILE_EXTENT=512's ~1MB/tile -- see tile_constants.py) -- a small
    # local budget keeps this test's fixture image small.
    from shared.rendering import residency as shared_residency_module

    local_budget = 2
    monkeypatch.setattr(
        shared_residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", local_budget
    )
    render_pass, renderer, ctx, updates, store, update_calls = _setup(monkeypatch)
    try:
        grid = renderer.tile_service.grid_for(1)
        total_tiles = grid.rows * grid.columns
        assert total_tiles > local_budget

        render_pass._realize_tile_residency(renderer, ctx, updates)

        resident = {
            index
            for index in renderer.tile_service.visible_tiles(1)
            if renderer.tile_service.is_resident(1, index)
        }
        assert len(resident) == local_budget
        assert update_calls, "expected renderer.host.update() to fire another frame"
    finally:
        store.close()


def test_remaining_tiles_upload_on_a_follow_up_call(monkeypatch):
    from shared.rendering import residency as shared_residency_module

    local_budget = 2
    monkeypatch.setattr(
        shared_residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", local_budget
    )
    render_pass, renderer, ctx, updates, store, update_calls = _setup(monkeypatch)
    try:
        grid = renderer.tile_service.grid_for(1)
        total_tiles = grid.rows * grid.columns

        resident_counts = []
        for _ in range(10):
            render_pass._realize_tile_residency(renderer, ctx, updates)
            resident = {
                index
                for index in renderer.tile_service.visible_tiles(1)
                if renderer.tile_service.is_resident(1, index)
            }
            resident_counts.append(len(resident))
            if len(resident) == total_tiles:
                break

        assert resident_counts[0] == local_budget
        assert resident_counts[-1] == total_tiles
        assert resident_counts == sorted(resident_counts)
    finally:
        store.close()


def test_time_budget_stops_upload_before_count_budget(monkeypatch):
    """docs/dev/rendering/tile-rendering-system.md "Planned: time-boxed
    upload budget": the wall-clock check must be able to stop a call before
    even TILE_UPLOAD_BUDGET_PER_CALL tiles are uploaded, if the clock says
    the per-call time budget is already spent."""
    from tabs.multi_compare.scene.passes import residency as residency_module

    render_pass, renderer, ctx, updates, store, update_calls = _setup(monkeypatch)
    try:
        clock = iter([0.0] + [1000.0] * 100)
        monkeypatch.setattr(
            residency_module.time, "monotonic", lambda: next(clock)
        )

        render_pass._realize_tile_residency(renderer, ctx, updates)

        assert render_pass.slot_resources.slot_textures == {}
        assert update_calls, "expected renderer.host.update() to fire another frame"
    finally:
        store.close()
