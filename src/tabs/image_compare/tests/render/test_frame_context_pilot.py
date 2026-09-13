"""P1A frame-context pilot: collector + 2 pilot integrations.

Covers ``canvas/frame_context.py`` (FrameDecision / FrameContext /
dump / reset / last-frame snapshot) and the two additive pilot writers:
mag-gate (``render_gate.py``) and fallback decision (``fallback.py``).

Additive-only contract asserted here: recording into the context never
changes outcomes — same inputs with and without ``frame_context`` produce
identical results, and no log call is removed (existing log tests keep
passing unmodified).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tabs.image_compare.canvas import frame_context as fc_mod
from tabs.image_compare.canvas.frame_context import (
    FrameContext,
    last_frame_snapshot,
    snapshot_last_frame,
)


@pytest.fixture
def ctx():
    return FrameContext()


def test_collector_holds_two_pilot_decisions_and_dump_has_reasons(ctx):
    ctx.record("mag_gate", "ran", "mag_gate dirty=True visible_overlays=1", ids=("id1",))
    ctx.record(
        "fallback",
        "skipped",
        "fallback atomic=False more_pending=False promoted=True current=2",
        ids=(("stored_0", "stored_1"), None),
    )
    assert len(ctx) == 2
    dump = ctx.dump()
    lines = dump.splitlines()
    assert len(lines) == 2
    # grep-friendly single lines: verdict + reason + ids each
    assert "mag_gate" in lines[0] and "ran" in lines[0]
    assert "dirty=True" in lines[0] and "id1" in lines[0]
    assert "fallback" in lines[1] and "skipped" in lines[1]
    assert "promoted=True" in lines[1]


def test_collector_resets_per_frame(ctx):
    ctx.record("mag_gate", "ran", "mag_gate dirty=True visible_overlays=1")
    assert len(ctx) == 1
    ctx.reset()
    assert len(ctx) == 0
    assert ctx.dump() == ""
    ctx.record("fallback", "skipped", "fallback atomic=False promoted=True")
    assert len(ctx) == 1


def test_verdict_vocabulary_rejects_unknown(ctx):
    with pytest.raises(ValueError):
        ctx.record("mag_gate", "maybe", "not a verdict")


def test_last_frame_snapshot_roundtrip(ctx):
    prev = last_frame_snapshot()
    try:
        ctx.record("mag_gate", "skipped", "mag_gate dirty=False visible_overlays=1")
        snapshot_last_frame(ctx)
        snap = last_frame_snapshot()
        assert snap is not None and len(snap) == 1
        assert snap[0].pass_name == "mag_gate"
        # snapshot is frozen: later records do not leak into it
        ctx.record("fallback", "ran", "fallback atomic=True")
        assert len(last_frame_snapshot()) == 1
    finally:
        if prev is None:
            fc_mod._last_frame_snapshot = None
        else:
            fc_mod._last_frame_snapshot = prev


# ---------------------------------------------------------------------------
# renderer wiring: context is born in render(), snapshot on skip path
# ---------------------------------------------------------------------------


def test_renderer_creates_context_and_snapshots_skipped_frame():
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    prev = last_frame_snapshot()
    try:
        r = RhiCanvasRenderer()
        assert isinstance(r.frame_context, FrameContext)
        widget = SimpleNamespace(renderTarget=lambda: None)
        assert r.render(widget, object(), None) is False
        assert last_frame_snapshot() is not None
        assert len(r.frame_context) == 0
    finally:
        if prev is None:
            fc_mod._last_frame_snapshot = None
        else:
            fc_mod._last_frame_snapshot = prev


# ---------------------------------------------------------------------------
# fallback pilot: records decision, outcome identical with/without context
# ---------------------------------------------------------------------------


def _fallback_renderer(last_good):
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    r = RhiCanvasRenderer()
    r._last_good_texture_keys, r._last_good_diff_key = last_good
    r._prev_sources_is_same = False
    r._content_swap_active = False
    return r


def _run_fallback(r, monkeypatch, *, texture_keys, last_good_pending, source_changed, frame_context):
    import tabs.image_compare.canvas.rhi_renderer.use_cases.fallback as fb

    monkeypatch.setattr(fb, "build_array_draw_plan", lambda *a, **k: ["fb"])
    monkeypatch.setattr(fb, "drop_covered_fallback_items", lambda f, c, base: f)
    base = SimpleNamespace(letterbox1=(0.0, 0.0, 0.5, 1.0), letterbox2=(0.5, 0.0, 0.5, 1.0))
    return r._resolve_fallback_plan(
        tile_service=SimpleNamespace(),
        texture_keys=texture_keys,
        diff_source_key=None,
        base_image=base,
        sampler_name="linear",
        viewport_zoom=(1.0, 1.0),
        viewport_offset=(0.0, 0.0),
        main_more_pending=last_good_pending,
        current_array_plan=["cur"],
        source_changed=source_changed,
        rekeyed={},
        current_sources_is_same=False,
        frame_context=frame_context,
    )


def test_fallback_records_ran_and_outcome_unchanged(monkeypatch):
    ctx = FrameContext()
    keys = (("stored_0", "stored_1"), None)
    r = _fallback_renderer(keys)
    # new content + more pending -> atomic hold: fallback engages (ran)
    new_key, plan = _run_fallback(
        r, monkeypatch, texture_keys=("new_0", "new_1"),
        last_good_pending=True, source_changed=True, frame_context=ctx,
    )
    assert len(ctx) == 1
    assert ctx._decisions[0].pass_name == "fallback"
    assert ctx._decisions[0].verdict == "ran"
    assert "atomic=True" in ctx.dump()

    # parity: same frame without context resolves identically
    r2 = _fallback_renderer(keys)
    new_key2, plan2 = _run_fallback(
        r2, monkeypatch, texture_keys=("new_0", "new_1"),
        last_good_pending=True, source_changed=True, frame_context=None,
    )
    assert (new_key, plan) == (new_key2, plan2)


def test_fallback_records_skipped_on_clean_promotion(monkeypatch):
    ctx = FrameContext()
    keys = (("stored_0", "stored_1"), None)
    r = _fallback_renderer(keys)
    new_key, plan = _run_fallback(
        r, monkeypatch, texture_keys=("stored_0", "stored_1"),
        last_good_pending=False, source_changed=False, frame_context=ctx,
    )
    assert new_key == keys
    assert len(ctx) == 1
    assert ctx._decisions[0].verdict == "skipped"
    assert "promoted=True" in ctx.dump()


# ---------------------------------------------------------------------------
# mag-gate pilot: dirty rebuild records ran, clean frame records skipped
# ---------------------------------------------------------------------------


def _mag_presenter(rebuilt):
    image_label = SimpleNamespace(_source_images_ready=True, _source_image_ids=["id1", "id2"])
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            interaction_state=SimpleNamespace(resize_in_progress=False),
            view_state=SimpleNamespace(showing_single_image_mode=0),
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(unification_in_progress=False),
                image_state=SimpleNamespace(image1=None, image2=None),
            ),
        ),
        get_session_state_slot=lambda name: object(),
    )
    return SimpleNamespace(
        main_window_app=SimpleNamespace(
            _is_ui_stable=True, isVisible=lambda: True, isMinimized=lambda: False,
        ),
        store=store,
        widget=SimpleNamespace(isVisible=lambda: True, image_label=image_label),
        overlay=SimpleNamespace(
            get_signature=lambda: "sig1",
            rebuild_overlay=lambda: rebuilt.append(1),
        ),
        get_current_label_dimensions=lambda: (400, 400),
        _last_mag_signature=None,
    )


def test_mag_gate_records_ran_then_skipped(monkeypatch):
    import tabs.image_compare.presenters.image_canvas.background_parts.use_cases.render_gate as rg

    monkeypatch.setattr(rg, "update_comparison_geometry", lambda *a, **k: None)
    monkeypatch.setattr(rg, "handle_have_gate", lambda *a, **k: False)
    monkeypatch.setattr(rg, "handle_background", lambda *a, **k: False)
    monkeypatch.setattr(
        rg,
        "_peek_sources",
        lambda presenter, doc: {
            "source1": "s1", "source2": "s2",
            "peeked_pixel1": None, "peeked_pixel2": None,
            "peeked_preview1": None, "peeked_preview2": None,
            "path1": "a", "path2": "b",
        },
    )

    def fake_query(store, capability_id, default=None):
        if capability_id == "overlay.all_states":
            return [{"visible": True}]
        if capability_id == "overlay.enabled":
            return True
        return default

    monkeypatch.setattr(rg, "_query_overlay", fake_query)

    rebuilt: list = []
    presenter = _mag_presenter(rebuilt)
    ctx = FrameContext()

    # frame 1: signature changed -> rebuild runs, verdict ran
    assert rg.update_comparison_if_needed(presenter, frame_context=ctx) is True
    assert rebuilt == [1]
    assert len(ctx) == 1
    assert ctx._decisions[0].pass_name == "mag_gate"
    assert ctx._decisions[0].verdict == "ran"
    assert "dirty=True" in ctx._decisions[0].reason

    # frame 2: same signature -> clean, verdict skipped, no rebuild
    assert rg.update_comparison_if_needed(presenter, frame_context=ctx) is False
    assert rebuilt == [1]
    assert len(ctx) == 2
    assert ctx._decisions[1].verdict == "skipped"
    assert "dirty=False" in ctx.dump()
