"""GUARD: the Algorithms analyze action issues no AI request.

``use_cases.ai_analyze.analyze`` dispatches on the ONE ``ActionContext``
backend. With ``backend="algorithms"`` it must re-enter the deterministic local
pass and never reach the transport or the AI scorecard cache — the AI work is
only legal under the AI backend.

This already holds on ``int/backend-isolation`` (the algorithms branch calls
``owner._start_proxy_analysis`` and returns); it is kept as the action-level
guard next to the dispatch-level reds, so a later "unify the analyze entry"
change cannot widen the Algorithms branch.
"""

from __future__ import annotations

import pytest

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_ALGORITHMS,
    ActionContext,
)
from tabs.image_gallery.use_cases.ai_analyze import analyze


class _Owner:
    def __init__(self) -> None:
        self.state = SimpleNamespace(
            items=[], series=[], mode=None, source_path=Path("/gallery")
        )
        self.proxy_starts: list = []
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True,
                api_key="k",
                model="judge-model",
                base_url="http://stub/v1",
            )
        )
        self.widget = SimpleNamespace(
            refresh_card=lambda _item: None, refresh_cards=lambda _items: None
        )

    def _find_item(self, path):
        for item in self.state.items:
            if str(item.path) == str(path):
                return item
        return None

    def _start_proxy_analysis(self, items, source, mode) -> None:
        self.proxy_starts.append((list(items), source, mode))

    def _tr(self, _key, default):
        return default


# Order-dependent under per-test distribution (measured 2026-10-28): green serially, in
# its own file, and under the tier default (--dist loadfile, 4/4 runs), but it fails in
# SOME orders when xdist schedules one TEST at a time and each worker shuffles with its
# own seed — a different test failed in two consecutive runs of the same pinned seed, so
# there is no single polluter to blame. Documented in docs/dev/TESTING.md § Quarantine.
@pytest.mark.flaky
def test_algorithms_action_issues_no_post(counters) -> None:
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0})
    owner = _Owner()
    owner.state.items = [item]
    ctx = ActionContext(
        targets=(item.path,),
        backend=BACKEND_ALGORITHMS,
        mode="batch_synthetic",
    )

    refusal = analyze(owner, ctx)

    assert refusal is None
    assert len(owner.proxy_starts) == 1, (
        "the Algorithms action must re-run the deterministic measured pass"
    )
    assert counters["call_sync"] == 0, (
        "the Algorithms analyze action issued an AI transport call"
    )
    assert counters["save_analysis"] == 0
    assert counters["save_local_metrics"] == 0
