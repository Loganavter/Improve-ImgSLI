"""INVARIANT: a scorecard with ZERO axes is never requested.

Owner 2026-10-26: the judge names the axes BEFORE any per-card analysis
(axes-first). If the AI slot is still empty, a request would ask for zero axes,
cost a call and return nothing measurable. The analyze entry must refuse by name
instead of spending — and must not mark the cards as errors (the selector may
still be in flight).

Red before the guard: ``_analyze_ai`` built the identity and called
``_begin_analysis`` per card with an empty profile, so the transport was reached
with a 0-axis prompt.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import AnalysisStatus, GalleryItem
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.use_cases import ai_analyze
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_AI,
    REFUSAL_NO_PROFILE,
    ActionContext,
)


class _Owner:
    def __init__(self, item: GalleryItem) -> None:
        self.state = SimpleNamespace(items=[item], mode="camera")
        self.widget = SimpleNamespace(refresh_card=lambda _item: None)
        self.begun: list = []
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True,
                api_key="k",
                base_url="http://x",
                model="m",
                reasoning_effort="auto",
            )
        )

    def _begin_analysis(self, ctx, item) -> None:
        self.begun.append((ctx, item))


def _ctx(item: GalleryItem, profile) -> ActionContext:
    return ActionContext(
        targets=(item.path,),
        backend=BACKEND_AI,
        profile=profile,
        mode="camera",
    )


def _empty_profile() -> MetricProfile:
    return MetricProfile(mode="camera", source="vlm")


def _judge_profile() -> MetricProfile:
    return MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(
            SimpleNamespace(
                name="halation",
                definition="glow at bright edges",
                scale="0-100",
                direction="lower-is-better",
            ),
        ),
    )


def test_an_empty_ai_profile_refuses_before_any_request(tmp_path, counters) -> None:
    item = GalleryItem(path=tmp_path / "a.png", mtime_ns=1)
    owner = _Owner(item)

    refusal = ai_analyze.analyze(owner, _ctx(item, _empty_profile()))

    assert refusal is not None and refusal.reason == REFUSAL_NO_PROFILE, (
        f"a 0-axis analyze must refuse by name, got {refusal!r}"
    )
    assert counters["call_sync"] == 0, "a 0-axis analyze reached the transport"
    assert counters["save_analysis"] == 0
    assert owner.begun == [], "the analyze pipeline started with no axes"
    assert item.analysis_status == AnalysisStatus.NOT_ANALYZED, (
        "an unready profile is not an ERROR on the card — the selector may still "
        "be in flight"
    )


def test_a_judge_profile_still_starts_the_analysis(tmp_path, counters) -> None:
    """Non-vacuity: the guard is about EMPTY, not about AI analysis."""
    item = GalleryItem(path=tmp_path / "a.png", mtime_ns=1)
    owner = _Owner(item)

    refusal = ai_analyze.analyze(owner, _ctx(item, _judge_profile()))

    assert refusal is None
    assert len(owner.begun) == 1, "a profile with axes must reach _begin_analysis"
