"""Session crop default must follow the auto_crop_black_borders setting.

Ported from public #31 (non-destructive crop phase 1, W1+W2) onto
private/main: the public global toggle ``set_sessions_crop_enabled`` /
``sync_crop_service`` session registry never existed on private — OFF is
expressed at the controller level (``_get_crop_service()`` returns ``None``
while the setting is OFF). Decode tiers therefore serve FULL-FRAME
unconditionally here; the port keeps the no-bake + box-metadata assertions
and drops the global-toggle machinery tests.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from tabs.image_compare.pipeline.session import ImageSession


def _bordered_png(path):
    canvas = Image.new("RGBA", (200, 160), (0, 0, 0, 255))
    canvas.paste(Image.new("RGBA", (120, 80), (200, 180, 160, 255)), (40, 40))
    canvas.save(path)
    return str(path)


def test_preview_tier_disabled_setting_serves_uncropped(tmp_path):
    """OFF must not crop the preview tier (no-bake: always full-frame)."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="preview-off")
    # Bare call (no explicit service) — previously resurrected the live
    # session default and returned a 120x80 crop.
    qimg = sess.cache.get_or_load_preview(path)
    assert qimg is not None
    assert (qimg.width(), qimg.height()) == (200, 160)


def test_preview_tier_enabled_setting_serves_fullframe_with_box_metadata(tmp_path):
    """W1+W2 non-destructive crop: ON serves FULL-FRAME; box is side metadata.

    Replaces the old bake expectation (ON cropped bordered previews):
    decode tiers never bake crop anymore. Detection still works — the box
    is queryable via ``effective_crop_box_for_path`` while the pixels stay
    full-frame.
    """
    from tabs.image_compare.pipeline.crop_box import effective_crop_box_for_path

    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="preview-on")
    assert sess.crop_service is not None
    qimg = sess.cache.get_or_load_preview(path)
    assert qimg is not None
    assert (qimg.width(), qimg.height()) == (200, 160)
    box = effective_crop_box_for_path(path, crop_service=sess.crop_service)
    assert box is not None
    assert box.width < 200 and box.height < 160
    assert box.width >= 100 and box.height >= 60


def test_pixel_tier_disabled_setting_serves_uncropped(tmp_path):
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="pixel-off")
    store = sess.cache.get_or_load(path)
    try:
        assert store.size == (200, 160)
    finally:
        store.close()
