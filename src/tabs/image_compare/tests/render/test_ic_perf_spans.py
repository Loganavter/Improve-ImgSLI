"""Wave C (plan-engine-perf-debugger-2026-09-20): IC zoom span hooks.

Wheel-to-photon span chain on the Image Compare zoom path. Every hook
emits a span into the IC FrameContext owner
(``RhiCanvasRenderer.frame_context``) with lazy detail factories only —
no draw-behavior change (span/record only, None-safe skips).

Hook points (one test section each):

- ``ic.wheel_tick`` — ``canvas/interaction.py::handle_wheel_event``
  (carries the ``wheel-<id>`` join atom in ``detail["trace_id"]``)
- ``ic.present_proxy`` — enqueue-side ONLY (``widget.update()`` call
  sites on the zoom path + ``CanvasWidget._request_update``); the span
  closes when ``update()`` returns, so compositor time is EXCLUDED by
  construction — never read it as photon timing
- ``ic.enqueue`` — ``canvas/render_context.py::request_update``
- ``ic.prepare`` — ``rhi_renderer/renderer.py::render`` (around
  ``prepare_frame``)
- ``ic.realize_main`` / ``ic.realize_magnifier`` —
  ``rhi_renderer/use_cases/tile_residency.py``
- ``ic.mips`` — ``rhi_renderer/renderer.py::render`` (around the
  mip-cascade call)
- ``ic.submit`` — ``rhi_renderer/use_cases/draw.py::submit_array_draw``

Fakes follow ``test_wheel_zoom_magnitude.py`` conventions
(``SimpleNamespace`` canvas + ``CanvasRuntimeState``, no Qt windows).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from engine.frame.context import FrameContext
from tabs.image_compare.canvas.interaction import handle_wheel_event
from tabs.image_compare.canvas.state import CanvasRuntimeState

#: Every stage the Wave C chain must emit (analyzer must list all of
#: these — zero missing stages — for the zoom-burst repro).
EXPECTED_IC_STAGES = frozenset(
    {
        "ic.wheel_tick",
        "ic.present_proxy",
        "ic.enqueue",
        "ic.prepare",
        "ic.realize_main",
        "ic.realize_magnifier",
        "ic.mips",
        "ic.submit",
    }
)


class _WheelEvent:
    def __init__(self, angle_delta_y: int = 120):
        self._angle_delta_y = angle_delta_y
        self.accepted = False

    def accept(self):
        self.accepted = True

    def modifiers(self):
        return Qt.KeyboardModifier.ControlModifier

    def position(self):
        return SimpleNamespace(x=lambda: 40.0, y=lambda: 30.0)

    def angleDelta(self):
        return SimpleNamespace(y=lambda: self._angle_delta_y)


def _canvas(renderer):
    return SimpleNamespace(
        _rhi_renderer=renderer,
        runtime_state=CanvasRuntimeState(),
        width=lambda: 100,
        height=lambda: 80,
        update=lambda: None,
        zoomChanged=SimpleNamespace(emit=lambda *_args: None),
    )


def _span_names(ctx: FrameContext) -> set[str]:
    return {span.name for span in ctx.spans}


def test_wheel_tick_emits_join_atom_and_present_proxy():
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer
    from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level

    renderer = RhiCanvasRenderer()
    canvas = _canvas(renderer)
    set_zoom_level(canvas, 10.0)
    set_pan_offsets(canvas, 0.0, 0.0)

    handle_wheel_event(canvas, _WheelEvent(120))

    names = _span_names(renderer.frame_context)
    assert "ic.wheel_tick" in names
    assert "ic.present_proxy" in names
    (tick,) = [
        span
        for span in renderer.frame_context.spans
        if span.name == "ic.wheel_tick"
    ]
    detail = tick.resolved_detail
    assert detail["trace_id"].startswith("wheel-")
    assert detail["angle_delta_y"] == 120


def test_wheel_tick_none_safe_without_renderer():
    canvas = SimpleNamespace(
        runtime_state=CanvasRuntimeState(),
        width=lambda: 100,
        height=lambda: 80,
        update=lambda: None,
        zoomChanged=SimpleNamespace(emit=lambda *_args: None),
    )
    from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level

    set_zoom_level(canvas, 10.0)
    set_pan_offsets(canvas, 0.0, 0.0)
    # No _rhi_renderer: span skipped, zoom still applied (no behavior change).
    handle_wheel_event(canvas, _WheelEvent(120))
    from ui.canvas_infra.viewport.state import get_zoom_level

    assert get_zoom_level(canvas) != 10.0


def test_enqueue_span_on_request_update():
    from tabs.image_compare.canvas.render_context import request_update
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    renderer = RhiCanvasRenderer()
    canvas = _canvas(renderer)
    request_update(canvas)
    assert "ic.enqueue" in _span_names(renderer.frame_context)


def test_render_skip_path_emits_prepare():
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    renderer = RhiCanvasRenderer()
    widget = SimpleNamespace(renderTarget=lambda: None)
    assert renderer.render(widget, object(), None) is False
    assert "ic.prepare" in _span_names(renderer.frame_context)


def test_realize_spans_with_stubbed_residency():
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer
    from tabs.image_compare.canvas.rhi_renderer.use_cases import tile_residency as tr

    renderer = RhiCanvasRenderer()
    renderer.resources.residency = SimpleNamespace(
        realize_tile_plan=lambda *a, **k: False
    )
    canvas = _canvas(renderer)
    base = SimpleNamespace()

    tr.realize_main_tiles(
        renderer,
        canvas,
        ("tex-a", "tex-b"),
        base,
        object(),
        None,
        (1.0, 1.0),
        (0.0, 0.0),
        {},
    )
    assert "ic.realize_main" in _span_names(renderer.frame_context)

    ctx = SimpleNamespace(
        source_texture_ids=("src-a", "src-b"),
        feature_overlay=SimpleNamespace(gpu_active=True),
        source_images_ready=True,
        diff_source_ready=False,
        diff_source_texture_id=0,
    )
    tr.realize_magnifier_tiles(
        renderer,
        canvas,
        ctx,
        ("tex-a", "tex-b"),
        base,
        object(),
        (1.0, 1.0),
        (0.0, 0.0),
        {},
    )
    assert "ic.realize_magnifier" in _span_names(renderer.frame_context)


def _fake_command_buffer():
    calls: list = []

    def _rec(name):
        def _fn(*args, **kwargs):
            calls.append(name)

        return _fn

    return SimpleNamespace(
        calls=calls,
        resourceUpdate=_rec("resourceUpdate"),
        beginPass=_rec("beginPass"),
        endPass=_rec("endPass"),
    )


def test_submit_span_with_fake_command_buffer():
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer
    from tabs.image_compare.canvas.rhi_renderer.use_cases.draw import (
        submit_array_draw,
    )

    renderer = RhiCanvasRenderer()
    widget = SimpleNamespace(renderTarget=lambda: None)
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80)
    )
    command_buffer = _fake_command_buffer()
    submit_array_draw(
        renderer,
        widget,
        command_buffer,
        [],
        ctx=None,
        updates=SimpleNamespace(),
        target=target,
        clear_color=SimpleNamespace(),
        frame_context=renderer.frame_context,
    )
    assert "ic.submit" in _span_names(renderer.frame_context)
    assert command_buffer.calls == ["beginPass", "endPass"]
    # Existing submit-gate record still written alongside the span.
    assert any(
        d.pass_name == "submit" for d in renderer.frame_context._decisions
    )


def test_submit_none_safe_without_context():
    from tabs.image_compare.canvas.rhi_renderer.use_cases.draw import (
        submit_array_draw,
    )
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    renderer = RhiCanvasRenderer()
    widget = SimpleNamespace(renderTarget=lambda: None)
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80)
    )
    command_buffer = _fake_command_buffer()
    submit_array_draw(
        renderer,
        widget,
        command_buffer,
        [],
        ctx=None,
        updates=SimpleNamespace(),
        target=target,
        clear_color=SimpleNamespace(),
        frame_context=None,
    )
    assert command_buffer.calls == ["beginPass", "endPass"]


def test_full_render_fake_path_emits_prepare_mips_submit(monkeypatch):
    """End-to-end ``render()`` with stubbed GPU boundary.

    ``should_draw=False`` (no base image) still runs the upload-submit,
    mip-cascade and draw-submit phases, so one ``render()`` call emits
    ``ic.prepare`` + ``ic.mips`` + ``ic.submit`` on the owner context.
    """
    import tabs.image_compare.canvas.rhi_renderer.use_cases.frame_setup as fs
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    renderer = RhiCanvasRenderer()
    ctx = SimpleNamespace(
        render_list=SimpleNamespace(base_image=None),
        images_uploaded=[True, True],
        scene_frame=SimpleNamespace(),
        canvas_width=100,
        canvas_height=80,
        canvas_offset_x=0.0,
        canvas_offset_y=0.0,
        diff_source_ready=False,
    )
    monkeypatch.setattr(
        fs, "build_render_runtime_context", lambda widget: ctx
    )
    monkeypatch.setattr(fs, "should_render_blank_white", lambda scene: False)
    monkeypatch.setattr(
        fs, "_viewport_zoom_offset_for_tile", lambda *a, **k: ((1.0, 1.0), (0.0, 0.0))
    )
    renderer.resources.apply_pending_uploads = lambda *a, **k: None
    renderer.resources.generate_all_dirty_mips = lambda *a, **k: {}
    renderer.rhi = SimpleNamespace(
        nextResourceUpdateBatch=lambda: SimpleNamespace()
    )
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80)
    )
    clear = SimpleNamespace(
        red=lambda: 0, green=lambda: 0, blue=lambda: 0, alpha=lambda: 255
    )
    widget = SimpleNamespace(
        _rhi_renderer=renderer,
        renderTarget=lambda: target,
        width=lambda: 100,
        height=lambda: 80,
        fixedColorBufferSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80),
    )
    command_buffer = _fake_command_buffer()
    assert renderer.render(widget, command_buffer, clear) is True
    names = _span_names(renderer.frame_context)
    assert {"ic.prepare", "ic.mips", "ic.submit"} <= names


def test_zoom_burst_chain_covers_all_stages(monkeypatch):
    """Zoom-burst repro (in-process): N synthetic wheel ticks through the
    real hooks; every Wave C stage must appear at least once (the
    analyzer-side "zero missing stages" gate is verified by the export
    test below on the same span set)."""
    import tabs.image_compare.canvas.rhi_renderer.use_cases.frame_setup as fs
    from tabs.image_compare.canvas.render_context import request_update
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer
    from tabs.image_compare.canvas.rhi_renderer.use_cases import tile_residency as tr
    from tabs.image_compare.canvas.rhi_renderer.use_cases.draw import (
        submit_array_draw,
    )
    from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level

    renderer = RhiCanvasRenderer()
    renderer.resources.residency = SimpleNamespace(
        realize_tile_plan=lambda *a, **k: False
    )
    canvas = _canvas(renderer)
    set_zoom_level(canvas, 4.0)
    set_pan_offsets(canvas, 0.0, 0.0)
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80)
    )
    mag_ctx = SimpleNamespace(
        source_texture_ids=("src-a", "src-b"),
        feature_overlay=SimpleNamespace(gpu_active=True),
        source_images_ready=True,
        diff_source_ready=False,
        diff_source_texture_id=0,
    )

    for _ in range(5):
        handle_wheel_event(canvas, _WheelEvent(120))
        request_update(canvas)
        tr.realize_main_tiles(
            renderer, canvas, ("t-a", "t-b"), SimpleNamespace(), object(),
            None, (1.0, 1.0), (0.0, 0.0), {},
        )
        tr.realize_magnifier_tiles(
            renderer, canvas, mag_ctx, ("t-a", "t-b"), SimpleNamespace(),
            object(), (1.0, 1.0), (0.0, 0.0), {},
        )
        submit_array_draw(
            renderer, canvas, _fake_command_buffer(), [],
            ctx=None, updates=SimpleNamespace(), target=target,
            clear_color=SimpleNamespace(), frame_context=renderer.frame_context,
        )
    # should_draw=False render() pass for ic.mips coverage.
    ctx = SimpleNamespace(
        render_list=SimpleNamespace(base_image=None),
        images_uploaded=[True, True],
        scene_frame=SimpleNamespace(),
        canvas_width=100,
        canvas_height=80,
        canvas_offset_x=0.0,
        canvas_offset_y=0.0,
        diff_source_ready=False,
    )
    monkeypatch.setattr(fs, "build_render_runtime_context", lambda widget: ctx)
    monkeypatch.setattr(fs, "should_render_blank_white", lambda scene: False)
    monkeypatch.setattr(
        fs, "_viewport_zoom_offset_for_tile", lambda *a, **k: ((1.0, 1.0), (0.0, 0.0))
    )
    renderer.resources.apply_pending_uploads = lambda *a, **k: None
    renderer.resources.generate_all_dirty_mips = lambda *a, **k: {}
    renderer.rhi = SimpleNamespace(
        nextResourceUpdateBatch=lambda: SimpleNamespace()
    )
    clear = SimpleNamespace(
        red=lambda: 0, green=lambda: 0, blue=lambda: 0, alpha=lambda: 255
    )
    render_widget = SimpleNamespace(
        _rhi_renderer=renderer,
        renderTarget=lambda: target,
        width=lambda: 100,
        height=lambda: 80,
        fixedColorBufferSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80),
    )
    renderer.render(render_widget, _fake_command_buffer(), clear)

    assert EXPECTED_IC_STAGES <= _span_names(renderer.frame_context)

    # Wheel join atoms survive export: every ic.wheel_tick event carries a
    # ``wheel-<id>`` trace_id in args (Perfetto join key).
    from engine.frame.trace_export import build_trace

    events = build_trace([renderer.frame_context], pid=1)
    wheel_args = [
        event["args"]
        for event in events
        if event.get("ph") == "X" and event.get("name") == "ic.wheel_tick"
    ]
    assert len(wheel_args) == 5
    assert all(
        str(args.get("trace_id", "")).startswith("wheel-") for args in wheel_args
    )
    stage_names = {
        event["name"] for event in events if event.get("ph") == "X"
    }
    assert EXPECTED_IC_STAGES <= stage_names
