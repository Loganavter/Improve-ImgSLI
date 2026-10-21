"""W7: the resolver is the one place *(policy, axes, capabilities)* -> runs.

``plan-gallery-analysis-engine-2026-10-20`` §Invariants I2/I3 and §Gates G7:
producer selection must be a declared plan, an automatic network producer must
carry a cap, and a plan that cannot be paid for must be refused instead of
silently truncated. These cases pin the policy table, the deterministic order
(a set/reversed list resolve identically), the explicit gap for an axis no plan
step answers, and both refusal paths (no budget, cap exceeded).
"""

from __future__ import annotations

import pytest

from engine.analysis.contracts import Budget, ProducerSpec
from engine.analysis.registry import ProducerRegistry, discover
from engine.analysis.resolver import (
    NO_PRODUCER_REASON,
    POLICIES,
    ResolutionError,
    resolve_plan,
)

PRODUCERS = "tabs.image_gallery.analysis.producers"

#: The axes no *local* producer answers today — the local policy must report
#: them as gaps, never borrow a number for them. ``typicality``/``aesthetic`` are
#: identity/proxy axes the network scorecard owns; ``brisque`` joined them in W13
#: when the learned-quality producer was deleted (it duplicated
#: ``pair_metrics``): no producer measures BRISQUE now, so a local plan gaps it.
AI_ONLY_AXES = ("typicality", "aesthetic", "brisque")

CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance")
FIDELITY_AXES = (
    "ssim",
    "detail_gain",
    "color_accuracy",
    "clipping_delta",
    "halo_delta",
    "chroma_fringe_delta",
    "lpips",
    "dists",
)

BOTH_INPUTS = frozenset({"images", "reference"})


def _registry() -> ProducerRegistry:
    return discover(PRODUCERS)


def _spec(
    producer_id: str,
    provides: dict[str, str],
    *,
    cost: str = "free",
    automatic: bool = False,
    max_per_run: int | None = None,
    requires=frozenset({"images"}),
) -> ProducerSpec:
    return ProducerSpec(
        id=producer_id,
        provides=provides,
        requires=frozenset(requires),
        cost=cost,  # type: ignore[arg-type]
        automatic=automatic,
        max_per_run=max_per_run,
    )


def _paid_spec(producer_id: str, axis: str) -> ProducerSpec:
    """A capped, automatic, backend-requiring producer (a network run)."""
    return _spec(
        producer_id,
        {axis: "measured"},
        cost="per_image",
        automatic=True,
        max_per_run=4,
        requires=frozenset({"images", "backend"}),
    )


# ---------------------------------------------------------------------------
# policy vocabulary and the local policy
# ---------------------------------------------------------------------------


def test_policies_are_the_declared_vocabulary():
    assert POLICIES == ("local", "ai", "ai_assisted")


def test_local_policy_selects_only_free_non_automatic_producers():
    registry = _registry()
    resolution = resolve_plan(
        registry, policy="local", capabilities=BOTH_INPUTS
    )

    assert resolution.plan.policy == "local"
    assert resolution.plan.runs == tuple(spec.id for spec in resolution.runs)
    assert "ai_scorecard" not in resolution.plan.runs
    # The local plan is the three free analyzers: W13 deleted learned-quality
    # and folded LPIPS/DISTS into the fidelity producer that already computes
    # them, so no run repeats another run's detector pass.
    assert resolution.plan.runs == (
        "artifact_catalog",
        "camera_scalars",
        "fidelity_reference",
    )
    for spec in resolution.runs:
        assert spec.cost == "free"
        assert spec.automatic is False
    # Registry order, not axis order: the plan is readable as "the local
    # analyzers in discovery order".
    assert tuple(spec.id for spec in resolution.runs) == tuple(
        spec.id
        for spec in registry.producers
        if spec.cost == "free" and spec.automatic is False
    )


def test_local_policy_gaps_the_axes_it_cannot_answer():
    resolution = resolve_plan(
        _registry(), policy="local", capabilities=BOTH_INPUTS
    )

    assert tuple(axis for axis, _reason in resolution.gaps) == AI_ONLY_AXES
    assert {reason for _axis, reason in resolution.gaps} == {NO_PRODUCER_REASON}


def test_local_policy_drops_a_reference_producer_without_a_reference():
    resolution = resolve_plan(
        _registry(), policy="local", capabilities=frozenset({"images"})
    )

    assert "fidelity_reference" not in resolution.plan.runs
    gapped = {axis for axis, _reason in resolution.gaps}
    assert gapped >= set(FIDELITY_AXES)
    assert gapped >= set(AI_ONLY_AXES)
    assert "camera_scalars" in resolution.plan.runs


def test_empty_capabilities_mean_not_declared_rather_than_nothing_available():
    """The documented convention: no capability set does not narrow the plan."""
    registry = _registry()
    unbounded = resolve_plan(registry, policy="local")
    declared = resolve_plan(
        registry, policy="local", capabilities=BOTH_INPUTS
    )

    assert unbounded.plan.runs == declared.plan.runs
    assert unbounded.gaps == declared.gaps


# ---------------------------------------------------------------------------
# deterministic order
# ---------------------------------------------------------------------------


def test_resolution_is_independent_of_axis_input_permutation():
    registry = _registry()
    all_axes = registry.axes()
    baseline = resolve_plan(registry, policy="local", axes=list(all_axes))

    for permutation in (
        tuple(reversed(all_axes)),
        set(all_axes),
        tuple(all_axes),
    ):
        again = resolve_plan(registry, policy="local", axes=permutation)
        assert again == baseline

    # Unknown ids are appended after the known vocabulary, sorted — so even an
    # unknown axis cannot reorder the known gaps.
    with_unknown = resolve_plan(
        registry, policy="local", axes=["zzz", *all_axes, "aaa"]
    )
    assert tuple(axis for axis, _ in with_unknown.gaps) == (
        *AI_ONLY_AXES,
        "aaa",
        "zzz",
    )
    assert with_unknown.plan.runs == baseline.plan.runs


def test_unprovided_axis_becomes_an_explicit_gap():
    registry = ProducerRegistry([_spec("alpha", {"sharpness": "measured"})])

    resolution = resolve_plan(registry, policy="local", axes=("ghost",))

    assert resolution.plan.runs == ()
    assert resolution.gaps == (("ghost", NO_PRODUCER_REASON),)


def test_unknown_policy_is_refused():
    with pytest.raises(ResolutionError, match="unknown analysis policy"):
        resolve_plan(_registry(), policy="heuristically")


# ---------------------------------------------------------------------------
# the network policies and the budget
# ---------------------------------------------------------------------------


def test_ai_policy_selects_the_backend_producer_with_a_budget():
    resolution = resolve_plan(
        _registry(),
        policy="ai",
        capabilities=frozenset({"images", "backend"}),
        budget=Budget(declared=1, cap=1),
    )

    assert resolution.plan.runs == ("ai_scorecard",)
    assert {axis for axis, _ in resolution.gaps} == {
        "banding",
        "blocking",
        "chroma_fringing",
        "halo",
        "invented_texture",
        "noise_amplification",
        "over_smoothing",
    }


def test_ai_policy_without_a_budget_is_refused_before_anything_runs():
    with pytest.raises(ResolutionError, match="needs a budget"):
        resolve_plan(
            _registry(),
            policy="ai",
            capabilities=frozenset({"images", "backend"}),
        )


def test_ai_assisted_plans_local_first_then_the_network_producer():
    resolution = resolve_plan(
        _registry(),
        policy="ai_assisted",
        capabilities=frozenset({"images", "reference", "backend"}),
        budget=Budget(declared=1, cap=1),
    )

    runs = resolution.plan.runs
    assert runs[-1] == "ai_scorecard"
    assert runs[:-1] == tuple(
        spec.id
        for spec in _registry().producers
        if spec.cost == "free" and spec.automatic is False
    )
    assert resolution.gaps == ()


def test_ai_assisted_without_a_budget_is_refused_when_it_would_spend():
    with pytest.raises(ResolutionError, match="needs a budget"):
        resolve_plan(
            _registry(),
            policy="ai_assisted",
            capabilities=frozenset({"images", "backend"}),
        )


def test_budget_cap_refuses_instead_of_silently_truncating():
    registry = ProducerRegistry(
        [
            _paid_spec("alpha", "sharpness"),
            _paid_spec("beta", "noise"),
        ]
    )

    with pytest.raises(ResolutionError, match="budget cap is 1") as caught:
        resolve_plan(
            registry,
            policy="ai",
            capabilities=frozenset({"images", "backend"}),
            budget=Budget(declared=1, cap=1),
        )

    message = str(caught.value)
    assert "alpha" in message and "beta" in message, (
        "a refusal names what it could not fit, so the fix is visible"
    )


def test_budget_cap_of_exactly_the_planned_runs_is_accepted():
    registry = ProducerRegistry(
        [
            _paid_spec("alpha", "sharpness"),
            _paid_spec("beta", "noise"),
        ]
    )

    resolution = resolve_plan(
        registry,
        policy="ai",
        capabilities=frozenset({"images", "backend"}),
        budget=Budget(declared=2, cap=2),
    )

    assert resolution.plan.runs == ("alpha", "beta")


def test_axes_restrict_the_plan_to_producers_that_answer_them():
    resolution = resolve_plan(
        _registry(),
        policy="local",
        axes=CAMERA_AXES,
        capabilities=BOTH_INPUTS,
    )

    assert resolution.plan.runs == ("camera_scalars",)
    assert resolution.gaps == ()
