"""Array-slice uploads are hard-bounded before anything reaches QRhi.

Dogma (docs/dev/rendering/tile-rendering-system.md "Summary of the invariant",
plus the tile-array atlas path): ``TileArrayResourcesBase.upload_tile_to_array``
writes one cropped tile 1:1 into ``tile_arrays[array_index]`` layer ``layer``.
The layer must address a slice the array was *created* with, and the image must
fit one layer, because the backend copy is a subresource copy: on D3D11 a
mismatched ``CopySubresourceRegion`` fails silently and the layer keeps the
previous occupant's pixels -- read on screen as "this band shows another
tile". A rejected tile must therefore be dropped (and retried once its
geometry/slot is sane), never half-recorded as resident: ``mark_resident`` is
what makes the draw plan sample the layer, so recording it for a layer this
call never wrote is the corruption the guard exists to prevent.

This is a hardening guard, not a mechanism claim about the D3D11 artifact (that
needs a real device). It pins the pre-submit contract only: skipped upload, no
residency record, one bounded warning per distinct violation, and a skipped
counter exposed through the existing tile dump.

No QRhi context is created here: the real ``TileArrayResourcesBase.__init__``
touches no GPU object, the array creation is stubbed out, and ``updates`` just
records what would have been submitted.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtGui import QImage

from engine.cache.tile_texture_service import TileTextureService
from engine.gpu import array_resources as array_resources_module
from engine.gpu.array_resources import TileArrayResourcesBase
from core.log_names import APP_LOGGER_NAME

LAYER_PX = 16
CAPACITY = 2


class _SentinelTexture:
    """Stands in for a created ``QRhiTexture`` (identity only, never used)."""


class _RecordingUpdates:
    """Records what the caller would hand to ``command_buffer.resourceUpdate``."""

    def __init__(self) -> None:
        self.uploads: list[tuple[object, object]] = []
        self.mip_requests: list[object] = []

    def uploadTexture(self, texture, description) -> None:
        self.uploads.append((texture, description))

    def generateMips(self, texture) -> None:
        self.mip_requests.append(texture)


class _RecordingTileService(TileTextureService):
    """Real slot allocator/residency bookkeeping, with the calls recorded."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mark_resident_calls: list[tuple[object, tuple[int, int]]] = []

    def mark_resident(self, source_id, index, byte_size, content_size=None) -> None:
        self.mark_resident_calls.append((source_id, index))
        super().mark_resident(source_id, index, byte_size, content_size)


def _resources(*, capacity: int = CAPACITY, layer_px: int = LAYER_PX) -> TileArrayResourcesBase:
    resources = TileArrayResourcesBase(
        rhi_getter=lambda: None,
        sampler_getter=lambda name: None,
        load_shader=lambda name: None,
        layer_px=layer_px,
        array_capacity=capacity,
        name_prefix="bounds-test",
        instance_stride=16,
        uniform_block_size=64,
        instance_attributes=(),
        vertex_shader_name="unused.vert.qsb",
        fragment_shader_name="unused.frag.qsb",
    )
    # No QRhi: the single array the guard admits is already "created".
    resources.tile_arrays = [_SentinelTexture()]
    resources._ensure_tile_array = lambda array_index: None
    return resources


def _image(width: int = 8, height: int = 8) -> QImage:
    return QImage(width, height, QImage.Format.Format_RGBA8888)


def _service_with_full_first_array() -> _RecordingTileService:
    """A service whose allocator is one layer wider than the bound array.

    That is the real drift shape: the array was created with
    ``array_capacity`` layers, while the service defaults to a larger
    ``max_array_size`` and can therefore hand out ``layer == capacity``.
    """
    service = _RecordingTileService(max_array_size=CAPACITY + 1)
    for row in range(CAPACITY):
        service.mark_resident("occupant", (row, 0), 4, (4, 4))
    assert service.slot_for("occupant", (CAPACITY - 1, 0)) == (0, CAPACITY - 1)
    return service


def test_layer_outside_the_array_capacity_is_not_uploaded():
    resources = _resources()
    service = _service_with_full_first_array()
    updates = _RecordingUpdates()
    occupant_slots = {
        row: service.slot_for("occupant", (row, 0)) for row in range(CAPACITY)
    }

    resources.upload_tile_to_array(service, "tile", (0, 0), _image(), updates)

    assert updates.uploads == []
    # Not resident, no slot, no content record: the draw plan can never sample
    # a layer this call refused to write. (A first-time slot is only knowable
    # once mark_resident allocates it, so the guard rolls that record back --
    # the end state is the same as never recording it.)
    assert not service.is_resident("tile", (0, 0))
    assert service.slot_for("tile", (0, 0)) is None
    assert service.content_size_for("tile", (0, 0)) is None
    assert service.resident_tiles("tile") == set()
    # The pre-existing occupants keep their slots untouched.
    assert {
        row: service.slot_for("occupant", (row, 0)) for row in range(CAPACITY)
    } == occupant_slots
    assert resources.array_upload_skipped_count == 1


def test_image_larger_than_a_layer_is_not_uploaded():
    resources = _resources()
    service = _RecordingTileService(max_array_size=CAPACITY)
    updates = _RecordingUpdates()

    resources.upload_tile_to_array(
        service, "tile", (0, 0), _image(LAYER_PX + 1, 8), updates
    )

    assert updates.uploads == []
    assert service.mark_resident_calls == []
    assert not service.is_resident("tile", (0, 0))
    assert resources.array_upload_skipped_count == 1


def test_null_or_empty_image_is_not_uploaded():
    resources = _resources()
    service = _RecordingTileService(max_array_size=CAPACITY)
    updates = _RecordingUpdates()

    resources.upload_tile_to_array(service, "tile", (0, 0), QImage(), updates)

    assert updates.uploads == []
    assert service.mark_resident_calls == []
    assert resources.array_upload_skipped_count == 1


def test_happy_path_uploads_and_marks_resident_unchanged(monkeypatch):
    resources = _resources()
    service = _RecordingTileService(max_array_size=CAPACITY)
    updates = _RecordingUpdates()
    dirty_layers: dict[int, set[int]] = {}
    image = _image(LAYER_PX, LAYER_PX)
    submitted_entries: list[object] = []

    class _CapturingDescription:
        # QRhiTextureUploadDescription is write-only from Python (no
        # ``entries()`` getter), so capture the entry the production code
        # builds instead of re-deriving the layer independently.
        def __init__(self, entry) -> None:
            submitted_entries.append(entry)

    monkeypatch.setattr(
        array_resources_module, "QRhiTextureUploadDescription", _CapturingDescription
    )

    tile_key = resources.upload_tile_to_array(
        service, "tile", (0, 0), image, updates, dirty_layers
    )

    assert updates.uploads != []
    texture, _description = updates.uploads[0]
    assert texture is resources.tile_arrays[0]
    assert len(submitted_entries) == 1
    entry = submitted_entries[0]
    assert entry.layer() == 0
    assert entry.level() == 0
    assert entry.description().image().width() == LAYER_PX
    assert service.mark_resident_calls == [("tile", (0, 0))]
    assert service.is_resident("tile", (0, 0))
    assert service.slot_for("tile", (0, 0)) == (0, 0)
    assert service.content_size_for("tile", (0, 0)) == (LAYER_PX, LAYER_PX)
    assert dirty_layers == {0: {0}}
    assert updates.mip_requests == []
    assert resources.array_upload_skipped_count == 0
    assert tile_key == service.tile_key("tile", 0, 0)


def test_happy_path_without_dirty_layers_still_regenerates_mips():
    resources = _resources()
    service = _RecordingTileService(max_array_size=CAPACITY)
    updates = _RecordingUpdates()

    resources.upload_tile_to_array(service, "tile", (0, 0), _image(), updates)

    assert updates.mip_requests == [resources.tile_arrays[0]]


def test_one_warning_per_distinct_violation_not_per_frame(caplog):
    resources = _resources()
    service = _service_with_full_first_array()
    updates = _RecordingUpdates()

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        for _ in range(3):
            resources.upload_tile_to_array(service, "tile", (0, 0), _image(), updates)

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "tile" in message
    assert str(CAPACITY) in message  # the offending layer
    assert resources.array_upload_skipped_count == 3


def test_skipped_upload_is_reported_in_the_tile_dump(monkeypatch):
    resources = _resources()
    service = _RecordingTileService(max_array_size=CAPACITY)
    updates = _RecordingUpdates()
    events: list[tuple[str, dict]] = []

    monkeypatch.setattr(array_resources_module, "tile_dump_enabled", lambda: True)
    monkeypatch.setattr(
        array_resources_module,
        "log_tile_event",
        lambda kind, **fields: events.append((kind, fields)),
    )

    resources.upload_tile_to_array(
        service, "tile", (0, 0), _image(LAYER_PX + 1, 8), updates
    )

    skipped = [fields for kind, fields in events if kind == "array.upload_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"]
    assert skipped[0]["skipped_count"] == 1
    assert skipped[0]["image_w"] == LAYER_PX + 1


def test_rejected_tile_does_not_raise_out_of_the_frame():
    resources = _resources()
    service = _RecordingTileService(max_array_size=CAPACITY)
    updates = _RecordingUpdates()

    # A geometry bug upstream must degrade to a dropped tile, never a crash.
    resources.upload_tile_to_array(service, "tile", (0, 0), None, updates)
    resources.upload_tile_to_array(
        service, "tile", (1, 1), _image(LAYER_PX * 4, LAYER_PX * 4), updates
    )

    assert updates.uploads == []
    assert resources.array_upload_skipped_count == 2


@pytest.mark.parametrize("capacity", [1, 4])
def test_layers_inside_a_smaller_or_larger_array_are_still_admitted(capacity):
    resources = _resources(capacity=capacity)
    service = _RecordingTileService(max_array_size=capacity)
    updates = _RecordingUpdates()

    resources.upload_tile_to_array(
        service, "tile", (0, 0), _image(), updates, {0: set()}
    )

    assert len(updates.uploads) == 1
    assert service.is_resident("tile", (0, 0))
    assert resources.array_upload_skipped_count == 0
