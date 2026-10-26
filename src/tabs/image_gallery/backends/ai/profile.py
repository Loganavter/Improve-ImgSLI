"""The AI analysis backend — the vision judge's judgment domain.

ADR 009 wave A2: the judge's axis set is made, owned and read HERE. Wave A3
gives the two operations that read numbers their own modules; this file stays
the OWNER (profile generation, state slot, lifecycle) and delegates:

* ``make_profile`` → ``use_cases.profile_ai.choose_profile_sync`` (one pinned
  call per folder generation: probe members, free-form axis naming, the 5..8
  rule, the pin). Its ``None`` — AI not configured, no probe, transport failure,
  an unusable reply — is this backend having NO profile, so it surfaces as
  ``NoProfileYet``; it is never repaired with the local axis set (owner rule
  2026-10-26, ``ANALYSIS_BACKENDS.md`` §5);
* ``measure`` → :mod:`.measure` (``analysis.read.read_axes(domain="ai")``, i.e.
  the scorecard's per-axis records, over registry ids AND judged names);
* ``rank`` → :mod:`.rank` (``services.jev_client.rank_series_jev`` over the
  measured vector). ``None`` from a degraded Jev answer (Noul / low confidence /
  transport error / malformed) is an EMPTY ``RankResult``: the contract's "a path
  absent from ``ranks`` is unmeasured — never rank 0, never a borrowed number".
  The Algorithms order is NOT substituted here; that decision belongs to the
  caller, not to the owner of the profile.

Two capabilities are declared beyond the four the Algorithms backend has —
``pairwise`` and ``ask`` — because both are AI-domain-only features the rules
already gate (``pairwise_rank`` runs in the AI domain only, ``ask_router`` is
advisory). Wave A3 gives ``pairwise`` its wire: :mod:`.rank` honours a pairwise
order (declared capability) while the Algorithms backend raises
``CapabilityNotDeclared`` for the same request, and the production trigger asks
``backends.composition.pairwise_backend`` before scheduling a pass.

An axis-less profile — the AI slot before the judge has answered — is
``NoProfileYet`` at every boundary (``_require_profile``): it measures nothing,
ranks nothing, asks nothing, and never falls through to the local mode mapping.

Wave A4 gives this adapter its **lifecycle ownership**: ``reset``
(:mod:`.reset`) clears every cache the judge's domain fills — scorecards, VLM
profile pins, Jev rank pins, tie-break/brief files, the A/B verdict store and the
Ask-AI answer caches bound through :meth:`AIBackend.new_ask_cache` — and advances
this adapter's work generation. That generation is what the three worker-thread
pins ask immediately before they write, so a result produced before a reset can
no longer land in a store the reset just emptied.
"""

from __future__ import annotations

import logging
import weakref

from core.log_names import APP_LOGGER_NAME

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
    AI_PROFILE_SLOT,
    DOMAIN_AI,
    ForeignProfileError,
    domain_of,
)

from .measure import measure as _measure
from .rank import rank as _rank

#: What this backend promises: the four shared operations plus the two features
#: only the judge's domain has (pairwise near-tie passes, advisory questions).
CAPABILITIES: frozenset[str] = frozenset(
    {"measure", "rank", "profile", "pairwise", "ask", "reset"}
)

logger = logging.getLogger(APP_LOGGER_NAME)



class AIBackend:
    """The vision judge's backend: named axes, scorecard read, Jev rank.

    One instance per process (``BACKEND`` below) is the registry's adapter. An
    EMPTY profile is a first-class state: ``make_profile`` refuses to invent one
    (``NoProfileYet``), ``measure``/``rank`` refuse to run without one, and the
    UI's existing "not ready / no profile" surfaces paint instead of showing
    local detector numbers (``use_cases.action_context.REFUSAL_NO_PROFILE``).
    """

    descriptor = BackendDescriptor(
        backend_id=DOMAIN_AI,
        schema_version=PROFILE_SCHEMA_VERSION,
        capabilities=CAPABILITIES,
        cache_namespace="ai",
    )

    #: The ``GalleryState`` field this backend owns.
    slot = AI_PROFILE_SLOT

    def __init__(self) -> None:
        self._profiles: dict[str, object] = {}
        self._current: OwnedProfile | None = None
        #: Monotonic work generation, advanced by every :meth:`reset`.
        self._generation = 0
        #: The Ask-AI answer caches this backend owns, one per owner (a
        #: controller session). Weak keys: the cache lives exactly as long as
        #: the owner does, and a reset still reaches every live one — which is
        #: precisely what the cache never had (it survived every reset because
        #: the controller owned it and no clear knew about it).
        self._ask_caches: "weakref.WeakKeyDictionary[object, dict]" = (
            weakref.WeakKeyDictionary()
        )

    # -- profile -----------------------------------------------------------

    def make_profile(
        self,
        request: ProfileRequest,
        *,
        context: SeriesContext | None = None,
    ) -> OwnedProfile:
        """Ask the judge for this series' axes through the existing selector.

        The selector's answer is pinned in ``services.profile_cache`` exactly as
        today (one paid call per unchanged folder generation). No answer — the
        backend is not configured, no probe could be prepared, the transport
        failed, the reply broke the 5..8/evidence rule — is ``NoProfileYet``: the
        AI backend has no profile, and the local mode mapping is not a profile of
        THIS backend.
        """
        from tabs.image_gallery.use_cases import profile_ai

        context = context if context is not None else SeriesContext()
        members = select_members(request.member_keys, context.members)
        profile = profile_ai.choose_profile_sync(
            members,
            mode=request.mode,
            settings=context.settings,
            folder_key=context.folder_key,
            salience=context.salience,
            reference_path=context.reference_path,
            cache=context.cache,
            client_call=context.client_call,
            refresh=bool(context.refresh),
        )
        if profile is None:
            raise NoProfileYet(
                backend_id=self.descriptor.backend_id, operation="make_profile"
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

        The AI slot accepts the judge's own answer only: a series/heuristic
        (Algorithms) profile here would let the local derivation fuel the AI
        prompt, so it is ``ForeignProfileError`` — the adapter decides, not the
        core. An axis-less profile is ``NoProfileYet``: the slot never holds a
        judge "answer" that names no axis (that state is the ABSENCE of a
        profile, and it used to fall through to local axes downstream).
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
            # ``measure``/``rank`` against its OwnedProfile resolves.
            self._own(profile)
        setattr(state, self.slot, profile)
        return profile

    def load_profile(self, state):
        """This backend's slot: ``None`` when the judge has not answered yet."""
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
        """The judge's per-axis records, read through ``analysis.read``.

        No request is issued here: the scorecard numbers are already on the
        items (``item.analysis``), and an item the model has not scored is a
        ``gap`` record — never a detector number.
        """
        return _measure(self, request, context=context)

    def rank(
        self,
        request: RankRequest,
        *,
        context: SeriesContext | None = None,
    ) -> RankResult:
        """The AI-domain order through the existing Jev rank entry point."""
        return _rank(self, request, context=context)

    def require_pairwise(self) -> None:
        """Declare the A/B pass: this backend is the one allowed to spend on it."""
        require_capability(self.descriptor, PAIRWISE_CAPABILITY)


    # -- lifecycle ---------------------------------------------------------

    def new_ask_cache(self, owner) -> dict[str, object]:
        """Bind a fresh Ask-AI answer cache to *owner* and return it.

        The answer cache is a MEASUREMENT cache (a paid answer about the items a
        reset zeroes), so it belongs to the backend that produced the answers —
        a reset must be able to drop it without the use case knowing the
        controller has one. Per owner, not process-wide: the answers are an
        in-session convenience, and a second session must not inherit them (or
        its own "the cache starts empty" assertions stop being true).

        An owner that cannot be weakly referenced is not remembered (the caller
        still gets a working cache); the binding is what makes ``reset`` reach
        it, so that limitation is traced rather than hidden.
        """
        cache: dict[str, object] = {}
        try:
            self._ask_caches[owner] = cache
        except TypeError:
            logger.debug(
                "ask cache: owner %r is not weak-referenceable; a reset will not "
                "reach this cache",
                type(owner).__name__,
            )
        return cache

    def ask_caches(self) -> tuple[dict[str, object], ...]:
        """Every live Ask-AI answer cache this backend owns."""
        try:
            return tuple(self._ask_caches.values())
        except Exception:
            return ()

    def clear_ask_caches(self) -> int:
        """Empty every bound Ask cache; return how many answers were dropped."""
        dropped = 0
        try:
            caches = list(self._ask_caches.values())
        except Exception:
            caches = []
        for cache in caches:
            try:
                dropped += len(cache)
                cache.clear()
            except Exception:
                continue
        return dropped

    def reset(self) -> dict[str, int]:
        """Drop every cache this backend owns (a new world); advance generation.

        Delegates to :mod:`.reset`, where the generation advance is the FIRST
        statement and the stores follow. The returned mapping is the reset
        summary's own vocabulary, filled by the owner of each cache — not by the
        use case that shows the numbers.
        """
        from .reset import reset as _reset

        return _reset(self)

    def release(self) -> None:
        """Tear down what ``reset`` cannot (the per-owner Ask bindings)."""
        from .reset import release as _release

        _release(self)

    # -- work generations --------------------------------------------------

    @property
    def generation(self) -> int:
        """The live work generation (advanced by every :meth:`reset`)."""
        return int(self._generation)

    def series_quality(self, item, *, profile) -> float | None:
        """One member's judge-only quality — the cross-series payload's number.

        Declared on the adapter so the core asks for it through
        ``backends.composition.backend("ai")`` instead of importing
        ``backends.ai.measure`` directly (ADR 009 §2 as amended). The import is
        lazy: ``measure`` pulls the quality read, which must not be imported
        while this package is still initialising.
        """
        from .measure import series_quality as _member_quality

        return _member_quality(item, profile=profile)

    def lease(self) -> WorkGeneration:
        """The lease a worker snapshots when it starts working for this backend."""
        return WorkGeneration(
            backend_id=self.descriptor.backend_id, generation=self.generation
        )

    def assert_generation(self, lease: WorkGeneration, *, operation: str) -> None:
        """Refuse a *lease* this backend has dropped (``reset`` moved on).

        ``BackendMismatch`` for the other backend's lease (this adapter never
        issued it), ``NoProfileYet`` for an older generation of this one: after a
        reset there is no profile of that generation for the result to belong to,
        so the write is refused instead of landing in a cache that was cleared a
        moment ago.
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
        """The owned profile's ``MetricProfile``, or a loud refusal (see A2 rules).

        An axis-less profile is ``NoProfileYet`` too: the AI backend with no axis
        set has nothing to measure or rank, and the local mode mapping is not a
        profile of this backend (ADR 009 A3 killed that fallback).
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
        return f"AIBackend(profiles={len(self._profiles)}, slot={self.slot!r})"


__all__ = ["CAPABILITIES", "AIBackend"]
