"""``run(ctx)`` — camera scalars over one already-decoded proxy image.

Wraps ``services.camera_metrics.measure_camera_from_image``; it does not
re-implement or re-tune the math. Raw values keep their detector meaning and
``metric_scores`` stays the ONE raw→0..100 mapping, so a value produced here is
the same number the report already shows.

No file I/O, no store, no controller, no ``services.proxy``: the context owns
the decode (plan trap 1 / gate G11). A raw key the measurement did not report
becomes ``status="gap"`` with its reason — never a substituted ``0``, which
would read as "perfectly neutral/exposed" and outrank measured items.
"""

from __future__ import annotations

from engine.analysis.contracts import AxisValue
from engine.analysis.context import AnalysisContext

from tabs.image_gallery.services import camera_metrics, metric_scores

from . import manifest

#: Producer id carried by every record (the manifest id is the run-level one).
PRODUCER_ID = "local"

NO_IMAGE_REASON = "the analysis context carries no decoded proxy image"
NOT_MEASURED_REASON = "camera metrics measured nothing on this image"


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


def _axis_value(axis: str, raw: dict) -> AxisValue:
    spec = metric_scores.spec_for(axis)
    if spec is None:
        return _gap(axis, f"no metric spec is registered for {axis!r}")
    got = metric_scores.raw_for(spec, raw)
    if got is None:
        return _gap(axis, f"camera metrics report no {axis!r} value")
    return AxisValue(
        axis=axis,
        value=float(metric_scores.score_for(spec, got[1])),
        producer=PRODUCER_ID,
    )


def run(ctx: AnalysisContext) -> tuple[AxisValue, ...]:
    """Camera scalars for *ctx*; gaps (with reasons) when an input is missing."""
    if ctx.proxy_image is None:
        return _gaps(ctx.require("images") or NO_IMAGE_REASON)
    raw = camera_metrics.measure_camera_from_image(ctx.proxy_image)
    if not raw:
        return _gaps(NOT_MEASURED_REASON)
    return tuple(_axis_value(axis, raw) for axis in _axes())


__all__ = ["PRODUCER_ID", "run"]
