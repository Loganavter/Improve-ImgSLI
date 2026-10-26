"""The Algorithms backend's RANK (ADR 009 wave A3).

The deterministic fusion order — and ONLY that: this module reads the local
measurement (engine records / ``item.metrics``) over the axes its own
measurement produced (:func:`.measure.local_axes`), never a VLM scorecard and
never the judge's free-form names.

Two boundaries the A2 adapter already enforced are repeated here because this
is now the module a caller reaches:

* the profile must be this backend's own (``BackendMismatch`` for the AI
  backend's, ``NoProfileYet`` for a generation this adapter did not make). An
  AI-domain ``MeasurementEnvelope``/``OwnedProfile`` therefore cannot be ranked
  here at all;
* the axis set is passed to the fusion explicitly (``rank_series(axes=…)``),
  so even a locally tagged profile that carried judge entries cannot make the
  local order depend on ``item.analysis`` — the judge half is not a local
  number and must not move a local rank.

``pairwise_order`` is a REQUEST FOR A CAPABILITY this backend does not declare
(``CAPABILITIES`` in :mod:`.profile`): the A/B refinement is VLM work, so asking
the Algorithms adapter for it is ``CapabilityNotDeclared`` — the loud refusal
the capability model exists for (ADR 009 §"a capability is requested from the
descriptor, never assumed"), not a silently ignored argument.
"""

from __future__ import annotations

from tabs.image_gallery.backends.context import SeriesContext, select_members
from tabs.image_gallery.backends.contract import (
    PAIRWISE_CAPABILITY,
    RankRequest,
    RankResult,
    require_capability,
)

from .measure import local_axes


def rank(
    adapter,
    request: RankRequest,
    *,
    context: SeriesContext | None = None,
) -> RankResult:
    """The deterministic fusion order over this backend's own registry axes.

    *adapter* is the owning :class:`~.profile.AlgorithmsBackend`; it resolves
    the ``OwnedProfile`` to the ``MetricProfile`` it made. A non-empty
    ``pairwise_order`` is refused with ``CapabilityNotDeclared`` before any
    measurement happens (this backend never produces such an order).
    """
    if request.pairwise_order:
        require_capability(adapter.descriptor, PAIRWISE_CAPABILITY)
    from tabs.image_gallery.services.rank_fusion import rank_series

    profile = adapter._require_profile(request.profile, operation="rank")
    members = select_members(
        request.item_keys, (context.members if context is not None else ())
    )
    ranks = rank_series(
        members,
        mode=getattr(profile, "mode", None),
        profile=profile,
        axes=local_axes(profile),
    )
    return RankResult(ranks=ranks or {})


__all__ = ["rank"]
