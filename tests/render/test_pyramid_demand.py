"""D3 unit tests: ``PyramidDemandService`` + ``DemandPolicy``.

Non-blind: every assertion is computed against an independently re-stated
expectation (the raw ``demand_level``/``dest_scale_fit`` math, the documented
``TiledImageSource`` ordering) and the fakes record what they were asked, so a
reversed ``levels_sequence``, a swallowed ``ensure_level`` call, or a
wrong-axis fit all fail loudly. No Qt, no real store/coordinator.
"""

import pytest

from engine.cache.lod import LevelKey, demand_level, dest_scale_fit
from engine.cache.pyramid_demand import DemandPolicy, PyramidDemandService


class _FakeStore:
    """Minimal ``PyramidPixelStore``-shaped stand-in (no Qt, no files)."""

    def __init__(
        self,
        *,
        size=(5000, 3000),
        level_count=4,
        built=(),
        generation=7,
    ):
        self.size = size
        self.level_count = level_count
        self._built = set(built)
        self.generation = generation
        self._levels = {level: f"store-L{level}" for level in range(level_count)}

    def is_level_built(self, k):
        return k in self._built

    def level_if_built(self, k):
        if k not in self._built:
            return None
        return self._levels.get(k)


class _FakeCoordinator:
    def __init__(self, *, raises=False):
        self.calls = []
        self._raises = raises

    def demand_level(self, store, k, *, should_abort=None, on_ready=None):
        self.calls.append(
            {
                "store": store,
                "k": k,
                "should_abort": should_abort,
                "on_ready": on_ready,
            }
        )
        if self._raises:
            raise RuntimeError("coordinator boom")
        return True


# ---------------------------------------------------------------------------
# level_for_view: parity with the raw lod math.
# ---------------------------------------------------------------------------

_FIT_CASES = [
    ((800, 600), 1.0),
    ((800, 600), 0.5),
    ((1920, 1080), 0.25),
    ((600, 800), 4.0),
    ((5000, 3000), 0.125),
]

_SRC = (5000, 3000)
_LEVEL_COUNT = 4


def test_level_for_view_parity_with_raw_math():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    store = _FakeStore(size=_SRC, level_count=_LEVEL_COUNT)
    for fb, zoom in _FIT_CASES:
        expected = demand_level(dest_scale_fit(tuple(fb), _SRC, zoom), _LEVEL_COUNT)
        got = svc.level_for_view(store, fb_size=fb, zoom=zoom)
        assert got == expected, (fb, zoom, got, expected)


def test_level_for_view_honours_explicit_level_count_override():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    store = _FakeStore(size=_SRC, level_count=_LEVEL_COUNT)
    fb, zoom = (1920, 1080), 0.25
    # An explicit, smaller level_count clamps the answer the raw math gives.
    assert svc.level_for_view(store, fb_size=fb, zoom=zoom, level_count=2) == (
        demand_level(dest_scale_fit(tuple(fb), _SRC, zoom), 2)
    )


def test_level_for_view_invalid_size_and_garbage_never_raise():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    assert svc.level_for_view(_FakeStore(size=(0, 3000)), fb_size=(800, 600), zoom=1.0) == 0
    assert svc.level_for_view(_FakeStore(size=(5000, 0)), fb_size=(800, 600), zoom=1.0) == 0

    class _BadStore:
        size = None
        level_count = "not-an-int"

    assert svc.level_for_view(_BadStore(), fb_size=(800, 600), zoom=1.0) == 0
    assert svc.level_for_view(None, fb_size=(800, 600), zoom=1.0) == 0


# ---------------------------------------------------------------------------
# levels_sequence: coarsest-first, finest (level 0) last.
# ---------------------------------------------------------------------------


def test_levels_sequence_coarsest_first_finest_last():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    key = object()
    store = _FakeStore(size=_SRC, level_count=4, built={0, 1, 2}, generation=11)
    seq = svc.levels_sequence(store, key=key)

    assert len(seq) == 3
    # Coarsest is first, level 0 (finest) is last with a None level key.
    assert seq[0][0] == LevelKey(key, 2, 11)
    assert seq[1][0] == LevelKey(key, 1, 11)
    assert seq[2][0] is None
    # Position fixes the level number: last entry is level 0's store.
    assert seq[2][1] == store.level_if_built(0)
    assert seq[0][1] == store.level_if_built(2)

    # Anti-tautology: the sequence is NOT finest-first. A reversed
    # implementation ([None, LevelKey(...,1), LevelKey(...,2)]) must fail.
    assert [entry[0] for entry in seq] != [
        None,
        LevelKey(key, 1, 11),
        LevelKey(key, 2, 11),
    ]


def test_levels_sequence_uses_highest_built_level_as_contiguous_top():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    key = object()
    # Pyramid builds upward, so built == 0..m; only 0..3 built gives m=3.
    store = _FakeStore(level_count=6, built={0, 1, 2, 3}, generation=5)
    seq = svc.levels_sequence(store, key=key)
    assert [entry[0] for entry in seq] == [
        LevelKey(key, 3, 5),
        LevelKey(key, 2, 5),
        LevelKey(key, 1, 5),
        None,
    ]
    # A gap is not produced by this API: the contiguous range m..0 is emitted.
    assert [entry[0] for entry in seq].count(None) == 1


def test_levels_sequence_empty_when_nothing_built():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    assert svc.levels_sequence(_FakeStore(built=set()), key=object()) == ()


def test_levels_sequence_contiguous_m_policy_no_gap():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    key = object()
    # A lone built level-2 stands in for the (API-impossible) gap case; the
    # policy is contiguous m..0, so no gap entry is emitted and the level-0
    # slot is filled in even when its base store lookup is not "built".
    store = _FakeStore(level_count=4, built={2}, generation=3)
    seq = svc.levels_sequence(store, key=key)
    assert [entry[0] for entry in seq] == [LevelKey(key, 2, 3), LevelKey(key, 1, 3), None]
    assert seq[-1] == (None, None)


def test_levels_sequence_never_raises_on_dead_store():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())

    class _BadStore:
        level_count = "nope"

    assert svc.levels_sequence(_BadStore(), key=object()) == ()


# ---------------------------------------------------------------------------
# level_store: fail-closed.
# ---------------------------------------------------------------------------


def test_level_store_returns_built_and_none_for_unbuilt():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())
    store = _FakeStore(built={0, 1})
    assert svc.level_store(store, 0) == store._levels[0]
    assert svc.level_store(store, 1) == store._levels[1]
    assert svc.level_store(store, 3) is None


def test_level_store_never_raises():
    svc = PyramidDemandService(coordinator=_FakeCoordinator())

    class _BadStore:
        def level_if_built(self, k):
            raise RuntimeError("boom")

    assert svc.level_store(_BadStore(), 2) is None


# ---------------------------------------------------------------------------
# ensure_level: base/already-built no-ops, unbuilt forwards, swallow errors.
# ---------------------------------------------------------------------------


def test_ensure_level_base_and_already_built_are_noops():
    coord = _FakeCoordinator()
    svc = PyramidDemandService(coordinator=coord)
    store = _FakeStore(built={0, 1})
    svc.ensure_level(store, 0)
    svc.ensure_level(store, 1)
    svc.ensure_level(store, -3)
    assert coord.calls == []


def test_ensure_level_forwards_to_coordinator_once():
    coord = _FakeCoordinator()
    svc = PyramidDemandService(coordinator=coord)
    store = _FakeStore(built={0})

    def _abort():
        return False

    def _ready(payload):
        return None

    svc.ensure_level(store, 2, should_abort=_abort, on_ready=_ready)
    assert len(coord.calls) == 1
    call = coord.calls[0]
    assert call["store"] is store
    assert call["k"] == 2
    assert call["should_abort"] is _abort
    assert call["on_ready"] is _ready


def test_ensure_level_swallows_coordinator_exception():
    coord = _FakeCoordinator(raises=True)
    svc = PyramidDemandService(coordinator=coord)
    # Must not propagate.
    svc.ensure_level(_FakeStore(built={0}), 3)


# ---------------------------------------------------------------------------
# DemandPolicy.
# ---------------------------------------------------------------------------


def test_demand_policy_defaults():
    p = DemandPolicy()
    assert p.cap_edge is None
    assert p.mode == "demand"
    assert p.settle is False


def test_demand_policy_rejects_unknown_mode():
    with pytest.raises(ValueError):
        DemandPolicy(mode="nope")
    # Both documented modes construct.
    assert DemandPolicy(mode="eager").mode == "eager"
    assert DemandPolicy(mode="demand").mode == "demand"
