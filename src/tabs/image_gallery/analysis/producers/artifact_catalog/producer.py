"""``run(ctx)`` — the seven artifact flags, exactly as the legacy aggregate says.

Wraps ``services.artifacts.analyze_images(proxy_image, source_image)`` — the one
call the production stage already makes — and maps each returned ``Severity`` to
its rank (``clean=0``, ``mild=1``, ``flagged=2``). The detector heuristics and
the source-anchoring policy (``_anchor_severity`` over banding/halo/blocking/
chroma_fringing) stay in the service: this producer neither re-tunes nor
re-implements them, so an engine record and the ``entry["artifacts"]`` catalog
for the same item cannot disagree.

Deliberately NOT one producer per detector: the aggregate's anchoring delta is
above the detectors, and a per-detector wrapper would silently report the
unanchored severity for the four absolute axes (the W7 dark-launch finding this
wave closes).

No file I/O, no store, no controller, no ``services.proxy``: the context owns
the decode (plan trap 1 / gate G11). ``ctx.source_image`` is optional — the
service runs the source-relative detectors and the anchoring only when it is
present, and returns the plain absolute flags otherwise.
"""

from __future__ import annotations

from engine.analysis.contracts import AxisValue
from engine.analysis.context import AnalysisContext

from . import manifest

#: Producer id carried by every record (the manifest id is the run-level one).
PRODUCER_ID = "local"

NO_IMAGE_REASON = "the analysis context carries no decoded proxy image"

#: ``Severity`` → rank. Higher = worse, so a flagged defect never sorts as "good".
SEVERITY_RANK = {"clean": 0.0, "mild": 1.0, "flagged": 2.0}


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


def _rank(severity: object) -> float | None:
    value = getattr(severity, "value", severity)
    return SEVERITY_RANK.get(str(value).lower())


def _axis_value(axis: str, severities: dict) -> AxisValue:
    severity = severities.get(axis)
    if severity is None:
        return _gap(axis, f"the artifact catalog reported no {axis!r} severity")
    rank = _rank(severity)
    if rank is None:
        return _gap(
            axis, f"the artifact catalog returned an unknown severity {severity!r}"
        )
    return AxisValue(axis=axis, value=rank, producer=PRODUCER_ID)


def run(ctx: AnalysisContext) -> tuple[AxisValue, ...]:
    """The seven artifact flags for *ctx*; gaps (with a reason) without an image."""
    if ctx.proxy_image is None:
        reason = ctx.require("images") or NO_IMAGE_REASON
        return tuple(_gap(axis, reason) for axis in _axes())
    from tabs.image_gallery.services import artifacts

    severities = artifacts.analyze_images(ctx.proxy_image, ctx.source_image)
    # Keyed by the axis id (``Artifact`` is a str Enum: its ``value`` is the id).
    by_axis = {
        str(getattr(artifact, "value", artifact)): severity
        for artifact, severity in severities.items()
    }
    return tuple(_axis_value(axis, by_axis) for axis in _axes())


__all__ = ["PRODUCER_ID", "SEVERITY_RANK", "run"]
