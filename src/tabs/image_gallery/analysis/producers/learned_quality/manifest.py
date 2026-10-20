"""Manifest — the learned perceptual trio (metadata only, no backend import).

The axes are the three learned registry specs of ``metric_scores.SPECS``
(``lpips`` / ``dists`` reference-based, ``brisque`` no-reference). They are
spelled here rather than derived from the registry because a derived manifest
would claim every measured axis, and re-listing the trio is the smallest
vocabulary that cannot drift.

No ``quality_models`` import: that module is fail-soft at import, but its
backend (``torch`` + ``piq``) shares OpenMP with PySide6 and can segfault at
teardown, so discovery — which imports every manifest on each start — must not
touch it (plan trap 2). The producer imports the seam inside ``run()``.

``requires={"images"}`` only: BRISQUE needs no reference, and the reference
half is answered with an explicit gap for a sourceless item instead of making
the whole producer ineligible (which would silently drop BRISQUE too).
"""

from __future__ import annotations

from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="learned_quality",
    provides={
        "lpips": "measured",
        "dists": "measured",
        "brisque": "measured",
    },
    requires=frozenset({"images"}),
    cost="free",
    automatic=False,
)
