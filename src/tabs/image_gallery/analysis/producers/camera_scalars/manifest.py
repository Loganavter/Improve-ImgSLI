"""Manifest — reference-free camera scalars (metadata only, no imports of math).

Discovery imports every manifest on each start, so this module must stay light:
no PIL, no numpy, no learned backend. The axes are the canonical
``metric_scores.SPECS`` ids.

The white-balance axis is declared even though ``services/camera_metrics.py``
never reports it today: declaring it keeps it in the registry vocabulary (plan
§Pool) and lets the producer answer it with an explicit ``gap`` instead of the
axis silently vanishing from the report.
"""

from __future__ import annotations

from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="camera_scalars",
    provides={
        "sharpness": "measured",
        "exposure": "measured",
        "clipping": "measured",
        "noise": "measured",
        "white_balance": "measured",
    },
    requires=frozenset({"images"}),
    cost="free",
    automatic=False,
)
