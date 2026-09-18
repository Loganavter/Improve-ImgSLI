"""Timeline thumbnails: dynamic width preserved, initial/fallback waves use
capped priority indices, and the coordinator prefers visible timeline indices.

P1 proxy-source structure contracts (no timing asserts — CI/flake
discipline): the 160x90 request resolves pyramid-coarse / cached-base
sources without decoding, falls back to the full-res path on miss, and
cover output lands exactly on 160x90.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md (video timeline thumbnails).
"""

from __future__ import annotations
from types import SimpleNamespace

from PIL import Image


_THUMB = (160, 90)


def _proxy_service(*, repo_cache, renderer):
    """Bare VideoExporterService with fakes — no GPU/tab context needed."""
    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    service = VideoExporterService.__new__(VideoExporterService)
    service._image_repository = SimpleNamespace(_images_cache=dict(repo_cache))
    service._thumbnail_frame_renderer = renderer
    service._thumbnail_proxy_resolver = None
    service._last_thumbnail_source = None
    service._thumbnail_callback_bridge = None
    service._last_render_backend = "gpu"
    return service


def _proxy_base(width=5760, height=3240):
    return SimpleNamespace(width=width, height=height, is_open=True)


def _proxy_pyramid(*, proxy, picked=2, depth=3):
    return SimpleNamespace(
        level_count=depth,
        best_level_for_scale=lambda _scale: picked,
        level=lambda k: proxy if k == picked else (_ for _ in ()).throw(AssertionError(k)),
    )

def test_renderer_thumbnail_cover_crops_to_fixed_size():
    """Cover (not fit): any opaque render lands exactly on thumbnail_size.
    Contract changed with the transparent-margin trim (0eb33996): the old
    fit-height dynamic-width form (320x90) is gone — strip blocks are
    uniform 160x90, cover-scaled + center-cropped."""
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        _render_thumbnail_using_renderer,
    )

    def fake_renderer(_snap, _target_w, _target_h, *, auto_crop=False):
        assert auto_crop is False
        return Image.new("RGBA", (640, 180), (255, 0, 0, 255))

    result = _render_thumbnail_using_renderer(
        snap=object(),
        thumbnail_size=(160, 90),
        auto_crop=False,
        render_scale=1.0,
        render_snapshot=fake_renderer,
    )

    assert result is not None
    assert result.size == (160, 90)

def test_finish_trims_transparent_margins_before_cover():
    """Snapshot-plan letterbox pads (transparent) must not survive into the
    strip pixmap: painted over the light strip background they read as gaps
    between blocks. Full-bleed renders pass through untouched."""
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        _finish_thumbnail_image,
    )

    # 160x90 with transparent side margins (as dumped live: opaque content
    # only in cols 20..138) → trimmed, then cover-scaled to exactly 160x90.
    img = Image.new("RGBA", (160, 90), (0, 0, 0, 0))
    px = img.load()
    for y in range(90):
        for x in range(20, 139):
            px[x, y] = (170, 143, 107, 255)
    result = _finish_thumbnail_image(img, (160, 90))
    assert result is not None
    assert result.size == (160, 90)
    alpha = result.getdata(3)
    assert min(alpha) > 0, "no transparent margins may survive"

    # Full-bleed opaque render: byte-identical passthrough (no-op).
    full = Image.new("RGBA", (160, 90), (170, 143, 107, 255))
    assert _finish_thumbnail_image(full, (160, 90)).tobytes() == full.tobytes()

    # Fully transparent render: nothing to show.
    assert _finish_thumbnail_image(Image.new("RGBA", (160, 90), (0, 0, 0, 0)), (160, 90)) is None

def test_thumbnail_service_initial_wave_uses_priority_indices_only(monkeypatch):
    from tabs.image_compare.plugins.video_editor.services.thumbnails import ThumbnailService

    class FakeRecording:
        def evaluate_at(self, _timestamp: float):
            return object()

        def get_duration(self) -> float:
            return 10.0

    service = ThumbnailService()
    queued_indices: list[int] = []
    monkeypatch.setattr(
        service,
        "_queue_thumbnail_worker",
        lambda index, *, priority, track_finish: queued_indices.append(index),
    )

    task_id = service.generate_thumbnails(
        FakeRecording(),
        target_count=50,
        priority_indices=[8, 16, 16, 32],
        fps=60,
    )

    assert task_id > 0
    assert queued_indices == [8, 16, 32]

def test_thumbnail_service_fallback_wave_is_capped(monkeypatch):
    from tabs.image_compare.plugins.video_editor.services.thumbnails import ThumbnailService

    class FakeRecording:
        def evaluate_at(self, _timestamp: float):
            return object()

        def get_duration(self) -> float:
            return 20.0

    service = ThumbnailService()
    queued_indices: list[int] = []
    monkeypatch.setattr(
        service,
        "_queue_thumbnail_worker",
        lambda index, *, priority, track_finish: queued_indices.append(index),
    )

    service.generate_thumbnails(
        FakeRecording(),
        target_count=200,
        priority_indices=[],
        fps=60,
    )

    assert 1 <= len(queued_indices) <= 12

def test_thumbnail_coordinator_prefers_timeline_viewport_indices():
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import ThumbnailCoordinator

    timeline = SimpleNamespace(
        get_visible_thumbnail_frame_indices=lambda overscan_blocks=0: [12, 24, 36],
    )
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_current_recording=lambda: object(),
            get_fps=lambda: 60,
            get_frame_count=lambda: 100,
        ),
        playback_engine=SimpleNamespace(get_current_frame=lambda: 50),
        thumbnail_service=SimpleNamespace(),
        emit_thumbnails_updated=lambda _thumbnails: None,
    )

    assert coordinator.get_visible_frame_indices() == [12, 24, 36]


def test_timeline_resize_debounces_thumbnail_generation(monkeypatch):
    """Window/timeline resize must not queue GPU thumbnails on every pixel."""
    from PySide6.QtCore import QObject

    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    generate_calls: list[list[int]] = []
    thumbnail_service = SimpleNamespace(
        generate_additional_thumbnails=lambda indices, fps=None: generate_calls.append(
            list(indices)
        ),
    )
    timeline = SimpleNamespace(
        get_visible_thumbnail_frame_indices=lambda overscan_blocks=0: [4, 8, 12],
    )
    timer_parent = QObject()
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_fps=lambda: 60,
            get_frame_count=lambda: 100,
        ),
        playback_engine=SimpleNamespace(),
        thumbnail_service=thumbnail_service,
        emit_thumbnails_updated=lambda _thumbnails: None,
        timer_parent=timer_parent,
    )
    coordinator._test_timer_parent = timer_parent
    pings: list[int] = []
    monkeypatch.setattr(
        coordinator._visible_refresh,
        "ping",
        lambda: pings.append(1),
    )

    coordinator.on_timeline_resized()
    coordinator.on_timeline_viewport_changed()
    coordinator.on_timeline_resized()

    assert pings == [1, 1, 1]
    assert generate_calls == []

    coordinator._refresh_visible_thumbnails()
    assert generate_calls == [[4, 8, 12]]


def test_thumbnail_proxy_prefers_pyramid_coarse_level(monkeypatch):
    """Structure: warm pyramid → coarse level, no full-res decode."""
    import tabs.image_compare.plugins.video_editor.services.video_export.service as svc

    proxy = object()
    base = _proxy_base()
    snap = SimpleNamespace(image1_path="a.png", image2_path="b.png")
    monkeypatch.setattr(
        svc, "pyramid_for", lambda _store: _proxy_pyramid(proxy=proxy)
    )
    calls = {}

    def fake_render_from_images(_snap, _request, image1, image2, **_kwargs):
        calls["from_images"] = (image1, image2)
        return SimpleNamespace(
            image=Image.new("RGBA", _THUMB, (10, 20, 30, 255)),
            backend="gpu",
        )

    def fake_render(_snap, _request):
        calls["render"] = True
        raise AssertionError("full-res path must not run on a pyramid hit")

    renderer = SimpleNamespace(
        render_from_images=fake_render_from_images, render=fake_render
    )
    service = _proxy_service(
        repo_cache={("a.png", False): base, ("b.png", False): base},
        renderer=renderer,
    )
    result = service.render_snapshot_thumbnail_to_pil(snap, 160, 90)

    assert calls.get("from_images") == (proxy, proxy)
    assert "render" not in calls
    assert service.last_thumbnail_source == ("pyramid", "pyramid")
    assert result is not None and result.size == (160, 90)


def test_thumbnail_proxy_falls_back_to_cached_base(monkeypatch):
    """Structure: pyramid absent/incomplete → decoded base reused, no decode."""
    import tabs.image_compare.plugins.video_editor.services.video_export.service as svc

    base = _proxy_base()
    snap = SimpleNamespace(image1_path="a.png", image2_path="b.png")
    monkeypatch.setattr(svc, "pyramid_for", lambda _store: None)
    seen = {}

    def fake_render_from_images(_snap, _request, image1, image2, **_kwargs):
        seen["images"] = (image1, image2)
        return SimpleNamespace(
            image=Image.new("RGBA", _THUMB, (40, 50, 60, 255)),
            backend="gpu",
        )

    service = _proxy_service(
        repo_cache={("a.png", False): base, ("b.png", False): base},
        renderer=SimpleNamespace(render_from_images=fake_render_from_images),
    )
    result = service.render_snapshot_thumbnail_to_pil(snap, 160, 90)

    assert seen["images"] == (base, base)
    assert service.last_thumbnail_source == ("cache", "cache")
    assert result is not None and result.size == (160, 90)


def test_thumbnail_proxy_miss_never_decodes():
    """Structure: cold caches → full-res fallback, repository never decoded."""
    base_missing = SimpleNamespace(
        _images_cache={},
        get_image=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not decode on the probe path")
        ),
    )
    snap = SimpleNamespace(image1_path="a.png", image2_path="b.png")
    calls = {}

    def fake_render(_snap, _request):
        calls["render"] = True
        return SimpleNamespace(
            image=Image.new("RGBA", _THUMB, (70, 80, 90, 255)),
            backend="gpu",
        )

    def fake_render_from_images(*_args, **_kwargs):
        calls["from_images"] = True
        raise AssertionError("proxy path must not run on a miss")

    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    service = VideoExporterService.__new__(VideoExporterService)
    service._image_repository = base_missing
    service._thumbnail_frame_renderer = SimpleNamespace(
        render=fake_render, render_from_images=fake_render_from_images
    )
    service._thumbnail_proxy_resolver = None
    service._last_thumbnail_source = None
    service._thumbnail_callback_bridge = None
    service._last_render_backend = "gpu"

    result = service.render_snapshot_thumbnail_to_pil(snap, 160, 90)

    assert calls.get("render") is True
    assert "from_images" not in calls
    assert service.last_thumbnail_source == ("miss", "miss")
    assert result is not None and result.size == (160, 90)


def test_thumbnail_async_proxy_delivers_without_decode(monkeypatch):
    """Structure: async hit renders from proxy; async miss uses render_async."""
    import tabs.image_compare.plugins.video_editor.services.video_export.service as svc

    base = _proxy_base()
    snap = SimpleNamespace(image1_path="a.png", image2_path="b.png")
    monkeypatch.setattr(svc, "pyramid_for", lambda _store: None)
    delivered = []

    def fake_render_from_images(_snap, _request, _i1, _i2, **_kwargs):
        return SimpleNamespace(
            image=Image.new("RGBA", _THUMB, (1, 2, 3, 255)), backend="gpu"
        )

    def fake_render_async(_snap, _request, _cb):
        raise AssertionError("render_async must not run on a proxy hit")

    service = _proxy_service(
        repo_cache={("a.png", False): base, ("b.png", False): base},
        renderer=SimpleNamespace(
            render_from_images=fake_render_from_images,
            render_async=fake_render_async,
        ),
    )
    service.render_snapshot_thumbnail_to_pil_async(
        snap, 160, 90, delivered.append
    )

    assert len(delivered) == 1
    assert delivered[0].size == (160, 90)
    assert service.last_thumbnail_source == ("cache", "cache")


def test_thumbnail_proxy_resolver_override_wins(monkeypatch):
    """Structure: injected resolver short-circuits the built-in lookup."""
    import tabs.image_compare.plugins.video_editor.services.video_export.service as svc

    custom = object()
    snap = SimpleNamespace(image1_path="a.png", image2_path="b.png")
    monkeypatch.setattr(
        svc, "pyramid_for", lambda _store: (_ for _ in ()).throw(
            AssertionError("built-in lookup must not run when overridden")
        )
    )
    seen = {}

    def fake_render_from_images(_snap, _request, image1, image2, **_kwargs):
        seen["images"] = (image1, image2)
        return SimpleNamespace(
            image=Image.new("RGBA", _THUMB, (9, 9, 9, 255)), backend="gpu"
        )

    service = _proxy_service(
        repo_cache={},
        renderer=SimpleNamespace(render_from_images=fake_render_from_images),
    )
    service.set_thumbnail_proxy_resolver(
        lambda _path, _auto_crop, _size: (custom, "pyramid")
    )
    result = service.render_snapshot_thumbnail_to_pil(snap, 160, 90)

    assert seen["images"] == (custom, custom)
    assert service.last_thumbnail_source == ("pyramid", "pyramid")
    assert result is not None and result.size == (160, 90)


def test_cover_source_to_content_fills_thumbnail_target():
    """Structure: cover (not fit) lands exactly on the content box."""
    from tabs.image_compare.services.video_snapshot_rendering.geometry import (
        cover_source_to_content,
        is_thumbnail_target_size,
    )

    assert is_thumbnail_target_size(160, 90) is True
    assert is_thumbnail_target_size(1920, 1080) is False

    wide = Image.new("RGB", (320, 90), (200, 100, 50))
    assert cover_source_to_content(wide, (160, 90)).size == (160, 90)
    tall = Image.new("RGB", (90, 180), (50, 100, 200))
    assert cover_source_to_content(tall, (160, 90)).size == (160, 90)
