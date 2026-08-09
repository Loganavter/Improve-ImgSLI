"""docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up, fifth fix:
``invalidate_render_state`` (called on every image swap via
``loading.py``'s ``_invalidate_image_canvas_render_state``) used to
unconditionally clear the GPU-side diff texture reference
(``upload_diff_source_pil_image(None)``), independent of diff_mode and of
the ``cached_diff_source_key`` staleness mechanism -- defeating the point
of keeping the previous pair's diff visible until the new one is ready.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tabs.image_compare.presenters.image_canvas.lifecycle import (
    invalidate_render_state,
)


def _presenter():
    image_label = SimpleNamespace(upload_diff_source_pil_image=MagicMock())
    widget = SimpleNamespace(image_label=image_label)
    return SimpleNamespace(
        widget=widget,
        main_window_app=SimpleNamespace(toast_manager=None),
        _last_bg_signature="x",
        _last_mag_signature="x",
        _last_img_sig="x",
        _cached_base_pixmap=object(),
        current_displayed_pixmap=object(),
        _pending_interactive_mode=True,
        _pending_cached_diff_request_key=("ssim", 1, 2, (1, 1), (1, 1)),
        _active_diff_toast_key="x",
        _active_diff_toast_id=None,
    ), image_label


def test_invalidate_render_state_does_not_touch_diff_texture():
    presenter, image_label = _presenter()

    invalidate_render_state(presenter)

    image_label.upload_diff_source_pil_image.assert_not_called()


def test_invalidate_render_state_still_resets_signature_caches():
    presenter, _ = _presenter()

    invalidate_render_state(presenter)

    assert presenter._last_bg_signature is None
    assert presenter._last_mag_signature is None
    assert presenter._last_img_sig is None
    assert presenter._cached_base_pixmap is None
    assert presenter.current_displayed_pixmap is None
