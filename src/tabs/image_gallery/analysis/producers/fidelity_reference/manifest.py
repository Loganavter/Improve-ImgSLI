"""Manifest — source-relative fidelity deltas (metadata only, no math imports).

A reference is genuinely required here: every axis is a *difference* against the
source image, so without one there is nothing to subtract from and the run
answers with gaps instead of an absolute number that would mean something else.
"""

from __future__ import annotations

from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="fidelity_reference",
    provides={
        "ssim": "measured",
        "detail_gain": "measured",
        "color_accuracy": "measured",
        "clipping_delta": "measured",
        "halo_delta": "measured",
        "chroma_fringe_delta": "measured",
    },
    requires=frozenset({"images", "reference"}),
    cost="free",
    automatic=False,
)
