"""P2 engine: frame-bus envelope enforced, ids record-only, join continuity.

``record()`` enforces the envelope (non-empty pass_name, verdict
vocabulary) but never interprets ``ids`` — non-schema atoms ride through
verbatim (pinned pilot precedent). ``reset()`` archives EVERY frame's
counter deltas (including empty maps) so ``archived_frame_ids`` is a
continuous join key across the empty verdict frames ``past_decisions``
deliberately skips; ``count()`` stays cumulative while ``count_frame()`` /
``counts_for_frame()`` expose the per-frame view.
"""

from __future__ import annotations

import pytest

from engine.frame.context import FrameContext, make_ids


def test_pass_name_envelope_enforced():
    ctx = FrameContext()
    with pytest.raises(ValueError):
        ctx.record("", "ran", "empty pass")
    with pytest.raises(ValueError):
        ctx.record(None, "ran", "none pass")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ctx.record("mag_gate", "maybe", "bad verdict")


def test_ids_schema_is_record_only_not_enforced():
    ctx = FrameContext()
    decision = ctx.record("mag_gate", "ran", "reason", ids=("id1",))
    assert decision.ids == ("id1",)
    tagged = ctx.record("fallback", "skipped", "r", ids=make_ids(0, "a"))
    assert tagged.ids[0] == "frame=0"


def test_empty_frames_archive_counts_for_join_continuity():
    ctx = FrameContext()
    ctx.record("mag_gate", "ran", "x")
    ctx.reset()  # frame 0: decisions, no bumps
    ctx.reset()  # frame 1: empty
    ctx.reset()  # frame 2: empty
    ctx.record("fallback", "ran", "y")
    ctx.bump("wheel-tick")
    ctx.reset()  # frame 3: decisions + bumps
    # Verdict window still skips empties (pinned behavior)...
    assert [fid for fid, _ in ctx.past_decisions] == [0, 3]
    # ...but the counter archive joins continuously, empties included.
    assert ctx.archived_frame_ids == (0, 1, 2, 3)
    assert ctx.has_frame(1) and ctx.has_frame(3)
    assert not ctx.has_frame(99)
    assert ctx.counts_for_frame(1) == {}
    assert ctx.counts_for_frame(3) == {"wheel-tick": 1}


def test_per_frame_counters_live_and_cumulative():
    ctx = FrameContext()
    assert ctx.count("w") == 0
    assert ctx.count_frame("w") == 0
    assert ctx.bump("w") == 1
    assert ctx.bump("w") == 2
    assert ctx.count("w") == 2 and ctx.count_frame("w") == 2
    ctx.reset()  # frame 0 archived with deltas {"w": 2}
    assert ctx.count("w") == 2, "cumulative survives reset"
    assert ctx.count_frame("w") == 0, "live delta restarts per frame"
    assert ctx.counts_for_frame(0) == {"w": 2}
    assert ctx.counts_for_frame(ctx.frame_id) == {}
    assert ctx.counts_for_frame(999) == {}
    ctx.bump("w", amount=5)
    assert ctx.counts_for_frame(ctx.frame_id) == {"w": 5}
    assert ctx.count("w") == 7
