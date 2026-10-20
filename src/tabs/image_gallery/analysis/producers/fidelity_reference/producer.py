"""``run(ctx)`` — source-relative fidelity deltas over two decoded images.

Wraps ``services.fidelity_metrics.compute_fidelity_from_images``; the detector
math and its caps stay there. Its raw keys (ssim, hf_ratio, delta_e,
clipping_delta, halo_delta, chroma_fringe_delta) are mapped through
``metric_scores`` — the ONE raw→0..100 mapping — so an axis id here resolves to
the same number the report already shows.

No file I/O, no store, no controller, no ``services.proxy``: both images arrive
decoded in the context (plan trap 1 / gate G11). A raw key the computation did
not produce is a ``status="gap"`` with its reason, never a zero — fidelity
"unavailable" and fidelity "0 %" are different answers to the user.
"""

from __future__ import annotations

from engine.analysis.contracts import AxisValue
from engine.analysis.context import AnalysisContext

from tabs.image_gallery.services import fidelity_metrics, metric_scores

from . import manifest

#: Producer id carried by every record (the manifest id is the run-level one).
PRODUCER_ID = "local"

NO_IMAGE_REASON = "the analysis context carries no decoded proxy image"
NO_REFERENCE_REASON = "the analysis context carries no source (reference) image"
NOT_MEASURED_REASON = "fidelity metrics measured nothing on this pair"


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
        return _gap(axis, f"fidelity metrics report no {axis!r} value")
    return AxisValue(
        axis=axis,
        value=float(metric_scores.score_for(spec, got[1])),
        producer=PRODUCER_ID,
        # Pre-score detector value: the legacy fidelity dict is rebuilt from it
        # instead of re-computing the pair (W12 dedupe).
        raw=float(got[1]),
    )


def run(ctx: AnalysisContext) -> tuple[AxisValue, ...]:
    """Fidelity deltas for *ctx*; gaps (with reasons) when an input is missing."""
    if ctx.proxy_image is None:
        return _gaps(ctx.require("images") or NO_IMAGE_REASON)
    if ctx.source_image is None:
        return _gaps(ctx.require("reference") or NO_REFERENCE_REASON)
    raw = fidelity_metrics.compute_fidelity_from_images(
        ctx.proxy_image, ctx.source_image
    )
    if not raw:
        return _gaps(NOT_MEASURED_REASON)
    return tuple(_axis_value(axis, raw) for axis in _axes())


__all__ = ["PRODUCER_ID", "run"]
