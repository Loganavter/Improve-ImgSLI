"""Manifest — the seven artifact flags, answered by the legacy aggregate.

Why one producer and not seven (W8, ``task-gallery-analysis-engine-w8-artifact-
catalog-2026-10-20``): production does not call the detectors one-to-one. It
calls ``services.artifacts.analyze_images(proxy, source)``, which layers
``_anchor_severity`` over the four *absolute* detectors (banding, halo,
blocking, chroma_fringing) when a source image is present. A producer that
wrapped ``detect_*`` directly could therefore report a severity the report
disagrees with for those four axes. One producer that wraps the aggregate cannot
drift from it by construction.

The axes are ``candidate``: each detector answers a ``Severity`` flag, and a
flag is not a 0..100 quality number (plan §Pool: artifacts become
``MetricKind.CANDIDATE`` axes, never numbers). ``requires={"images"}`` — a
source image is an improvement, not a precondition: it is what the anchoring
and the source-relative detectors consume, and it must never be a hard
requirement, or a folder without a reference would lose the absolute flags
entirely.

``provides`` order is the record order the producer returns (the registry keeps
each manifest's own order), so it is written as the catalog's reading order
rather than alphabetically.
"""

from __future__ import annotations

from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="artifact_catalog",
    provides={
        "banding": "candidate",
        "halo": "candidate",
        "blocking": "candidate",
        "chroma_fringing": "candidate",
        "invented_texture": "candidate",
        "noise_amplification": "candidate",
        "over_smoothing": "candidate",
    },
    requires=frozenset({"images"}),
    cost="free",
    automatic=False,
)
