"""Parametric-crop export: bake effective box at composition (lane mc-crop-export).

Same path in two slots with override on/off must export different pixels
matching live sampling (full-store crop region); override-None uncropped
slots keep the cached object itself (byte-identical to pre-change).
"""

from types import SimpleNamespace

import numpy as np
from PIL import Image

from engine.store.tiled_pixel_store import TiledPixelStore, pixel_source_size
from tabs.multi_compare.models import CompareSlot
from tabs.multi_compare.pipeline.cache import MultiComparePixelCache
from tabs.multi_compare.use_cases.crop import effective_crop_box
from tabs.multi_compare.use_cases.export import _cropped_export_source, _export_sources


def _half_red_half_blue(w=20, h=20):
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, : w // 2] = (255, 0, 0, 255)
    arr[:, w // 2 :] = (0, 0, 255, 255)
    arr[:, :, 3] = 255
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))


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


def _controller(cache, slots, *, service, setting=True):
    ctrl = SimpleNamespace(
        pixel_cache=cache,
        widget=SimpleNamespace(state=SimpleNamespace(slots=list(slots))),
        _crop_service=service,
        store=SimpleNamespace(
            settings=SimpleNamespace(auto_crop_black_borders=setting)
        ),
    )
    ctrl._get_crop_service = lambda: service if setting else None
    return ctrl


def test_same_path_override_on_off_exports_different_pixels_matching_live():
    path = "crop-export-same-path.png"
    full = _half_red_half_blue()
    try:
        cache = MultiComparePixelCache()
        cache.put_pixel(path, full)
        box = (0, 0, 10, 20)  # left red half
        service = _Service(_Box(box))
        slots = [
            CompareSlot(id=1, path=path, crop_override=False),
            CompareSlot(id=2, path=path, crop_override=True),
        ]
        ctrl = _controller(cache, slots, service=service)

        # No decode beyond the cache hit: demand fill must not fire.
        def _no_decode(_path, *, crop_service=None):
            raise AssertionError("export must not decode beyond cache hit")

        cache.get_or_load_pixel = _no_decode  # type: ignore[method-assign]

        sources = _export_sources(ctrl)
        assert set(sources) == {1, 2}
        # Uncropped slot keeps the cached object itself.
        assert sources[1] is full
        assert pixel_source_size(sources[1]) == (20, 20)
        # Cropped slot: left-half pixels only.
        assert pixel_source_size(sources[2]) == (10, 20)
        # Live-sampling parity: cropped export == full store's crop region.
        live = np.asarray(full.read_array(box))
        exported = np.asarray(sources[2].read_array((0, 0, 10, 20)))
        assert np.array_equal(exported, live)
        # Different pixels: full has blue on the right, cropped is all red.
        assert tuple(np.asarray(full.read_array((0, 0, 20, 20)))[10, 15]) == (
            0, 0, 255, 255,
        )
        assert tuple(exported[10, 5]) == (255, 0, 0, 255)
    finally:
        full.close()
        for _s in list(locals().get("sources", {}).values()):
            if _s is not full:
                try:
                    _s.close()
                except Exception:
                    pass


def test_uncropped_export_byte_identical_for_override_none():
    path = "crop-export-uncropped.png"
    full = _half_red_half_blue()
    try:
        cache = MultiComparePixelCache()
        cache.put_pixel(path, full)
        service = _Service(_Box((0, 0, 10, 20)))
        slots = [CompareSlot(id=1, path=path, crop_override=None)]
        # Global setting off -> effective box None -> pre-change behavior.
        ctrl = _controller(cache, slots, service=service, setting=False)
        assert effective_crop_box(ctrl, slots[0]) is None
        sources = _export_sources(ctrl)
        assert sources[1] is full
        assert np.array_equal(
            np.asarray(sources[1].read_array((0, 0, 20, 20))),
            np.asarray(full.read_array((0, 0, 20, 20))),
        )
    finally:
        full.close()


def test_empty_intersection_skips_slot():
    path = "crop-export-empty.png"
    full = _half_red_half_blue()
    try:
        cache = MultiComparePixelCache()
        cache.put_pixel(path, full)
        # Box entirely outside the 20x20 frame -> empty intersection -> gap.
        service = _Service(_Box((100, 100, 120, 120)))
        slots = [CompareSlot(id=1, path=path, crop_override=True)]
        ctrl = _controller(cache, slots, service=service)
        assert _cropped_export_source(full, (100, 100, 120, 120)) is None
        assert _export_sources(ctrl) == {}
    finally:
        full.close()
