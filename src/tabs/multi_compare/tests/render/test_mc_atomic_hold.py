"""MC atomic LOD hold: no mixed-tier frame on a level transition.

Parity with image_compare's ``_atomic_level_hold`` (``use_cases/fallback.py``):
a pyramid-boundary zoom swaps the whole tier while the new one streams in
partial, so the MC base-images call site must hold the old tier whole until
the new one promotes instead of layering a partial grid over it.

Content identity (not counts alone): N indices carry N distinguishable
payloads; the hold frame asserts every payload equals the old tier's content,
the evicted-baseline frame asserts no stale payload leaks in.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from engine.cache.fallback_lod import resolve_fallback_lod
from engine.cache.lod import LevelKey
from tabs.multi_compare.scene.passes.base_images import _is_level_hold


def _content(key, index):
    """Distinguishable payload per (tier, index): identity, not a count."""
    return (key, index, f"payload-{key}-{index[0]}x{index[1]}")


def _run_hold(*, old_key, new_key, n_current=2, n_fallback=4, fallback_resident=True):
    current_items = [_content(new_key, (0, c)) for c in range(n_current)]
    fallback_items = [_content(old_key, (r, c)) for r in range(2) for c in range(2)][:n_fallback]
    assert len({item[2] for item in current_items + fallback_items}) == n_current + n_fallback
    atomic = _is_level_hold(old_key, new_key)
    new_last_good, plan = resolve_fallback_lod(
        key=new_key,
        current_items=current_items,
        more_pending=True,
        last_good_key=old_key,
        build_fallback_items=lambda _k: list(fallback_items) if fallback_resident else [],
        drop_covered=lambda fb, cur: fb,
        atomic=atomic,
    )
    return atomic, new_last_good, plan, current_items, fallback_items


def test_level_hold_decision_matrix():
    """_is_level_hold fires exactly on same-slot tier changes."""
    sid = 3
    assert _is_level_hold(sid, LevelKey(sid, 1)) is True
    assert _is_level_hold(LevelKey(sid, 1), sid) is True
    assert _is_level_hold(LevelKey(sid, 1), LevelKey(sid, 2)) is True
    assert _is_level_hold(LevelKey(sid, 2), LevelKey(sid, 1)) is True
    # Same key: promotion path, nothing to hold.
    assert _is_level_hold(sid, sid) is False
    assert _is_level_hold(LevelKey(sid, 1), LevelKey(sid, 1)) is False
    # No baseline yet: atomicity moot, engine fails open.
    assert _is_level_hold(None, LevelKey(sid, 1)) is False
    # Different slots are not one slot's tier change.
    assert _is_level_hold(sid, LevelKey(9, 1)) is False
    assert _is_level_hold(sid, 9) is False


def test_level_transition_holds_single_tier():
    """Pyramid-boundary zoom: plan carries the old tier whole, zero new tiles."""
    old_key, new_key = 3, LevelKey(3, 1)
    atomic, new_last_good, plan, current_items, fallback_items = _run_hold(
        old_key=old_key, new_key=new_key
    )
    assert atomic is True
    assert new_last_good == old_key
    # Whole old tier, payload-identical per index -- no mixed-tier frame.
    assert len(plan) == len(fallback_items)
    for got, want in zip(plan, fallback_items):
        assert got == want
        assert got[0] == old_key
    new_payloads = {item[2] for item in current_items}
    assert not (new_payloads & {item[2] for item in plan})


def test_level_transition_back_to_base_holds():
    """Zoom back to native (LevelKey -> bare sid) holds symmetrically."""
    old_key, new_key = LevelKey(3, 1), 3
    atomic, new_last_good, plan, current_items, fallback_items = _run_hold(
        old_key=old_key, new_key=new_key
    )
    assert atomic is True
    assert new_last_good == old_key
    assert [item[2] for item in plan] == [item[2] for item in fallback_items]
    assert not ({item[2] for item in current_items} & {item[2] for item in plan})


def test_level_transition_fail_open_when_baseline_evicted():
    """Evicted baseline: atomicity moot, partial current drawn, never blank."""
    old_key, new_key = 3, LevelKey(3, 1)
    atomic, new_last_good, plan, current_items, _fallback = _run_hold(
        old_key=old_key, new_key=new_key, fallback_resident=False
    )
    assert atomic is True
    assert new_last_good == old_key
    assert [item[2] for item in plan] == [item[2] for item in current_items]


def test_no_hold_without_level_transition():
    """Steady-state promotion: same key promotes, plan is current alone."""
    key = LevelKey(3, 1)
    current_items = [_content(key, (0, c)) for c in range(2)]
    atomic = _is_level_hold(key, key)
    assert atomic is False
    new_last_good, plan = resolve_fallback_lod(
        key=key,
        current_items=current_items,
        more_pending=False,
        last_good_key=key,
        build_fallback_items=lambda _k: (_ for _ in ()).throw(AssertionError("must not build")),
        drop_covered=lambda fb, cur: fb,
        atomic=atomic,
    )
    assert new_last_good == key
    assert plan == current_items


def test_call_site_passes_level_hold():
    """Guard: the MC call site opts into the level hold through its TilePolicy.

    ``resolve_fallback_lod``'s ``atomic`` is no longer passed by hand -- the
    surface's ``TilePolicy`` gates it and ``resolve_frame_fallback`` computes
    it, so the guard pins the policy-bound call and the ``is_level_hold``
    detection feeding it.
    """
    from pathlib import Path

    text = Path(__file__).resolve().parents[2] / "scene" / "passes" / "base_images.py"
    src = text.read_text(encoding="utf-8")
    assert "_is_level_hold(old_key, key)" in src
    assert "is_level_hold=_atomic_level_hold" in src
    assert "resolve_frame_fallback(" in src
    assert "TILE_POLICY," in src
