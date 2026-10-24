"""IC parity with MC for the Phase 9 mip cascade: skip flag + deferred re-kick.

Both canvas tabs are on-demand, so a cascade group deferred by
``MIPS_CASCADE_TIME_BUDGET_MS`` gets no further ``render()`` call unless the
renderer asks for one. Multi Compare already handles that (its scene renderer
records the deferral and calls ``self.host.update()``); Image Compare only
logged ``deferred=%d`` and waited for the 250 ms DnD keep-warm tick, so a
recycled array layer kept sampling the previous occupant through its coarse
mips. Same story for the ``IMGSLI_SKIP_MIP_CASCADE`` bisection flag: MC
honoured it, IC did not, so one env var could not A/B both tabs.

Red-before (pre-change tree): ``_run_mips_cascade`` and
``_request_cascade_rekick`` do not exist, a deferred cascade produces no
follow-up ``update()``, and ``IMGSLI_SKIP_MIP_CASCADE`` does not reach IC.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _renderer():
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    return RhiCanvasRenderer()


def _widget():
    updates: list[int] = []
    return SimpleNamespace(update=lambda: updates.append(1)), updates


# ---------------------------------------------------------------------------
# (a) a deferred cascade group requests exactly ONE follow-up repaint
# ---------------------------------------------------------------------------


def test_deferred_cascade_requests_exactly_one_follow_up_repaint():
    r = _renderer()
    widget, updates = _widget()
    r._pending_dirty_layers = {0: {3, 4}}

    rekick = getattr(r, "_request_cascade_rekick", None)
    assert rekick is not None, (
        "RhiCanvasRenderer has no deferred-cascade re-kick seam: a cascade "
        "group deferred by the time budget waits for the 250 ms keep-warm "
        "tick, so a recycled array layer keeps sampling stale upper mips"
    )

    assert rekick(widget) is True
    assert updates == [1]
    # The tracer sees the deferral (same source name MC records).
    assert [d.pass_name for d in r.frame_context.invalidations()] == [
        "invalidate.cascade_deferred"
    ]


# ---------------------------------------------------------------------------
# (b) IMGSLI_SKIP_MIP_CASCADE skips the cascade call and clears pending
# ---------------------------------------------------------------------------


def test_skip_flag_bypasses_cascade_and_clears_pending(monkeypatch):
    import tabs.image_compare.canvas.rhi_renderer.renderer as renderer_mod

    r = _renderer()
    calls: list[int] = []
    # Pending would normally survive the cascade; with the flag on it must not.
    r.resources = SimpleNamespace(
        generate_all_dirty_mips=lambda *a, **k: calls.append(1) or {0: {1}}
    )
    r._pending_dirty_layers = {0: {1}}

    run = getattr(r, "_run_mips_cascade", None)
    assert run is not None, (
        "RhiCanvasRenderer does not honour IMGSLI_SKIP_MIP_CASCADE — MC does, "
        "so one env var cannot A/B the cascade in both tabs"
    )

    monkeypatch.setattr(renderer_mod, "_SKIP_MIP_CASCADE", True)
    pending, ms = run(object(), {0: {1}}, 1)

    assert calls == [], "skip flag must not reach generate_all_dirty_mips"
    assert pending == {}
    assert ms == 0.0


# ---------------------------------------------------------------------------
# (c) no busy loop: an empty pending map requests nothing
# ---------------------------------------------------------------------------


def test_no_repaint_request_without_deferral():
    r = _renderer()
    widget, updates = _widget()

    rekick = getattr(r, "_request_cascade_rekick", None)
    assert rekick is not None, "missing deferred-cascade re-kick seam"

    assert rekick(widget) is False
    assert updates == []
    assert r.frame_context.invalidations() == []


# ---------------------------------------------------------------------------
# flag off: the cascade still runs and its deferred map is returned
# ---------------------------------------------------------------------------


def test_cascade_runs_when_flag_off_and_returns_deferred_map(monkeypatch):
    import tabs.image_compare.canvas.rhi_renderer.renderer as renderer_mod

    r = _renderer()
    calls: list[int] = []
    r.resources = SimpleNamespace(
        generate_all_dirty_mips=lambda *a, **k: calls.append(1) or {0: {1}}
    )

    run = getattr(r, "_run_mips_cascade", None)
    assert run is not None, "missing mips-cascade seam"

    monkeypatch.setattr(renderer_mod, "_SKIP_MIP_CASCADE", False)
    pending, ms = run(None, {0: {1}}, 1)

    assert calls == [1]
    assert pending == {0: {1}}
    assert isinstance(ms, float) and ms >= 0.0


# ---------------------------------------------------------------------------
# env truth table must be byte-identical to MC's
# ("" / 0 / false / no / off = off, anything else = on)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", False),
        ("0", False),
        ("false", False),
        (" FALSE ", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("yes", True),
        (" ON ", True),
    ],
)
def test_skip_flag_truth_table_matches_multi_compare(raw, expected):
    from tabs.image_compare.canvas.rhi_renderer.renderer import (
        _skip_mip_cascade_requested,
    )

    assert _skip_mip_cascade_requested(raw) is expected


# ---------------------------------------------------------------------------
# wiring: render() itself must re-kick, not just the seam
# ---------------------------------------------------------------------------


def test_render_rekicks_widget_when_cascade_defers(monkeypatch):
    """One real ``render()`` with a stubbed GPU boundary: the deferred map the
    cascade returns becomes exactly one ``widget.update()`` call."""
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
    monkeypatch.setattr(fs, "build_render_runtime_context", lambda widget: ctx)
    monkeypatch.setattr(fs, "should_render_blank_white", lambda scene: False)
    monkeypatch.setattr(
        fs,
        "_viewport_zoom_offset_for_tile",
        lambda *a, **k: ((1.0, 1.0), (0.0, 0.0)),
    )
    renderer.resources.apply_pending_uploads = lambda *a, **k: None
    # The cascade defers one group (time budget), as it does on a first touch
    # of a recycled layer.
    renderer.resources.generate_all_dirty_mips = lambda *a, **k: {0: {5}}
    renderer.rhi = SimpleNamespace(nextResourceUpdateBatch=lambda: SimpleNamespace())

    target = SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 100, height=lambda: 80)
    )
    clear = SimpleNamespace(
        red=lambda: 0, green=lambda: 0, blue=lambda: 0, alpha=lambda: 255
    )
    updates: list[int] = []
    widget = SimpleNamespace(
        _rhi_renderer=renderer,
        renderTarget=lambda: target,
        width=lambda: 100,
        height=lambda: 80,
        fixedColorBufferSize=lambda: SimpleNamespace(
            width=lambda: 100, height=lambda: 80
        ),
        update=lambda: updates.append(1),
    )
    command_buffer = SimpleNamespace(
        resourceUpdate=lambda batch: None,
        beginPass=lambda *a, **k: None,
        endPass=lambda: None,
    )

    assert renderer.render(widget, command_buffer, clear) is True
    assert updates == [1]
