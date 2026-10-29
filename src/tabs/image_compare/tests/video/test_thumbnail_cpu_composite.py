"""CPU filmstrip tiles — identity, split, gating, fail-open, cost.

The strip used to pay one offscreen GPU round-trip per tile (15-30 ms warm,
measured 2026-10-29) for what is a 160x90 composite. ``cpu_thumbnail``
composes that tile in PIL from the already-resolved pyramid proxies (~2 ms)
and the service prefers it only when the snapshot carries nothing the
composite cannot reproduce.

What these tests pin (content, not counts — a "tile appeared" assertion stays
green under a pane swap, see ``test_thumbnail_content_identity``):

1. identity — two distinct payloads land on their own sides;
2. split — ``split_position_visual`` moves the boundary, both axes;
3. gating — overlay/filename/diff/single-image snapshots keep the GPU path
   and never reach the composer; a composable snapshot never reaches the GPU;
4. fail-open — a composer miss (cold proxy) still paints the tile via the
   GPU renderer; an unknown mode never reaches the composer;
5. cost — the composite stays well under the 5 ms coarse bound (printed).
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from PIL import Image

from core.store_viewport import ViewState, ViewportState
from tabs.image_compare.canvas.features.capture.state.feature_state import (
    CaptureWidgetState,
)
from tabs.image_compare.canvas.features.divider.state.feature_state import (
    DividerWidgetState,
)
from tabs.image_compare.canvas.features.guides.state.feature_state import (
    GuidesWidgetState,
)
from tabs.image_compare.canvas.features.magnifier.state.feature_state import (
    MagnifierWidgetState,
)
from tabs.image_compare.plugins.video_editor.services.thumbnails import (
    ThumbnailService,
)
from tabs.image_compare.services.video_snapshot_rendering.cpu_thumbnail import (
    compose_thumbnail_cpu,
    thumbnail_needs_gpu,
)

_THUMB = (160, 90)
#: Coarse proxy size the P1 seam hands the strip on a 1080p-ish pair.
_PROXY = (375, 250)

LEFT_PAYLOAD = (200, 20, 20, 255)
RIGHT_PAYLOAD = (20, 20, 200, 255)
#: Never one of the pane payloads: a GPU tile that leaked into the CPU
#: assertions cannot pass by accident.
GPU_ONLY_PAYLOAD = (7, 200, 90, 255)

_FPS = 10


def _proxy(color=LEFT_PAYLOAD, size=_PROXY):
    return Image.new("RGBA", size, color)


def _snap(*, states=None, **view_kwargs):
    """Real ``ViewportState``/``ViewState`` — the fields the gate reads."""
    view = ViewState(**view_kwargs)
    if states:
        view.canvas_widget_state = dict(states)
    return SimpleNamespace(viewport_state=ViewportState(view_state=view))


def _compose(snap, image1=None, image2=None, size=_THUMB):
    return compose_thumbnail_cpu(
        snap,
        size[0],
        size[1],
        image1=_proxy() if image1 is None else image1,
        image2=_proxy(RIGHT_PAYLOAD) if image2 is None else image2,
    )


# ---------------------------------------------------------------------------
# 1. Identity: each pane carries its own payload.
# ---------------------------------------------------------------------------


def test_two_pane_payloads_land_on_their_own_sides():
    tile = _compose(_snap())

    assert tile is not None
    assert tile.size == _THUMB
    left = tile.getpixel((12, 45))
    right = tile.getpixel((_THUMB[0] - 13, 45))
    assert left == LEFT_PAYLOAD, f"left pane shows {left}"
    assert right == RIGHT_PAYLOAD, f"right pane shows {right}"
    assert left != right


def test_horizontal_split_puts_image1_on_top():
    tile = _compose(_snap(is_horizontal=True))

    top = tile.getpixel((_THUMB[0] // 2, 12))
    bottom = tile.getpixel((_THUMB[0] // 2, _THUMB[1] - 13))
    assert top == LEFT_PAYLOAD, f"top pane shows {top}"
    assert bottom == RIGHT_PAYLOAD, f"bottom pane shows {bottom}"


# ---------------------------------------------------------------------------
# 2. Split position moves the boundary.
# ---------------------------------------------------------------------------


def _first_right_pane_column(tile):
    for x in range(tile.width):
        if tile.getpixel((x, tile.height // 2)) == RIGHT_PAYLOAD:
            return x
    return None


def test_split_position_moves_the_boundary_by_its_fraction():
    states = {"divider": DividerWidgetState(visible=False)}

    half = _compose(_snap(states=states, split_position_visual=0.5))
    quarter = _compose(_snap(states=states, split_position_visual=0.25))

    assert _first_right_pane_column(half) == 80
    assert _first_right_pane_column(quarter) == 40
    # The boundary moved by exactly the fraction delta, not by a fixed step.
    assert _first_right_pane_column(half) - _first_right_pane_column(quarter) == 40
    assert half.getpixel((79, 45)) == LEFT_PAYLOAD
    assert quarter.getpixel((39, 45)) == LEFT_PAYLOAD


def test_split_position_moves_the_boundary_vertically():
    states = {"divider": DividerWidgetState(visible=False)}
    tile = _compose(_snap(states=states, is_horizontal=True, split_position_visual=0.25))

    assert tile.getpixel((80, 21)) == LEFT_PAYLOAD
    assert tile.getpixel((80, 23)) == RIGHT_PAYLOAD


def test_divider_is_drawn_only_when_visible():
    hidden = _compose(
        _snap(states={"divider": DividerWidgetState(visible=False)})
    )
    shown = _compose(
        _snap(
            states={
                "divider": DividerWidgetState(
                    visible=True, thickness=3, color=_color(255, 255, 0, 255)
                )
            }
        )
    )
    assert hidden.getpixel((80, 45)) == RIGHT_PAYLOAD
    assert shown.getpixel((80, 45)) == (255, 255, 0, 255)
    assert shown.getpixel((80, 12)) == (255, 255, 0, 255)


def _color(r, g, b, a=255):
    from domain.types import Color

    return Color(r, g, b, a)


def test_channel_mode_zeroes_the_other_channels():
    red_view = _compose(_snap(channel_view_mode="R"))
    green_view = _compose(_snap(channel_view_mode="G"))

    assert red_view.getpixel((12, 45)) == (200, 0, 0, 255)
    assert green_view.getpixel((12, 45)) == (0, 20, 0, 255)


def test_pil_cover_keeps_the_store_cover_geometry():
    """The CPU path resizes in PIL but must cover exactly like the store
    helper (shared ``cover_crop_box``) — 375x250 into a 4:3 tile keeps the
    middle band, so the source's left/right markers stay where the GPU path
    would put them."""
    from tabs.image_compare.services.video_snapshot_rendering.geometry import (
        cover_source_to_content,
    )
    from engine.store.tiled_pixel_store import TiledPixelStore

    source = Image.new("RGBA", (375, 250), LEFT_PAYLOAD)
    source.paste(_proxy(RIGHT_PAYLOAD, size=(125, 250)), (250, 0))
    store = TiledPixelStore.from_pil(source)
    try:
        expected = cover_source_to_content(store, (160, 120))
        expected_px = expected.crop((0, 0, expected.width, expected.height))
    finally:
        store.close()

    tile = _compose(_snap(), image1=source, image2=source, size=(160, 120))

    assert tile.size == expected_px.size == (160, 120)
    for point in ((20, 60), (140, 60)):
        mine = tile.getpixel(point)
        theirs = expected_px.getpixel(point)
        assert all(abs(a - b) <= 2 for a, b in zip(mine, theirs)), (
            f"{point}: cpu {mine} vs store {theirs}"
        )


# ---------------------------------------------------------------------------
# 3. Gating: overlay-bearing snapshots keep the GPU path.
# ---------------------------------------------------------------------------


def test_gate_flags_overlay_and_filename_state():
    assert thumbnail_needs_gpu(_snap()) is False
    assert thumbnail_needs_gpu(
        _snap(states={"magnifier": MagnifierWidgetState(enabled=True)})
    ) is True
    assert thumbnail_needs_gpu(
        _snap(states={"guides": GuidesWidgetState(enabled=True)})
    ) is True
    # A disabled magnifier with its default instance model is COMPOSABLE:
    # the live canvas always carries that model while the loupe paints
    # nothing until the feature flag turns on (measured 2026-10-29: a default
    # session capture shows no loupe, and gating on ``models`` would have
    # sent every real recording to the GPU path).
    assert thumbnail_needs_gpu(
        _snap(
            states={
                "magnifier": MagnifierWidgetState(
                    enabled=False,
                    models={"default": object()},
                )
            }
        )
    ) is False
    assert thumbnail_needs_gpu(
        _snap(
            states={
                "magnifier": MagnifierWidgetState(
                    enabled=True,
                    models={"default": object()},
                )
            }
        )
    ) is True
    filename_snap = _snap()
    filename_snap.viewport_state.render_config.include_file_names_in_saved = True
    assert thumbnail_needs_gpu(filename_snap) is True


def test_gate_stays_open_for_state_it_cannot_reproduce():
    # Diff images are built by the render plan; single-pane preview is
    # widget-side in the live canvas — neither is carried by a snapshot.
    assert thumbnail_needs_gpu(_snap(diff_mode="highlight")) is True
    assert thumbnail_needs_gpu(_snap(showing_single_image_mode=1)) is True
    assert thumbnail_needs_gpu(_snap(channel_view_mode="CMYK")) is True
    assert thumbnail_needs_gpu(_snap(overlay_enabled=True)) is True
    # Fail-open on anything unreadable.
    assert thumbnail_needs_gpu(object()) is True


def test_capture_state_alone_does_not_force_the_gpu_path():
    """Capture rings need magnifier-instance runtime data — never in a
    snapshot — and the live canvas lazily creates the capture state with
    ``visible=True``, so gating on it would disable the CPU path everywhere.
    """
    assert thumbnail_needs_gpu(
        _snap(states={"capture": CaptureWidgetState(visible=True)})
    ) is False
    assert thumbnail_needs_gpu(
        _snap(
            states={
                "capture": CaptureWidgetState(visible=True),
                "magnifier": MagnifierWidgetState(enabled=True),
            }
        )
    ) is True


class _FixedRecording:
    """``evaluate_at`` always returns the same snapshot (frame identity is
    covered by ``test_thumbnail_content_identity``; here the snapshot is the
    variable)."""

    def __init__(self, snap, duration=0.3):
        self._snap = snap
        self._duration = duration

    def evaluate_at(self, _timestamp: float):
        return self._snap

    def get_duration(self) -> float:
        return self._duration


class _Harness:
    """Real ThumbnailService, real queue path, workers run inline."""

    def __init__(self, qapp):
        self.qapp = qapp
        self.service = ThumbnailService()
        self.service.set_thumbnail_disk_cache(None)
        self.service._thread_pool.start = lambda worker, priority=0: worker.run()
        self.cpu_calls: list = []
        self.gpu_calls: list = []
        self.pixmaps: dict[int, object] = {}
        self.service.thumbnailReady.connect(
            lambda index, pixmap: self.pixmaps.__setitem__(index, pixmap)
        )

    def wire(self, *, composer_result=None, gpu_payload=GPU_ONLY_PAYLOAD,
             composer_raises=False):
        def composer(snap, out_w, out_h, *, auto_crop=False):
            self.cpu_calls.append((snap, out_w, out_h, auto_crop))
            if composer_raises:
                raise AssertionError("composer must not run for this snapshot")
            return composer_result

        def gpu_async(snap, out_w, out_h, callback, *, auto_crop=False):
            self.gpu_calls.append((snap, out_w, out_h, auto_crop))
            callback(_proxy(gpu_payload, size=(out_w, out_h)))

        def gpu_sync(snap, out_w, out_h, *, auto_crop=False):
            self.gpu_calls.append((snap, out_w, out_h, auto_crop))
            return _proxy(gpu_payload, size=(out_w, out_h))

        self.service.set_snapshot_renderer(gpu_sync)
        self.service.set_async_snapshot_renderer(gpu_async)
        self.service.set_cpu_thumbnail_composer(composer)
        return self

    def generate(self, snap):
        self.service.generate_thumbnails(
            _FixedRecording(snap),
            target_count=1,
            thumbnail_size=_THUMB,
            fps=_FPS,
            priority_indices=[0],
        )
        self.qapp.processEvents()

    def tile_color(self, index=0):
        pixmap = self.pixmaps.get(index)
        if pixmap is None or pixmap.isNull():
            return None
        image = pixmap.toImage()
        color = image.pixelColor(image.width() // 2, image.height() // 2)
        return (color.red(), color.green(), color.blue(), color.alpha())


def test_composable_snapshot_never_touches_the_gpu_renderer(qapp):
    harness = _Harness(qapp).wire(
        composer_result=_proxy(LEFT_PAYLOAD, size=_THUMB)
    )

    harness.generate(_snap())

    assert len(harness.cpu_calls) == 1, "composable snapshot must use the composer"
    assert harness.gpu_calls == [], "the GPU renderer must not run for a CPU tile"
    assert harness.tile_color() == LEFT_PAYLOAD


def test_overlay_snapshot_never_touches_the_composer(qapp):
    for states in (
        {"magnifier": MagnifierWidgetState(enabled=True)},
        {"guides": GuidesWidgetState(enabled=True)},
    ):
        harness = _Harness(qapp).wire(composer_raises=True)

        harness.generate(_snap(states=states))

        assert harness.cpu_calls == [], (
            f"composer ran for an overlay snapshot {list(states)}"
        )
        assert len(harness.gpu_calls) == 1
        assert harness.tile_color() == GPU_ONLY_PAYLOAD

    filename_snap = _snap()
    filename_snap.viewport_state.render_config.include_file_names_in_saved = True
    harness = _Harness(qapp).wire(composer_raises=True)
    harness.generate(filename_snap)
    assert harness.cpu_calls == []
    assert harness.tile_color() == GPU_ONLY_PAYLOAD


# ---------------------------------------------------------------------------
# 4. Fail-open: a miss still paints the tile through the GPU path.
# ---------------------------------------------------------------------------


def test_composer_miss_falls_back_to_the_gpu_renderer(qapp):
    harness = _Harness(qapp).wire(composer_result=None)

    harness.generate(_snap())

    assert len(harness.cpu_calls) == 1, "the (composable) composer is tried first"
    assert len(harness.gpu_calls) == 1, "a composer miss must use the GPU renderer"
    assert harness.tile_color() == GPU_ONLY_PAYLOAD


def test_unknown_mode_never_reaches_the_composer(qapp):
    harness = _Harness(qapp).wire(composer_raises=True)

    harness.generate(_snap(diff_mode="highlight"))

    assert harness.cpu_calls == []
    assert len(harness.gpu_calls) == 1
    assert harness.tile_color() == GPU_ONLY_PAYLOAD


def test_service_composer_returns_none_on_a_cold_proxy(monkeypatch):
    """Missing proxy at the service seam: no decode, ``None`` -> GPU path."""
    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    service = VideoExporterService.__new__(VideoExporterService)
    service._image_repository = SimpleNamespace(
        _images_cache={},
        get_image=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("the CPU path must never decode")
        ),
    )
    service._thumbnail_proxy_resolver = None
    service._last_thumbnail_source = None

    snap = _snap()
    snap.image1_path = "a.png"
    snap.image2_path = "b.png"
    assert service.compose_thumbnail_cpu(snap, 160, 90) is None
    assert service.last_thumbnail_source == ("miss", "miss")


def test_service_composer_composites_on_a_proxy_hit():
    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    service = VideoExporterService.__new__(VideoExporterService)
    service._thumbnail_proxy_resolver = (
        lambda path, auto_crop, size: (
            (_proxy(LEFT_PAYLOAD), "pyramid")
            if path == "a.png"
            else (_proxy(RIGHT_PAYLOAD), "pyramid")
        )
    )
    service._image_repository = SimpleNamespace(_images_cache={})
    service._last_thumbnail_source = None

    snap = _snap()
    snap.image1_path = "a.png"
    snap.image2_path = "b.png"
    tile = service.compose_thumbnail_cpu(snap, 160, 90)

    assert tile is not None and tile.size == _THUMB
    assert tile.getpixel((12, 45)) == LEFT_PAYLOAD
    assert tile.getpixel((147, 45)) == RIGHT_PAYLOAD
    assert service.last_thumbnail_source == ("pyramid", "pyramid")


# ---------------------------------------------------------------------------
# 5. Cost: the composite is cheap enough for the strip.
# ---------------------------------------------------------------------------


def test_composite_cost_stays_under_the_coarse_bound():
    """2 panes at 160x90 from 375x250 proxies, real tiled stores.

    The GPU round-trip this replaces costs 15-30 ms warm; the 5 ms bound is
    deliberately coarse so this stays an honest bound, not a benchmark.
    """
    from engine.store.tiled_pixel_store import TiledPixelStore

    store1 = TiledPixelStore.from_pil(_proxy(LEFT_PAYLOAD))
    store2 = TiledPixelStore.from_pil(_proxy(RIGHT_PAYLOAD))
    try:
        snap = _snap()
        # Warm the resampler path so the measurement is the composite.
        assert _compose(snap, image1=store1, image2=store2) is not None
        samples = []
        for _ in range(5):
            started = time.perf_counter()
            tile = _compose(snap, image1=store1, image2=store2)
            samples.append((time.perf_counter() - started) * 1000.0)
            assert tile is not None
    finally:
        store1.close()
        store2.close()

    samples.sort()
    median_ms = samples[len(samples) // 2]
    print(
        f"[cpu-thumb] compose 2 panes 160x90 from 375x250 proxies: "
        f"median {median_ms:.2f} ms (all {[round(s, 2) for s in samples]})"
    )
    assert median_ms < 5.0, f"CPU composite too slow: {median_ms:.2f} ms"
