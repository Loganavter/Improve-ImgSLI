"""Manifest — the per-image AI scorecard (metadata only, no client imports).

The axes are the MEASURED registry, imported from ``metric_scores.SPECS``
rather than re-listed here: the tree already carries three drifting
vocabularies (16 ``SPECS`` / 17 ``SCORECARD_AXIS_IDS`` / 17 ``parse._AXIS_IDS``)
and a hand-written manifest would be a fourth (plan §Pool). ``composition`` is
deliberately absent — it is the AI-only axis with no local detector, so it is
not one of the measured axes this producer answers.

``metric_scores`` is stdlib-pure (dataclasses + the ``MetricKind`` enum), so the
manifest import stays light: discovery imports every manifest on every start
(plan §"Analyzers are auto-discovered producer packages", trap 2).

``automatic=True`` with ``max_per_run=_AI_VISIBLE_CAP`` (12): this is the
producer that may cost money without an explicit click, so it carries the same
visible-item ceiling the controller already applies
(``controller.py`` ``_AI_VISIBLE_CAP``; plan I3/G7).
"""

from __future__ import annotations

from engine.analysis.contracts import ProducerSpec

from tabs.image_gallery.services import metric_scores

#: Same ceiling as ``GalleryController._AI_VISIBLE_CAP`` — an automatic network
#: producer must not fan out past the visible items.
MAX_PER_RUN = 12

PRODUCER = ProducerSpec(
    id="ai_scorecard",
    provides={
        spec.id: "measured"
        for spec in metric_scores.SPECS
        if spec.kind is metric_scores.MetricKind.MEASURED
    },
    requires=frozenset({"images", "backend"}),
    cost="per_image",
    automatic=True,
    max_per_run=MAX_PER_RUN,
)
