"""Resolver — the only place *(policy, axes, capabilities)* becomes declared runs.

Why a single resolver (``plan-gallery-analysis-engine-2026-10-20`` §Invariants
I2/I3/I5): producer selection used to be scattered across the controller and
three use cases (``== "ai"`` switches, a domain-blind tie-break tail), so
"which producer may run for this axis under this policy?" had no single answer,
and an automatic network producer could fan out with no ceiling. Here the answer
is a ``Resolution``: a frozen ``AnalysisPlan`` naming the runs *in registry
order*, the ordered ``ProducerSpec`` tuple the runner executes, and an explicit
``gaps`` tuple for axes no plan step can answer.

Rules, stated once so no caller re-derives them:

- ``local`` — free, non-automatic producers only. No network, no spend; this is
  the default and the only policy the dark-launch hook (W7) selects.
- ``ai`` — producers that require a backend (``"backend" in spec.requires``).
  A plan that may spend refuses without a ``Budget``: an undeclared, uncapped
  network fan-out is the defect this engine removes (plan I3/G7).
- the AI-assisted policy — the local producers first, then the backend
  producers, both in registry order; the budget's ``cap`` bounds the number of
  non-free runs.

A budget that cannot cover the declared non-free runs raises ``ResolutionError``
— the engine never silently truncates a plan to fit the cap, because a truncated
plan looks exactly like a complete one to every surface that reads it.

Determinism: ``axes`` is normalized to registry order (unknown ids after the
known ones, sorted), and every selection iterates ``registry.producers`` (already
sorted by id). Passing the same axis set in a different order therefore yields
the same plan, the same gap order and the same runs.

Capabilities: ``capabilities`` narrows the candidate set to producers whose
``requires`` are all actually provided by this item (plan §Pool: the offered set
is derived from real inputs, not a mode guess). An EMPTY set means "inputs not
declared" and does not narrow — otherwise the common call
``resolve_plan(registry, policy="local")`` would silently plan nothing. A caller
that knows the inputs (the proxy hook builds them from the context) passes them
and gets capability-correct gaps.

Pure stdlib: no Qt, no tab imports, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import AnalysisPlan, Budget, ProducerSpec
from .registry import ProducerRegistry

#: The policies a plan may declare, in the order the UI lists them. Named
#: constants on purpose: the policy names are interpreted HERE and nowhere else,
#: so a comparison names the policy constant instead of re-spelling the literal
#: (the ``== "ai"`` shape is the ad-hoc domain gate the plan's W2 ratchet bans
#: outside this module).
LOCAL_POLICY = "local"
AI_POLICY = "ai"
AI_ASSISTED_POLICY = "ai_assisted"
POLICIES: tuple[str, ...] = (LOCAL_POLICY, AI_POLICY, AI_ASSISTED_POLICY)

#: A producer declaring this requirement needs a resolved ``BackendRef`` to run.
BACKEND_REQUIREMENT = "backend"

#: One reason for every unanswered axis: the plan has no step that answers it.
NO_PRODUCER_REASON = "no producer provides this axis"


class ResolutionError(Exception):
    """A policy cannot be satisfied as declared (no budget, cap exceeded, …).

    Raised *before* any producer runs, so a refusal has no side effect: no
    request, no spend, no partial plan a surface could mistake for a full one.
    """


@dataclass(frozen=True, slots=True)
class Resolution:
    """The declared work for one folder generation plus its unanswered axes.

    ``plan.runs`` (producer ids) and ``runs`` (the specs) are the same order —
    registry order — so the journal, the plan and the executor cannot disagree
    about what ran. ``gaps`` is ``(axis, reason)`` because a gap's reason is what
    a surface shows for an empty row.
    """

    plan: AnalysisPlan
    runs: tuple[ProducerSpec, ...]
    gaps: tuple[tuple[str, str], ...]


def resolve_plan(
    registry: ProducerRegistry,
    *,
    policy: str,
    axes: Iterable[str] | None = None,
    capabilities: Iterable[str] = frozenset(),
    budget: Budget | None = None,
) -> Resolution:
    """Resolve *policy* over *registry* into a runnable ``Resolution``.

    ``axes=None`` means every axis the registry knows (the vocabulary is the
    union of producer ``provides``; a removed producer takes its axes with it).
    ``axes=()`` deliberately plans nothing.

    Raises ``ResolutionError`` for an unknown policy, a spending plan without a
    budget, an automatic producer without a cap, or a plan whose non-free runs
    exceed ``budget.cap``.
    """
    name = str(policy or "").strip().lower()
    if name not in POLICIES:
        raise ResolutionError(
            f"unknown analysis policy {policy!r}; expected one of "
            f"{', '.join(POLICIES)}"
        )

    requested = _requested_axes(registry, axes)
    caps = _normalized_capabilities(capabilities)
    narrow = bool(caps)

    def capable(spec: ProducerSpec) -> bool:
        # An empty capability set means "not declared", not "nothing available":
        # see the module docstring for why that is the safe default here.
        return not narrow or spec.requires <= caps

    local = tuple(
        spec
        for spec in registry.producers
        if spec.cost == "free" and spec.automatic is False and capable(spec)
    )
    backend = tuple(
        spec
        for spec in registry.producers
        if BACKEND_REQUIREMENT in spec.requires and capable(spec)
    )

    if name == LOCAL_POLICY:
        selected = local
    elif name == AI_POLICY:
        if budget is None:
            raise ResolutionError(
                "policy 'ai' plans network runs and needs a budget: declare the "
                "cap before any request can be made (plan I3/G7)"
            )
        selected = backend
    else:  # ai_assisted
        if budget is None and backend:
            raise ResolutionError(
                "policy 'ai_assisted' includes non-free producers and needs a "
                "budget; pass policy='local' for a free-only plan"
            )
        selected = _unique(local + backend)

    for spec in selected:
        if spec.automatic and spec.max_per_run is None:
            raise ResolutionError(
                f"producer {spec.id!r} is automatic but declares no max_per_run: "
                "an uncapped automatic producer cannot be planned"
            )

    wanted = frozenset(requested)
    runs = tuple(spec for spec in selected if any(axis in wanted for axis in spec.provides))

    gaps: list[tuple[str, str]] = []
    for axis in requested:
        if not any(axis in spec.provides for spec in selected):
            gaps.append((axis, NO_PRODUCER_REASON))

    non_free = tuple(spec for spec in runs if spec.cost != "free")
    if non_free:
        # Reached only with a budget (the policy branches above refuse without
        # one), so the cap is a real ceiling rather than an absent field.
        cap = int(budget.cap)  # type: ignore[union-attr]
        if len(non_free) > cap:
            raise ResolutionError(
                f"policy {name!r} plans {len(non_free)} non-free run(s) "
                f"({', '.join(spec.id for spec in non_free)}) but the budget cap "
                f"is {cap}: declare a larger cap or ask for fewer axes"
            )

    plan = AnalysisPlan(
        id=f"analysis:{name}:{len(runs)}",
        generation=0,
        policy=name,
        runs=tuple(spec.id for spec in runs),
    )
    return Resolution(plan=plan, runs=runs, gaps=tuple(gaps))


def _requested_axes(
    registry: ProducerRegistry, axes: Iterable[str] | None
) -> tuple[str, ...]:
    """Normalize *axes* to registry order; unknown ids last, sorted.

    This is what makes the result independent of the caller's container type and
    iteration order (a set, a reversed list and a tuple all resolve identically).
    """
    if axes is None:
        return registry.axes()
    if isinstance(axes, str):
        axes = (axes,)
    requested = {str(axis).strip() for axis in axes}
    requested.discard("")
    known = tuple(axis for axis in registry.axes() if axis in requested)
    known_set = frozenset(known)
    return known + tuple(sorted(requested - known_set))


def _normalized_capabilities(capabilities: Iterable[str]) -> frozenset[str]:
    return frozenset(
        name for name in (str(item).strip() for item in (capabilities or ())) if name
    )


def _unique(specs: Iterable[ProducerSpec]) -> tuple[ProducerSpec, ...]:
    """Deduplicate by id while preserving order (a spec may be local AND ai)."""
    seen: set[str] = set()
    out: list[ProducerSpec] = []
    for spec in specs:
        if spec.id in seen:
            continue
        seen.add(spec.id)
        out.append(spec)
    return tuple(out)


__all__ = [
    "AI_ASSISTED_POLICY",
    "AI_POLICY",
    "BACKEND_REQUIREMENT",
    "LOCAL_POLICY",
    "NO_PRODUCER_REASON",
    "POLICIES",
    "Resolution",
    "ResolutionError",
    "resolve_plan",
]
