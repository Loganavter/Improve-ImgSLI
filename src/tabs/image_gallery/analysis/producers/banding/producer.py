"""``run(ctx)`` — the ``banding`` artifact flag over one already-decoded image.

Wraps ``services.artifacts.detect_banding``; the heuristic stays there and is neither
re-tuned nor re-implemented. The result is a **candidate flag, not a quality
score**: the manifest declares ``banding`` as ``candidate``, and the value is the
severity rank (``clean=0``, ``mild=1``, ``flagged=2``) — monotone in "how bad",
with no invented 0..100 number the detector never produced.

No file I/O, no store, no controller, no ``services.proxy``: the context owns
the decode (plan trap 1 / gate G11). ``ctx.source_image`` is optional and is
passed through: the source-relative detectors compare against it, while the
absolute ones (banding/halo/blocking/chroma_fringing) ignore the argument — the
source-anchoring policy for those stays in ``artifacts.analyze_images`` and is
not re-implemented here.
"""

from __future__ import annotations

from engine.analysis.contracts import AxisValue
from engine.analysis.context import AnalysisContext

#: Producer id carried by every record (the manifest id is the run-level one).
PRODUCER_ID = "local"

#: Axis this package answers (also declared in the manifest).
AXIS = "banding"

NO_IMAGE_REASON = "the analysis context carries no decoded proxy image"

#: ``Severity`` → rank. Higher = worse, so a flagged defect never sorts as "good".
SEVERITY_RANK = {"clean": 0.0, "mild": 1.0, "flagged": 2.0}


def _rank(severity: object) -> float | None:
    value = getattr(severity, "value", severity)
    return SEVERITY_RANK.get(str(value).lower())


def run(ctx: AnalysisContext) -> tuple[AxisValue, ...]:
    """The ``banding`` flag for *ctx*; a gap (with a reason) when there is no image."""
    if ctx.proxy_image is None:
        return (
            AxisValue(
                axis=AXIS,
                value=None,
                producer=PRODUCER_ID,
                status="gap",
                reason=ctx.require("images") or NO_IMAGE_REASON,
            ),
        )
    from tabs.image_gallery.services import artifacts

    severity = artifacts.detect_banding(ctx.proxy_image, ctx.source_image)
    rank = _rank(severity)
    if rank is None:
        return (
            AxisValue(
                axis=AXIS,
                value=None,
                producer=PRODUCER_ID,
                status="gap",
                reason=f"detector returned an unknown severity {severity!r}",
            ),
        )
    return (AxisValue(axis=AXIS, value=rank, producer=PRODUCER_ID),)


__all__ = ["AXIS", "PRODUCER_ID", "run"]
