"""The Algorithms backend's MEASUREMENT (ADR 009 wave A3).

A2 put the profile, the measurement and the rank in one adapter module. A3
splits the two operations that actually read numbers into their own files, so
"which artifact does this backend read" is a file boundary instead of a
docstring promise:

* this module reads the LOCAL records — ``analysis.read.read_axes`` over
  ``item.analysis_records`` / ``item.metrics`` (the engine's ``AxisValue``),
  and nothing else;
* :mod:`.rank` orders them with the deterministic fusion;
* both refuse a profile they did not make (``BackendMismatch``) and a profile
  with no axes (``NoProfileYet``).

Two rules live here because they are the Algorithms backend's own answers and
no other module may re-derive them:

* :func:`axes_for_mode` — the mode mapping (``metric_profile.profile_for_mode``)
  is this backend's LAST local derivation (``profile_for_series`` falls back to
  it while the series has no discriminating measurement). It is a profile of
  THIS backend, tagged ``source="heuristic"``, so the core asks the owner
  instead of keeping a second copy of the rule (``rank_fusion
  .measured_axes_for`` used to answer it itself — that copy is what let an
  empty AI profile fall through to local axes, ADR 009 A3).
* :func:`local_axes` — the axes this backend can MEASURE: the profile's
  registry half (``axis_ids``) only. The judge half (``axis_entries``) is the
  other backend's vocabulary; asking the local read path for a judge-named axis
  would mint a ``gap`` record that looks like a local measurement of an axis
  nobody local ever produced. So it never travels into this backend — not in
  ``measure``, not in ``rank``.

Pure: no Qt, no HTTP, no state. The envelope is built from the request + the
caller's ``SeriesContext``; nothing is remembered between calls.
"""

from __future__ import annotations

from tabs.image_gallery.analysis.read import read_axes
from tabs.image_gallery.backends.context import (
    MeasuredItem,
    SeriesContext,
    item_key_of,
    select_members,
)
from tabs.image_gallery.backends.contract import MeasurementEnvelope, MeasureRequest
from tabs.image_gallery.services.metric_profile import (
    DOMAIN_ALGORITHMS,
    profile_for_mode,
)


def axes_for_mode(mode=None) -> tuple[str, ...]:
    """This backend's mode-implied axis set (the ``heuristic`` profile).

    The single definition of "which axes a mode implies" as a BACKEND artifact:
    ``rank_fusion.measured_axes_for`` delegates here for the no-profile case,
    so a caller in the AI domain cannot reach the mode mapping by passing no
    profile (it is refused, see :mod:`tabs.image_gallery.services.rank_fusion`).
    """
    return tuple(profile_for_mode(mode).axis_ids)


def local_axes(profile) -> tuple[str, ...]:
    """The axes this backend measures in *profile*: ``axis_ids`` (registry half).

    Deliberately NOT ``backends.context.profile_axes`` (which also returns the
    judge's names): a judge-named axis has no local producer, so it is not part
    of this backend's measurement — and it must not travel into the local rank
    either (``.rank.rank`` passes this set to the fusion).
    """
    out: list[str] = []
    for axis in tuple(getattr(profile, "axis_ids", ()) or ()):
        name = str(axis)
        if name and name not in out:
            out.append(name)
    return tuple(out)


def measure(
    adapter,
    request: MeasureRequest,
    *,
    context: SeriesContext | None = None,
) -> MeasurementEnvelope:
    """Per-member ``AxisValue`` records, read through ``analysis.read``.

    *adapter* is the owning :class:`~.profile.AlgorithmsBackend`: it resolves
    the request's ``OwnedProfile`` to the ``MetricProfile`` it made
    (``BackendMismatch`` / ``NoProfileYet`` are its answers, never repaired
    here). The axes are :func:`local_axes` — the registry half — so a profile
    that somehow carried a judge name cannot make this backend report a local
    record for it.
    """
    profile = adapter._require_profile(request.profile, operation="measure")
    members = select_members(
        request.item_keys, (context.members if context is not None else ())
    )
    axes = local_axes(profile)
    records = tuple(
        MeasuredItem(
            item_key=item_key_of(member),
            records=tuple(
                read_axes(
                    member,
                    domain=DOMAIN_ALGORITHMS,
                    axes=axes,
                    profile=profile,
                )
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


__all__ = ["axes_for_mode", "local_axes", "measure"]
