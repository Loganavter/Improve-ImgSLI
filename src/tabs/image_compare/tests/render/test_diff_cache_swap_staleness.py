"""docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up: SSIM diff must
stay visible (stale, from the previous image pair) across an image swap
instead of vanishing while the new diff computes -- covers
``request_cached_diff_image_async``'s ``cached_diff_source_key`` gating,
which is what makes that possible (render_flow.py no longer gates the
request itself on ``cached_diff_image is None``).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from tabs.image_compare.canvas.features.magnifier.workers import diff_cache
from tabs.image_compare.presenters.image_canvas.background_parts import diff_toasts
from shared.rendering.image_identity import image_uid


def _presenter(*, cached_diff_image=None, cached_diff_source_key=None):
    render_cache = SimpleNamespace(
        cached_diff_image=cached_diff_image,
        cached_diff_source_key=cached_diff_source_key,
    )
    session_data = SimpleNamespace(render_cache=render_cache)
    viewport = SimpleNamespace(session_data=session_data)
    store = SimpleNamespace(viewport=viewport)
    thread_pool = SimpleNamespace(start=MagicMock())
    main_window_app = SimpleNamespace(thread_pool=thread_pool)
    return SimpleNamespace(
        store=store,
        main_window_app=main_window_app,
        schedule_update=MagicMock(),
    )


def _stub_toasts(monkeypatch):
    for name in (
        "show_or_reuse_diff_toast",
        "complete_diff_toast",
        "dismiss_active_diff_toast",
        "update_diff_toast_progress",
    ):
        monkeypatch.setattr(diff_toasts, name, MagicMock())


def test_request_skipped_when_already_served_for_this_source_pair(monkeypatch):
    """The stale-diff-stays-visible behavior only works if a request for a
    pair that's already been served doesn't fire again every frame -- this
    is the guard that keeps render_flow.py's now-unconditional per-frame
    call cheap and non-recomputing."""
    _stub_toasts(monkeypatch)
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))
    served_key = ("ssim", image_uid(img1), image_uid(img2), img1.size, img2.size)
    presenter = _presenter(
        cached_diff_image=object(), cached_diff_source_key=served_key
    )

    diff_cache.request_cached_diff_image_async(presenter, img1, img2, "ssim")

    presenter.main_window_app.thread_pool.start.assert_not_called()


def test_request_fires_and_updates_served_key_for_a_new_source_pair(monkeypatch):
    """A genuinely new source pair (e.g. after a swap) must still trigger a
    fresh computation despite cached_diff_image already holding the
    *previous* pair's stale diff -- staleness is decided by
    cached_diff_source_key, not by cached_diff_image being None."""
    _stub_toasts(monkeypatch)
    old_diff = object()
    presenter = _presenter(
        cached_diff_image=old_diff,
        cached_diff_source_key=("ssim", 111, 222, (1, 1), (1, 1)),
    )
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))
    new_diff = object()
    monkeypatch.setattr(diff_cache, "build_cached_diff_image_task", lambda *a, **k: new_diff)

    def fake_start(worker, priority=0):
        worker.run()

    presenter.main_window_app.thread_pool.start = fake_start

    diff_cache.request_cached_diff_image_async(presenter, img1, img2, "ssim")

    render_cache = presenter.store.viewport.session_data.render_cache
    assert render_cache.cached_diff_image is new_diff
    assert render_cache.cached_diff_source_key == (
        "ssim",
        image_uid(img1),
        image_uid(img2),
        img1.size,
        img2.size,
    )


def test_request_does_not_clear_stale_diff_while_pending(monkeypatch):
    """While the new pair's diff is still computing, the previous pair's
    diff must remain in cached_diff_image (nothing here clears it) -- this
    is what keeps the canvas showing the old diff instead of a blank/plain
    image in the interim."""
    _stub_toasts(monkeypatch)
    old_diff = object()
    presenter = _presenter(
        cached_diff_image=old_diff,
        cached_diff_source_key=("ssim", 111, 222, (1, 1), (1, 1)),
    )
    img1 = Image.new("RGB", (10, 10))
    img2 = Image.new("RGB", (10, 10))

    # Worker submitted but never run (simulates "still computing").
    presenter.main_window_app.thread_pool.start = MagicMock()

    diff_cache.request_cached_diff_image_async(presenter, img1, img2, "ssim")

    render_cache = presenter.store.viewport.session_data.render_cache
    assert render_cache.cached_diff_image is old_diff
    assert render_cache.cached_diff_source_key == ("ssim", 111, 222, (1, 1), (1, 1))