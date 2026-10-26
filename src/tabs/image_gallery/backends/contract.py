"""The analysis-backend adapter contract (ADR 009, wave A1).

An **analysis backend** owns one judgment domain end to end: it makes the
metric profile for a series, measures the series against that profile and ranks
it. ADR 009 replaces "the controller field says which numbers are shown" with
two adapters behind this one contract, so a value's owner travels with the
value instead of being inferred from the active domain.

This module is types and boundary checks only — no behaviour is rewired in A1
(``metric_profile``, ``profile_for_domain``, ``rank_fusion``, ``pairwise_rank``,
``cache_reset`` and the controller keep their current shape until A2–A4).

Three rules the types make unrepresentable rather than merely discouraged:

* **Ownership is a field, not a string in a log line.** ``OwnedProfile`` and
  ``MeasurementEnvelope`` carry ``backend_id``; ``assert_envelope_owned`` and
  ``BackendDescriptor.assert_owns`` refuse a foreign artifact at the boundary.
  The idiom is ``stacking_policy.resolve_render_pass_order``: a role without a
  row is a ``KeyError``, never a silent default — so here a mismatched owner is
  a typed error, never a coercion.
* **A schema version is declared once per backend** and every artifact states
  the version it was built under; a mismatch is ``SchemaMismatch`` (the profile
  caches and the on-disk judgments outlive a code change).
* **A capability is requested from the descriptor, never assumed.** A caller
  that needs pairwise ranking asks ``require_capability``; a backend that has
  not declared it cannot be asked to provide it. The idiom is the keyframing
  adapters: values are reachable only through the owning adapter's bindings, and
  an unknown descriptor is a lookup failure.

ADR 009 forbids a fallback branch in the core, so nothing here has a
``fallback()`` / ``default()`` / ``or_other_backend()`` seam: the caller picks a
backend by id and lives with the answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol

from .errors import BackendMismatch, CapabilityNotDeclared, SchemaMismatch
from .generation import WorkGeneration

#: The one OPTIONAL capability the gallery requests by name: the A/B (pairwise)
#: refinement of a near-tie top set. Only the judge's domain has it (the pass is
#: VLM work), so a caller asks the descriptor instead of assuming the feature is
#: shared — ``require_capability(descriptor, PAIRWISE_CAPABILITY)``.
PAIRWISE_CAPABILITY = "pairwise"


@dataclass(frozen=True)
class BackendDescriptor:
    """What a backend is, declared once at registration.

    ``backend_id`` is the registry key (``registry[backend_id]``);
    ``schema_version`` is the version of the profile/envelope payloads this
    backend produces; ``capabilities`` is the closed set of optional features the
    backend promises (``require_capability`` reads it); ``cache_namespace`` is
    the one disk-cache namespace the backend owns — a second backend claiming it
    is ``CacheNamespaceCollision``.
    """

    backend_id: str
    schema_version: int
    capabilities: frozenset[str]
    cache_namespace: str

    def assert_owns(self, profile: "OwnedProfile") -> None:
        """Accept *profile* only if this backend made it under this schema.

        Ownership has two halves, checked in this order: a foreign backend is
        ``BackendMismatch`` (the profile belongs elsewhere), a foreign
        ``schema_version`` is ``SchemaMismatch`` (the profile is stale or too
        new). Both are loud; neither returns a repaired profile.
        """
        if profile.backend_id != self.backend_id:
            raise BackendMismatch(
                what="profile",
                expected_backend_id=self.backend_id,
                actual_backend_id=profile.backend_id,
            )
        if profile.schema_version != self.schema_version:
            raise SchemaMismatch(
                what="profile",
                backend_id=self.backend_id,
                expected_schema_version=self.schema_version,
                actual_schema_version=profile.schema_version,
            )


@dataclass(frozen=True)
class OwnedProfile:
    """A metric profile whose owning backend is a FIELD.

    ``axes`` is the profile's axis set in the backend's own order — registry ids
    and judge-named names alike (``ANALYSIS_BACKENDS.md`` §5: the two halves are
    provenance, not quality). ``entries`` carries the backend's own axis-entry
    records (for the AI backend: the judge-named proposals); this contract does
    not interpret them, it only guarantees they travel with the owner.

    ``profile_id`` is the backend-local identity a measurement envelope points
    back at (``MeasurementEnvelope.profile_id``), e.g. a cache key or a
    folder-generation stamp.
    """

    backend_id: str
    profile_id: str
    schema_version: int
    axes: tuple[str, ...]
    entries: tuple[object, ...] = ()


@dataclass(frozen=True)
class MeasurementEnvelope:
    """One backend's measurements of a series under one owned profile.

    ``records`` are the backend's own per-axis measurement records (the gallery
    engine's ``AxisValue`` shape for the local backend), opaque to this contract:
    the envelope's job is identity and schema, not record interpretation, so a
    second record vocabulary cannot be invented here.

    ``profile_id`` is the profile the numbers were measured against, so a reader
    can refuse an envelope whose profile is not the active one.
    """

    backend_id: str
    schema_version: int
    profile_id: str
    records: tuple[object, ...]


@dataclass(frozen=True)
class ProfileRequest:
    """What a backend needs to decide "which axes exist" for a series.

    Field set follows the two current producers: ``mode`` is the folder mode
    (``metric_profile.MODES``); ``member_keys`` are the series members the
    profile is derived from (paths or cache keys, backend's choice — this layer
    never decodes them); ``has_reference`` says whether a source hub exists,
    which is what gates the ``reference`` axes today.
    """

    mode: str
    member_keys: tuple[str, ...] = ()
    has_reference: bool = False


@dataclass(frozen=True)
class MeasureRequest:
    """What a backend needs to measure a series against an owned profile.

    ``item_keys`` are the series members to measure; an empty tuple means "every
    member the profile was made for", so a caller that already narrowed the
    series states it explicitly and a caller that did not does not have to.
    """

    profile: OwnedProfile
    item_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankRequest:
    """What a backend needs to order a series.

    ``pairwise_order`` mirrors ``rank_fusion.rank_series``'s opt-in parameter:
    an explicit ordering of a subset (the near-tie top set from A/B
    comparisons). Empty means "pointwise only"; it never changes which items are
    measured, only the order of the subset the backend was given.
    """

    profile: OwnedProfile
    item_keys: tuple[str, ...] = ()
    pairwise_order: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankResult:
    """``item_key -> rank`` (1-based), as ``rank_fusion.rank_series`` returns.

    A path absent from ``ranks`` is unmeasured — never rank 0, never last, never
    a borrowed number.
    """

    ranks: Mapping[str, int]

    def __post_init__(self) -> None:
        # Frozen must mean frozen: a plain dict field would let a caller reorder
        # a delivered rank after the fact (same rule as the engine's immutable
        # records, ``engine/analysis/contracts.py`` ``freeze_mapping``).
        if not isinstance(self.ranks, Mapping):
            raise TypeError(
                f"RankResult.ranks must be a mapping, got {type(self.ranks).__name__}"
            )
        object.__setattr__(self, "ranks", MappingProxyType(dict(self.ranks)))


class AnalysisBackend(Protocol):
    """One judgment domain behind the adapter contract.

    Deliberately NOT ``runtime_checkable``: the registry validates the concrete
    adapter (descriptor + callables) at registration, which is a stronger and
    earlier check than an ``isinstance`` that only scans attribute names.

    Lifecycle: ``make_profile`` at series resolution, then any number of
    ``measure``/``rank`` calls against that profile; ``reset`` drops in-memory
    state for a new folder generation; ``release`` frees persistent resources.
    ``measure``/``rank`` before ``make_profile`` are ``NoProfileYet``.

    ``reset`` is the OWNER's answer to "drop what you filled": it clears every
    cache the backend's domain owns (addressed by ``descriptor
    .cache_namespace``) and advances the backend's work generation, and it
    RETURNS the counts keyed by the fields the caller's reset summary publishes
    for those caches (``{}`` when the backend publishes none). A caller iterating
    the registry therefore holds no list of cache names — the adapters do (ADR
    009 wave A4).

    ``lease`` / ``assert_generation`` are the other half: a worker snapshots
    ``lease()`` when it starts and hands it back to the OWNING adapter
    immediately before it writes a cache entry; a reset in between makes that
    lease stale and the adapter refuses the write (``NoProfileYet`` with the
    generation detail, ``BackendMismatch`` for the other backend's lease).
    """

    descriptor: BackendDescriptor

    def make_profile(self, request: ProfileRequest) -> OwnedProfile: ...

    def measure(self, request: MeasureRequest) -> MeasurementEnvelope: ...

    def rank(self, request: RankRequest) -> RankResult: ...

    def reset(self) -> Mapping[str, int]: ...

    def release(self) -> None: ...

    def lease(self) -> WorkGeneration: ...

    def assert_generation(self, lease: WorkGeneration, *, operation: str) -> None: ...


def assert_envelope_owned(
    descriptor: BackendDescriptor,
    envelope: MeasurementEnvelope,
) -> None:
    """Refuse an envelope another backend (or another schema) produced.

    Same two halves as ``BackendDescriptor.assert_owns``: identity first, then
    the schema the numbers were produced under.
    """
    if envelope.backend_id != descriptor.backend_id:
        raise BackendMismatch(
            what="measurement envelope",
            expected_backend_id=descriptor.backend_id,
            actual_backend_id=envelope.backend_id,
        )
    if envelope.schema_version != descriptor.schema_version:
        raise SchemaMismatch(
            what="measurement envelope",
            backend_id=descriptor.backend_id,
            expected_schema_version=descriptor.schema_version,
            actual_schema_version=envelope.schema_version,
        )


def require_capability(descriptor: BackendDescriptor, name: str) -> None:
    """Raise ``CapabilityNotDeclared`` unless *descriptor* declares *name*."""
    if name not in descriptor.capabilities:
        raise CapabilityNotDeclared(
            backend_id=descriptor.backend_id,
            capability=name,
            declared=descriptor.capabilities,
        )


__all__ = [
    "AnalysisBackend",
    "BackendDescriptor",
    "MeasureRequest",
    "MeasurementEnvelope",
    "OwnedProfile",
    "PAIRWISE_CAPABILITY",
    "ProfileRequest",
    "RankRequest",
    "RankResult",
    "WorkGeneration",
    "assert_envelope_owned",
    "require_capability",
]
