"""INVARIANT: an AI result produced before a metrics reset cannot land after it.

A reset asks for a fresh, unranked view. A VLM reply that was already in flight
(or queued) when the reset happened describes measurements the user just threw
away: landing it would write a pre-reset scorecard into ``item.analysis``, into
the disk cache and onto the card — the reset would look like it did nothing.

This drives the REAL landing seam ``ai_analysis._on_analysis_ready`` with the
delivery token captured BEFORE ``clear_metrics_caches``. No controller is
required: the function is an owner-facing use case and the minimal fake below
implements exactly the controller primitives it calls (``_is_current_folder_gen``
/ ``_find_item`` / ``widget.refresh_card`` / ``_refresh_open_quick_look``).

Falsification story (red on ``int/backend-isolation``): the reset clears items
and disk caches but bumps no delivery token, so the stale ``epoch`` still
compares current and the scorecard lands — ``analysis`` set, status ``DONE``,
``save_analysis`` called once.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import AiAnalysisResult, AnalysisStatus, GalleryItem
from tabs.image_gallery.use_cases import ai_analysis
from tabs.image_gallery.use_cases.cache_reset import clear_metrics_caches


class _Owner:
    """Minimal AI-domain owner: the guards and sinks ``_on_analysis_ready`` uses."""

    def __init__(self) -> None:
        self._judgment_domain = "ai"
        self._domain_epoch = 3
        self._folder_gen = 7
        self.state = SimpleNamespace(
            items=[],
            series=[],
            mode=None,
            judgment_domain="ai",
            rank_domain="ai",
        )
        self.refreshed = []
        self.widget = SimpleNamespace(
            refresh_card=lambda item: self.refreshed.append(item),
            refresh_cards=lambda _items: None,
        )

    def _find_item(self, path):
        for item in self.state.items:
            if str(item.path) == str(path):
                return item
        return None

    def _is_current_folder_gen(self, gen) -> bool:
        return int(gen) == int(self._folder_gen)

    def _refresh_open_quick_look(self) -> None:
        pass


def test_reset_drops_pre_reset_ai_delivery(counters) -> None:
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0})
    item.analysis_status = AnalysisStatus.PENDING
    owner = _Owner()
    owner.state.items = [item]

    # The delivery token a worker would have snapshotted when it was scheduled.
    delivery_epoch = owner._domain_epoch
    clear_metrics_caches(owner)
    counters.clear()

    result = AiAnalysisResult(
        description="",
        tags=(),
        model="judge-model",
        analyzed_at_iso="t",
        axes={"sharpness": 70},
    )
    ai_analysis._on_analysis_ready(
        owner,
        item.path,
        item.mtime_ns,
        result,
        gen=owner._folder_gen,
        identity={},
        epoch=delivery_epoch,
    )

    assert item.analysis is None, (
        "a scorecard produced before the reset landed on the item after it"
    )
    assert item.analysis_status == AnalysisStatus.NOT_ANALYZED, (
        f"status after a stale delivery must stay NOT_ANALYZED, got "
        f"{item.analysis_status!r}"
    )
    assert counters["save_analysis"] == 0, (
        "a pre-reset scorecard was written to the disk cache after the reset"
    )
