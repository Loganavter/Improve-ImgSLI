"""INVARIANT: a metrics reset is ONE registry iteration, not a list of cache names.

ADR 009 wave A4 moves "which caches does a reset clear" from
``use_cases.cache_reset`` (a sixteen-step list of module-level clear calls, in a
file that owned none of them) to the adapters that fill those caches. Three
consequences this file pins, each with its own falsification story:

* **no name list** — ``cache_reset`` must reach the stores only through
  ``backend.reset()``. Falsified by adding the old direct calls back: the AST
  check below sees an ``ai_cache.clear_all()`` / ``clear_default_cache(...)``
  attribute call in that module and fails.
* **the barrier still comes first, per backend too** — each adapter's
  ``reset`` advances its work generation before it drops a store, so a pin a
  worker thread is about to write is refused (``test_stale_pins_are_refused_
  by_the_adapter.py`` drives the three real pins). Falsified by a reset that
  clears first and bumps afterwards: the lease taken before the reset would
  still compare current and the write would land.
* **ownership is declared, not inferred** — every cache module states the ONE
  backend namespace it belongs to, so clearing a foreign store is
  ``BackendMismatch``; and the registry still refuses two backends claiming one
  namespace (``CacheNamespaceCollision``).

The Ask-AI answer cache is the concrete bug this wave closes: it lived on the
controller (``_ask_cache``) and no clear knew about it, so a paid answer outlived
every reset. It is now issued by the AI adapter and dropped by its ``reset``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.backends import (
    BackendMismatch,
    CacheNamespaceCollision,
    AnalysisBackendRegistry,
    NoProfileYet,
    generation_is_current,
)
from tabs.image_gallery.backends.ai import BACKEND as AI_BACKEND
from tabs.image_gallery.backends.algorithms import BACKEND as ALGORITHMS_BACKEND
from tabs.image_gallery.backends.composition import register_gallery_backends
from tabs.image_gallery.backends.reset import require_namespace
from tabs.image_gallery.services import ai_cache, jev_cache, metrics_cache, profile_cache
from tabs.image_gallery.use_cases import cache_reset
from tabs.image_gallery.use_cases.cache_reset import clear_metrics_caches

#: The store clears a reset used to call by name (each belongs to an adapter now).
_NAMED_CLEARS = frozenset(
    {"clear_all", "clear_cached_analysis", "clear_default_cache", "clear_local_metrics"}
)


class _Owner:
    """Minimal reset owner: an empty pool plus the optional hooks."""

    def __init__(self, items=()) -> None:
        self.state = SimpleNamespace(items=list(items))
        self._domain_epoch = 0
        self._analysis_epoch = 0
        self.profile_clears = 0

    def clear_metric_profile(self) -> None:
        self.profile_clears += 1


# ---------------------------------------------------------------------------
# 1. the use case holds no cache-name list
# ---------------------------------------------------------------------------


def test_cache_reset_clears_stores_only_through_the_adapters() -> None:
    tree = ast.parse(inspect.getsource(cache_reset))
    named = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _NAMED_CLEARS
    ]
    assert named == [], (
        "cache_reset names the stores it clears again "
        f"({sorted(set(named))}) — the owning adapter's reset() is the only seam"
    )


def test_cache_reset_iterates_the_registry_and_calls_reset() -> None:
    tree = ast.parse(inspect.getsource(cache_reset.clear_metrics_caches))
    in_a_loop = {
        node.func.attr
        for loop in ast.walk(tree)
        if isinstance(loop, (ast.For, ast.AsyncFor))
        for node in ast.walk(loop)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "reset" in in_a_loop, (
        "the reset does not call backend.reset() inside a loop: the adapters no "
        "longer decide what a reset drops"
    )


# ---------------------------------------------------------------------------
# 2. the reset bumps BOTH backends' generations before anything is written
# ---------------------------------------------------------------------------


def test_reset_makes_every_backends_pre_reset_lease_stale() -> None:
    owner = _Owner()
    backends = register_gallery_backends()

    leases = {backend.descriptor.backend_id: backend.lease() for backend in backends}
    generations = {backend.descriptor.backend_id: backend.generation for backend in backends}

    clear_metrics_caches(owner)

    assert set(leases) == {"algorithms", "ai"}, "fixture sanity: both adapters registered"
    for backend in backends:
        backend_id = backend.descriptor.backend_id
        assert backend.generation == generations[backend_id] + 1, (
            f"backend {backend_id!r} did not advance its work generation on reset"
        )
        assert generation_is_current(
            leases[backend_id], operation="write a pin"
        ) is False, (
            f"a pre-reset lease of {backend_id!r} still measures as current — a pin "
            "written after the drain would land in the store the reset emptied"
        )
        with pytest.raises(NoProfileYet) as excinfo:
            backend.assert_generation(leases[backend_id], operation="write a pin")
        assert "generation" in str(excinfo.value), (
            "the refusal must name the dropped generation, not read like a "
            f"missing profile: {excinfo.value}"
        )


def test_a_foreign_lease_is_refused_by_the_wrong_adapter() -> None:
    """The refusal is the OWNING adapter's: generation numbers are not global."""
    lease = AI_BACKEND.lease()
    with pytest.raises(BackendMismatch) as excinfo:
        ALGORITHMS_BACKEND.assert_generation(lease, operation="write a pin")
    assert "ai" in str(excinfo.value) and "algorithms" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3. the Ask-AI answer cache belongs to the AI backend (and is really dropped)
# ---------------------------------------------------------------------------


def test_the_ask_ai_answers_are_dropped_by_the_reset() -> None:
    owner = _Owner()
    # The controller binds exactly this way (``controller._ask_cache``).
    ask_cache = AI_BACKEND.new_ask_cache(owner)
    ask_cache["scope|question|backend|model"] = "an answer the user paid for"
    # A second session's cache: per-owner bindings (weak keys), all reached by
    # the reset — a live owner keeps its binding.
    other_owner = _Owner()
    other_cache = AI_BACKEND.new_ask_cache(other_owner)
    other_cache["other|question|backend|model"] = "another paid answer"
    assert ask_cache and other_cache and ask_cache is not other_cache

    clear_metrics_caches(owner)

    assert ask_cache == {}, (
        "the Ask-AI answer survived the reset: a paid answer about items the reset "
        "zeroed is a measurement, and no clear reached it before ADR 009 A4"
    )
    assert other_cache == {}, (
        "the reset must reach every bound session's answers, not only the owner it "
        "was handed"
    )


# ---------------------------------------------------------------------------
# 4. namespace ownership: declared by the store, enforced at the clear
# ---------------------------------------------------------------------------


def test_every_backend_cache_declares_its_owner_namespace() -> None:
    assert ai_cache.CACHE_NAMESPACE == "ai"
    assert profile_cache.CACHE_NAMESPACE == "ai"
    assert jev_cache.CACHE_NAMESPACE == "ai"
    assert metrics_cache.CACHE_NAMESPACE == "algorithms"
    from tabs.image_gallery.services import vlm_cache
    from tabs.image_gallery.use_cases import pairwise_rank

    assert vlm_cache.CACHE_NAMESPACE == "ai"
    assert pairwise_rank.CACHE_NAMESPACE == "ai"


def test_clearing_another_backends_store_is_a_typed_refusal() -> None:
    """Falsified by dropping the check: the AI adapter would empty local records."""
    with pytest.raises(BackendMismatch) as excinfo:
        require_namespace(AI_BACKEND.descriptor, metrics_cache)
    assert "algorithms" in str(excinfo.value), (
        f"the refusal must name the store's real owner: {excinfo.value}"
    )
    with pytest.raises(BackendMismatch):
        require_namespace(ALGORITHMS_BACKEND.descriptor, ai_cache)
    # Both owners accept their own stores (non-vacuity).
    require_namespace(AI_BACKEND.descriptor, ai_cache, jev_cache)
    require_namespace(ALGORITHMS_BACKEND.descriptor, metrics_cache)


def test_release_drops_the_ask_bindings_a_reset_keeps(counters) -> None:
    """``release`` is the teardown ``reset`` must not be: it drops the bindings."""
    from tabs.image_gallery.backends.ai import AIBackend

    adapter = AIBackend()
    owner = _Owner()
    cache = adapter.new_ask_cache(owner)
    cache["scope|question|backend|model"] = "an answer"

    adapter.release()

    assert cache == {}, "release must still empty what the reset half owns"
    assert adapter.ask_caches() == (), (
        "release kept the per-owner binding a reset deliberately keeps — the end of "
        "a session must not leave a cache bound to a dead owner"
    )


def test_two_backends_still_cannot_share_one_cache_namespace() -> None:
    """The registry gate A1 shipped must survive A4's namespace declarations."""
    registry = AnalysisBackendRegistry()
    registry.register(AI_BACKEND)

    class _Pretender:
        """A second backend claiming the AI backend's namespace."""

        descriptor = type(AI_BACKEND.descriptor)(
            backend_id="pretender",
            schema_version=1,
            capabilities=frozenset(),
            cache_namespace="ai",
        )

        def make_profile(self, request):  # pragma: no cover - never reached
            raise AssertionError

        def measure(self, request):  # pragma: no cover - never reached
            raise AssertionError

        def rank(self, request):  # pragma: no cover - never reached
            raise AssertionError

        def reset(self):
            return {}

        def release(self):
            return None

    with pytest.raises(CacheNamespaceCollision) as excinfo:
        registry.register(_Pretender())
    assert "ai" in str(excinfo.value) and "pretender" in str(excinfo.value)
