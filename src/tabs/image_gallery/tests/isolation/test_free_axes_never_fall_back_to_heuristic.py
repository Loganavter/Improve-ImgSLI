"""INVARIANT (owner rule 2026-10-27): a refused judge answer is NEVER the local
heuristic axis set, and a KEPT answer is the judge's own.

The owner's log that broke this invariant: the AI backend was selected, the
model's answer named the axes, and the gallery ranked the folder on the camera
registry (``source=heuristic``) — "снова все метрики из camera режима". Two
different mechanisms fed that log and this file pins the seam they share:

- a **refused** answer (no usable axis, a thin count, a transport error) must
  leave the AI domain with NO axis set — the card says why, and the algorithms
  slot keeps its own heuristic set for the Algorithms backend only;
- an answer whose axes were all KEPT must reach the AI slot AS THE JUDGE'S SET,
  even when the axes are bare names with no definitions. Red before: the parser
  refused every free bare name, so this complete answer became a "thin" one, was
  retried, failed, and the AI domain ended up with no axes at all (an error)
  instead of the set the owner paid for.

Falsification story, per test:

- ``test_a_refused_answer...`` — red if any AI-domain read answers the camera
  mapping after a refusal: ``active_profile(domain="ai")`` must be the EMPTY
  judge profile (``NoProfileYet`` downstream), while the algorithms slot is
  untouched. The non-vacuity half (the heuristic offer exists and is reachable
  for the LOCAL backend) keeps the test from passing by having no profile at all.
- ``test_a_kept_free_answer...`` — red on the base commit for a different reason:
  3 bare free names were refused, the reply was retried and then dropped, so
  ``state.ai_profile`` stayed ``None``. After the owner rule the same reply is
  the judge's own axis set, applied through the REAL apply-tail.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.backends import NoProfileYet
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AnalysisStatus, GalleryItem
from tabs.image_gallery.services.metric_profile import (
    MetricProfile,
    PROFILE_REJECT_FAILED,
    profile_for_mode,
)
from tabs.image_gallery.services.profile_judged import scorecard_axis_ids
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.use_cases import profile_ai, profile_select

#: The camera registry set the leak substituted. Named once, asserted as absent.
HEURISTIC_AXES = profile_for_mode("camera").axis_ids


class _Owner:
    """Qt-free double binding the REAL ``_apply_profile_outcome`` apply-tail."""

    def __init__(self, items) -> None:
        self.state = SimpleNamespace(
            items=list(items),
            mode="camera",
            source_path=None,
            algorithms_profile=profile_for_mode("camera"),
            ai_profile=None,
            profile_reject_reason="",
        )
        self._judgment_domain = "ai"
        self._folder_gen = 0
        self._profile_consumed_gen = None
        self._profile_failed_gen = None
        self.refreshed: list = []
        self.widget = SimpleNamespace(
            refresh_cards=self.refreshed.extend,
            refresh_card=self.refreshed.append,
        )

    def _is_current_folder_gen(self, gen) -> bool:
        return GalleryController._is_current_folder_gen(self, gen)

    def _apply_profile_outcome(self, profile, gen) -> None:
        GalleryController._apply_profile_outcome(self, profile, gen)

    def _mark_ai_profile_error(self, reason: str) -> None:
        GalleryController._mark_ai_profile_error(self, reason)

    def _trace_axis_provenance(self, profile=None) -> None:
        GalleryController._trace_axis_provenance(self, profile)

    def _tr(self, key: str, default: str) -> str:
        return default


@pytest.fixture
def _stub_image_encoding(monkeypatch):
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _items() -> list:
    """Two members whose measured spread is the evidence a call is built from."""
    return [
        SimpleNamespace(
            path=Path("/gallery/a.png"), mtime_ns=1, metrics={"sharpness": 0.0}
        ),
        SimpleNamespace(
            path=Path("/gallery/b.png"), mtime_ns=1, metrics={"sharpness": 400.0}
        ),
    ]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        api_key="k",
        base_url="http://x",
        model="m",
        reasoning_effort="auto",
    )


def _choose(items, rows, *, calls, cache):
    """The REAL selector with an injected transport that always answers *rows*."""

    def _client(base_url, api_key, payload):
        calls.append(payload)
        return {"choices": [{"message": {"content": json.dumps({"axes": rows})}}]}

    return profile_ai.choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )


def _gallery_items(items) -> list:
    return [GalleryItem(path=item.path, mtime_ns=item.mtime_ns) for item in items]


def test_a_refused_answer_leaves_the_ai_domain_without_any_axis_set(
    tmp_path, _stub_image_encoding
):
    items = _items()
    calls: list = []
    # ONE axis: refused by the count rule, retried once, then dropped.
    profile = _choose(items, ["glow_bloom"], calls=calls, cache=ProfileCache(tmp_path))
    assert profile is None, "a one-axis answer is still not a profile"
    assert len(calls) == 2, "the refusal costs exactly one retry"

    owner = _Owner(_gallery_items(items))
    owner._apply_profile_outcome(profile, 0)

    assert owner.state.ai_profile is None, (
        "a refused answer must leave the AI slot EMPTY — storing anything here is "
        "the local axis set the owner complained about"
    )
    assert owner.state.profile_reject_reason == PROFILE_REJECT_FAILED
    assert all(
        item.analysis_status == AnalysisStatus.ERROR for item in owner.state.items
    ), "the cards say why instead of quietly showing camera numbers"

    ai = profile_select.active_profile(owner.state, domain="ai")
    assert bool(ai) is False, f"the AI domain got an axis set: {ai}"
    assert ai.axis_entries == () and ai.axis_ids == ()
    assert ai.source != "heuristic", "the AI slot must never be tagged heuristic"
    with pytest.raises(NoProfileYet):
        measured_axes_for("camera", profile=ai)
    with pytest.raises(NoProfileYet):
        scorecard_axis_ids("camera", profile=ai)

    # Non-vacuity: the LOCAL backend still owns its heuristic set — the refusal
    # is about the AI slot, not about the app losing its detector axes.
    local = profile_select.active_profile(owner.state, domain="algorithms")
    assert local.source == "heuristic"
    assert local.axis_ids == HEURISTIC_AXES

    # The series offer the fallback would have pinned is a real, reachable
    # profile — it is simply not the AI backend's answer.
    offer = profile_select.derive_profile(items, mode="camera")
    assert bool(offer) and offer != owner.state.ai_profile


def test_a_kept_free_answer_is_the_judges_own_set_not_the_heuristic(
    tmp_path, _stub_image_encoding
):
    """Red before: these three bare names were refused, so the AI slot stayed empty."""
    items = _items()
    calls: list = []
    rows = ["glow_bloom", "halation_bleed", "veil_haze"]

    profile = _choose(items, rows, calls=calls, cache=ProfileCache(tmp_path))
    assert len(calls) == 1, "an answer whose axes are all kept is not retried"
    assert profile is not None and profile.source == "vlm"

    owner = _Owner(_gallery_items(items))
    owner._apply_profile_outcome(profile, 0)

    assert owner.state.ai_profile is profile, (
        "the judge's own axis set must land in the AI slot "
        f"(rejected as {owner.state.profile_reject_reason!r})"
    )
    applied = profile_select.active_profile(owner.state, domain="ai")
    assert applied == profile
    assert [entry.name for entry in applied.axis_entries] == rows
    assert applied.source != "heuristic"
    assert scorecard_axis_ids("camera", profile=applied) == tuple(rows), (
        "the asked set is the judge's, never the camera mapping"
    )
    assert not set(HEURISTIC_AXES) & set(scorecard_axis_ids("camera", profile=applied))
    assert owner.state.algorithms_profile == profile_for_mode("camera"), (
        "the AI answer must not overwrite the Algorithms backend's own slot"
    )
    assert owner.state.profile_reject_reason == ""
