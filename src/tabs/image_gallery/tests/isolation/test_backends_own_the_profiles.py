"""INVARIANT (ADR 009 A2): the two profile slots belong to two BACKENDS.

A1 shipped the adapter contract, the typed errors and the registry; nothing was
owned. This suite pins the wave-A2 move: the profile of each judgment domain is
MADE, OWNED and READ by its adapter, and the core no longer decides which
profile belongs to whom.

Falsification stories (each names the regression it kills):

- **(a)** an Algorithms adapter that accepts the judge's axis set — the
  cross-backend borrow ``ANALYSIS_BACKENDS.md`` §5 calls the recurring defect.
  A builder that returned a ``source="vlm"`` profile, or a caller handing the
  Algorithms adapter an AI-owned envelope, must raise ``BackendMismatch``.
- **(b)** an AI adapter with no profile that measures/ranks anyway — it would
  either borrow local axes or spend a call on a 0-axis scorecard. Both must be
  ``NoProfileYet`` with NO transport request issued.
- **(c)** a composition that registers one adapter, none, or two under the same
  cache namespace. Exactly one registration point, two distinct ids, two
  distinct namespaces, the declared capability sets.
- **(d)** a profile read that bypasses the adapter (a core slot lookup or a
  second derivation). The slot accessor and the one-line deprecated
  ``profile_for_domain`` must both reach the owning adapter.

Red-before: ``backends/algorithms`` and ``backends/ai`` did not exist on the
wave-A1 base, so this module failed at import (collection error) — there was no
adapter to own anything.

``tests/runtime/**`` is NOT touched by this wave (an in-review lane owns it), so
everything here is self-contained: plain ``GalleryItem`` objects, no Qt, no
network (the ``counters`` fixture stubs the transport).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery import backends
from tabs.image_gallery.backends import (
    BackendMismatch,
    MeasureRequest,
    NoProfileYet,
    ProfileRequest,
    RankRequest,
)
from tabs.image_gallery.backends.ai import BACKEND as AI_BACKEND
from tabs.image_gallery.backends.algorithms import BACKEND as ALGORITHMS_BACKEND
from tabs.image_gallery.backends.composition import (
    backend,
    register_gallery_backends,
)
from tabs.image_gallery.backends.context import (
    SeriesContext,
    owned_profile,
    profile_axes,
)
from tabs.image_gallery.backends.errors import CacheNamespaceCollision
from tabs.image_gallery.models import GalleryItem, GalleryState
from tabs.image_gallery.services.metric_profile import (
    ALGORITHMS_PROFILE_SLOT,
    AI_PROFILE_SLOT,
    DOMAIN_AI,
    DOMAIN_ALGORITHMS,
    MetricProfile,
    profile_for_domain,
)
from tabs.image_gallery.use_cases import profile_ai, profile_select
from tabs.image_gallery.use_cases.profile_select import active_profile

JUDGE_AXIS = "halation"


def _item(name: str, **metrics) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update(metrics)
    return item


def _series() -> tuple[GalleryItem, GalleryItem]:
    """A series whose local spread is decisive: sharpness separates them."""
    return _item("a.png", sharpness=10.0, noise=0.9), _item(
        "b.png", sharpness=900.0, noise=0.1
    )


def _judge_profile(mod: str = "camera") -> MetricProfile:
    return MetricProfile(
        mode=mod,
        source="vlm",
        axis_entries=(
            SimpleNamespace(
                name=JUDGE_AXIS,
                definition="bright edges bloom into a soft halo",
                scale="0-100",
                direction="lower-is-better",
            ),
        ),
    )


def _state(**slots) -> GalleryState:
    return GalleryState(mode="camera", **slots)


# ---------------------------------------------------------------------------
# (a) the Algorithms adapter owns LOCAL axes only — a judge profile is refused
# ---------------------------------------------------------------------------


def test_the_algorithms_adapter_refuses_a_judge_profile_from_its_builder(
    monkeypatch,
) -> None:
    """A builder that answered with the model's axes cannot become owned here."""
    from tabs.image_gallery.backends.algorithms import AlgorithmsBackend

    monkeypatch.setattr(
        profile_select, "derive_profile", lambda *_a, **_k: _judge_profile()
    )

    with pytest.raises(BackendMismatch) as excinfo:
        AlgorithmsBackend().make_profile(ProfileRequest(mode="camera"))

    message = str(excinfo.value)
    assert DOMAIN_AI in message and DOMAIN_ALGORITHMS in message, (
        "the refusal must name BOTH backends, else it reads as a generic error"
    )


def test_the_algorithms_adapter_refuses_a_foreign_envelope() -> None:
    """The AI backend's owned profile is not measurable by the local one."""
    from tabs.image_gallery.backends.algorithms import AlgorithmsBackend

    adapter = AlgorithmsBackend()
    foreign = owned_profile(AI_BACKEND.descriptor, _judge_profile())

    with pytest.raises(BackendMismatch):
        adapter.measure(MeasureRequest(profile=foreign))
    with pytest.raises(BackendMismatch):
        adapter.rank(RankRequest(profile=foreign))


def test_the_algorithms_adapter_refuses_the_judge_profile_in_its_slot() -> None:
    """Installing/reading the wrong tag stays the loud seam it was.

    Asserted DIRECTLY at the adapter boundary: every production caller of the
    state accessor wraps it in ``except Exception``, so a swallowed failure
    would prove nothing.
    """
    from tabs.image_gallery.backends.algorithms import AlgorithmsBackend
    from tabs.image_gallery.services.metric_profile import ForeignProfileError

    adapter = AlgorithmsBackend()
    state = _state(**{ALGORITHMS_PROFILE_SLOT: _judge_profile()})

    with pytest.raises(ForeignProfileError):
        adapter.load_profile(state)
    with pytest.raises(ForeignProfileError):
        adapter.install(state, _judge_profile())


def test_the_algorithms_adapter_builds_the_series_offer_through_the_builder() -> None:
    """Non-vacuity: the real builder runs and its offer is what gets owned."""
    from tabs.image_gallery.backends.algorithms import AlgorithmsBackend

    a, b = _series()
    adapter = AlgorithmsBackend()
    owned = adapter.make_profile(
        ProfileRequest(mode="camera"), context=SeriesContext(members=(a, b))
    )

    assert owned.backend_id == DOMAIN_ALGORITHMS
    assert "sharpness" in owned.axes, "the series' decisive local axis is offered"
    assert adapter.profile is not None and adapter.profile.source == "series"
    assert owned.axes == profile_axes(adapter.profile)


# ---------------------------------------------------------------------------
# (b) an EMPTY AI profile is NoProfileYet — never local axes, never a request
# ---------------------------------------------------------------------------


def test_an_empty_ai_profile_raises_from_measure_and_rank(counters) -> None:
    from tabs.image_gallery.backends.ai import AIBackend

    adapter = AIBackend()
    # The judge HAS a profile shape, but this adapter never made it — exactly
    # the state of a folder whose selector has not answered yet.
    owned = owned_profile(AI_BACKEND.descriptor, _judge_profile())
    state = _state()

    with pytest.raises(NoProfileYet) as measure_error:
        adapter.measure(MeasureRequest(profile=owned), context=SeriesContext())
    assert DOMAIN_AI in str(measure_error.value)

    with pytest.raises(NoProfileYet):
        adapter.rank(RankRequest(profile=owned), context=SeriesContext())

    assert counters["call_sync"] == 0, (
        "a profile-less AI backend reached the transport — a 0-axis spend"
    )
    assert counters["save_analysis"] == 0
    # ...and the accessor does not paper over it with local axes.
    assert not active_profile(state, domain=DOMAIN_AI), (
        "the empty AI slot must read as EMPTY, never as the local mode mapping"
    )


def test_an_ai_profile_request_that_cannot_be_answered_is_no_profile_yet(
    counters,
) -> None:
    """The selector's ``None`` is this backend having no profile (not a borrow)."""
    from tabs.image_gallery.backends.ai import AIBackend

    unconfigured = SimpleNamespace(enabled=False, api_key="", model="", base_url="")
    adapter = AIBackend()
    a, b = _series()

    with pytest.raises(NoProfileYet):
        adapter.make_profile(
            ProfileRequest(mode="camera"),
            context=SeriesContext(
                members=(a, b), settings=unconfigured, client_call=None
            ),
        )

    assert counters["call_sync"] == 0, "an unconfigured AI backend must not call"
    assert counters["profile_put"] == 0
    assert adapter.profile is None


def test_the_ai_adapter_owns_the_judge_answer_it_asked_for(monkeypatch) -> None:
    """The adapter delegates to the real selector and owns its answer."""
    from tabs.image_gallery.backends.ai import AIBackend

    seen: dict = {}

    def _selector(items, *, mode, settings, **kwargs):
        seen.update(items=tuple(items), mode=mode, settings=settings, kwargs=kwargs)
        return _judge_profile(mode)

    monkeypatch.setattr(profile_ai, "choose_profile_sync", _selector)
    a, b = _series()
    settings = SimpleNamespace(enabled=True, api_key="k", model="m", base_url="u")
    adapter = AIBackend()

    owned = adapter.make_profile(
        ProfileRequest(mode="camera"),
        context=SeriesContext(members=(a, b), settings=settings),
    )

    assert seen["items"] == (a, b) and seen["mode"] == "camera"
    assert seen["settings"] is settings, "the entry point got the caller's settings"
    assert owned.backend_id == DOMAIN_AI
    assert owned.axes == (JUDGE_AXIS,), "the judge's own free-form axis is owned"
    assert owned.entries and adapter.profile is not None


# ---------------------------------------------------------------------------
# (c) one composition point: two ids, two namespaces, the declared capabilities
# ---------------------------------------------------------------------------


def test_both_adapters_are_registered_with_distinct_namespaces() -> None:
    registered = register_gallery_backends()
    by_id = {adapter.descriptor.backend_id: adapter for adapter in registered}

    assert set(by_id) == {DOMAIN_ALGORITHMS, DOMAIN_AI}
    assert by_id[DOMAIN_ALGORITHMS] is ALGORITHMS_BACKEND
    assert by_id[DOMAIN_AI] is AI_BACKEND
    assert registry_namespaces(by_id) == {DOMAIN_ALGORITHMS, DOMAIN_AI}

    assert by_id[DOMAIN_ALGORITHMS].descriptor.capabilities == frozenset(
        {"measure", "rank", "profile", "reset"}
    )
    assert by_id[DOMAIN_AI].descriptor.capabilities == frozenset(
        {"measure", "rank", "profile", "pairwise", "ask", "reset"}
    )
    for descriptor in (d.descriptor for d in by_id.values()):
        assert descriptor.schema_version >= 1


def test_the_composition_is_idempotent_but_duplicate_registration_is_not() -> None:
    """A second composition pass is a no-op; two ADAPTERS on one id are an error."""
    first = register_gallery_backends()
    second = register_gallery_backends()
    assert [a.descriptor.backend_id for a in first] == [
        a.descriptor.backend_id for a in second
    ]

    with pytest.raises(ValueError):
        backends.registry.register(ALGORITHMS_BACKEND)

    from tabs.image_gallery.backends.algorithms import AlgorithmsBackend

    colliding = AlgorithmsBackend()
    colliding.descriptor = backends.BackendDescriptor(
        backend_id="algorithms-shadow",
        schema_version=1,
        capabilities=frozenset({"profile"}),
        cache_namespace="algorithms",
    )
    with pytest.raises(CacheNamespaceCollision):
        backends.registry.register(colliding)


def test_an_unknown_backend_id_is_still_a_key_error() -> None:
    with pytest.raises(KeyError):
        backend("judge")


def registry_namespaces(by_id) -> set[str]:
    return {adapter.descriptor.cache_namespace for adapter in by_id.values()}


# ---------------------------------------------------------------------------
# (d) the profile READ goes through the adapter, not through a core slot
# ---------------------------------------------------------------------------


def test_the_slot_accessor_reads_through_the_owning_adapter(monkeypatch) -> None:
    local = MetricProfile(axis_ids=("sharpness",), mode="camera", source="series")
    state = _state(**{ALGORITHMS_PROFILE_SLOT: local})
    calls: list[tuple] = []

    original = type(ALGORITHMS_BACKEND).load_profile

    def _spy(self, target):
        calls.append((self.descriptor.backend_id, target))
        return original(self, target)

    monkeypatch.setattr(type(ALGORITHMS_BACKEND), "load_profile", _spy)

    assert active_profile(state, domain=DOMAIN_ALGORITHMS) is local
    assert profile_for_domain(state, DOMAIN_ALGORITHMS) is local
    assert calls and all(backend_id == DOMAIN_ALGORITHMS for backend_id, _ in calls), (
        "the read bypassed the adapter — a core slot lookup again"
    )


def test_installing_a_profile_goes_through_the_adapter_and_lands_in_its_slot() -> None:
    local = MetricProfile(axis_ids=("sharpness",), mode="camera", source="series")
    state = _state()

    installed = backend(DOMAIN_ALGORITHMS).install(state, local)

    assert installed is local
    assert getattr(state, ALGORITHMS_PROFILE_SLOT) is local
    assert getattr(state, AI_PROFILE_SLOT) is None, (
        "the local install touched the AI backend's slot"
    )


def test_the_two_slots_are_written_by_their_own_adapters() -> None:
    local = MetricProfile(axis_ids=("sharpness",), mode="camera", source="series")
    judge = _judge_profile()
    state = _state()

    backend(DOMAIN_ALGORITHMS).install(state, local)
    backend(DOMAIN_AI).install(state, judge)

    assert profile_for_domain(state, DOMAIN_ALGORITHMS) is local
    assert profile_for_domain(state, DOMAIN_AI) is judge
    assert state.algorithms_profile is not state.ai_profile
