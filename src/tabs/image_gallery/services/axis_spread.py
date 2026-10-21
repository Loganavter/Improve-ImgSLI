"""The series' own per-axis SPREAD — one measurement, one definition (P1/P5).

Split out of ``services/metric_profile`` (file-size policy; that module is the
pool/mode/offer vocabulary, this one is the measurement the offer is built from).
Re-exported as ``metric_profile.axis_spreads`` — callers and tests keep reading it
from the profile seam, and there is never a second implementation.

Pure: no Qt, no HTTP, no state.
"""

from __future__ import annotations

from tabs.image_gallery.services.metric_scores import (
    raw_for,
    score_for,
    spec_for,
)


def axis_spreads(items) -> dict[str, float]:
    """``{axis_id: spread}`` for every pool axis the series can separate.

    ``spread`` is ``max − min`` of the axis' 0–100 quality score over the items
    that carry a value; axes with fewer than two measured values are omitted (a
    single value must never invent a signal). Registry (pool) order.

    A value for an axis is the item's engine record (``analysis_records``,
    ``status="ok"``) when the item has a record for that axis, else the legacy
    ``raw_for`` → ``score_for`` score. The record is already 0–100, so it is used
    as-is. A record that is not ``ok`` (``gap``/``error``) **excludes** the item
    from that axis — never 0, and never backfilled from ``item.metrics`` (the
    engine ran and had nothing, which is a different fact).

    The ONE spread over ITEM metrics, TWO named readers and no third:
    the P5 offer (:func:`profile_for_series` — "which axes can separate THIS
    series", i.e. what the model is asked about, and through
    ``profile_select.salience_axes`` the adaptive-probe summary) reads it to
    decide which axes are offered at all. It is NOT the rank's salience
    measurement: the rank / Jev vector asks a different question — "does this
    axis separate these variants under the producing INSTRUMENT's noise floor" —
    over the per-member vectors, and that answer lives in
    ``rank_fusion.axis_salience``.
    """
    # Deferred import: ``rank_fusion`` imports this module at load time, so a
    # module-level import would be circular. One reader of the records
    # (``rank_fusion._record_scores`` / ``_record_axes``) — never a second one.
    from tabs.image_gallery.services.metric_profile import MEASURED_POOL
    from tabs.image_gallery.services.rank_fusion import _record_axes, _record_scores

    try:
        members = list(items or ())
    except Exception:
        members = []
    if len(members) < 2:
        return {}
    record_maps: list[tuple[dict[str, float], frozenset[str]]] = []
    for item in members:
        try:
            record_maps.append((_record_scores(item), _record_axes(item)))
        except Exception:
            record_maps.append(({}, frozenset()))
    out: dict[str, float] = {}
    for axis_id in MEASURED_POOL:
        spec = spec_for(axis_id)
        if spec is None:
            continue
        values: list[int] = []
        for item, (record_scores, recorded_axes) in zip(members, record_maps):
            try:
                if axis_id in recorded_axes:
                    record_value = record_scores.get(axis_id)
                    if record_value is not None:
                        values.append(int(record_value))
                    continue  # a gap/error record excludes the item for this axis
                metrics = getattr(item, "metrics", None)
                if not isinstance(metrics, dict) or not metrics:
                    continue
                got = raw_for(spec, metrics)
                if got is None:
                    continue
                _key, raw = got
                values.append(int(score_for(spec, raw)))
            except Exception:
                continue
        if len(values) >= 2:
            out[axis_id] = float(max(values) - min(values))
    return out


__all__ = ["axis_spreads"]
