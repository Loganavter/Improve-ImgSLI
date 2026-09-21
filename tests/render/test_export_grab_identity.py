"""Export grab identity: throttle key is content-based, grabs pump to quiescence.

Regression for the silent wrong-image export: the single-frame grab throttle
keyed on ``id(plan)/id(diff_image)``. CPython recycles addresses after GC, so
a fresh same-size plan within the 50 ms window aliased the previous frame's
cached pixels and batch exports silently repeated one image. The key is now
content-identity (``export_grab_content_key`` — sizes, source/display keys,
stable image uids, render-scene scalars; no ``id()`` anywhere in the key
path) and grabs pump tile residency to quiescence before reading back, so a
cold-tier first frame cannot grab a partial tier.

Content identity is the law here: every test asserts pixel identity (which
plan's pixels came back), never just grab success. Distinct-content payloads
per index; the cold-tier cases assert the grab ran only after quiescence.
"""

from __future__ import annotations

import gc
from types import SimpleNamespace

from PIL import Image

from plugins.export.services import gpu_export_proxy as proxy_mod
from plugins.export.services.gpu_export_proxy import (
    GpuExportProxy,
    export_grab_content_key,
)
import engine.gpu.export_tiling as tiling_mod
import engine.gpu.offscreen_canvas as offscreen_mod


def _pixel_holders(seed: int):
    """Two distinct pixel-source objects with distinguishable identity."""
    return (
        SimpleNamespace(name=f"img1-{seed}"),
        SimpleNamespace(name=f"img2-{seed}"),
    )


def _make_plan(index: int, size=(64, 64)):
    img1, img2 = _pixel_holders(index)
    src1, src2 = _pixel_holders(1000 + index)
    return SimpleNamespace(
        canvas_w=size[0],
        canvas_h=size[1],
        source_key=(f"left-{index}.png", f"right-{index}.png", size, size),
        display_cache_key=(f"left-{index}.png", f"right-{index}.png", size),
        image1=img1,
        image2=img2,
        source_image1=src1,
        source_image2=src2,
        render_scene=SimpleNamespace(
            blank_white=False,
            single_image_preview=0,
            clip_overlays_to_image_bounds=False,
            is_horizontal=False,
            split_position_visual=0.1 * index,
            overlay_clip_rect=None,
            channel_mode_int=0,
            diff_mode_active=False,
            diff_mode_int=0,
            zoom_interpolation_method="BILINEAR",
            feature_overrides={},
        ),
        output_scale=1.0,
        fill_rgba=None,
        capture_visible=False,
        guides_enabled=False,
        guides_thickness=1,
        preserve_zoom=False,
    )


def _make_widget(*, pending_frames: int = 0):
    """Fake offscreen widget: ``grabFramebuffer`` returns a sentinel; the
    frame advancer (installed by each test) drives ``_tile_more_pending``
    down to quiescence like the live residency pass does."""
    state = SimpleNamespace(
        _export_canvas_viewport=None,
        _tile_more_pending=bool(pending_frames > 0),
    )
    return SimpleNamespace(
        runtime_state=state,
        _pending_left=pending_frames,
        grabbed_while_pending=[],
        upload_diff_source_pil_image=lambda _img: None,
        grabFramebuffer=lambda: object(),
    )


def _install_single_frame_fakes(monkeypatch, widget, applied: dict):
    """Fake the Qt/GL boundary around ``_render_plan_frame_single``.

    The grab converts to a solid-color image keyed by the applied plan's
    index, so tests assert *which* plan's pixels came back.
    """

    def fake_apply(plan):
        applied["index"] = int(plan.source_key[0].split("-")[1].split(".")[0])

    monkeypatch.setattr(
        "ui.canvas_presentation.plan_applicator.apply_render_plan_to_canvas",
        lambda _widget, plan: fake_apply(plan),
    )
    monkeypatch.setattr(
        proxy_mod, "resize_and_show_offscreen_widget", lambda _w, _size: None
    )

    def fake_frame(_widget):
        _widget.frames_rendered = getattr(_widget, "frames_rendered", 0) + 1
        if _widget._pending_left > 0:
            _widget._pending_left -= 1
        _widget.runtime_state._tile_more_pending = _widget._pending_left > 0

    monkeypatch.setattr(proxy_mod, "render_widget_frame", fake_frame)
    monkeypatch.setattr(offscreen_mod, "render_widget_frame", fake_frame)

    def fake_convert(_qimg):
        widget.grabbed_while_pending.append(
            bool(widget.runtime_state._tile_more_pending)
        )
        return Image.new("RGBA", (64, 64), (applied["index"], 10, 20, 255))

    monkeypatch.setattr(proxy_mod, "qimage_to_pil_rgba", fake_convert)


def test_same_size_batch_gc_between_frames_returns_own_pixels(monkeypatch):
    """P0 repro: batch of same-size plans with plan GC between frames.

    Each grab must return its own plan's pixels, never the previous frame's
    cached image — even when the new plan reuses the freed plan's address.
    """
    applied: dict = {}
    widget = _make_widget()
    _install_single_frame_fakes(monkeypatch, widget, applied)
    proxy = GpuExportProxy()

    seen_pixels = []
    for index in range(4):
        plan = _make_plan(index)
        if index > 0:
            old_id = seen_pixels[-1][1]
            # Try to force address reuse so the new plan lands on the freed
            # address (the exact aliasing the old id() key tripped on).
            for _ in range(20000):
                if id(plan) == old_id:
                    break
                plan = _make_plan(index)
        old_id = id(plan)
        timings: dict = {}
        image = proxy._render_plan_frame_single(widget, plan, None, timings)
        pixel = image.getpixel((0, 0))
        assert pixel == (index, 10, 20, 255), (
            f"frame {index} grabbed wrong pixels {pixel} (stale throttle hit)"
        )
        assert timings.get("grab_throttled") is None
        seen_pixels.append((pixel, old_id))
        del plan
        gc.collect()

    assert [p[0][0] for p in seen_pixels] == [0, 1, 2, 3]


def test_identical_plan_still_throttles(monkeypatch):
    """The throttle still fires for a truly identical plan (no perf loss)."""
    applied: dict = {}
    widget = _make_widget()
    _install_single_frame_fakes(monkeypatch, widget, applied)
    conversions = {"n": 0}
    real_convert = proxy_mod.qimage_to_pil_rgba

    def counting_convert(qimg):
        conversions["n"] += 1
        return real_convert(qimg)

    monkeypatch.setattr(proxy_mod, "qimage_to_pil_rgba", counting_convert)
    proxy = GpuExportProxy()
    plan = _make_plan(7)

    first = proxy._render_plan_frame_single(widget, plan, None, {})
    timings: dict = {}
    second = proxy._render_plan_frame_single(widget, plan, None, timings)

    assert timings.get("grab_throttled") == 1.0
    assert conversions["n"] == 1
    assert list(first.tobytes()) == list(second.tobytes())


def test_content_key_distinguishes_plans_and_is_stable(monkeypatch):
    """Key equality is content equality: distinct plans differ, the same plan
    repeats, and every key hashes (usable as a cache key)."""
    applied: dict = {}
    widget = _make_widget()
    _install_single_frame_fakes(monkeypatch, widget, applied)

    plan_a = _make_plan(1)
    key_a1 = export_grab_content_key(plan_a, None)
    key_a2 = export_grab_content_key(plan_a, None)
    assert key_a1 == key_a2
    hash(key_a1)

    plan_b = _make_plan(2)
    assert export_grab_content_key(plan_b, None) != key_a1

    # Same-size plan differing only in split position must differ too
    # (batch video frames share paths/sizes; the scene carries the frame).
    plan_c = _make_plan(1)
    plan_c.render_scene.split_position_visual = 0.99
    assert export_grab_content_key(plan_c, None) != key_a1

    # A rebuilt plan (fresh image objects, fresh uids) always misses the
    # previous key even with identical scalar fields — the safe direction
    # (an extra render, never a wrong image).
    plan_rebuilt = _make_plan(1)
    assert export_grab_content_key(plan_rebuilt, None) != key_a1


def test_grab_pumps_cold_tier_to_quiescence(monkeypatch):
    """Cold-tier first frame: 3 pending frames pump before the grab, and the
    grab itself observes quiescence (never a partial tier)."""
    applied: dict = {}
    widget = _make_widget(pending_frames=3)
    _install_single_frame_fakes(monkeypatch, widget, applied)
    proxy = GpuExportProxy()

    timings: dict = {}
    image = proxy._render_plan_frame_single(widget, _make_plan(3), None, timings)

    # One initial frame plus two pumped frames drain the three pending
    # frames; the grab itself observes quiescence (never a partial tier).
    assert timings.get("export_pump_frames") == 2.0
    assert widget.frames_rendered == 3
    assert widget.grabbed_while_pending == [False]
    assert image.getpixel((0, 0)) == (3, 10, 20, 255)


def test_tiled_exporter_single_pumps_first_tile(monkeypatch):
    """Engine tiled path: ``_render_single`` pumps a cold tier before grab."""
    widget = _make_widget(pending_frames=2)
    monkeypatch.setattr(tiling_mod, "_ensure_live", lambda _w: None)
    monkeypatch.setattr(
        tiling_mod, "resize_and_show_offscreen_widget", lambda _w, _s: None
    )

    def fake_frame(_w):
        if _w._pending_left > 0:
            _w._pending_left -= 1
        _w.runtime_state._tile_more_pending = _w._pending_left > 0

    monkeypatch.setattr(tiling_mod, "render_widget_frame", fake_frame)
    monkeypatch.setattr(offscreen_mod, "render_widget_frame", fake_frame)
    monkeypatch.setattr(
        tiling_mod, "qimage_to_pil_rgba", lambda _q: Image.new("RGBA", (32, 16), (9, 9, 9, 255))
    )

    exporter = tiling_mod.TiledFramebufferExporter(
        widget,
        set_export_viewport=lambda _vp: None,
        prepare_frame=lambda: None,
        query_max_texture_size=lambda: 4096,
    )
    image = exporter._render_single(32, 16)

    assert widget._pending_left == 0
    assert image.getpixel((0, 0)) == (9, 9, 9, 255)
