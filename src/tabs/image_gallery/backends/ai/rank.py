"""The AI backend's RANK (ADR 009 wave A3).

The judge's order over the judge's own measurement:

* ``services.jev_client.rank_series_jev`` builds the measured vector from the
  AI-domain read over THIS profile's axes and asks Jev to order it. A degraded
  answer (Noul / low confidence / transport error / malformed / no axis set) is
  an EMPTY ``RankResult`` — the contract's "a path absent from ``ranks`` is
  unmeasured — never rank 0, never a borrowed number". The Algorithms order is
  NOT substituted here: choosing the other backend's rank is a product decision,
  not this adapter's.
* ``pairwise_order`` is the ONE optional capability this backend declares
  (``PAIRWISE_CAPABILITY``). The A/B pass itself lives in
  ``use_cases.pairwise_rank`` (it spends per pair against the shared judge
  budget); what the rank does with its result is the documented subset rule of
  ``rank_fusion.rank_series``: the named paths take the leading ranks in the
  given order and every other member follows in the measured order. No number is
  recomputed and a path this series did not measure is ignored.
"""

from __future__ import annotations

from tabs.image_gallery.backends.context import SeriesContext, select_members
from tabs.image_gallery.backends.contract import (
    PAIRWISE_CAPABILITY,
    RankRequest,
    RankResult,
    require_capability,
)
from tabs.image_gallery.services.metric_profile import DOMAIN_AI

from .measure import scorecard_axes


def _pairwise_first(ranks, pairwise_order) -> dict[str, int]:
    """*ranks* with the pairwise-ordered paths moved to the front (1..k)."""
    ordered = [str(path) for path in (pairwise_order or ()) if str(path)]
    if not ordered or not ranks:
        return dict(ranks)
    head = [path for path in ordered if path in ranks]
    seen = set(head)
    tail = sorted(
        (path for path in ranks if path not in seen),
        key=lambda path: (ranks[path], path),
    )
    return {path: index for index, path in enumerate(head + tail, start=1)}


def rank(
    adapter,
    request: RankRequest,
    *,
    context: SeriesContext | None = None,
) -> RankResult:
    """The AI-domain order through the existing Jev rank entry point."""
    from tabs.image_gallery.services import jev_client

    if request.pairwise_order:
        # Declared by this backend; the refusal path is the other one's.
        require_capability(adapter.descriptor, PAIRWISE_CAPABILITY)
    profile = adapter._require_profile(request.profile, operation="rank")
    scorecard_axes(profile)  # NoProfileYet before any request is built
    members = select_members(
        request.item_keys, (context.members if context is not None else ())
    )
    context = context if context is not None else SeriesContext()
    base_url = str(getattr(context.settings, "base_url", "") or "")
    api_key = str(getattr(context.settings, "api_key", "") or "")
    client = context.client or jev_client.make_client(base_url, api_key)
    ranks = jev_client.rank_series_jev(
        members,
        mode=getattr(profile, "mode", None),
        client=client,
        cache=context.cache,
        domain=DOMAIN_AI,
        profile=profile,
        base_url=base_url,
    )
    return RankResult(ranks=_pairwise_first(ranks or {}, request.pairwise_order))


__all__ = ["rank"]
