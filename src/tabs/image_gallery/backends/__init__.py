"""Analysis-backend adapter contract, typed errors and registry (ADR 009 A1).

The public surface later waves consume::

    BackendDescriptor(backend_id, schema_version, capabilities, cache_namespace)
    AnalysisBackend.descriptor
    AnalysisBackend.make_profile(ProfileRequest) -> OwnedProfile
    AnalysisBackend.measure(MeasureRequest) -> MeasurementEnvelope
    AnalysisBackend.rank(RankRequest) -> RankResult
    AnalysisBackend.reset() -> Mapping[str, int] ; AnalysisBackend.release()
    AnalysisBackend.lease() -> WorkGeneration      # snapshot when work starts
    AnalysisBackend.assert_generation(lease, operation=...)  # before the write
    OwnedProfile(backend_id, profile_id, schema_version, axes, entries)
    MeasurementEnvelope(backend_id, schema_version, profile_id, records)
    registry[backend_id]      # KeyError when unknown
    iter_backends()
    PAIRWISE_CAPABILITY                          # the one optional capability name
    require_capability(descriptor, name)          # CapabilityNotDeclared
    assert_envelope_owned(descriptor, envelope)   # BackendMismatch
    errors: BackendMismatch, NoProfileYet, CapabilityNotDeclared, SchemaMismatch,
            CacheNamespaceCollision

Re-exports are the only content: this package declares the contract, the typed
errors and the store. The two adapters live in ``algorithms/`` and ``ai/`` and
are registered by ``composition.py`` (the ONE composition point, wave A2);
importing this package registers nothing.
"""

from __future__ import annotations

from .contract import (
    AnalysisBackend,
    BackendDescriptor,
    MeasurementEnvelope,
    MeasureRequest,
    OwnedProfile,
    PAIRWISE_CAPABILITY,
    ProfileRequest,
    RankRequest,
    RankResult,
    assert_envelope_owned,
    require_capability,
)
from .errors import (
    BackendContractError,
    BackendMismatch,
    CacheNamespaceCollision,
    CapabilityNotDeclared,
    NoProfileYet,
    SchemaMismatch,
)
from .generation import (
    WorkGeneration,
    current_generation,
    generation_is_current,
    require_current,
)
from .registry import AnalysisBackendRegistry, iter_backends, register, registry

__all__ = [
    "AnalysisBackend",
    "AnalysisBackendRegistry",
    "BackendContractError",
    "BackendDescriptor",
    "BackendMismatch",
    "CacheNamespaceCollision",
    "CapabilityNotDeclared",
    "MeasureRequest",
    "MeasurementEnvelope",
    "NoProfileYet",
    "OwnedProfile",
    "PAIRWISE_CAPABILITY",
    "ProfileRequest",
    "RankRequest",
    "RankResult",
    "SchemaMismatch",
    "WorkGeneration",
    "assert_envelope_owned",
    "current_generation",
    "generation_is_current",
    "iter_backends",
    "register",
    "registry",
    "require_capability",
    "require_current",
]
