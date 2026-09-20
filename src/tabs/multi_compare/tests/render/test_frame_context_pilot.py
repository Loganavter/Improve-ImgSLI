"""MC frame-context pilot: renderer ownership + bus vocabulary proof (wave C).

Mirrors ``src/tabs/image_compare/tests/render/test_frame_context_pilot.py``
for Multi Compare (plan-mc-frame-context-2026-09-20, Wave C). Waves A+B are
the production side (renderer owns ``FrameContext``; passes record into
it); this file is PROOF ONLY — no production code is touched here.

Covered (all with fakes, no GPU):
- context advances per ``render()`` call, including the early-skip paths
  (``frame_id`` increments across renders);
- every record carries a ``frame=N`` id (``ids[0] == frame_tag(frame_id)``);
- ``snapshot_last_frame`` is readable after ``render()`` and holds this
  frame's passes;
- ``release()``-reinit preserves context identity AND ``frame_id``
  continuity (create-once guard pin: no ``frame_id`` restart);
- at least one record per bus phase is present after a synthetic render
  (``prepare_frame``, ``realize_slots``/``lod_commit``, ``resourceUpdate``,
  ``mips``, ``submit``, ``coverage``/``fallback``; tick marker via
  ``_frame_context_from_widget`` unit-level).

Fake-coverage note (wave D / perf-debugger scope): a full live ``render()``
past ``prepare_frame`` needs a real QRhi host (``renderTarget()``,
``clipSpaceCorrMatrix``, command buffer passes), which fakes cannot reach
headless. The per-phase records below are therefore asserted at two
levels — (1) ``FrameContext`` unit-level (reset/snapshot/ids vocabulary)
and (2) renderer-level with the lightest fake that reaches ``prepare`` +
snapshot (the not-initialized early-skip path). Live per-pass writer
coverage (``lod_commit``/``realize_slots``/``submit`` through real passes)
belongs to wave D with a live backend, not to this pilot.
"""

from __future__ import annotations

from types import SimpleNamespace

from engine.frame import context as fc_mod
from engine.frame.context import (
    FrameContext,
    frame_tag,
    last_frame_snapshot,
    make_ids,
    snapshot_last_frame,
)


def _fresh_renderer():
    """Renderer with fakes, never initialized: ``render()`` takes the
    not-initialized early-skip path (``prepare_frame``/skipped + snapshot,
    returns False). ``mc_first_frame_debug`` is env-gated so a bare
    ``SimpleNamespace`` host is enough."""
    from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer

    return MultiCompareRhiRenderer(SimpleNamespace())


def _save_snapshot():
    return last_frame_snapshot()


def _restore_snapshot(prev):
    if prev is None:
        fc_mod._last_frame_snapshot = None
    else:
        fc_mod._last_frame_snapshot = prev


# ---------------------------------------------------------------------------
# (a) context advances per render, including early-skip paths
# ---------------------------------------------------------------------------


def test_context_advances_per_render_including_early_skip():
    prev = _save_snapshot()
    try:
        renderer = _fresh_renderer()
        assert renderer.frame_context.frame_id == 0
        assert renderer.render(object()) is False
        assert renderer.frame_context.frame_id == 1
        assert renderer.render(object()) is False
        assert renderer.frame_context.frame_id == 2
    finally:
        _restore_snapshot(prev)


# ---------------------------------------------------------------------------
# (b) records carry frame=N ids (ids[0] == frame_tag)
# ---------------------------------------------------------------------------


def test_records_carry_frame_tag_ids():
    prev = _save_snapshot()
    try:
        renderer = _fresh_renderer()
        renderer.render(object())
        decisions = list(renderer.frame_context)
        assert decisions, "early-skip render must record prepare_frame/skipped"
        for decision in decisions:
            assert decision.ids, f"{decision.pass_name} must carry ids"
            assert decision.ids[0] == frame_tag(renderer.frame_context.frame_id)
            assert decision.ids[0] == "frame=1"
    finally:
        _restore_snapshot(prev)


def test_make_ids_puts_frame_tag_first():
    ids = make_ids(7, "atom")
    assert ids[0] == "frame=7"
    assert ids[1:] == ("atom",)


# ---------------------------------------------------------------------------
# (c) snapshot_last_frame readable after render, holds this frame's passes
# ---------------------------------------------------------------------------


def test_snapshot_last_frame_readable_after_render():
    prev = _save_snapshot()
    try:
        renderer = _fresh_renderer()
        renderer.render(object())
        snap = last_frame_snapshot()
        assert snap is not None and len(snap) >= 1
        assert snap[0].pass_name == "prepare_frame"
        assert snap[0].verdict == "skipped"
        assert snap[0].ids[0] == "frame=1"
        # snapshot is per-frame: the next render replaces it with the new
        # frame's passes (later *records* into an old context never leak
        # in — the tuple is frozen at snapshot time).
        renderer.render(object())
        snap2 = last_frame_snapshot()
        assert snap2 is not None and len(snap2) == len(snap)
        assert snap2[0].ids[0] == "frame=2"
        assert snap[0].ids[0] == "frame=1"
    finally:
        _restore_snapshot(prev)


# ---------------------------------------------------------------------------
# (d) release()-reinit preserves context identity AND frame_id continuity
# ---------------------------------------------------------------------------


def test_release_reinit_preserves_context_identity_and_frame_id():
    prev = _save_snapshot()
    try:
        renderer = _fresh_renderer()
        renderer.render(object())
        renderer.render(object())
        assert renderer.frame_context.frame_id == 2
        owned = renderer.frame_context
        renderer.release()
        # create-once guard: reinit reattaches the existing context object,
        # it must not mint a fresh FrameContext (frame_ids would restart).
        assert renderer.frame_context is owned
        assert renderer.frame_context.frame_id == 2
        assert renderer.render(object()) is False
        assert renderer.frame_context.frame_id == 3
        snap = last_frame_snapshot()
        assert snap is not None and snap[0].ids[0] == "frame=3"
    finally:
        _restore_snapshot(prev)


# ---------------------------------------------------------------------------
# (e) one record per bus phase after a synthetic render + tick marker
# ---------------------------------------------------------------------------


#: MC decision-bus vocabulary (mirrors the IC pass names; see
#: plan-mc-frame-context-2026-09-20 §Ownership). One synthetic record per
#: phase, as written by waves A+B: renderer (prepare_frame/resourceUpdate/
#: mips), residency (lod_commit/realize_slots), base_images
#: (fallback/coverage/submit), feature passes (overlay.*), interaction
#: (invalidate.mc_zoom_tick).
_BUS_PHASES = (
    "prepare_frame",
    "lod_commit",
    "realize_slots",
    "resourceUpdate",
    "mips",
    "fallback",
    "coverage",
    "submit",
)


def test_bus_phase_vocabulary_present_after_synthetic_render():
    ctx = FrameContext()
    frame_id = ctx.begin_frame()
    for phase in _BUS_PHASES:
        ctx.record(phase, "ran", f"{phase} synthetic", ids=make_ids(frame_id, "synthetic"))
    # tick marker resolves through the widget, like the live wheel path
    # (interaction._frame_context_from_widget reads widget._renderer).
    from tabs.multi_compare.canvas.interaction import _frame_context_from_widget

    widget = SimpleNamespace(_renderer=SimpleNamespace(frame_context=ctx))
    tick_context = _frame_context_from_widget(widget)
    assert tick_context is ctx
    tick_context.record_invalidation(
        "mc_zoom_tick",
        "wheel tick delta=120 zoom 1.000000->1.100000 fit_cache=miss",
        ids=make_ids(frame_id, 120, (1.0, 1.1), "fit-miss"),
    )
    snapshot_last_frame(ctx)

    by_pass = {d.pass_name: d for d in ctx}
    for phase in _BUS_PHASES:
        assert phase in by_pass, f"bus phase {phase!r} missing after synthetic render"
        assert by_pass[phase].ids[0] == frame_tag(frame_id)
    assert "invalidate.mc_zoom_tick" in by_pass
    assert by_pass["invalidate.mc_zoom_tick"].ids[0] == frame_tag(frame_id)

    snap = last_frame_snapshot()
    assert snap is not None and len(snap) == len(_BUS_PHASES) + 1


def test_frame_context_from_widget_none_safe_for_fakes():
    from tabs.multi_compare.canvas.interaction import _frame_context_from_widget

    assert _frame_context_from_widget(SimpleNamespace()) is None
    assert _frame_context_from_widget(object()) is None
