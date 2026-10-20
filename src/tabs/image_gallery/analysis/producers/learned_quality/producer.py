"""``run(ctx)`` — the learned perceptual trio over one decoded proxy image.

Wraps ``services.quality_models``, the ONE learned-backend seam: LPIPS + DISTS
come from ``pair_metrics(proxy, source)``, BRISQUE from
``nr_metrics(proxy)``. This module does not import ``torch``/``piq`` itself —
``quality_models`` loads them lazily inside that seam (torch + PySide6 share
OpenMP and can segfault at teardown), and its functions are already fail-soft:
an absent backend is an empty dict, never an exception and never invented
numbers.

Raw values keep their detector meaning and ``metric_scores`` stays the ONE
raw→0..100 mapping, so an axis produced here is the same number the report
already shows.

Two gates stay distinct, exactly as ``quality_models`` documents them: an
*availability* failure (backend missing/error) gaps every axis with the
backend's own reason, while BRISQUE's per-image *applicability* gate (content
is illustrative) gaps only BRISQUE. A reference axis on a sourceless item names
the missing source rather than the backend, because that is the actual cause.

No file I/O, no store, no controller, no ``services.proxy``: the context owns
the decode (plan trap 1 / gate G11).
"""

from __future__ import annotations

import logging

from engine.analysis.contracts import AxisValue
from engine.analysis.context import AnalysisContext

from tabs.image_gallery.services import metric_scores, quality_models

from . import manifest

logger = logging.getLogger("ImproveImgSLI")

#: Producer id carried by every record (the manifest id is the run-level one).
PRODUCER_ID = "local"

NO_IMAGE_REASON = "the analysis context carries no decoded proxy image"
NO_REFERENCE_REASON = "the analysis context carries no source (reference) image"
NO_VALUE_REASON = "the learned backend measured no value for this axis"

#: Axes that need a source to compare against (BRISQUE does not).
REFERENCE_AXES = frozenset({"lpips", "dists"})


def _axes() -> tuple[str, ...]:
    """The declared axes, from the manifest (single source of the vocabulary)."""
    return tuple(manifest.PRODUCER.provides)


def _gap(axis: str, reason: str) -> AxisValue:
    return AxisValue(
        axis=axis,
        value=None,
        producer=PRODUCER_ID,
        status="gap",
        reason=reason,
    )


def _gaps(reason: str) -> tuple[AxisValue, ...]:
    return tuple(_gap(axis, reason) for axis in _axes())


def _backend_reason() -> str:
    """Why the backend returned nothing — its own explicit state, not a guess.

    ``quality_models`` records ``ready`` / ``missing`` / ``error`` plus a reason
    instead of failing silently, so an unavailable axis says which gate stopped
    it. A ``ready`` backend with no number means the per-image applicability
    gate (e.g. BRISQUE on illustrative content), which is a different state.
    """
    try:
        status = quality_models.backend_status()
        detail = quality_models.backend_reason()
    except Exception as exc:  # noqa: BLE001 - a reason must never become a crash
        return f"the learned backend state could not be read: {type(exc).__name__}: {exc}"
    if status != "ready":
        return f"the learned backend is {status}" + (f": {detail}" if detail else "")
    return NO_VALUE_REASON


def _axis_value(axis: str, raw: dict, missing_reason: str) -> AxisValue:
    spec = metric_scores.spec_for(axis)
    if spec is None:
        return _gap(axis, f"no metric spec is registered for {axis!r}")
    got = metric_scores.raw_for(spec, raw)
    if got is None:
        return _gap(axis, missing_reason)
    return AxisValue(
        axis=axis,
        value=float(metric_scores.score_for(spec, got[1])),
        producer=PRODUCER_ID,
    )


def run(ctx: AnalysisContext) -> tuple[AxisValue, ...]:
    """Learned trio for *ctx*; gaps (with reasons) when an input is missing."""
    if ctx.proxy_image is None:
        return _gaps(ctx.require("images") or NO_IMAGE_REASON)
    has_source = ctx.source_image is not None
    try:
        raw: dict = {}
        if has_source:
            raw.update(quality_models.pair_metrics(ctx.proxy_image, ctx.source_image))
        raw.update(quality_models.nr_metrics(ctx.proxy_image))
    except Exception as exc:  # noqa: BLE001 - a backend failure is a gap, not a crash
        # ``quality_models`` already swallows its own failures, so this is the
        # belt-and-braces path for an injected/future backend that raises.
        logger.debug("learned quality producer failed", exc_info=True)
        return _gaps(f"the learned backend raised {type(exc).__name__}: {exc}")
    unavailable = _backend_reason()
    return tuple(
        _axis_value(
            axis,
            raw,
            NO_REFERENCE_REASON if axis in REFERENCE_AXES and not has_source else unavailable,
        )
        for axis in _axes()
    )


__all__ = ["PRODUCER_ID", "run"]
