"""The AI backend's MEASUREMENT (ADR 009 wave A3).

Split out of the A2 adapter for the same reason as the Algorithms side: the
operation that reads numbers gets its own file, so "which artifact does this
backend read" is a boundary and not a promise.

What this module reads — and nothing else:

* the scorecard — ``analysis.read.read_axes(domain="ai")`` over
  ``item.analysis`` (the VLM's per-axis records; an item the model has not
  scored is a ``gap`` record with its own reason, never a detector number);
* the profile's FULL axis set (``backends.context.profile_axes``: the registry
  ids the judge picked AND the free-form names it invented). Both halves are
  this backend's own vocabulary by owner decision #694 — a judge-named axis is
  measured by the judge, which is exactly what makes it rankable here.

:func:`scorecard_axes` and :func:`series_quality` are public because the AI
domain's other seams ask them instead of re-deriving an axis list or an
aggregate:

* ``services.jev_client`` / ``services.ai_client.prompt`` ask the profile's own
  axes through ``profile_judged.scorecard_axis_ids`` (which delegates the
  registry half to ``rank_fusion.measured_axes_for``);
* ``services.series_priority`` aggregates ONE number per item for its Jev
  payload — that number is the judge's own mean over this profile
  (:func:`series_quality`), never the local fusion aggregate
  (``rank_fusion.item_quality(mode=…)`` with no profile), which is what used to
  travel into an AI-domain payload.

An axis-less profile is ``NoProfileYet``: this backend has no axis set, so it
has nothing to measure (owner rule 2026-10-26 — the local mode mapping is not a
profile of this backend and is never substituted).
"""

from __future__ import annotations

from tabs.image_gallery.analysis.read import read_axes
from tabs.image_gallery.backends.context import (
    MeasuredItem,
    SeriesContext,
    item_key_of,
    profile_axes,
    require_axes,
    select_members,
)
from tabs.image_gallery.backends.contract import MeasurementEnvelope, MeasureRequest
from tabs.image_gallery.services.metric_profile import DOMAIN_AI


def scorecard_axes(profile) -> tuple[str, ...]:
    """Every axis of *profile* this backend measures: registry ids + judge names.

    ``NoProfileYet`` when the profile carries none — the caller must render
    "not ready" rather than measure an empty axis set.
    """
    return require_axes(profile, backend_id=DOMAIN_AI, operation="scorecard_axes")


def measure(
    adapter,
    request: MeasureRequest,
    *,
    context: SeriesContext | None = None,
) -> MeasurementEnvelope:
    """The judge's per-axis records, read through ``analysis.read``.

    No request is issued here: the scorecard numbers are already on the items
    (``item.analysis``). *adapter* is the owning
    :class:`~.profile.AIBackend`, which resolves the ``OwnedProfile`` to the
    ``MetricProfile`` it made.
    """
    profile = adapter._require_profile(request.profile, operation="measure")
    members = select_members(
        request.item_keys, (context.members if context is not None else ())
    )
    axes = profile_axes(profile)
    records = tuple(
        MeasuredItem(
            item_key=item_key_of(member),
            records=tuple(
                read_axes(member, domain=DOMAIN_AI, axes=axes, profile=profile)
            ),
        )
        for member in members
    )
    return MeasurementEnvelope(
        backend_id=adapter.descriptor.backend_id,
        schema_version=adapter.descriptor.schema_version,
        profile_id=request.profile.profile_id,
        records=records,
    )


def series_quality(item, *, profile) -> float | None:
    """The judge's own 0..100 aggregate for *item* over *profile*'s axes.

    One number per item, from ONE instrument: the mean of the AI-domain read
    restricted to the profile's axes (registry + judge-named alike). An item
    the model has scored on none of them is ``None`` — never 0, never the local
    aggregate. ``NoProfileYet`` when the profile has no axes.

    This is the aggregate ``services.series_priority`` puts in its Jev payload;
    it lives here because it is the AI backend's measurement, not a second
    quality scale invented by a service.
    """
    axes = scorecard_axes(profile)
    try:
        from tabs.image_gallery.services.quality_read import domain_axis_scores

        read = domain_axis_scores(item, domain=DOMAIN_AI)
    except Exception:
        read = {}
    numbers: list[float] = []
    for axis in axes:
        score = read.get(axis)
        if score is None:
            continue
        try:
            numbers.append(float(score))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


__all__ = ["measure", "scorecard_axes", "series_quality"]
