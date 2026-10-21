"""P1 (plan-gallery-ai-judgement) — completeness + one retry, and no alias tail.

Falsification story (each test names the live defect it kills):

- **a** — the last VLM score arrives while a rank is in flight: the refused
  trigger must be remembered by the stage gate and re-run EXACTLY ONCE after
  the batch finishes, and the order applied last must cover every member.
  Live 2026-10-21 19:12:22,870: score → ``gate skip`` 22,880 → ``rank applied
  items=6`` 27,430 with ``img_6`` unscored (J1). Pre-change the trigger was
  returned on and never retried.
- **a2** — the live shape of the same run: a 6-member series with 5 scored is
  NOT rankable. Pre-change the dispatcher only required 2 scored members and
  launched a 5/6 rank.
- **b** — a reply naming 2 of 6 aliases: the tail is the measured fusion
  (``_tail_order``), never alias/``str(path)`` order, and the trace says
  ``tail=deterministic`` (J2). Pre-change ``["img_5","img_4"]`` was completed
  alphabetically and applied as a full 1..N.
- **c** — the retry is bounded: a second identical trigger after the re-rank is
  a no-op (no loop), and no pending fingerprint is left behind.

Network-free: the transport is a stub that ranks the measured vector it is
given. The REAL vector builder, decision parser, tail order and apply path run
(the only substitution is the HTTP call and the worker pool).
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, Mode, Series
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.jev_client import (
    rank_series_jev_detailed,
)
from tabs.image_gallery.use_cases import pipeline_stages as ps


def _ai_item(name: str, **axes) -> GalleryItem:
    """An item carrying the VLM scorecard — the AI domain's scoring read.

    ``ssim`` is mirrored onto ``sharpness`` (same quality, same spread): P7-B
    refuses a vector with fewer than two axes; the refusal has its own test, so
    these completeness fixtures stay about completeness.
    """
    if "sharpness" not in axes and "ssim" in axes:
        axes["sharpness"] = axes["ssim"]
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(axes)
    )
    return it


def _unscored_item(name: str) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)


def _series(*items) -> Series:
    return Series(id="series_1", members=list(items))


def _chat(decision: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(decision)}}]}


def _reply_by_measured_score(payload: dict) -> dict:
    """Stub transport: order the aliases it was shown by their mean score.

    Deterministic stand-in for the model; the payload it receives is the REAL
    measured vector, so this reply is a full ranking of whatever the worker was
    shown (and therefore reveals a vector that misses a member's scores).
    """
    body = json.loads(payload["messages"][-1]["content"][0]["text"])

    def _mean(entry) -> float:
        scores = list((entry.get("scores") or {}).values())
        return (sum(scores) / len(scores)) if scores else -1.0

    ordered = sorted(body["items"], key=lambda e: (-_mean(e), e["alias"]))
    return _chat({"ranking": [e["alias"] for e in ordered]})


def _frozen(members) -> list[GalleryItem]:
    """Snapshot the members as the worker would at job start.

    The live race is exactly this: the worker reads the items when it starts,
    a late score changes them while it runs. Cloning the analysis keeps the
    in-flight batch's vector stable under a later mutation of the live items.
    """
    out: list[GalleryItem] = []
    for m in members:
        try:
            clone = copy.copy(m)
            clone.analysis = copy.deepcopy(getattr(m, "analysis", None))
            out.append(clone)
        except Exception:
            out.append(m)
    return out


class _RankCtrl:
    """Minimal controller surface for the real dispatcher/gate/apply path."""

    def __init__(self, groups, items, *, cache_dir) -> None:
        self.state = SimpleNamespace(
            series=list(groups),
            items=list(items),
            mode=Mode.FIDELITY,
            rank_domain="algorithms",
        )
        self._judgment_domain = "ai"
        self._folder_gen = 0
        self._stage_gate = ps.StageGate()
        self._AI_VISIBLE_CAP = 12
        self.widget = SimpleNamespace(
            visible_paths=lambda: [],
            refresh_card=lambda it: None,
            refresh_cards=lambda its: None,
            set_ranks_visible=lambda visible: None,
            set_rank_provenance=lambda source=None, domain=None: None,
        )
        self.launches: list[list[str]] = []
        self.vectors: list[dict] = []
        self.applied: list[dict[str, int]] = []
        self.degraded: list[str] = []
        self.client_calls = 0
        self.hold_next = False
        self._held = None
        self._cache = jev_cache.JevRankCache(cache_dir)
        self._client = self._reply

    # -- transport ---------------------------------------------------------
    def _reply(self, payload: dict) -> dict:
        self.client_calls += 1
        return _reply_by_measured_score(payload)

    # -- controller seams bound to this fake -------------------------------
    def _find_item(self, path):
        return GalleryController._find_item(self, path)

    def _run_jev_ranks(self):
        return GalleryController._run_jev_ranks(self)

    def _run_jev_rank_for_series(self, members, *, on_complete=None):
        snapshot = _frozen(list(members or ()))
        self.launches.append([str(getattr(m, "path", "")) for m in snapshot])
        self.vectors.append(_vector_of(snapshot))

        def _finish() -> None:
            outcome = rank_series_jev_detailed(
                snapshot,
                mode="fidelity",
                client=self._client,
                cache=self._cache,
                domain="ai",
            )
            if outcome.ranks:
                GalleryController._apply_jev_outcome(self, snapshot, outcome)
                self.applied.append(dict(outcome.ranks))
            else:
                self.degraded.append(str(outcome.reason))
            if callable(on_complete):
                on_complete(GalleryController._jev_outcome_ok(outcome))

        if self.hold_next:
            self.hold_next = False
            self._held = _finish
            return
        _finish()

    # -- test control ------------------------------------------------------
    def release(self) -> None:
        """Deliver the held batch's completion (the in-flight rank finishes)."""
        finish, self._held = self._held, None
        assert finish is not None, "no launch was held — nothing in flight"
        finish()


def _vector_of(members) -> dict:
    from tabs.image_gallery.services.jev_client import build_measured_vector

    return build_measured_vector(members, mode="fidelity", domain="ai")


def _six_items(scores) -> list[GalleryItem]:
    return [_ai_item(f"img_{i}.png", ssim=s) for i, s in enumerate(scores, start=1)]


# ---------------------------------------------------------------------------
# gate contract (the retry channel lives INSIDE the gate)
# ---------------------------------------------------------------------------


def test_gate_hands_back_the_fingerprint_it_refused_in_flight() -> None:
    gate = ps.StageGate()
    assert gate.begin("jev_rank", 0, "A") is True
    assert gate.begin("jev_rank", 0, "B") is False  # newer vector, refused
    assert gate.finished("jev_rank", 0) == "B", "the refused trigger must not be lost"


def test_gate_returns_none_when_the_refused_fingerprint_is_the_one_that_ran() -> None:
    """A repeated identical trigger must not manufacture a retry (no loop)."""
    gate = ps.StageGate()
    assert gate.begin("jev_rank", 0, "A") is True
    assert gate.begin("jev_rank", 0, "A") is False
    assert gate.finished("jev_rank", 0) is None


def test_gate_finished_return_is_ignorable_and_invalidate_drops_pending() -> None:
    gate = ps.StageGate()
    gate.begin("metrics", 1, "A")
    gate.begin("metrics", 1, "B")
    gate.invalidate(1)
    assert gate.finished("metrics", 1) is None
    assert gate.begin("metrics", 1, "A") is True


# ---------------------------------------------------------------------------
# rank_completeness — the ONE completeness decision
# ---------------------------------------------------------------------------


def test_rank_completeness_names_the_loss_and_clears_when_complete() -> None:
    members = _six_items([90, 80, 70, 60, 50, 40])
    complete = _vector_of(members)
    assert ps.rank_completeness(members, complete) == (6, 6, "")

    partial = _vector_of(members[:5] + [_unscored_item("img_6.png")])
    scored, total, reason = ps.rank_completeness(members, partial)
    assert (scored, total) == (5, 6)
    assert reason == "5 of 6 members carry a measured score"


def test_rank_completeness_flags_a_vector_missing_a_member_entry() -> None:
    members = _six_items([90, 80, 70])
    short = _vector_of(members[:2])
    scored, total, reason = ps.rank_completeness(members, short)
    assert (scored, total) == (2, 3)
    assert reason == "2 of 3 members are in the vector"


# ---------------------------------------------------------------------------
# (a) a late score during an in-flight rank → exactly one re-rank
# ---------------------------------------------------------------------------


def test_late_score_during_in_flight_rank_triggers_exactly_one_rerank(
    tmp_path, caplog, monkeypatch
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _six_items([90, 80, 70, 60, 50, 40])
    ctrl = _RankCtrl([_series(*items)], items, cache_dir=tmp_path)
    paths = [str(it.path) for it in items]

    ctrl.hold_next = True
    with caplog.at_level(logging.INFO, logger="ImproveImgSLI"):
        ctrl._run_jev_ranks()  # batch A: complete vector, in flight
        assert ctrl.launches == [paths]
        assert ps.rank_completeness(items, ctrl.vectors[0]) == (6, 6, "")

        # The last VLM score lands while batch A is still ranking (live 19:12:22).
        items[-1].analysis = AiAnalysisResult(
            description="", tags=(), model="m", analyzed_at_iso="t", axes={"ssim": 99}
        )
        ctrl._run_jev_ranks()  # refused: a run for this scope is in flight
        assert len(ctrl.launches) == 1, "single-flight still holds — no second batch yet"

        ctrl.release()  # batch A reports; the gate hands back the refused key

    assert len(ctrl.launches) == 2, "the refused trigger must be re-run exactly once"
    assert ctrl.launches[-1] == paths, "the retry ranks the WHOLE series"
    assert "re-run after in-flight batch" in caplog.text

    final = ctrl.applied[-1]
    assert set(final) == set(paths), "the order applied last covers every member"
    assert sorted(final.values()) == [1, 2, 3, 4, 5, 6]
    assert final[paths[-1]] == 1, "the late score decides the winner (it is the top score)"
    assert ctrl.vectors[-1]["items"][-1]["scores"] == {"ssim": 99}


# ---------------------------------------------------------------------------
# (a2) the live shape: 5 of 6 scored is not a rankable series
# ---------------------------------------------------------------------------


def test_partial_series_is_not_ranked_until_every_member_is_scored(
    tmp_path, caplog, monkeypatch
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _six_items([90, 80, 70, 60, 50]) + [_unscored_item("img_6.png")]
    ctrl = _RankCtrl([_series(*items)], items, cache_dir=tmp_path)
    paths = [str(it.path) for it in items]

    with caplog.at_level(logging.INFO, logger="ImproveImgSLI"):
        ctrl._run_jev_ranks()

    assert ctrl.launches == [], "an order over 5 of 6 members must not be dispatched"
    assert "jev rank partial: 5/6 scored" in caplog.text
    assert "5 of 6 members carry a measured score" in caplog.text

    items[-1].analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"ssim": 40}
    )
    with caplog.at_level(logging.INFO, logger="ImproveImgSLI"):
        ctrl._run_jev_ranks()

    assert len(ctrl.launches) == 1
    assert ctrl.launches[0] == paths
    assert sorted(ctrl.applied[-1].values()) == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# (b) a short model reply is completed by the measured fusion, not by alias order
# ---------------------------------------------------------------------------


def test_two_alias_reply_yields_a_score_based_tail_and_traces_it(
    tmp_path, caplog, monkeypatch
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    # Path order a..f, score order b > d > f > e > c > a (aliases img_1..img_6):
    # an alias-order tail and a score-order tail cannot coincide here.
    items = _six_items([40, 90, 50, 80, 60, 70])
    paths = [str(it.path) for it in items]

    def _client(payload):
        return _chat({"ranking": ["img_2", "img_4"]})  # the live 2-of-6 reply

    outcome = rank_series_jev_detailed(
        items,
        mode="fidelity",
        client=_client,
        cache=jev_cache.JevRankCache(tmp_path),
        domain="ai",
    )

    assert outcome.decided, outcome.reason
    assert outcome.tail == "deterministic"
    assert outcome.ranks == {
        paths[1]: 1,  # img_2, 90
        paths[3]: 2,  # img_4, 80
        paths[5]: 3,  # img_6, 70  <- score order
        paths[4]: 4,  # img_5, 60
        paths[2]: 5,  # img_3, 50
        paths[0]: 6,  # img_1, 40  <- alias order would have put img_1 third
    }

    ctrl = _RankCtrl([_series(*items)], items, cache_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="ImproveImgSLI"):
        GalleryController._apply_jev_outcome(ctrl, items, outcome)
    assert "jev rank applied: items=6 source=jev tail=deterministic" in caplog.text


def test_full_model_reply_is_traced_as_the_model_tail(tmp_path) -> None:
    items = _six_items([40, 90, 50, 80, 60, 70])

    def _client(payload):
        return _chat({"ranking": [f"img_{i}" for i in (2, 4, 6, 5, 3, 1)]})

    outcome = rank_series_jev_detailed(
        items,
        mode="fidelity",
        client=_client,
        cache=jev_cache.JevRankCache(tmp_path),
        domain="ai",
    )
    assert outcome.decided, outcome.reason
    assert outcome.tail == "model", "a reply naming every alias needs no tail"


# ---------------------------------------------------------------------------
# (c) the retry is bounded — a second identical trigger is a no-op
# ---------------------------------------------------------------------------


def test_second_identical_trigger_after_the_retry_is_a_noop(tmp_path) -> None:
    items = _six_items([90, 80, 70, 60, 50, 40])
    ctrl = _RankCtrl([_series(*items)], items, cache_dir=tmp_path)

    ctrl.hold_next = True
    ctrl._run_jev_ranks()  # batch A in flight
    items[-1].analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"ssim": 99}
    )
    ctrl._run_jev_ranks()  # refused, remembered
    ctrl.release()  # batch A finishes → one retry (batch B)
    assert len(ctrl.launches) == 2

    ctrl._run_jev_ranks()  # unchanged state: the completed fingerprint blocks it
    ctrl._run_jev_ranks()
    assert len(ctrl.launches) == 2, "a repeated trigger must not spawn a third batch"
    assert ctrl._stage_gate._pending == {}, "no refused fingerprint is left behind"
    assert ctrl._stage_gate._inflight == {}, "the gate is released"


def test_unchanged_series_ranks_once_across_repeated_settles(tmp_path) -> None:
    """The pre-existing single-flight guarantee still holds for one vector."""
    items = _six_items([90, 80, 70, 60, 50, 40])
    ctrl = _RankCtrl([_series(*items)], items, cache_dir=tmp_path)
    ctrl._run_jev_ranks()
    ctrl._run_jev_ranks()
    ctrl._run_jev_ranks()
    assert len(ctrl.launches) == 1
