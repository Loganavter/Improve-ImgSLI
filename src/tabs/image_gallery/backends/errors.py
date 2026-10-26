"""Typed violations of the analysis-backend adapter contract (ADR 009).

Five failures, one base: every boundary in ``backends/`` either returns the
owning backend's own artifact or raises one of these — never a substitute value
and never a fallback branch (ADR 009 forbids a fallback anywhere in the core).
Each exception therefore formats its own message from NAMED fields, so a raise
site cannot omit the offending ids/versions: the message is part of the type,
not a caller's string.

Why not plain ``ValueError``/``KeyError``:

* a caller that needs to distinguish "this profile belongs to the other
  backend" from "this profile is stale" cannot do it from a message;
* the plan's recurring defect class is a *silent* cross-read
  (``ANALYSIS_BACKENDS.md`` §5 ``ForeignProfileError``), so the failure has to
  be greppable and name BOTH ids.

``KeyError`` is still the registry's answer for an unknown ``backend_id``
(``registry[backend_id]``) — that is a lookup miss, not a contract violation,
and the message names the id plus the registered set.
"""

from __future__ import annotations


class BackendContractError(Exception):
    """Base class for every analysis-backend contract violation.

    Deliberately has no ``fallback``/``default`` recovery helper: catching this
    base means "stop", not "try the other backend".
    """


class BackendMismatch(BackendContractError):
    """An artifact owned by one backend was handed to another backend.

    Raised by ``BackendDescriptor.assert_owns`` and ``assert_envelope_owned``.
    """

    def __init__(
        self,
        *,
        what: str,
        expected_backend_id: str,
        actual_backend_id: str,
    ) -> None:
        self.what = what
        self.expected_backend_id = expected_backend_id
        self.actual_backend_id = actual_backend_id
        super().__init__(
            f"{what} belongs to backend {actual_backend_id!r}, "
            f"not {expected_backend_id!r}"
        )


class NoProfileYet(BackendContractError):
    """``measure``/``rank`` was called before the backend made a profile.

    There is no implicit "make one now" and no empty result: a backend without a
    profile has nothing to measure against, and pretending otherwise is how a
    profile-free run used to score items under the wrong axis set.

    A STALE WORK GENERATION is the same refusal (ADR 009 wave A4): after
    ``reset`` the backend holds no profile of the generation that worker started
    under, so a pin produced under it has nothing to belong to. ``detail``
    states which half was refused — the message stays built from named fields,
    the caller does not print its own sentence.
    """

    def __init__(self, *, backend_id: str, operation: str, detail: str = "") -> None:
        self.backend_id = backend_id
        self.operation = operation
        self.detail = detail
        super().__init__(
            f"backend {backend_id!r}: {operation}() "
            f"{detail or 'called before make_profile()'}"
        )


class CapabilityNotDeclared(BackendContractError):
    """A caller requested a capability the backend's descriptor never declared."""

    def __init__(
        self,
        *,
        backend_id: str,
        capability: str,
        declared: frozenset[str],
    ) -> None:
        self.backend_id = backend_id
        self.capability = capability
        self.declared = declared
        super().__init__(
            f"backend {backend_id!r} does not declare capability {capability!r} "
            f"(declared: {sorted(declared)})"
        )


class SchemaMismatch(BackendContractError):
    """A profile/envelope was produced under another ``schema_version``.

    Both versions are named: a stale artifact (older) and a newer artifact read
    by an older backend are different operator problems.
    """

    def __init__(
        self,
        *,
        what: str,
        backend_id: str,
        expected_schema_version: int,
        actual_schema_version: int,
    ) -> None:
        self.what = what
        self.backend_id = backend_id
        self.expected_schema_version = expected_schema_version
        self.actual_schema_version = actual_schema_version
        super().__init__(
            f"{what} from backend {backend_id!r} carries schema_version "
            f"{actual_schema_version}, expected {expected_schema_version}"
        )


class CacheNamespaceCollision(BackendContractError):
    """Two backends claimed the same disk-cache namespace.

    Sharing a namespace would let one backend read (and clear) another's cached
    judgments, so registration refuses it instead of partitioning lazily.
    """

    def __init__(
        self,
        *,
        cache_namespace: str,
        existing_backend_id: str,
        new_backend_id: str,
    ) -> None:
        self.cache_namespace = cache_namespace
        self.existing_backend_id = existing_backend_id
        self.new_backend_id = new_backend_id
        super().__init__(
            f"cache namespace {cache_namespace!r} is already owned by backend "
            f"{existing_backend_id!r}; backend {new_backend_id!r} cannot claim it"
        )


__all__ = [
    "BackendContractError",
    "BackendMismatch",
    "CacheNamespaceCollision",
    "CapabilityNotDeclared",
    "NoProfileYet",
    "SchemaMismatch",
]
