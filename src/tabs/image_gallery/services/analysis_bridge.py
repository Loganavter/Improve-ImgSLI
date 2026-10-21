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

P9a — the engine is the DEFAULT. ``engine_enabled`` is the one reader of the
env flag: ON unless the value is an explicit off value, so a normal run needs no
env var and ``IMGSLI_ANALYSIS_ENGINE=0`` is the kill-switch (the legacy stage
calls are still present and are what a disabled run executes). The legacy
branch is deleted in a later wave, not here.

Pure + Qt-free (safe for ``GenericWorker``); no Store/EventBus writes.

INTERFACE: ``ENGINE_FLAG``, ``ENGINE_OFF_VALUES``, ``engine_enabled``,
``LEGACY_RAW_KEYS``, ``CAMERA_AXES``, ``FIDELITY_AXES``, ``ARTIFACT_AXES``,
``raw_dict``, ``artifact_dict``, ``upscale_factor``,
``stage_dicts_from_records``, ``engine_records``.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("ImproveImgSLI")

#: Env flag of the analysis engine (plan-gallery-analysis-engine-2026-10-20 P1;
#: P9a made the engine the default, so this is now a kill-switch).
ENGINE_FLAG = "IMGSLI_ANALYSIS_ENGINE"

#: The only values that turn the engine OFF (``str.strip().lower()`` before the
#: comparison). Anything else — unset, empty, whitespace, garbage — is ON: a
#: typo must not silently restore the legacy path.
ENGINE_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def engine_enabled() -> bool:
    """Whether the analysis engine owns the proxy batch (P9a: ON by default).

    Read per call rather than cached, so the kill-switch applies to the next
    batch without a restart. Only ``ENGINE_OFF_VALUES`` disables the engine;
    everything else (unset, empty, unknown) keeps it on.
    """
    try:
        raw = os.environ.get(ENGINE_FLAG)
    except Exception:  # pragma: no cover - environ is a plain dict in CPython
        return True
    if raw is None:
        return True
    return raw.strip().lower() not in ENGINE_OFF_VALUES


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
#: vocabulary: a missing record sends that stage back to its legacy call.
CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance", "brisque")
FIDELITY_AXES = ("ssim", "detail_gain", "color_accuracy", "clipping_delta", "halo_delta",
                 "chroma_fringe_delta", "lpips", "dists")
ARTIFACT_AXES = ("banding", "halo", "blocking", "chroma_fringing", "invented_texture",
                 "noise_amplification", "over_smoothing")


def raw_dict(by_axis: dict, axes) -> dict | None:
    """``{legacy raw key: pre-score raw}`` of the axes answering ``ok``; None when
    the stage cannot be reproduced (missing/``error`` record, or no ``raw``), so
    the caller runs that one legacy call. A ``gap`` is an answer: it is absent,
    exactly as the legacy dict has no such key."""
    out: dict = {}
    for axis in axes:
        record = by_axis.get(axis)
        if record is None or str(getattr(record, "status", "")) == "error":
            return None
        if str(getattr(record, "status", "")) != "ok":
            continue
        raw = getattr(record, "raw", None)
        if raw is None:
            return None
        out[LEGACY_RAW_KEYS.get(axis, axis)] = float(raw)
    return out


def artifact_dict(by_axis: dict) -> dict | None:
    """``{Artifact: Severity}`` from the catalog ranks; None if any is missing —
    the legacy catalog always carries all seven flags (clean on error), so a
    gap/error/unranked record cannot be rebuilt from records."""
    from tabs.image_gallery.models import Artifact, Severity

    by_rank = {0.0: Severity.CLEAN, 1.0: Severity.MILD, 2.0: Severity.FLAGGED}
    out: dict = {}
    for axis in ARTIFACT_AXES:
        record = by_axis.get(axis)
        raw = getattr(record, "raw", None)
        if str(getattr(record, "status", "")) != "ok" or raw is None:
            return None
        if float(raw) not in by_rank:
            return None
        out[Artifact(axis)] = by_rank[float(raw)]
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
    Each stage is rebuilt independently and an unreproducible stage stays OUT of
    the result, so the caller runs only that one legacy call.

    ``artifacts_from_records`` says whether these records' artifact severities
    are the catalog the entry needs: with ``full_res_artifacts`` the production
    catalog is the TILED one over a full-resolution store, and records measured
    over the bounded proxy would report a different severity for the same flag
    (W14 — the 8x8 block grid and thin rims do not survive the downscale). The
    caller passes ``False`` when it could not hand the engine that store, and
    then leaves the artifact dict to its own tiled call.
    """
    by_axis: dict = {}
    for record in records or ():
        by_axis.setdefault(str(getattr(record, "axis", "") or ""), record)
    by_axis.pop("", None)
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
        # the batch, and the legacy stages rebuild a complete entry without it
        # (plan G6 is about producer fallbacks, not about this opt-in seam).
        logger.warning(
            "proxy batch: analysis engine hook failed for %s", own, exc_info=True
        )
        return None


__all__ = [
    "ARTIFACT_AXES",
    "CAMERA_AXES",
    "ENGINE_FLAG",
    "ENGINE_OFF_VALUES",
    "FIDELITY_AXES",
    "LEGACY_RAW_KEYS",
    "artifact_dict",
    "engine_enabled",
    "engine_records",
    "raw_dict",
    "stage_dicts_from_records",
    "upscale_factor",
]
