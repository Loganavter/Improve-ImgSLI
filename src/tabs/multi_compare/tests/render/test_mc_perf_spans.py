"""Wave D (plan-engine-perf-debugger-2026-09-20): MC zoom span mantle.

Wheel-to-photon span chain on the Multi Compare zoom path, mirroring
Wave C's IC hooks (``test_ic_perf_spans.py``). Every hook emits a span
into the MC FrameContext owner
(``MultiCompareRhiRenderer.frame_context``) with lazy detail factories
only — no draw-behavior change (span/record only, None-safe skips).

Hook points (one test section each):

- ``mc.wheel_tick`` — ``canvas/interaction.py::handle_wheel_event``
  (carries the ``wheel-<id>`` join atom in ``detail["trace_id"]``)
- ``mc.present_proxy`` — enqueue-side ONLY (the wheel-path dispatch);
  the span closes when dispatch returns, so compositor time is EXCLUDED
  by construction — never read it as photon timing
- ``mc.enqueue`` — ``ui/canvas_widget.py::request_view_update``
- ``mc.prepare`` — ``scene/renderer.py::render`` (around sync + context
  build + ``prepare_frame`` record; skip paths included, like IC)
- ``mc.realize_slots`` — ``scene/renderer.py::render`` (around
  ``image_pass.prepare``)
- ``mc.mips`` — ``scene/renderer.py::render`` (around the
  mip-cascade call)
- ``mc.submit`` — ``scene/renderer.py::render`` (around
  beginPass/record/endPass)

Fakes follow ``test_mc_zoom_no_busy_cursor.py`` conventions (real
``MultiCompareState`` + real reducer, no Qt windows).
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QPoint, QRect

import pytest

from engine.frame.context import FrameContext
from tabs.multi_compare.canvas import interaction as mc_interaction
from tabs.multi_compare.models import CompareSlot, LeafNode, MultiCompareState
from tabs.multi_compare.scene.store import reduce as mc_reduce
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

#: Every stage the Wave D chain must emit (analyzer must list all of
#: these — zero missing stages — for the zoom-burst repro).
EXPECTED_MC_STAGES = frozenset(
    {
        "mc.wheel_tick",
        "mc.present_proxy",
        "mc.enqueue",
        "mc.prepare",
        "mc.realize_slots",
        "mc.mips",
        "mc.submit",
    }
)


class _WheelEvent:
    def __init__(self, delta_y=120, pos=None):
        self._delta_y = delta_y
        self._pos = pos if pos is not None else QPoint(50, 40)
        self.accepted = False
        self.ignored = False

    def angleDelta(self):
        return SimpleNamespace(y=lambda: self._delta_y)

    def position(self):
        return SimpleNamespace(toPoint=lambda: self._pos)

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class _FakeMcCanvas:
    """Minimal canvas for ``handle_wheel_event``: real state + real reducer."""

    ZOOM_MIN = 1.0
    ZOOM_MAX = 50.0
    ZOOM_STEP = 1.1

    def __init__(self, frame_context=None):
        self.pixel_cache = None
        self.state = MultiCompareState(
            slots=[CompareSlot(id=7, path=None, label="")],
            zoom=2.0,
            pan_x=0.0,
            pan_y=0.0,
        )
        self.dispatched: list = []
        if frame_context is not None:
            self._renderer = SimpleNamespace(frame_context=frame_context)

    def _leaf_rects(self):
        return [(LeafNode(slot_id=7), QRect(0, 0, 400, 300))]

    def _do_dispatch(self, action):
        self.dispatched.append(action)
        self.state = mc_reduce(self.state, action)


def _span_names(ctx: FrameContext) -> set[str]:
    return {span.name for span in ctx.spans}


def test_wheel_tick_emits_join_atom_and_present_proxy():
    ctx = FrameContext()
    canvas = _FakeMcCanvas(ctx)

    mc_interaction.handle_wheel_event(canvas, _WheelEvent(delta_y=120))

    names = _span_names(ctx)
    assert "mc.wheel_tick" in names
    assert "mc.present_proxy" in names
    (tick,) = [span for span in ctx.spans if span.name == "mc.wheel_tick"]
    detail = tick.resolved_detail
    assert detail["trace_id"].startswith("wheel-")
    assert detail["angle_delta_y"] == 120
    assert detail["zoom"][0] != detail["zoom"][1]
    # Zoom itself still applied through the real reducer (STORE guard).
    assert canvas.state.zoom != 2.0
    assert len(canvas.dispatched) == 1


def test_wheel_tick_ids_increment_per_tick():
    ctx = FrameContext()
    canvas = _FakeMcCanvas(ctx)

    mc_interaction.handle_wheel_event(canvas, _WheelEvent(delta_y=120))
    mc_interaction.handle_wheel_event(canvas, _WheelEvent(delta_y=120))

    trace_ids = [
        span.resolved_detail["trace_id"]
        for span in ctx.spans
        if span.name == "mc.wheel_tick"
    ]
    assert len(trace_ids) == 2
    assert trace_ids[0] != trace_ids[1]
    assert all(str(tid).startswith("wheel-") for tid in trace_ids)


def test_wheel_tick_none_safe_without_renderer():
    canvas = _FakeMcCanvas()
    # No _renderer: spans skipped, zoom still applied (no behavior change).
    mc_interaction.handle_wheel_event(canvas, _WheelEvent(delta_y=120))
    assert canvas.state.zoom != 2.0
    assert len(canvas.dispatched) == 1


def test_enqueue_span_on_request_view_update():
    from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget

    ctx = FrameContext()
    updated: list = []
    fake = SimpleNamespace(
        _renderer=SimpleNamespace(frame_context=ctx),
        update=lambda: updated.append(True),
        # Pending already set: skip the QTimer.singleShot arm (no event
        # loop headless) — the enqueue span wraps update() only.
        _view_update_pending=True,
    )
    MultiCompareCanvasWidget.request_view_update(fake)
    assert "mc.enqueue" in _span_names(ctx)
    assert updated == [True]


def test_enqueue_none_safe_without_renderer():
    from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget

    updated: list = []
    fake = SimpleNamespace(
        update=lambda: updated.append(True),
        _view_update_pending=True,
    )
    MultiCompareCanvasWidget.request_view_update(fake)
    assert updated == [True]


def test_render_skip_path_emits_prepare():
    from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer

    renderer = MultiCompareRhiRenderer(SimpleNamespace())
    assert renderer.render(object()) is False
    assert "mc.prepare" in _span_names(renderer.frame_context)


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


def _fake_full_render_host():
    """Host + RHI stubs sufficient to drive ``render()`` past prepare."""
    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 400, height=lambda: 300)
    )
    rhi = SimpleNamespace(
        nextResourceUpdateBatch=lambda: SimpleNamespace(),
        clipSpaceCorrMatrix=lambda: SimpleNamespace(data=lambda: [1.0] * 16),
    )
    host = SimpleNamespace(
        _active_composition=SimpleNamespace(canvas_w=800, canvas_h=600, layers=[]),
        _sync_textures=lambda: None,
        _theme_or_palette_bg=lambda: SimpleNamespace(),
        glass_panels=None,
        update=lambda: None,
    )
    host.renderTarget = lambda: target
    host.rhi = lambda: rhi
    return host, rhi, target


def _stub_image_pass():
    return SimpleNamespace(
        apply_pending_texture_ops=lambda *a, **k: None,
        slot_texture_ids=lambda: [],
        prepare=lambda *a, **k: None,
        take_dirty_layers=lambda: {},
        generate_all_dirty_mips=lambda *a, **k: {},
        record=lambda *a, **k: None,
    )


def test_full_render_fake_path_emits_prepare_realize_mips_submit():
    """End-to-end ``render()`` with stubbed GPU boundary.

    Empty composition (no layers) still runs the sync/prepare,
    realize, mip-cascade and draw-submit phases, so one ``render()``
    call emits ``mc.prepare`` + ``mc.realize_slots`` + ``mc.mips`` +
    ``mc.submit`` on the owner context.
    """
    from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer

    host, rhi, _target = _fake_full_render_host()
    renderer = MultiCompareRhiRenderer(host)
    renderer.rhi = rhi
    renderer.target = _target
    renderer.initialized = True
    renderer.image_pass = _stub_image_pass()

    assert renderer.render(_fake_command_buffer()) is True
    names = _span_names(renderer.frame_context)
    assert {"mc.prepare", "mc.realize_slots", "mc.mips", "mc.submit"} <= names


class _RaisingFeaturePass(CanvasRenderPass):
    """Feature pass whose ``record`` raises after the pass is already open."""

    stack_role = CanvasStackRole.HUD_LABEL
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.recorded = 0

    def prepare(self, widget, ctx, resource_updates, frame_context=None) -> None:
        pass

    def record(self, command_buffer, widget, ctx, frame_context=None) -> None:
        self.recorded += 1
        raise RuntimeError("feature record failed")


def test_submit_pass_closes_when_feature_record_raises():
    """Pass lifetime: a raising feature ``record`` still ends the pass.

    ``endPass`` must run in a ``finally``. Without it the MC submit pass stays
    open on the command buffer, so the next frame records into a never-closed
    pass (stuck black frame) instead of failing once at the seam. The
    exception still propagates.
    """
    from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer

    host, rhi, _target = _fake_full_render_host()
    renderer = MultiCompareRhiRenderer(host)
    renderer.rhi = rhi
    renderer.target = _target
    renderer.initialized = True
    renderer.image_pass = _stub_image_pass()
    raising = _RaisingFeaturePass()
    renderer.feature_passes = [raising]

    command_buffer = _fake_command_buffer()
    with pytest.raises(RuntimeError, match="feature record failed"):
        renderer.render(command_buffer)

    assert raising.recorded == 1
    assert command_buffer.calls.count("beginPass") == 1
    assert command_buffer.calls.count("endPass") == 1
    assert command_buffer.calls[-1] == "endPass"


def test_zoom_burst_chain_covers_all_stages():
    """Zoom-burst repro (in-process): N synthetic wheel ticks through the
    real hooks plus the enqueue hop and one fake full render; every Wave
    D stage must appear at least once (the analyzer-side "zero missing
    stages" gate is verified by the export test below on the same span
    set)."""
    from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer
    from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget

    ctx = FrameContext()
    canvas = _FakeMcCanvas(ctx)
    for _ in range(5):
        mc_interaction.handle_wheel_event(canvas, _WheelEvent(delta_y=120))
        MultiCompareCanvasWidget.request_view_update(
            SimpleNamespace(
                _renderer=SimpleNamespace(frame_context=ctx),
                update=lambda: None,
                _view_update_pending=True,
            )
        )

    host, rhi, _target = _fake_full_render_host()
    renderer = MultiCompareRhiRenderer(host)
    # Share the wheel-tick owner context so the burst and the frame land
    # in one span set (mirrors the live path where the widget reaches
    # the renderer-owned context via widget._renderer).
    renderer.frame_context = ctx
    renderer.rhi = rhi
    renderer.target = _target
    renderer.initialized = True
    renderer.image_pass = _stub_image_pass()
    assert renderer.render(_fake_command_buffer()) is True

    assert EXPECTED_MC_STAGES <= _span_names(ctx)

    # Wheel join atoms survive export: every mc.wheel_tick event carries
    # a ``wheel-<id>`` trace_id in args (Perfetto join key).
    from engine.frame.trace_export import build_trace

    events = build_trace([ctx], pid=1)
    wheel_args = [
        event["args"]
        for event in events
        if event.get("ph") == "X" and event.get("name") == "mc.wheel_tick"
    ]
    assert len(wheel_args) == 5
    assert all(
        str(args.get("trace_id", "")).startswith("wheel-") for args in wheel_args
    )
    stage_names = {event["name"] for event in events if event.get("ph") == "X"}
    assert EXPECTED_MC_STAGES <= stage_names


def test_two_context_export_merges_frame_lanes_by_design():
    """Both tabs openable in ONE Perfetto timeline: same ``frame_id``
    from an IC and an MC context lands on ONE ``frame-N`` lane (the
    exporter maps ``tid`` ← birth frame by design)."""
    from engine.frame.trace_export import build_trace

    mc_ctx = FrameContext()
    with mc_ctx.span("mc.prepare", detail=lambda: {"framebuffer": [400, 300]}):
        pass
    ic_ctx = FrameContext()
    with ic_ctx.span("ic.prepare", detail=lambda: {"widget": "Fake"}):
        pass
    assert mc_ctx.frame_id == ic_ctx.frame_id == 0

    events = build_trace([mc_ctx, ic_ctx], pid=1)
    thread_names = [
        event
        for event in events
        if event.get("ph") == "M" and event.get("name") == "thread_name"
    ]
    # One lane for the shared birth frame (not one per context).
    assert [event["tid"] for event in thread_names] == [0]
    lane = {
        event["name"]
        for event in events
        if event.get("ph") == "X" and event.get("tid") == 0
    }
    assert {"mc.prepare", "ic.prepare"} <= lane
