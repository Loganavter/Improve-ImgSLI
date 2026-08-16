"""docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up, seventh fix:
resolve_fallback_lod's ``atomic`` param. Default (``atomic=False``)
behavior must stay exactly as before (LOD/pyramid-level transitions keep
progressively revealing new tiles over the old ones); ``atomic=True``
(a genuine content swap) must hide ``current_items`` entirely until the
new key is fully resident, then flip over in one frame.
"""

from shared.rendering.fallback_lod import resolve_fallback_lod


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