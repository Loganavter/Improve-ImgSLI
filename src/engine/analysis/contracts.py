"""Immutable records of the gallery analysis engine (W1 substrate).

Why these types exist (``plan-gallery-analysis-engine-2026-10-20`` §Invariants):

- **Identity travels with the value.** Today "whose number is this" is inferred
  from a controller field — the read seam swaps a whole dict per judgment
  domain — so a value can be displayed under the wrong producer and a missing
  axis can silently borrow another producer's number (defect B6). An
  ``AxisValue`` therefore carries its own ``producer``, ``backend``, ``status``
  and ``reason``; a surface renders the record instead of inferring.
- **A gap is not a number.** ``status="gap"``/``"error"`` must never carry a
  value, so substitution is unrepresentable rather than merely discouraged.
- **A model identity is resolved once**, by the catalog, into a ``BackendRef``.
  Producers never spell a model id, so an endpoint/model mismatch cannot be
  introduced by a producer.
- **Frozen keeps late results honest.** A record that a surface renders must
  not mutate after the fact — that is how an in-flight result gets applied
  after a policy switch instead of being recorded as ``stale``.

Pure stdlib (no Qt, no app imports): this module is imported by tab producers,
and the engine layer never names its callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

#: Lifecycle state of one axis value. ``echo`` marks a value that a model
#: repeated from a local producer instead of measuring it (see the plan's
#: §"Provenance must be per axis"): it is displayable, but it is not an
#: independent measurement and must never be ranked as one.
AxisStatus = Literal["ok", "gap", "error", "stale", "echo"]
AXIS_STATUSES: frozenset[str] = frozenset({"ok", "gap", "error", "stale", "echo"})

#: What an axis *is*: a measured number, a yes/no candidate flag, or a model's
#: judgment. The kind is declared by the producer, never guessed by a surface.
AxisKind = Literal["measured", "candidate", "judgment"]
AXIS_KINDS: frozenset[str] = frozenset({"measured", "candidate", "judgment"})

#: Cost class of a producer run — the unit a budget is spent in.
CostClass = Literal["free", "per_image", "per_series", "per_folder", "per_question"]
COST_CLASSES: frozenset[str] = frozenset(
    {"free", "per_image", "per_series", "per_folder", "per_question"}
)

#: Outcome of one producer inside a run journal.
JournalStatus = Literal["ok", "gap", "error", "skipped"]
JOURNAL_STATUSES: frozenset[str] = frozenset({"ok", "gap", "error", "skipped"})

#: Statuses that assert "no number". Kept as one definition so the invariant in
#: ``AxisValue`` and any later reader cannot drift apart.
_NO_VALUE_STATUSES: frozenset[str] = frozenset({"gap", "error"})


def freeze_mapping(value: object | None) -> Mapping[str, object]:
    """Return an immutable copy of *value* (``{}`` for ``None``).

    Frozen dataclasses in this module carry mappings, and a plain ``dict`` field
    would let a caller mutate a record after it was built. The copy is shallow
    by design: params are scalars (model name, effort, temperature), and nesting
    a mutable container inside them is a caller bug this helper does not hide.
    """
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError(f"expected a mapping, got {type(value).__name__}")
    return MappingProxyType(dict(value))


def _hashable_mapping(value: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    """Hash ingredient for a mapping field.

    ``MappingProxyType`` is unhashable, so a frozen dataclass carrying one would
    raise on ``hash()`` — but ``BackendRef`` is a cache-key ingredient (plan I5),
    so it MUST hash. Unhashable values fall back to ``repr``; that keeps the
    hash total instead of turning a legitimate param into a runtime error.
    """
    items: list[tuple[str, object]] = []
    for key, item in value.items():
        try:
            hash(item)
        except TypeError:
            items.append((str(key), repr(item)))
        else:
            items.append((str(key), item))
    return tuple(sorted(items, key=lambda pair: pair[0]))


@dataclass(frozen=True, slots=True)
class BackendRef:
    """How a value was produced: provider + model + endpoint + params.

    Only the catalog builds these (``catalog.resolve``) — a producer receives a
    ``BackendRef`` and therefore cannot invent a model id or an endpoint. That
    is the fix for the defect where a path carried a vendor model constant while
    the endpoint came from the user's settings.
    """

    provider: str
    model: str
    base_url: str
    params: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        for name in ("provider", "model", "base_url"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"BackendRef.{name} must be a non-empty string")
        object.__setattr__(self, "params", freeze_mapping(self.params))

    def __hash__(self) -> int:
        return hash(
            (
                self.provider,
                self.model,
                self.base_url,
                _hashable_mapping(self.params),
            )
        )


@dataclass(frozen=True, slots=True)
class AxisValue:
    """One axis of one item, with its own provenance.

    Invariants (not style preferences — each one removes a shipped defect):

    - ``status="ok"`` requires a value: an "ok" with no number renders as an
      empty cell the caller then fills from somewhere else.
    - ``status`` in ``{"gap", "error"}`` forbids a value: a gap filled with
      another producer's number is the silent substitution this type exists to
      make unrepresentable.
    - ``producer`` is mandatory: an un-attributed number cannot be audited and
      cannot be invalidated when its producer is removed.
    - ``status="echo"`` requires the backend it echoed: an echo is attributed
      to the model that repeated it, not presented as a measurement.
    """

    axis: str
    value: float | None
    producer: str
    backend: BackendRef | None = None
    status: AxisStatus = "ok"
    reason: str = ""
    at: int = 0

    def __post_init__(self) -> None:
        if not str(self.axis or "").strip():
            raise ValueError("AxisValue.axis must be a non-empty string")
        if not str(self.producer or "").strip():
            raise ValueError("AxisValue.producer must be a non-empty string")
        if self.status not in AXIS_STATUSES:
            raise ValueError(
                f"AxisValue.status must be one of {sorted(AXIS_STATUSES)}, "
                f"got {self.status!r}"
            )
        if self.status == "ok":
            if self.value is None:
                raise ValueError(
                    "AxisValue(status='ok') requires a value; "
                    "use status='gap' for an unavailable axis"
                )
            object.__setattr__(self, "value", float(self.value))
        elif self.status in _NO_VALUE_STATUSES and self.value is not None:
            raise ValueError(
                f"AxisValue(status={self.status!r}) must not carry a value: "
                "a gap is never filled with another producer's number"
            )
        if self.status == "echo" and self.backend is None:
            raise ValueError(
                "AxisValue(status='echo') requires the backend whose value it repeats"
            )
        if self.reason is None:
            object.__setattr__(self, "reason", "")
        object.__setattr__(self, "at", int(self.at))


@dataclass(frozen=True, slots=True)
class ProducerSpec:
    """Manifest metadata of one producer — what it can answer, and at what cost.

    ``automatic=True`` REQUIRES ``max_per_run``: a producer that may run without
    an explicit user action and without a ceiling is exactly the unbounded
    fan-out this engine removes (plan I3/§Gates G7). A user-initiated producer
    may leave the cap unset — the user's own action is the bound.
    """

    id: str
    provides: Mapping[str, str]
    requires: frozenset[str] = frozenset()
    cost: CostClass = "free"
    automatic: bool = False
    version: int = 1
    max_per_run: int | None = None

    def __post_init__(self) -> None:
        if not str(self.id or "").strip():
            raise ValueError("ProducerSpec.id must be a non-empty string")
        provides = freeze_mapping(self.provides)
        if not provides:
            raise ValueError(
                f"ProducerSpec {self.id!r} declares no axes: a producer that "
                "provides nothing cannot be discovered or removed meaningfully"
            )
        unknown = sorted(
            str(kind) for kind in provides.values() if str(kind) not in AXIS_KINDS
        )
        if unknown:
            raise ValueError(
                f"ProducerSpec {self.id!r} declares unknown axis kind(s) {unknown}; "
                f"expected one of {sorted(AXIS_KINDS)}"
            )
        object.__setattr__(self, "provides", provides)
        object.__setattr__(
            self,
            "requires",
            frozenset(str(item) for item in (self.requires or ())),
        )
        if self.cost not in COST_CLASSES:
            raise ValueError(
                f"ProducerSpec {self.id!r} cost {self.cost!r} is not one of "
                f"{sorted(COST_CLASSES)}"
            )
        if int(self.version) < 1:
            raise ValueError(f"ProducerSpec {self.id!r} version must be >= 1")
        if self.max_per_run is not None and int(self.max_per_run) < 1:
            raise ValueError(
                f"ProducerSpec {self.id!r} max_per_run must be >= 1 when set"
            )
        if self.automatic and self.max_per_run is None:
            raise ValueError(
                f"ProducerSpec {self.id!r} is automatic but declares no "
                "max_per_run: an unbounded automatic producer is the bug this "
                "engine removes"
            )

    def __hash__(self) -> int:
        return hash(
            (
                self.id,
                _hashable_mapping(self.provides),
                self.requires,
                self.cost,
                self.automatic,
                self.version,
                self.max_per_run,
            )
        )


@dataclass(frozen=True, slots=True)
class AnalysisPlan:
    """Declared work for one folder generation: which producers may run, in order.

    The plan is the unit a policy switch replaces (plan I4): a result that
    arrives from a superseded generation is marked ``stale``, never applied to
    the new one.
    """

    id: str
    generation: int
    policy: str
    runs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.id or "").strip():
            raise ValueError("AnalysisPlan.id must be a non-empty string")
        if not str(self.policy or "").strip():
            raise ValueError(
                "AnalysisPlan.policy must be a non-empty string: an unlabeled "
                "plan cannot answer 'was network allowed here?'"
            )
        if int(self.generation) < 0:
            raise ValueError("AnalysisPlan.generation must be >= 0")
        object.__setattr__(self, "runs", tuple(str(run) for run in (self.runs or ())))


@dataclass(frozen=True, slots=True)
class Budget:
    """Declared request accounting: what was promised, the cap, and the spend.

    ``spent <= cap <= declared`` is the ordering that makes "declared" mean
    something: a cap above the declaration is an un-declared run, and a spend
    above the cap is the silent fan-out the budget exists to stop.
    """

    declared: int
    cap: int
    spent: int = 0

    def __post_init__(self) -> None:
        declared, cap, spent = int(self.declared), int(self.cap), int(self.spent)
        if declared < 0 or cap < 0 or spent < 0:
            raise ValueError("Budget values must be >= 0")
        if not spent <= cap <= declared:
            raise ValueError(
                f"Budget requires spent <= cap <= declared, got "
                f"spent={spent}, cap={cap}, declared={declared}"
            )


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """What one producer did in a run — the record the UI shows as "why"."""

    producer: str
    status: JournalStatus
    reason: str = ""
    items: int = 0

    def __post_init__(self) -> None:
        if not str(self.producer or "").strip():
            raise ValueError("JournalEntry.producer must be a non-empty string")
        if self.status not in JOURNAL_STATUSES:
            raise ValueError(
                f"JournalEntry.status must be one of {sorted(JOURNAL_STATUSES)}, "
                f"got {self.status!r}"
            )
        if int(self.items) < 0:
            raise ValueError("JournalEntry.items must be >= 0")


@dataclass(frozen=True, slots=True)
class RunJournal:
    """Ordered journal of one run (empty means "nothing ran", not "all fine")."""

    entries: tuple[JournalEntry, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries or ()))


__all__ = [
    "AXIS_KINDS",
    "AXIS_STATUSES",
    "COST_CLASSES",
    "JOURNAL_STATUSES",
    "AnalysisPlan",
    "AxisKind",
    "AxisStatus",
    "AxisValue",
    "BackendRef",
    "Budget",
    "CostClass",
    "JournalEntry",
    "JournalStatus",
    "ProducerSpec",
    "RunJournal",
    "freeze_mapping",
]
