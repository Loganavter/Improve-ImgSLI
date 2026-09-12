"""Session crop default must follow the auto_crop_black_borders setting.

Regression: with the setting OFF, `_get_crop_service()` returns None, but
`PipelineCache`/`ImagePipeline` resurrected the session default via
`else self.crop_service` — the preview tier loaded CROPPED pixels while every
`[autocrop-debug]` verdict honestly said SKIP. `ImageSession.crop_service`
is always created live; `sync_crop_service()` / `set_sessions_crop_enabled()`
null it (and the cache default) when disabled.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from tabs.image_compare.pipeline.session import (
    ImageSession,
    set_sessions_crop_enabled,
)


def _bordered_png(path):
    canvas = Image.new("RGBA", (200, 160), (0, 0, 0, 255))
    canvas.paste(Image.new("RGBA", (120, 80), (200, 180, 160, 255)), (40, 40))
    canvas.save(path)
    return str(path)


def test_sync_off_nulls_session_and_cache_defaults():
    sess = ImageSession(session_id="sync-probe")
    try:
        assert sess.crop_service is not None
        assert sess.cache.crop_service is not None

        set_sessions_crop_enabled(False)
        assert sess.crop_service is None
        assert sess.cache.crop_service is None
    finally:
        set_sessions_crop_enabled(True)

    assert sess.crop_service is not None
    assert sess.cache.crop_service is not None


def test_preview_tier_disabled_setting_serves_uncropped(tmp_path):
    """The user's exact bug: OFF must not crop the preview tier."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="preview-off")
    try:
        set_sessions_crop_enabled(False)
        # Bare call (no explicit service) — previously resurrected the live
        # session default and returned a 120x80 crop.
        qimg = sess.cache.get_or_load_preview(path)
        assert qimg is not None
        assert (qimg.width(), qimg.height()) == (200, 160)
    finally:
        set_sessions_crop_enabled(True)


def test_preview_tier_enabled_setting_still_crops(tmp_path):
    """ON behavior unchanged: session default crops bordered previews."""
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="preview-on")
    try:
        set_sessions_crop_enabled(True)
        qimg = sess.cache.get_or_load_preview(path)
        assert qimg is not None
        assert qimg.width() < 200 and qimg.height() < 160
        assert qimg.width() >= 100 and qimg.height() >= 60
    finally:
        set_sessions_crop_enabled(True)


def test_store_toggle_syncs_sessions_via_scoped_change():
    """Тоггл настройки долетает до сессий без импорта таба хостом.

    application_service лишь диспатчит SetAutoCropBlackBordersAction;
    _on_store_scoped_change замечает смену флага и зовёт
    set_sessions_crop_enabled (tab-internal, sandbox-контракт цел).
    """
    from types import SimpleNamespace

    from tabs.image_compare._session_controller import SessionController

    sess = ImageSession(session_id="toggle-probe")
    assert sess.crop_service is not None
    fake = SimpleNamespace(
        store=SimpleNamespace(
            settings=SimpleNamespace(auto_crop_black_borders=False)
        ),
        _last_crop_enabled=None,
    )
    try:
        SessionController._on_store_scoped_change(fake, "viewport")
        assert sess.crop_service is None
        assert sess.cache.crop_service is None
        fake.store.settings.auto_crop_black_borders = True
        SessionController._on_store_scoped_change(fake, "viewport")
        assert sess.crop_service is not None
        assert sess.cache.crop_service is not None
    finally:
        set_sessions_crop_enabled(True)


def test_pixel_tier_disabled_setting_serves_uncropped(tmp_path):
    path = _bordered_png(tmp_path / "bordered.png")
    sess = ImageSession(session_id="pixel-off")
    try:
        set_sessions_crop_enabled(False)
        store = sess.cache.get_or_load(path)
        try:
            assert store.size == (200, 160)
        finally:
            store.close()
    finally:
        set_sessions_crop_enabled(True)
