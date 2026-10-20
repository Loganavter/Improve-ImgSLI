"""Manifest — the ``noise_amplification`` artifact flag (metadata only, no math imports).

The axis is a ``candidate``: the detector answers a ``Severity`` flag, and a
flag is not a 0..100 quality number (plan §Pool: artifacts become
``MetricKind.CANDIDATE`` axes, never numbers). ``requires={"images"}`` — a
source image is an improvement, not a precondition: it is what the
source-relative detectors need, and it must never be a hard requirement, or a
folder without a reference would lose the absolute detectors entirely.
"""

from __future__ import annotations

from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="artifact_noise_amplification",
    provides={"noise_amplification": "candidate"},
    requires=frozenset({"images"}),
    cost="free",
    automatic=False,
)
