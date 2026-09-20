"""docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up, seventh fix:
resolve_fallback_lod's ``atomic`` param. Default (``atomic=False``)
behavior must stay exactly as before (LOD/pyramid-level transitions keep
progressively revealing new tiles over the old ones); ``atomic=True``
(a genuine content swap) must hide ``current_items`` entirely until the
new key is fully resident, then flip over in one frame.
"""

from engine.cache.fallback_lod import resolve_fallback_lod


def test_default_progressive_merge_unchanged():
    fallback_items = ["fallback_a", "fallback_b"]
    current_items = ["current_a"]

    def build_fallback_items(prior_key):
        assert prior_key == "old"
        return fallback_items

    def drop_covered(items, current):
        assert items == fallback_items
        assert current == current_items
        return items

    new_key, plan = resolve_fallback_lod(
        key="new",
        current_items=current_items,
        more_pending=True,
        last_good_key="old",
        build_fallback_items=build_fallback_items,
        drop_covered=drop_covered,
    )

    assert new_key == "old"
    assert plan == fallback_items + current_items


def test_atomic_hides_current_items_until_promoted():
    fallback_items = ["fallback_a", "fallback_b"]
    current_items = ["current_a"]
    drop_covered_called = False

    def build_fallback_items(prior_key):
        assert prior_key == "old"
        return fallback_items

    def drop_covered(items, current):
        nonlocal drop_covered_called
        drop_covered_called = True
        return items

    new_key, plan = resolve_fallback_lod(
        key="new",
        current_items=current_items,
        more_pending=True,
        last_good_key="old",
        build_fallback_items=build_fallback_items,
        drop_covered=drop_covered,
        atomic=True,
    )

    assert new_key == "old"
    assert plan == fallback_items
    assert "current_a" not in plan
    assert not drop_covered_called


def test_atomic_promotes_once_fully_resident():
    current_items = ["current_a", "current_b"]

    new_key, plan = resolve_fallback_lod(
        key="new",
        current_items=current_items,
        more_pending=False,
        last_good_key="old",
        build_fallback_items=lambda prior_key: (_ for _ in ()).throw(
            AssertionError("build_fallback_items must not run once promoted")
        ),
        drop_covered=lambda items, current: (_ for _ in ()).throw(
            AssertionError("drop_covered must not run once promoted")
        ),
        atomic=True,
    )

    assert new_key == "new"
    assert plan == current_items

def _noop_build(prior_key):
    raise AssertionError("must not build fallback on promotion path")


def _noop_drop(items, current):
    raise AssertionError("must not filter on promotion path")


def test_cascade_pending_holds_promotion():
    """Freshly uploaded tiles have no coarse mips yet: a complete tier
    (not more_pending) must NOT promote while cascade_pending, even with
    a full current plan. Live trace 2026-09-20 frames 85-86."""
    current_items = ["current_a", "current_b"]
    new_key, plan = resolve_fallback_lod(
        key="new",
        current_items=current_items,
        more_pending=False,
        last_good_key="old",
        build_fallback_items=lambda prior_key: ["fallback_a"],
        drop_covered=lambda items, current: [],
        atomic=True,
        cascade_pending=True,
    )
    assert new_key == "old"
    assert plan == ["fallback_a"]


def test_cascade_quiescent_promotes_immediately():
    new_key, plan = resolve_fallback_lod(
        key="new",
        current_items=["current_a"],
        more_pending=False,
        last_good_key="old",
        build_fallback_items=_noop_build,
        drop_covered=_noop_drop,
        atomic=True,
        cascade_pending=False,
    )
    assert new_key == "new"
    assert plan == ["current_a"]


def test_cascade_pending_defaults_to_old_behavior():
    """Default cascade_pending=False keeps every pre-existing call site
    (multi_compare progressive reveal) byte-identical in behavior."""
    new_key, plan = resolve_fallback_lod(
        key="new",
        current_items=["current_a"],
        more_pending=False,
        last_good_key="old",
        build_fallback_items=_noop_build,
        drop_covered=_noop_drop,
        atomic=False,
    )
    assert new_key == "new"
    assert plan == ["current_a"]
