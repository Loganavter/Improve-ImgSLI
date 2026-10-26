"""INVARIANT: the pairwise (A/B judge) refinement never runs under Algorithms.

Pairwise comparison is a paid VLM pass. The Algorithms backend owns a
deterministic order (``rank_fusion``); spending judge calls to refine it is the
"AI work under Algorithms" leak, and applying such an order would let a model
verdict overwrite a measured one.

Falsification story (red on ``int/backend-isolation``): the terminal-rank tail
of ``analysis_batch.dispatch_terminal_rank`` calls
``ai_analysis.dispatch_pairwise_refinement`` on every settled Algorithms run,
and that path schedules a comparison worker as soon as the profile axes form a
near-tie (measured here: one pool start). The observable contract asserted is
the spend boundary — no worker scheduled, no transport call, no rank applied —
not any internal branch.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem, Series
from tabs.image_gallery.use_cases import ai_analysis


class _Owner:
    """Algorithms owner with a settled metrics pass and a near-tie series."""

    def __init__(self) -> None:
        self._judgment_domain = "algorithms"
        self._domain_epoch = 2
        self._folder_gen = 7
        self._metrics_settled_gen = 7
        self._AI_VISIBLE_CAP = 4
        self.pool_starts = 0
        self.applied: list = []
        settings = SimpleNamespace(
            enabled=True,
            api_key="k",
            model="judge-model",
            base_url="http://stub/v1",
            pairwise_enabled=True,
            pairwise_top_n=3,
            pairwise_near_tie_threshold=8.0,
            sample_count=1,
            sampling_temperature=0.0,
            sampling_seed=0,
            vlm_max_edge_px=1024,
        )
        self._ai_settings_store = SimpleNamespace(load=lambda: settings)
        self.state = SimpleNamespace(
            items=[],
            series=[],
            mode=None,
            metric_profile=None,
            judgment_domain="algorithms",
            rank_domain="algorithms",
        )
        self.widget = SimpleNamespace(
            refresh_card=lambda _item: None, refresh_cards=lambda _items: None
        )

    def _pool_start(self, worker, priority=None) -> None:
        self.pool_starts += 1

    def _is_current_folder_gen(self, gen) -> bool:
        return int(gen) == int(self._folder_gen)

    def _apply_fusion_ranks(self, *_args, **_kwargs) -> None:
        self.applied.append((_args, _kwargs))


def _near_tie_item(name: str, sharpness: float) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update({"sharpness": sharpness})
    return item


def test_pairwise_never_runs_in_algorithms(counters) -> None:
    # Two measured variants inside the near-tie threshold: exactly the input
    # the pass exists to refine, so a skipped/passive owner is not why we are
    # green.
    a = _near_tie_item("a.png", 200.0)
    b = _near_tie_item("b.png", 204.0)
    owner = _Owner()
    owner.state.items = [a, b]
    owner.state.series = [Series(id="series_1", members=[a, b])]

    scheduled = ai_analysis.dispatch_pairwise_refinement(owner)

    assert owner.pool_starts == 0, (
        "the Algorithms backend scheduled a pairwise VLM pass "
        f"(pool_starts={owner.pool_starts})"
    )
    assert scheduled is False
    assert counters["call_sync"] == 0
    assert owner.applied == [], "a pairwise order was applied under Algorithms"
