"""Manifest — source-relative fidelity deltas (metadata only, no math imports).

A reference is genuinely required here: every axis is a *difference* against the
source image, so without one there is nothing to subtract from and the run
answers with gaps instead of an absolute number that would mean something else.

``lpips`` / ``dists`` are declared here rather than in a separate producer
(W13): ``fidelity_metrics.compute_fidelity_from_images`` already calls
``quality_models.pair_metrics`` once for the pair, so the learned distances
arrive in the SAME dict as the detector deltas. A second producer re-ran that
torch forward pass for the same two images — same numbers, double the cost.
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
        # Optional learned backend: absent backend = a gap with its own reason,
        # never a substituted distance (see producer._missing_reason).
        "lpips": "measured",
        "dists": "measured",
    },
    requires=frozenset({"images", "reference"}),
    cost="free",
    automatic=False,
)
