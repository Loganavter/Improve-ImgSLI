"""W3a: texture-upload and geometry paths intersect the effective crop box.

With pixel stores decoding FULL-FRAME, envelope rects, pixmap dims, tile
grids and preloaded textures must become box-clipped; a ``None`` box
(crop disabled / no borders) must behave IDENTICALLY to today.

Covers ``tabs.image_compare.canvas.texture_parts.crop_clip`` (the canvas
layer's single consumer of ``effective_crop_box_for_path``),
``base_images`` geometry/upload clipping, and residency grid registration.
"""

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from shared.image_processing.autocrop.model import CropBox
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.tile_texture_service import TileTextureService
from shared.rendering.unified_envelope import eager_envelope_rect
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources
from tabs.image_compare.canvas.texture_parts.base_images import (
    update_common_letterbox_geometry,
    upload_pil_images,
)
from tabs.image_compare.canvas.texture_parts.crop_clip import (
    BoxCroppedStoreView,
    box_dims,
    clip_box_for_image,
    clip_image_for_upload,
    resolve_box_for_path,
    resolve_slot_boxes,
    sanitize_box,
    scaled_box_for_source,
)


def _letterbox_widget(width=800, height=600, **state_extra):
    state = SimpleNamespace(
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _inner_content_rect_px=None,
        _clip_overlays_to_content_rect=False,
        _store=None,
        **state_extra,
    )
    return SimpleNamespace(
        runtime_state=state,
        width=lambda: width,
        height=lambda: height,
    )


# -- pure helpers ------------------------------------------------------------


def test_sanitize_box_full_frame_is_none_parity():
    assert sanitize_box(None, (200, 100)) is None
    assert sanitize_box((0, 0, 200, 100), (200, 100)) is None
    assert sanitize_box((0, 0, 999, 999), (200, 100)) is None  # clamped to full
    assert sanitize_box((10, 10, 10, 50), (200, 100)) is None  # degenerate
    assert sanitize_box((50, 10, 10, 50), (200, 100)) is None
    assert sanitize_box("nope", (200, 100)) is None
    assert sanitize_box((10, 10, 60, 60), (0, 0)) is None


def test_sanitize_box_clamps_to_frame():
    # Clamped to the full frame -> None (no crop, parity).
    assert sanitize_box((-50, -50, 500, 500), (200, 100)) is None
    assert sanitize_box((10, 20, 60, 80), (200, 100)) == (10, 20, 60, 80)
    assert box_dims((10, 20, 60, 80), (200, 100)) == (50, 60)
    assert box_dims(None, (200, 100)) == (200, 100)


def test_clip_box_for_image_identity_and_scaled():
    full = (400, 200)
    box = CropBox(100, 50, 300, 150)
    assert clip_box_for_image(box, full_size=full, img_size=(400, 200)) == (100, 50, 300, 150)
    # Half-size preview tier scales the box uniformly.
    assert clip_box_for_image(box, full_size=full, img_size=(200, 100)) == (50, 25, 150, 75)
    assert clip_box_for_image(None, full_size=full, img_size=(200, 100)) is None
    assert clip_box_for_image(box, full_size=None, img_size=(200, 100)) is None


def test_scaled_box_for_source_falls_back_to_live_size_without_probe():
    # Fake path: header probe fails -> sanitize against live size (exact
    # whenever live == original).
    assert scaled_box_for_source(
        CropBox(10, 10, 40, 40), path="/nonexistent/fake.png", live_size=(50, 50)
    ) == (10, 10, 40, 40)
    assert scaled_box_for_source(
        CropBox(0, 0, 50, 50), path="/nonexistent/fake.png", live_size=(50, 50)
    ) is None  # full -> None parity
    assert scaled_box_for_source(None, path="/nonexistent/fake.png", live_size=(50, 50)) is None


# -- GUI-thread rule ----------------------------------------------------------


def test_resolve_box_skips_unwarmed_service_without_blocking():
    calls = []

    class Unwarmed:
        def _has_cached(self, path):
            return False

        def warm_cache_async(self, paths):
            calls.append(list(paths))

        def get(self, path):  # pragma: no cover - must never run on GUI thread
            raise AssertionError("CropService.get called on unwarmed path")

    assert resolve_box_for_path("/some/file.png", Unwarmed()) is None
    assert calls == [["/some/file.png"]]


def test_resolve_box_queries_test_fakes_without_warm_check():
    class PlainFake:
        def __init__(self):
            self.seen = []

        def get(self, path):
            self.seen.append(path)
            return CropBox(1, 2, 30, 40)

    svc = PlainFake()
    assert resolve_box_for_path("/some/file.png", svc) == CropBox(1, 2, 30, 40)
    assert svc.seen == ["/some/file.png"]
    assert resolve_box_for_path(None, svc) is None
    assert resolve_box_for_path("/some/file.png", None) is None


def test_resolve_slot_boxes_none_without_service():
    widget = _letterbox_widget()
    assert resolve_slot_boxes(widget) == (None, None)


# -- BoxCroppedStoreView -------------------------------------------------------


def test_box_cropped_store_view_matches_offset_parent_crop(tmp_path):
    import numpy as np

    arr = np.zeros((48, 64, 4), dtype=np.uint8)
    arr[:, :, 0] = np.tile(np.arange(64, dtype=np.uint8), (48, 1))
    arr[:, :, 3] = 255
    store = TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"), tmp_dir=str(tmp_path))
    try:
        view = BoxCroppedStoreView(store, (8, 8, 40, 32))
        assert view.size == (32, 24)
        assert view.is_open
        from PySide6.QtGui import QImage as _QImage

        from shared.image_processing.tiled_pixel_store import (
            pixel_source_size,
            qimage_from_pixel_source,
        )
        from shared.image_processing.image_dims import get_image_dims
        from shared.rendering.tile_geometry import crop_apron_tile

        full_q = qimage_from_pixel_source(store, (8, 8, 40, 32))
        got = view.crop((0, 0, 32, 24))
        assert isinstance(got, _QImage)
        assert (got.width(), got.height()) == (32, 24)
        # Same pixels as cropping the parent store at the box offset.
        for x, y in ((0, 0), (31, 0), (0, 23), (31, 23), (16, 12)):
            assert got.pixel(x, y) == full_q.pixel(x, y)
        assert pixel_source_size(view) == (32, 24)
        assert get_image_dims(view) == (32, 24)
        # Generic .size/.crop branch serves the view without shared changes.
        tiled = crop_apron_tile(view, 0, 0, 32, 24)
        assert (tiled.width(), tiled.height()) == (32, 24)
        with pytest.raises(ValueError):
            view.crop("bad")
    finally:
        store.close()


def test_clip_image_for_upload_passthroughs():
    from PySide6.QtGui import QImage

    img = Image.new("RGBA", (10, 10))
    assert clip_image_for_upload(img, None) is img
    assert clip_image_for_upload(None, (0, 0, 5, 5)) is None
    clipped = clip_image_for_upload(img, (2, 2, 8, 8))
    assert clipped.size == (6, 6)
    qimg = QImage(10, 10, QImage.Format.Format_RGBA8888)
    qclipped = clip_image_for_upload(qimg, (2, 2, 8, 8))
    assert (qclipped.width(), qclipped.height()) == (6, 6)


# -- envelope geometry ----------------------------------------------------------


def test_none_box_envelope_parity_with_today():
    widget = _letterbox_widget(width=1000, height=500)
    update_common_letterbox_geometry(
        widget,
        Image.new("RGBA", (2000, 1000)),
        Image.new("RGBA", (1000, 2000)),
    )
    assert widget.runtime_state._letterbox_params[0] == widget.runtime_state._letterbox_params[1]
    assert widget.runtime_state._letterbox_params[0] == (0.25, 0.0, 0.5, 1.0)
    assert widget.runtime_state._content_rect_px == (250, 0, 500, 500)


def test_box_clipped_envelope_uses_box_dims():
    widget = _letterbox_widget(width=1000, height=500)
    update_common_letterbox_geometry(
        widget,
        Image.new("RGBA", (2000, 1000)),
        Image.new("RGBA", (1000, 2000)),
        crop_boxes=((0, 0, 1000, 500), (0, 0, 1000, 500)),
    )
    letterbox, rect = eager_envelope_rect(1000, 500, [(1000, 500), (1000, 500)])
    assert widget.runtime_state._letterbox_params[0] == letterbox
    assert widget.runtime_state._content_rect_px == rect
    # Full-frame envelope would be the 2000x2000 square fit...
    _, full_rect = eager_envelope_rect(1000, 500, [(2000, 1000), (1000, 2000)])
    assert full_rect == (250, 0, 500, 500)
    assert rect != full_rect
    assert rect == (0, 0, 1000, 500)
    assert letterbox == (0.0, 0.0, 1.0, 1.0)


# -- upload path with real files + real CropService ------------------------------


def _bordered_png(path, size, border, content=(200, 200, 200)):
    img = Image.new("RGB", size, (0, 0, 0))
    inner = Image.new("RGB", (size[0] - 2 * border, size[1] - 2 * border), content)
    img.paste(inner, (border, border))
    img.save(str(path))
    return str(path)


def _upload_widget(update_calls, crop_service=None):
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
        _store=None,
    )
    widget = SimpleNamespace(
        runtime_state=state,
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        width=lambda: 800,
        height=lambda: 600,
        update=lambda: update_calls.append(1),
    )
    if crop_service is not None:
        widget._crop_service = crop_service
    return widget


def test_upload_clips_display_textures_and_envelope_to_box(tmp_path):
    from shared.image_processing.autocrop import CropService

    p1 = _bordered_png(tmp_path / "a.png", (120, 80), 10)
    p2 = _bordered_png(tmp_path / "b.png", (120, 80), 10)
    svc = CropService()
    box1 = svc.get(p1)
    box2 = svc.get(p2)
    assert box1 is not None and box2 is not None, "fixture needs detectable borders"
    assert (box1.width, box1.height) != (120, 80)

    disp1 = Image.open(p1).convert("RGBA")
    disp2 = Image.open(p2).convert("RGBA")
    update_calls: list = []
    widget = _upload_widget(update_calls, crop_service=svc)
    upload_pil_images(
        widget, disp1, disp2, source_key=(p1, p2), shader_letterbox=True
    )

    state = widget.runtime_state
    # Box tuples join the change signature (late box arrival re-drives upload).
    assert state._stored_image_ids[-1] == (box1.to_tuple(), box2.to_tuple())
    # Queued preloaded textures are box-clipped.
    pending = {slot: img for (_key, img, slot) in state._pending_texture_uploads}
    assert (pending[0].width(), pending[0].height()) == (box1.width, box1.height)
    assert (pending[1].width(), pending[1].height()) == (box2.width, box2.height)
    # Envelope fits the box-clipped content, not the full frame.
    letterbox, rect = eager_envelope_rect(
        800, 600, [(box1.width, box1.height), (box2.width, box2.height)]
    )
    assert state._letterbox_params[0] == letterbox
    assert state._content_rect_px == rect
    _, full_rect = eager_envelope_rect(800, 600, [(120, 80), (120, 80)])
    assert rect != full_rect


def test_upload_without_service_keeps_full_frame(tmp_path):
    p1 = _bordered_png(tmp_path / "a.png", (120, 80), 10)
    p2 = _bordered_png(tmp_path / "b.png", (120, 80), 10)
    disp1 = Image.open(p1).convert("RGBA")
    disp2 = Image.open(p2).convert("RGBA")
    update_calls: list = []
    widget = _upload_widget(update_calls, crop_service=None)
    upload_pil_images(
        widget, disp1, disp2, source_key=(p1, p2), shader_letterbox=True
    )
    state = widget.runtime_state
    pending = {slot: img for (_key, img, slot) in state._pending_texture_uploads}
    assert (pending[0].width(), pending[0].height()) == (120, 80)
    assert (pending[1].width(), pending[1].height()) == (120, 80)
    letterbox, rect = eager_envelope_rect(800, 600, [(120, 80), (120, 80)])
    assert state._letterbox_params[0] == letterbox
    assert state._content_rect_px == rect


# -- residency grid registration --------------------------------------------------


def _tps(image: Image.Image, tmp_path) -> TiledPixelStore:
    return TiledPixelStore.from_pil(image, tmp_dir=str(tmp_path))


def _residency_widget(*, stored0, stored1, update_calls):
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
        _store=None,
    )
    widget = SimpleNamespace(
        runtime_state=state,
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        width=lambda: 800,
        height=lambda: 600,
        update=lambda: update_calls.append(1),
    )
    upload_pil_images(widget, stored0, stored1, shader_letterbox=True)
    return widget


def _resources():
    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    resources.upload_whole = MagicMock()
    return resources


def test_realize_registers_box_clipped_grid(tmp_path):
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    try:
        update_calls: list = []
        widget = _residency_widget(
            stored0=store, stored1=store, update_calls=update_calls
        )
        resources = _resources()
        tile_service = TileTextureService(max_tile_extent=512)
        updates = MagicMock()
        base_image = SimpleNamespace(
            letterbox1=(0.0, 0.0, 1.0, 1.0),
            letterbox2=(0.0, 0.0, 1.0, 1.0),
            zoom=1.0,
            pan_offset_x=0.0,
            pan_offset_y=0.0,
        )
        box = CropBox(100, 100, 1100, 700)  # 1000x600 of the 1200x800 store
        resources.residency.realize_tile_plan(
            tile_service,
            widget,
            ("stored_0", "stored_1"),
            base_image,
            updates,
            crop_boxes=(box, None),
        )
        grid0 = tile_service.grid_for("stored_0")
        grid1 = tile_service.grid_for("stored_1")
        assert (grid0.total_width, grid0.total_height) == (1000, 600)
        # None-box slot keeps today's full-frame grid identically.
        assert (grid1.total_width, grid1.total_height) == (1200, 800)
    finally:
        store.close()


def test_realize_none_box_grid_parity(tmp_path):
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    try:
        update_calls: list = []
        widget = _residency_widget(
            stored0=store, stored1=store, update_calls=update_calls
        )
        resources = _resources()
        tile_service = TileTextureService(max_tile_extent=512)
        updates = MagicMock()
        base_image = SimpleNamespace(
            letterbox1=(0.0, 0.0, 1.0, 1.0),
            letterbox2=(0.0, 0.0, 1.0, 1.0),
            zoom=1.0,
            pan_offset_x=0.0,
            pan_offset_y=0.0,
        )
        resources.residency.realize_tile_plan(
            tile_service,
            widget,
            ("stored_0", "stored_1"),
            base_image,
            updates,
        )
        grid0 = tile_service.grid_for("stored_0")
        assert (grid0.total_width, grid0.total_height) == (1200, 800)
    finally:
        store.close()
