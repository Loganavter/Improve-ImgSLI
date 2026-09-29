"""MC parametric-crop render clip (lane mc-crop-render).

Distinct-content harness (color-per-index images, NEVER counts-only):
the same full-frame store in two slots with different crop overrides must
sample different pixels; zoom/LOD stays sane on cropped slots; an empty
crop intersection yields gap (``None``), never neighbor bytes.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from engine.store.crop_window import crop_view_size, intersect_box
from engine.store.tiled_pixel_store import (
    TiledPixelStore,
    pixel_source_size,
    qimage_from_pixel_source,
)
from tabs.multi_compare.models import CompareSlot
from tabs.multi_compare.scene.passes import residency as _residency
from tabs.multi_compare.scene.passes.residency import (
    CroppedSlotView,
    controller_for_canvas,
    crop_box_for_slot,
    cropped_source_for_slot,
    lod_key_and_source,
)

_W, _H = 64, 32
_RED = (255, 0, 0, 255)
_BLUE = (0, 0, 255, 255)


class _Box:
    def __init__(self, tup):
        self._tup = tup

    def to_tuple(self):
        return self._tup


class _Service:
    def __init__(self, box):
        self._box = box

    def get(self, path):
        return self._box


def _controller(*, service=None, setting=True):
    ctrl = SimpleNamespace(
        _crop_service=service,
        store=SimpleNamespace(
            settings=SimpleNamespace(auto_crop_black_borders=setting)
        ),
    )
    ctrl._get_crop_service = lambda: service if setting else None
    return ctrl


def _half_red_half_blue() -> TiledPixelStore:
    img = Image.new("RGBA", (_W, _H), _RED)
    img.paste(Image.new("RGBA", (_W // 2, _H), _BLUE), (_W // 2, 0))
    return TiledPixelStore.from_pil(img)


def _left_half_box():
    return _Service(_Box((0, 0, _W // 2, _H)))


def _qcolor_name(qimg, x, y) -> str:
    c = qimg.pixelColor(int(x), int(y))
    if c.red() > 200 and c.blue() < 100:
        return "red"
    if c.blue() > 200 and c.red() < 100:
        return "blue"
    return f"other({c.red()},{c.green()},{c.blue()})"


def test_same_path_different_overrides_sample_different_pixels():
    store = _half_red_half_blue()
    ctrl = _controller(service=_left_half_box())
    slot_on = CompareSlot(id=1, path="same.png", crop_override=True)
    slot_off = CompareSlot(id=2, path="same.png", crop_override=False)

    cropped = cropped_source_for_slot(store, ctrl, slot_on, cache={})
    full = cropped_source_for_slot(store, ctrl, slot_off, cache={})

    assert isinstance(cropped, CroppedSlotView)
    assert full is store
    assert pixel_source_size(cropped) == (_W // 2, _H)

    # Cropped slot's own center pixel comes from the red (left) half...
    view_img = cropped.crop((0, 0, _W // 2, _H))
    assert _qcolor_name(view_img, 4, 4) == "red"
    assert _qcolor_name(view_img, _W // 2 - 4, _H - 4) == "red"
    # ...while the uncropped same-path slot still samples blue on the right.
    full_px = qimage_from_pixel_source(store, (_W - 4, 4, _W - 3, 5))
    assert _qcolor_name(full_px, 0, 0) == "blue"


def test_view_translates_box_local_reads_to_parent_coords():
    store = _half_red_half_blue()
    view = CroppedSlotView(store, (0, 0, _W // 2, _H))
    assert view.size == (_W // 2, _H)
    assert (view.width, view.height) == (_W // 2, _H)
    # View-local right edge maps to parent x=31 (red), not x=32+ (blue).
    edge = view.crop((_W // 2 - 2, 0, _W // 2, _H))
    assert _qcolor_name(edge, 0, 0) == "red"
    assert _qcolor_name(edge, 1, _H - 1) == "red"


def test_apron_overhang_clamps_to_crop_never_neighbor_bytes():
    store = _half_red_half_blue()
    view = CroppedSlotView(store, (0, 0, _W // 2, _H))
    # Tile-upload apron math asks beyond the view bounds; the view must
    # clamp to the crop window instead of bleeding blue pixels in.
    over = view.crop((-8, -8, _W // 2 + 8, _H + 8))
    assert (over.width(), over.height()) == (_W // 2, _H)
    for x, y in ((0, 0), (_W // 2 - 1, 0), (0, _H - 1), (_W // 2 - 1, _H - 1)):
        assert _qcolor_name(over, x, y) == "red"


def test_empty_intersection_yields_gap_none():
    store = _half_red_half_blue()
    ctrl = _controller(service=_Service(_Box((100, 100, 120, 120))))
    slot = CompareSlot(id=1, path="same.png", crop_override=True)
    assert intersect_box((0, 0, _W, _H), (100, 100, 120, 120)) is None
    assert crop_view_size((_W, _H), (100, 100, 120, 120)) == (0, 0)
    assert cropped_source_for_slot(store, ctrl, slot, cache={}) is None


def test_full_covering_box_keeps_real_source_identity():
    store = _half_red_half_blue()
    ctrl = _controller(service=_Service(_Box((0, 0, _W, _H))))
    slot = CompareSlot(id=1, path="same.png", crop_override=True)
    assert cropped_source_for_slot(store, ctrl, slot, cache={}) is store


def test_lod_scale_sane_on_cropped_slot():
    store = _half_red_half_blue()
    view = CroppedSlotView(store, (0, 0, _W // 2, _H))
    layer = SimpleNamespace(
        rect_fb=(0.0, 0.0, 32.0, 32.0), fit_x=1.0, fit_y=1.0, zoom=1.0
    )
    slot_lod_keys: dict = {}
    key, source = lod_key_and_source(7, view, layer, slot_lod_keys)
    # No pyramid is registered for a translating view: native resolution,
    # cropped size -- zoom/LOD scale computed against the cropped extent.
    assert key == 7
    assert source is view
    assert pixel_source_size(source) == (_W // 2, _H)
    assert slot_lod_keys == {}


def test_view_identity_stable_across_frames_then_toggles():
    store = _half_red_half_blue()
    ctrl = _controller(service=_left_half_box())
    slot = CompareSlot(id=1, path="same.png", crop_override=True)
    cache: dict = {}
    first = cropped_source_for_slot(store, ctrl, slot, cache=cache)
    second = cropped_source_for_slot(store, ctrl, slot, cache=cache)
    assert first is second  # swap duplicate-detection stays quiet
    slot_off = CompareSlot(id=1, path="same.png", crop_override=False)
    assert cropped_source_for_slot(store, ctrl, slot_off, cache=cache) is store


def test_tobytes_pil_emulation_for_swap_path():
    store = _half_red_half_blue()
    view = CroppedSlotView(store, (0, 0, _W // 2, _H))
    raw = view.tobytes()
    assert len(raw) == (_W // 2) * _H * 4
    assert tuple(raw[0:4]) == _RED


def test_crop_box_helpers_and_controller_walk():
    ctrl = _controller(service=_left_half_box())
    slot = CompareSlot(id=1, path="same.png", crop_override=True)
    assert crop_box_for_slot(ctrl, slot) == (0, 0, _W // 2, _H)
    assert crop_box_for_slot(ctrl, None) is None
    assert crop_box_for_slot(None, slot) is None
    assert crop_box_for_slot(object(), object()) is None

    assert controller_for_canvas(SimpleNamespace(_controller=ctrl)) is ctrl
    assert controller_for_canvas(object()) is None

    inner = SimpleNamespace(_controller=None, parentWidget=lambda: None)
    outer = SimpleNamespace(_controller=ctrl, parentWidget=lambda: None)
    canvas = SimpleNamespace(
        _controller=None, parentWidget=lambda: inner
    )
    inner.parentWidget = lambda: outer
    assert controller_for_canvas(canvas) is ctrl
