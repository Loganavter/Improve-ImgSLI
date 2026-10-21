"""The record → legacy-dict bridge, and the engine hook that produces records.

W12 removed the second detector pass from the engine-on Stage-2 path: the engine
runs FIRST and the legacy ``{stage: dict}`` entries are rebuilt from the
records' pre-score ``raw`` values. This module is that glue, moved out of
``services/proxy.py`` (W14) so the proxy stays a decode/cache module instead of
carrying the engine's record vocabulary as well.

Two independent pieces:

- ``engine_records`` — the ONE place that builds an ``AnalysisContext`` for an
  item and runs the local plan. It is the engine hook of the production path:
  the same decoded proxy the legacy stages consume, plus (when the caller
  prepared them) a full-resolution ``tiled_store`` and its
  ``tiled_source_store`` reference, so the artifact producer can answer the
  tiled catalog seen in ``full_res_artifacts`` mode instead of the bounded one.
- ``stage_dicts_from_records`` — the compatibility shim back to the legacy
  dicts, plus the constants describing their SHAPES.

P9b — the engine is the ONLY path. The env flag, its off values and the single
function that read them are gone: there is no kill-switch and no
"run the engine first, else the legacy stages" branch. A stage the records
cannot reproduce is a GAP in the entry (no numbers) plus one ``warning`` from
``services/proxy.py`` naming the stage and the producer — never a second
measurement by the legacy detector. The single deliberate exception is the
artifact catalog, which stays a fallback in ``services/proxy.py``: a missing
artifact entry renders as ``clean`` in the UI, so its absence would read as
"nothing wrong" instead of as a failure.

Pure + Qt-free (safe for ``GenericWorker``); no Store/EventBus writes.

INTERFACE: ``LEGACY_RAW_KEYS``, ``CAMERA_AXES``, ``FIDELITY_AXES``,
``ARTIFACT_AXES``, ``raw_dict``, ``artifact_dict``, ``upscale_factor``,
``records_by_axis``, ``unusable_axes``, ``reportable_gaps``, ``describe_gaps``,
``stage_dicts_from_records``, ``engine_records``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


#: Engine axis id -> the raw key its legacy stage dict uses, for the three axes
#: whose detector key is not the axis id — the entry is consumed by KEY
#: (``metrics_stage2`` needs ``hf_ratio``/``delta_e``, the report ``clipping_pct``).
LEGACY_RAW_KEYS = {
    "clipping": "clipping_pct",
    "detail_gain": "hf_ratio",
    "color_accuracy": "delta_e",
}

#: The axes each legacy Stage-2 dict carries, in its own order — the legacy
#: SHAPES (``measure_camera_from_image`` + the BRISQUE it appends;
#: ``compute_fidelity_from_images``' deltas + LPIPS/DISTS), not a producer
#: vocabulary. An axis no producer answers (today: ``brisque``, whose producer
#: W13 deleted) is simply absent from the rebuilt dict — a gap, not a reason to
#: re-measure the stage.
CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance", "brisque")
FIDELITY_AXES = ("ssim", "detail_gain", "color_accuracy", "clipping_delta", "halo_delta",
                 "chroma_fringe_delta", "lpips", "dists")
ARTIFACT_AXES = ("banding", "halo", "blocking", "chroma_fringing", "invented_texture",
                 "noise_amplification", "over_smoothing")


def records_by_axis(records) -> dict:
    """``{axis: record}`` for *records* (first record per axis wins).

    The one lookup the rebuild and its gap reporting share, so "which axes did
    this stage answer" is decided in exactly one place.
    """
    by_axis: dict = {}
    for record in records or ():
        by_axis.setdefault(str(getattr(record, "axis", "") or ""), record)
    by_axis.pop("", None)
    return by_axis


def _usable_raw(record) -> float | None:
    """The pre-score value a record can contribute, or None if it cannot.

    Only ``status="ok"`` with a ``raw`` is usable: a ``gap`` means the producer
    ran and measured nothing, an ``error`` means it failed. Both are absent from
    the rebuilt dict (P9b: gaps are the honest answer, never a legacy re-run).
    """
    if record is None or str(getattr(record, "status", "")) != "ok":
        return None
    raw = getattr(record, "raw", None)
    return None if raw is None else float(raw)


def unusable_axes(by_axis: dict, axes) -> tuple[str, ...]:
    """The axes of *axes* without a usable record — what the stage loses."""
    return tuple(axis for axis in axes if _usable_raw(by_axis.get(axis)) is None)


def reportable_gaps(by_axis: dict, axes) -> tuple[str, ...]:
    """The axes a caller must WARN about; ``()`` for a normal partial stage.

    Two cases only (P9b), so a healthy run stays quiet:

    - the stage lost EVERY axis (no usable ``ok``+``raw`` record) — its dict is
      absent from the entry;
    - a missing axis is an ``error`` (a producer that raised), even when the rest
      of the stage rebuilt.

    A plain ``gap`` is normal — nothing measured that axis (e.g. the learned
    backend is absent) — and the read path reports each gap with its own reason,
    so a partial stage of gaps is not a warning.
    """
    missing = unusable_axes(by_axis, axes)
    if not missing or len(missing) == len(axes):
        return missing
    if any(str(getattr(by_axis.get(axis), "status", "")) == "error" for axis in missing):
        return missing
    return ()


def describe_gaps(missing, by_axis: dict) -> str:
    """``axis (producer: reason), …`` — the evidence line of a stage warning."""
    parts: list[str] = []
    for axis in missing:
        record = by_axis.get(axis)
        if record is None:
            parts.append(f"{axis} (no record)")
            continue
        producer = str(getattr(record, "producer", "") or "unknown producer")
        reason = str(getattr(record, "reason", "") or "").strip()
        parts.append(f"{axis} ({producer}: {reason})" if reason else f"{axis} ({producer})")
    return ", ".join(parts)


def raw_dict(by_axis: dict, axes) -> dict | None:
    """``{legacy raw key: pre-score raw}`` of the axes that measured; None when
    NONE of them did (that stage has no honest numbers at all, so the entry
    carries no dict for it and ``services/proxy.py`` warns).

    Partial is the normal case: white_balance, halo_delta, lpips and friends are
    gaps when nothing measured them, and a gap contributes no key — exactly as
    the legacy dict had no such key. Nothing here calls a detector a second time
    (P9b).
    """
    aux: dict = {}
    for axis in axes:
        raw = _usable_raw(by_axis.get(axis))
        if raw is None:
            continue
        aux[LEGACY_RAW_KEYS.get(axis, axis)] = raw
    return aux or None


def artifact_dict(by_axis: dict) -> dict | None:
    """``{Artifact: Severity}`` from the catalog ranks; None if any is missing.

    All-or-nothing on purpose: the catalog always carries all seven flags in the
    UI (``clean`` on error), so a gap/error/unranked record cannot be rebuilt
    from records — and a partial catalog would be read as "these are clean".
    That is exactly why ``services/proxy.py`` keeps its artifact fallback (P9b):
    absence here renders as ``clean``, not as "missing".
    """
    from tabs.image_gallery.models import Artifact, Severity

    by_rank = {0.0: Severity.CLEAN, 1.0: Severity.MILD, 2.0: Severity.FLAGGED}
    out: dict = {}
    for axis in ARTIFACT_AXES:
        raw = _usable_raw(by_axis.get(axis))
        if raw is None or raw not in by_rank:
            return None
        out[Artifact(axis)] = by_rank[raw]
    return out


def upscale_factor(item_proxy, source_proxy) -> int | None:
    """Legacy ``upscale_factor`` (long side item/source) from the ORIGINAL sizes:
    not an axis — no detector measures it, no score maps it — so no record can
    carry it; the arithmetic is ``fidelity_metrics``' own (portrait-safe)."""
    try:
        (iw, ih), (sw, sh) = tuple(item_proxy.size), tuple(source_proxy.size)
        liw, lsw = max(int(iw), int(ih)), max(int(sw), int(sh))
        return max(1, int(round(liw / lsw))) if liw > 0 and lsw > 0 else None
    except Exception:
        return None


def stage_dicts_from_records(records, *, proxy, source_proxy, same,
                             include_camera, artifacts_from_records=True) -> dict[str, dict]:
    """The legacy Stage-2 dicts rebuilt from engine records (the W12 dedupe).

    The engine's detector pass is the single computation: what the controller
    applies is read off the records' pre-score ``raw`` instead of re-measured.
    Each stage is rebuilt independently from the axes that measured it; a stage
    whose records answer nothing stays OUT of the result, and the caller leaves
    the key off the entry and warns (P9b — there is no legacy call to fall back
    to for camera/fidelity).

    ``artifacts_from_records`` says whether these records' artifact severities
    are the catalog the entry needs: with ``full_res_artifacts`` the production
    catalog is the TILED one over a full-resolution store, and records measured
    over the bounded proxy would report a different severity for the same flag
    (W14 — the 8x8 block grid and thin rims do not survive the downscale). The
    caller passes ``False`` when it could not hand the engine that store, and
    then leaves the artifact dict to its own tiled call (the one retained
    fallback).
    """
    by_axis = records_by_axis(records)
    out: dict[str, dict] = {}
    if artifacts_from_records and (artifacts := artifact_dict(by_axis)) is not None:
        out["artifacts"] = artifacts
    if include_camera and (camera := raw_dict(by_axis, CAMERA_AXES)) is not None:
        out["camera"] = camera
    if source_proxy is not None and not same:
        if (fidelity := raw_dict(by_axis, FIDELITY_AXES)) is not None:
            factor = upscale_factor(proxy, source_proxy)
            if factor is not None:
                fidelity["upscale_factor"] = factor
            out["fidelity"] = fidelity
    return out


def engine_records(own, proxy_image, source_image, *, tiled_store=None,
                   tiled_source_store=None):
    """Engine records for one item (None when it did not run): the local plan over
    the SAME decoded proxy, feeding the entry's numbers
    (``stage_dicts_from_records``) and the read path's provenance (W9).

    ``tiled_store`` / ``tiled_source_store`` are the full-resolution item and
    reference the caller already opened for the tiled artifact catalog (W14):
    passing them lets the artifact producer answer that same catalog, so the
    records and ``entry["artifacts"]`` are one computation. ``None`` keeps
    today's proxy-based records (the caller then owns the tiled call).
    """
    try:
        from engine.analysis.registry import discover
        from engine.analysis.resolver import LOCAL_POLICY, resolve_plan
        from tabs.image_gallery.analysis.context_builder import build_context
        from tabs.image_gallery.analysis.runner import PRODUCERS_PACKAGE, run_plan

        ctx = build_context(
            own,
            proxy_image=proxy_image,
            source_image=source_image,
            tiled_store=tiled_store,
            tiled_source_store=tiled_source_store,
        )
        resolution = resolve_plan(
            discover(PRODUCERS_PACKAGE), policy=LOCAL_POLICY, capabilities=ctx.capabilities
        )
        records, _journal = run_plan(resolution, {str(own): ctx})
        return records[str(own)]
    except Exception:
        # Deliberate broad except, local to the engine hook: it must not break
        # the batch. The entry then carries the artifact catalog fallback and no
        # camera/fidelity numbers; ``services/proxy.py`` warns about each stage
        # (P9b — there is no legacy branch left to rebuild them).
        logger.warning(
            "proxy batch: analysis engine hook failed for %s", own, exc_info=True
        )
        return None


__all__ = [
    "ARTIFACT_AXES",
    "CAMERA_AXES",
    "FIDELITY_AXES",
    "LEGACY_RAW_KEYS",
    "artifact_dict",
    "describe_gaps",
    "engine_records",
    "raw_dict",
    "records_by_axis",
    "reportable_gaps",
    "stage_dicts_from_records",
    "unusable_axes",
    "upscale_factor",
]
