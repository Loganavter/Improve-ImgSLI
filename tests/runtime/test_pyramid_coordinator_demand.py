"""Demand entry on PyramidBuildCoordinator (E2 lazy-LOD trigger).

Covers ``PyramidBuildCoordinator.demand_level`` next to the eager loop:

* demand builds exactly to ``k`` (bounded loop — never full);
* already-built ``k`` returns True with no worker spawned;
* zoom-change pattern (``k1`` then ``k2 > k1``) builds only the delta;
* walk-abort mid-build builds nothing further and dismisses the toast;
* invalid / pre-aborted / in-flight demands return False;
* eager ``start_build`` regression (full build still works).
"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakePyramid:
    """Minimal PyramidPixelStore shape (E1 owns the real engine API)."""

    def __init__(self, total=5):
        self._built = 1  # level 0 exists (base)
        self._total = total
        self.build_calls = 0

    @property
    def level_count(self):
        return self._built

    @property
    def valid(self):
        return True

    def is_complete(self):
        return self._built >= self._total

    def is_level_built(self, k):
        if isinstance(k, bool) or not isinstance(k, int):
            return False
        return 0 <= k < self._built

    def build_next_level(self, should_abort=None):
        self.build_calls += 1
        if should_abort is not None:
            try:
                if bool(should_abort()):
                    return False
            except Exception:
                return False
        if self.is_complete():
            return False
        self._built += 1
        return True


class _InlinePool:
    """Thread pool stand-in that runs the worker synchronously."""

    def __init__(self):
        self.workers = []

    def start(self, worker):
        self.workers.append(worker)
        worker.run()


class _ManualPool:
    """Thread pool stand-in that captures workers for manual driving."""

    def __init__(self):
        self.workers = []

    def start(self, worker):
        self.workers.append(worker)


class _FakeToast:
    """LoadingToastCoordinator stand-in (bump/progress/finish/dismiss)."""

    def __init__(self):
        self.bumped = []
        self.progress = []
        self.finished = []
        self.dismissed = []

    def bump_pyramid_started(self, slot_id):
        self.bumped.append(slot_id)

    def set_progress(self, slot_id, percent):
        self.progress.append((slot_id, percent))

    def finish(self, slot_id):
        self.finished.append(slot_id)

    def dismiss(self, slot_id):
        self.dismissed.append(slot_id)


def _make(pool, toast=None, pyramid=None):
    from tabs._shared.pyramid import PyramidBuildCoordinator

    return PyramidBuildCoordinator(
        get_thread_pool=lambda: pool,
        toast_coordinator=toast,
        get_pyramid=lambda store: pyramid,
        estimate_levels=lambda w, h: 5,
    )


def _store():
    return SimpleNamespace(width=4096, height=4096)


def test_demand_builds_exactly_to_k(qapp):
    """Demand k=2 builds L1..L2 only — bounded, never full."""
    pool, toast = _InlinePool(), _FakeToast()
    pyr = _FakePyramid(total=5)
    coord = _make(pool, toast, pyr)
    store = _store()

    seen = []
    hooks = []
    assert coord.demand_level(
        store, 2, slot_id=7, toast_hook=hooks.append, on_ready=seen.append
    ) is True

    assert pyr.level_count == 3, "exactly L1..L2 land"
    assert pyr.build_calls == 2, "bounded loop — never build_all"
    assert pyr.is_level_built(2) is True
    assert pyr.is_complete() is False, "demand must not run to complete"
    assert len(pool.workers) == 1
    # toast routing: bump on kick, progress per level, finish on ready
    assert toast.bumped == [7]
    assert toast.progress, "per-level progress expected"
    assert toast.finished == [7]
    assert not toast.dismissed
    # hook observer mirrors the toast path
    assert hooks[0] == "started"
    assert hooks[-1] == "ready"
    assert "progress" in hooks
    # on_ready fan-out sees every level; the landing payload is complete
    assert len(seen) == 2
    assert seen[-1][3] is True


def test_demand_already_built_spawns_no_worker(qapp):
    """Satisfied k returns True with no worker and no extra builds."""
    pool, toast = _InlinePool(), _FakeToast()
    pyr = _FakePyramid(total=5)
    coord = _make(pool, toast, pyr)
    store = _store()

    assert coord.demand_level(store, 2, slot_id=7) is True
    calls = pyr.build_calls
    assert len(pool.workers) == 1

    hooks = []
    assert coord.demand_level(store, 2, slot_id=7, toast_hook=hooks.append) is True
    assert len(pool.workers) == 1, "no worker for an already-built level"
    assert pyr.build_calls == calls, "no rebuild of built levels"
    assert hooks == ["ready"]
    assert toast.finished == [7, 7]


def test_demand_zoom_change_builds_only_delta(qapp):
    """k1 then k2>k1 builds only the newly needed levels (GIMP-style)."""
    pool = _InlinePool()
    pyr = _FakePyramid(total=5)
    coord = _make(pool, None, pyr)
    store = _store()

    assert coord.demand_level(store, 1) is True
    assert pyr.level_count == 2
    assert pyr.build_calls == 1

    assert coord.demand_level(store, 3) is True
    assert pyr.level_count == 4, "only L2..L3 added"
    assert pyr.build_calls == 3, "delta builds only — L1 never rebuilt"
    assert pyr.is_complete() is False


def test_demand_walk_abort_builds_nothing_further(qapp):
    """should_abort flipping mid-build stops the loop; toast dismissed."""
    pool, toast = _InlinePool(), _FakeToast()
    pyr = _FakePyramid(total=5)
    coord = _make(pool, toast, pyr)
    store = _store()

    hooks = []
    # walk supersedes the build once L1 lands
    abort = lambda: pyr.level_count >= 2  # noqa: E731
    assert coord.demand_level(
        store, 4, slot_id=7, toast_hook=hooks.append, should_abort=abort
    ) is True

    assert pyr.level_count == 2, "nothing further after the walk"
    assert pyr.build_calls == 1
    assert pyr.is_level_built(4) is False
    assert toast.bumped == [7]
    assert toast.dismissed == [7], "stuck toast must be dismissed on abort"
    assert not toast.finished
    assert "aborted" in hooks
    assert "ready" not in hooks


def test_demand_rejections(qapp):
    """Invalid k / pre-abort / in-flight / no-pyramid all return False."""
    from engine.cache.image_identity import image_uid

    # invalid k
    coord = _make(_InlinePool(), None, _FakePyramid())
    assert coord.demand_level(_store(), -1) is False
    assert coord.demand_level(_store(), True) is False
    assert coord.demand_level(_store(), "2") is False

    # pre-aborted: no worker, no toast touch
    pool, toast = _InlinePool(), _FakeToast()
    coord = _make(pool, toast, _FakePyramid())
    assert coord.demand_level(_store(), 2, slot_id=7, should_abort=lambda: True) is False
    assert pool.workers == []
    assert toast.bumped == []

    # no pyramid
    coord = _make(_InlinePool(), None, None)
    assert coord.demand_level(_store(), 1) is False

    # in-flight: second demand refuses while the first owns the worker
    manual = _ManualPool()
    pyr = _FakePyramid(total=5)
    coord = _make(manual, None, pyr)
    store = _store()
    assert coord.demand_level(store, 2) is True
    assert image_uid(store) in coord.pyramid_builds
    assert coord.demand_level(store, 3) is False
    assert len(manual.workers) == 1


def test_demand_manual_pool_stops_at_target_then_resumes(qapp):
    """Async-shaped: captured worker builds to k; a later demand adds the delta."""
    manual = _ManualPool()
    pyr = _FakePyramid(total=5)
    coord = _make(manual, None, pyr)
    store = _store()

    assert coord.demand_level(store, 2) is True
    assert pyr.level_count == 1, "nothing completes synchronously"
    manual.workers[0].run()
    assert pyr.level_count == 3, "worker stopped exactly at k=2"
    assert pyr.build_calls == 2

    assert coord.demand_level(store, 3) is True
    assert len(manual.workers) == 2
    manual.workers[1].run()
    assert pyr.level_count == 4
    assert pyr.build_calls == 3, "resume added only L3"


def test_eager_start_build_regression(qapp):
    """Eager start_build still builds to complete (deferred IC/MC phase)."""
    pool, toast = _InlinePool(), _FakeToast()
    pyr = _FakePyramid(total=3)
    coord = _make(pool, toast, pyr)
    store = _store()

    assert coord.start_build(store, slot_id=7) is True
    assert pyr.is_complete() is True
    assert pyr.level_count == 3
    assert pyr.build_calls == 3, "2 builds + the terminal complete probe"
    assert toast.bumped == [7]
    assert toast.finished == [7]

    # complete pyramid: skip path still refuses + finishes the toast
    assert coord.start_build(store, slot_id=7) is False
