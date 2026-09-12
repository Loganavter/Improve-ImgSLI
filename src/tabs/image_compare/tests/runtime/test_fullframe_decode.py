"""W1+W2 regression: image_compare decode yields FULL-FRAME stores.

On an autocropped fixture (bordered image where ``CropService`` detects a
box) proves:

1. pixel + preview tiers serve full-frame even with the session detection
   service attached and enabled (no-bake);
2. the detected box stays available as side metadata via
   ``effective_crop_box_for_path`` (enabled → box, disabled/``None`` →
   ``None``, per-image ``override=False`` → ``None`` without detection);
3. cache keys are boxless (today's crop-disabled shape) no matter what crop
   args a caller passes; legacy ``True``-keyed entries miss, never collide;
4. single-flight keys agree across ``None`` / live-service callers.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from tabs.image_compare.pipeline.cache import (
    PipelineCache,
    _pixel_key,
    _preview_key,
)
from tabs.image_compare.pipeline.crop_box import effective_crop_box_for_path
from tabs.image_compare.pipeline.image_load_service import (
    ImageLoadService,
    _key_for_path,
)
from tabs.image_compare.pipeline.session import ImageSession


def _bordered_png(path):
    canvas = Image.new("RGBA", (200, 160), (0, 0, 0, 255))
    canvas.paste(Image.new("RGBA", (120, 80), (200, 180, 160, 255)), (40, 40))
    canvas.save(path)
    return str(path)


def test_pixel_tier_enabled_setting_serves_fullframe(tmp_path):
    """Pixel decode with a live detection service stays full-frame."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-pixel")
    assert sess.crop_service is not None  # detection attached
    store = sess.cache.get_or_load(path)
    try:
        assert store.size == (200, 160)
    finally:
        store.close()


def test_preview_tier_enabled_setting_serves_fullframe(tmp_path):
    """Preview decode with a live detection service stays full-frame."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-preview")
    assert sess.crop_service is not None
    qimg = sess.cache.get_or_load_preview(path)
    assert qimg is not None
    assert (qimg.width(), qimg.height()) == (200, 160)


def test_box_available_as_side_metadata(tmp_path):
    """Detection works while pixels stay full-frame."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-box")
    box = effective_crop_box_for_path(path, crop_service=sess.crop_service)
    assert box is not None
    assert box.width < 200 and box.height < 160
    assert box.width >= 100 and box.height >= 60
    # full-frame store alongside the box
    store = sess.cache.get_or_load(path)
    try:
        assert store.size == (200, 160)
    finally:
        store.close()


def test_box_helper_none_cases(tmp_path):
    """Disabled service → None; Off override → None; bad path → None."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-box-none")
    assert effective_crop_box_for_path(path, crop_service=None) is None
    assert effective_crop_box_for_path(path) is None
    assert effective_crop_box_for_path(path, crop_service=False) is None
    # per-image Off skips detection (no box, pixels stay full-frame anyway)
    assert (
        effective_crop_box_for_path(
            path, crop_service=sess.crop_service, override=False
        )
        is None
    )
    assert (
        effective_crop_box_for_path(
            str(tmp_path / "missing.png"), crop_service=sess.crop_service
        )
        is None
    )


def test_keys_boxless_shape(tmp_path):
    """Keys ignore crop args — always today's crop-disabled shape."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-keys")
    assert sess.crop_service is not None
    assert _pixel_key(path, sess.crop_service, None) == _pixel_key(path, None, None)
    assert _pixel_key(path, True) == _pixel_key(path, None, None)
    assert _pixel_key(path, None, None)[3] is False
    assert _preview_key(path, sess.crop_service, None) == _preview_key(path, None, None)
    assert _preview_key(path, None, None)[3] is False
    assert _preview_key(path, None, None)[4] == 1024
    assert _key_for_path(path, sess.crop_service) == _key_for_path(path, None)
    assert _key_for_path(path, None)[3] is False


def test_live_service_reads_hit_boxless_entries(tmp_path):
    """Reads passing a live service hit entries written boxless (no dupes)."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-hit")
    store = sess.cache.get_or_load(path)
    try:
        assert sess.cache.pixel_size == 1
        assert sess.cache.get_pixel(path, sess.crop_service) is store
        assert sess.cache.get_pixel(path, None) is store
        assert sess.cache.get_pixel(path, True) is store
    finally:
        store.close()


def test_legacy_true_keyed_entries_miss_never_collide(tmp_path):
    """A stale box-keyed (True) entry is invisible to boxless lookups."""
    path = _bordered_png(tmp_path / "bordered.png")
    cache = PipelineCache()
    store = cache.get_or_load(path)
    try:
        boxless = _pixel_key(path, None, None)
        assert boxless in cache._pixel
        st = os.stat(path)
        legacy = (os.path.normpath(path), st.st_mtime_ns, st.st_size, True)
        assert legacy != boxless
        sentinel = object()
        cache._pixel[legacy] = sentinel
        try:
            assert cache.get_pixel(path, None) is store
            assert cache.get_pixel(path, sentinel) is store
        finally:
            cache._pixel.pop(legacy, None)
    finally:
        store.close()


def test_singleflight_keys_agree(tmp_path):
    """Single-flight dedup converges for None and live-service callers."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="fullframe-flight")
    svc = ImageLoadService(
        cache=sess.cache,
        get_crop_service=lambda: sess.crop_service,
    )
    assert svc.key_for(path, None) == svc.key_for(path, sess.crop_service)
    assert svc.key_for(path, None)[3] is False
    assert not svc.is_loading(path, None)
    assert not svc.is_loading(path, sess.crop_service)
