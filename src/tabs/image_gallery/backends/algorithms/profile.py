"""The Algorithms analysis backend — the local detectors' judgment domain.

ADR 009 wave A2: the profile of the local/fusion domain is made, owned and read
HERE instead of in the tab's core. Wave A3 gives the two operations that read
numbers their own modules; this file stays the OWNER (profile generation, state
slot, lifecycle) and delegates:

* ``make_profile`` → ``use_cases.profile_select.derive_profile`` (the series
  offer: ``metric_profile.profile_for_series`` over the measured spreads,
  falling back to the mode mapping only while the series has no discriminating
  measurement — the LAST local fallback, named as such by the source label);
* ``measure`` → :mod:`.measure` (``analysis.read.read_axes(domain="algorithms")``
  over the profile's registry half);
* ``rank`` → :mod:`.rank` (``rank_fusion.rank_series`` over that same axis set,
  never a judge-named axis and never an AI scorecard).

What is NEW is the ownership, not the computation:

* a profile this backend did not make from the Algorithms builders is refused
  at the boundary (``BackendMismatch``) — the judge's ``source="vlm"`` answer
  can never enter this backend, and a profile this backend cannot find among the
  ones it made is ``NoProfileYet``, never a mode-mapping substitute;
* an axis-less profile is ``NoProfileYet`` as well (``_require_profile``): a
  profile with no axis measures nothing, and the mode mapping is not a repair;
* the state slot write and read go through the adapter (``install`` /
  ``load_profile``), so the core no longer decides which profile belongs here;
* ``axes_for_mode`` answers the mode mapping, which is THIS backend's own
  ``heuristic`` profile — the reason ``rank_fusion.measured_axes_for`` no longer
  keeps a copy of the rule (A3 killed that copy: it let an empty AI profile fall
  through to local axes);
* ``pairwise_order`` is not a shared feature but a CAPABILITY this backend does
  not declare, so :mod:`.rank` refuses it with ``CapabilityNotDeclared``.

The disk caches (metrics/proxy pins) were ADR 009 wave A4: the local metrics
store is cleared by THIS adapter's ``reset`` (``backends.algorithms.reset``),
which is why ``use_cases.cache_reset`` no longer names it. ``reset`` here drops
the in-memory profile generations, advances the adapter's work generation (the
lease a worker compares immediately before it writes) and clears the caches this
backend owns.
"""

from __future__ import annotations

from tabs.image_gallery.backends.context import (
    PROFILE_SCHEMA_VERSION,
    SeriesContext,
    owned_profile,
    profile_identity,
    require_axes,
    select_members,
)
from tabs.image_gallery.backends.contract import (
    BackendDescriptor,
    MeasurementEnvelope,
    MeasureRequest,
    OwnedProfile,
    PAIRWISE_CAPABILITY,
    ProfileRequest,
    RankRequest,
    RankResult,
    require_capability,
)
from tabs.image_gallery.backends.errors import BackendMismatch, NoProfileYet
from tabs.image_gallery.backends.generation import WorkGeneration
from tabs.image_gallery.services.metric_profile import (
    ALGORITHMS_PROFILE_SLOT,
    DOMAIN_ALGORITHMS,
    ForeignProfileError,
    domain_of,
)

from .measure import axes_for_mode, measure as _measure
from .rank import rank as _rank

#: What this backend promises. ``profile``/``measure``/``rank``/``reset`` are the
#: four things the Algorithms domain actually does; there is deliberately no
#: ``pairwise``/``ask`` — a paid judge call belongs to the AI backend.
CAPABILITIES: frozenset[str] = frozenset({"measure", "rank", "profile", "reset"})



class AlgorithmsBackend:
    """The local detectors' backend: series offer, local read, fusion rank.

    One instance per process (``BACKEND`` below) is the registry's adapter; the
    in-memory profile generations are keyed by ``profile_id``, so a caller that
    holds an owned profile from an earlier generation can still be answered
    correctly and a caller from another (or a reset) generation is refused with
    ``NoProfileYet`` instead of being measured against the wrong axis set.
    """

    descriptor = BackendDescriptor(
        backend_id=DOMAIN_ALGORITHMS,
        schema_version=PROFILE_SCHEMA_VERSION,
        capabilities=CAPABILITIES,
        cache_namespace="algorithms",
    )

    #: The ``GalleryState`` field this backend owns — written by :meth:`install`
    #: and read by :meth:`load_profile`, never by the core.
    slot = ALGORITHMS_PROFILE_SLOT

    def __init__(self) -> None:
        self._profiles: dict[str, object] = {}
        self._current: OwnedProfile | None = None
        #: Monotonic work generation, advanced by every :meth:`reset`. A worker
        #: snapshots :meth:`lease` when it starts and hands the lease back to
        #: this adapter immediately before it writes a cache entry.
        self._generation = 0

    # -- profile -----------------------------------------------------------

    def make_profile(
        self,
        request: ProfileRequest,
        *,
        context: SeriesContext | None = None,
    ) -> OwnedProfile:
        """Derive the series offer through the existing builder and own it.

        ``context.members`` is the live folder; without one the builder sees an
        empty series and answers exactly as it does today (the mode mapping).
        A profile the local builder cannot legitimately produce — anything
        tagged as the judge's (``source="vlm"``) — is refused: this backend owns
        local axes only.
        """
        from tabs.image_gallery.use_cases.profile_select import derive_profile

        members = select_members(
            request.member_keys, (context.members if context is not None else ())
        )
        profile = derive_profile(
            members,
            mode=request.mode,
            has_reference=request.has_reference,
        )
        tag = domain_of(profile)
        if tag != self.descriptor.backend_id:
            raise BackendMismatch(
                what="profile",
                expected_backend_id=self.descriptor.backend_id,
                actual_backend_id=tag,
            )
        require_axes(
            profile, backend_id=self.descriptor.backend_id, operation="make_profile"
        )
        return self._own(profile)

    def install(self, state, profile=None):
        """Store this backend's profile in ITS state slot and return it.

        The Algorithms slot accepts the local derivation only: a foreign-tagged
        profile is ``ForeignProfileError`` (the same loud seam the slot reader
        raised), so a caller cannot park the judge's axis set here, and an
        axis-less profile (which measures nothing) is ``NoProfileYet``.
        """
        if profile is None:
            profile = self._current_metric()
        if profile is None:
            raise NoProfileYet(
                backend_id=self.descriptor.backend_id, operation="install"
            )
        tag = domain_of(profile)
        if tag != self.descriptor.backend_id:
            raise ForeignProfileError(
                f"state.{self.slot} would hold a {tag}-tagged profile "
                f"(source={getattr(profile, 'source', '?')!r}); the "
                f"{self.descriptor.backend_id} backend must not own it"
            )
        # An axis-less profile is no profile: storing one would hand every later
        # measure/rank an empty axis set (ADR 009 A3 — the AI slot used to accept
        # it and the consumers fell through to the local mode mapping).
        require_axes(
            profile, backend_id=self.descriptor.backend_id, operation="install"
        )
        if profile_identity(self.descriptor, profile) not in self._profiles:
            # An answer that arrived through another seam (the controller's
            # landing path) becomes an owned generation here, so a later
            # ``measure``/``rank`` against its OwnedProfile resolves instead of
            # claiming the backend has no such profile while its slot holds it.
            self._own(profile)
        setattr(state, self.slot, profile)
        return profile

    def load_profile(self, state):
        """Read this backend's slot, or ``None`` when it has not answered yet.

        An EMPTY slot is ``None`` ("nothing derived yet"); a slot holding the
        other backend's profile is loud (``ForeignProfileError``) — the same two
        answers the core reader gave, now decided by the owner.
        """
        if state is None:
            return None
        try:
            profile = getattr(state, self.slot, None)
        except Exception:
            profile = None
        if profile is None:
            return None
        tag = domain_of(profile)
        if tag != self.descriptor.backend_id:
            raise ForeignProfileError(
                f"state.{self.slot} holds a {tag}-tagged profile (source="
                f"{getattr(profile, 'source', '?')!r}); the "
                f"{self.descriptor.backend_id} backend must not read it"
            )
        return profile

    # -- measurement / rank ------------------------------------------------

    def measure(
        self,
        request: MeasureRequest,
        *,
        context: SeriesContext | None = None,
    ) -> MeasurementEnvelope:
        """Per-member ``AxisValue`` records, read through ``analysis.read``."""
        return _measure(self, request, context=context)

    def rank(
        self,
        request: RankRequest,
        *,
        context: SeriesContext | None = None,
    ) -> RankResult:
        """The deterministic fusion order over this backend's own profile."""
        return _rank(self, request, context=context)

    def axes_for_mode(self, mode=None) -> tuple[str, ...]:
        """The mode mapping — this backend's own ``heuristic`` profile axes.

        The mode mapping is a LOCAL derivation (``profile_for_series``'s last
        fallback), so it belongs to this backend and nowhere else. The core asks
        here (``rank_fusion.measured_axes_for``) instead of keeping a copy.
        """
        return axes_for_mode(mode)

    def require_pairwise(self) -> None:
        """Refuse the A/B pass by CAPABILITY, not by convention.

        The pairwise refinement is the judge's work, so this backend never
        declares it: asking is ``CapabilityNotDeclared`` at the caller's seam.
        """
        require_capability(self.descriptor, PAIRWISE_CAPABILITY)


    # -- lifecycle ---------------------------------------------------------

    def reset(self) -> dict[str, int]:
        """Drop this backend's caches + profile generations (a new world).

        Delegates to :mod:`.reset`: the generation advance comes FIRST (so an
        in-flight worker's lease is stale before the stores move), then the
        in-memory profile generations are dropped and the owned disk caches are
        emptied. The returned mapping is the reset summary's own vocabulary —
        ``{}`` for this backend (the local metrics count is traced, not
        published).
        """
        from .reset import reset as _reset

        return _reset(self)

    def release(self) -> None:
        """Tear down what ``reset`` cannot; the local half holds nothing extra."""
        from .reset import release as _release

        _release(self)

    # -- work generations --------------------------------------------------

    @property
    def generation(self) -> int:
        """The live work generation (advanced by every :meth:`reset`)."""
        return int(self._generation)

    def lease(self) -> WorkGeneration:
        """The lease a worker snapshots when it starts working for this backend."""
        return WorkGeneration(
            backend_id=self.descriptor.backend_id, generation=self.generation
        )

    def assert_generation(self, lease: WorkGeneration, *, operation: str) -> None:
        """Refuse a *lease* this backend has dropped (``reset`` moved on).

        Two halves, the same order the artifact boundaries use: a lease issued
        by the OTHER backend is ``BackendMismatch`` (this adapter never validated
        it), a lease from an earlier generation of this one is ``NoProfileYet``
        with the generation detail — after a reset there is no profile of that
        generation to write the result under.
        """
        if lease.backend_id != self.descriptor.backend_id:
            raise BackendMismatch(
                what="work generation",
                expected_backend_id=self.descriptor.backend_id,
                actual_backend_id=lease.backend_id,
            )
        if int(lease.generation) != self.generation:
            raise NoProfileYet(
                backend_id=self.descriptor.backend_id,
                operation=operation,
                detail=(
                    f"is stale: generation {int(lease.generation)} was dropped by "
                    f"reset() (current {self.generation})"
                ),
            )

    # -- internals ---------------------------------------------------------

    @property
    def profile(self):
        """The ``MetricProfile`` currently owned (``None`` before one is made)."""
        return self._current_metric()

    def _own(self, profile) -> OwnedProfile:
        owned = owned_profile(self.descriptor, profile)
        self._profiles[owned.profile_id] = profile
        self._current = owned
        return owned

    def _current_metric(self):
        return self._metric(self._current.profile_id) if self._current else None

    def _metric(self, profile_id: str):
        return self._profiles.get(profile_id)

    def _require_profile(self, owned: OwnedProfile, *, operation: str):
        """The owned profile's ``MetricProfile``, or a loud refusal.

        Three halves are checked: the artifact must belong to this backend
        (``BackendMismatch`` — the judge's profile is not measurable here), it
        must be one of the generations this adapter built (``NoProfileYet`` —
        an empty slot, a reset, or a profile from another folder generation),
        and it must carry at least one axis (``NoProfileYet`` — a profile with
        no axis measures nothing; the mode mapping is this backend's own
        answer, not a repair of an empty artifact).
        """
        self.descriptor.assert_owns(owned)
        profile = self._metric(getattr(owned, "profile_id", ""))
        if profile is None:
            raise NoProfileYet(
                backend_id=self.descriptor.backend_id, operation=operation
            )
        require_axes(
            profile, backend_id=self.descriptor.backend_id, operation=operation
        )
        return profile

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"AlgorithmsBackend(profiles={len(self._profiles)}, "
            f"slot={self.slot!r})"
        )


__all__ = ["CAPABILITIES", "AlgorithmsBackend", "axes_for_mode"]
