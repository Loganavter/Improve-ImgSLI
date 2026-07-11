"""Display-cache rebuilds must not multiply expensive resize workers."""

from types import SimpleNamespace

from PIL import Image

from tabs.image_compare.presenters.image_canvas.background_parts.image_cache import (
    create_preview_cache_async,
    on_preview_cache_ready,
)


class _ThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker, priority=0):
        self.started.append((worker, priority))


def _presenter(img1, img2, limit):
    render_cache = SimpleNamespace(
        display_cache_image1=None,
        display_cache_image2=None,
        last_display_cache_params=None,
        scaled_image1_for_display=object(),
        scaled_image2_for_display=object(),
        cached_scaled_image_dims=(1, 1),
    )
    presenter = SimpleNamespace(
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                render_config=SimpleNamespace(display_resolution_limit=limit),
                session_data=SimpleNamespace(
                    image_state=SimpleNamespace(image1=img1, image2=img2),
                    render_cache=render_cache,
                ),
            )
        ),
        main_window_app=SimpleNamespace(thread_pool=_ThreadPool()),
        _display_cache_request_key=None,
        schedule_update=lambda: None,
    )
    presenter.background = SimpleNamespace(
        on_preview_cache_ready=lambda result: on_preview_cache_ready(
            presenter, result
        )
    )
    return presenter


def test_original_resolution_reuses_unified_images_without_worker_or_copy():
    img1 = Image.new("RGBA", (400, 300), "red")
    img2 = Image.new("RGBA", (400, 300), "blue")
    presenter = _presenter(img1, img2, limit=0)

    assert create_preview_cache_async(presenter, img1, img2) is True

    cache = presenter.store.viewport.session_data.render_cache
    assert presenter.main_window_app.thread_pool.started == []
    assert cache.display_cache_image1 is img1
    assert cache.display_cache_image2 is img2
    assert cache.scaled_image1_for_display is None
    assert cache.scaled_image2_for_display is None


def test_repeated_frames_start_only_one_resize_for_the_same_cache_key():
    img1 = Image.new("RGBA", (400, 300), "red")
    img2 = Image.new("RGBA", (400, 300), "blue")
    presenter = _presenter(img1, img2, limit=100)

    assert create_preview_cache_async(presenter, img1, img2) is False
    assert create_preview_cache_async(presenter, img1, img2) is False

    assert len(presenter.main_window_app.thread_pool.started) == 1


def test_stale_resize_result_cannot_replace_new_original_resolution_cache():
    img1 = Image.new("RGBA", (400, 300), "red")
    img2 = Image.new("RGBA", (400, 300), "blue")
    presenter = _presenter(img1, img2, limit=100)

    create_preview_cache_async(presenter, img1, img2)
    worker, _priority = presenter.main_window_app.thread_pool.started[0]
    stale_result = worker.fn(*worker.args, **worker.kwargs)

    presenter.store.viewport.render_config.display_resolution_limit = 0
    assert create_preview_cache_async(presenter, img1, img2) is True
    on_preview_cache_ready(presenter, stale_result)

    cache = presenter.store.viewport.session_data.render_cache
    assert cache.display_cache_image1 is img1
    assert cache.display_cache_image2 is img2
