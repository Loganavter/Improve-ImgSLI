"""Manifest — reference-free camera scalars (metadata only, no imports of math).

Discovery imports every manifest on each start, so this module must stay light:
no PIL, no numpy, no learned backend. The axes are the canonical
``metric_scores.SPECS`` ids.

The white-balance axis is declared even though ``services/camera_metrics.py``
never reports it today: declaring it keeps it in the registry vocabulary (plan
§Pool) and lets the producer answer it with an explicit ``gap`` instead of the
axis silently vanishing from the report.

``brisque`` is declared because the legacy camera stage DOES report it:
``measure_camera_from_image`` merges ``quality_models.nr_metrics`` (BRISQUE) into
the dict it returns, so the legacy report showed the axis on photographic
content. Declaring it here restores that axis to the engine (a local plan used
to gap it, showing fewer axes than the legacy UI on the same folder). Nothing
heavy is imported here — the producer maps the raw the camera measurement
already appended, and BRISQUE's content gate (cartoon/line-art/screenshot) or a
missing learned backend answers the axis with an explicit ``gap``
(task-gallery-brisque-axis-2026-10-21).
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
        # Appended by ``measure_camera_from_image`` via ``nr_metrics`` (legacy
        # camera stage); last here so the record order matches that dict.
        "brisque": "measured",
    },
    requires=frozenset({"images"}),
    cost="free",
    automatic=False,
)
