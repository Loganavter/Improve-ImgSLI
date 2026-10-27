"""Free axes the JUDGE named must RANK — the AI domain's terminal Jev pass.

Live defect (owner run, 2026-10-27 03:53: the folder's profile resolved to
``axes=- source=vlm mode=camera judged=line_crispness, denoise_smoothness,
color_saturation, gradient_banding, detail_preservation, halo_artifacts``) — six
axes, ALL of them judge-named, zero registry axes. The metric rows appeared in
Quick Look and the rank never did.

Falsification story (each test names the defect it kills, and each of the
``red-before`` ones was run against ``63eae8d`` — the failures are quoted in the
module's ``RED-BEFORE`` notes):

- **a** — a profile whose axes are ALL judge-named builds a COMPLETE vector and
  the terminal rank dispatches. The vector is read from ``item.analysis`` by the
  free axis names (the profile's own list), never from the local mode mapping.
- **b** — the settle's deferred tail is RESUMED when the profile resolves, and
  the rank follows the resolved axis set.
- **c** — the resume is per-tail ISOLATED: a raising analysis tail cannot strand
  the rank pass behind it (the marker is already cleared by then, so nothing
  would ever re-trigger it). ``RED-BEFORE``: the three tails shared one ``try``,
  so the rank was silently lost with only a ``logger.debug`` line.
- **d** — the marker is ARMED before the worker is launched: a reply delivered
  during ``_pool_start`` (a synchronous pool, the documented test double)
  released and resumed while the marker was still ``None``, and the marker was
  written afterwards and never cleared — every later settle of that generation
  then deferred forever. ``RED-BEFORE``: no rank, marker stuck on the generation.
- **e** — the resume is idempotent: a second release of the same generation does
  not re-run the tails (one rank batch per generation).
- **f** — the AI domain never builds the Jev vector from the LOCAL mode axis set:
  without a profile the builder refuses (``NoProfileYet``) instead of handing
  the ranker detector axes inside the AI domain. ``RED-BEFORE``:
  ``build_measured_vector(..., domain="ai", profile=None)`` returned
  ``scores={'sharpness': 60}`` — a camera axis, in the AI domain.
- **g** — a matrix scored only on axes the MODEL proposed is COMPLETE: the
  proposed-axes list is a dimension list the payload carries per member
  (``jev_axes.scored_axis_names`` counts it), so completeness must count it too.
  ``RED-BEFORE``: ``rank_completeness`` answered ``(0, 3, '0 of 3 members carry a
  measured score')`` for three members that each carried both numbers.
- **h** — no AI profile is a NAMED refusal, not a ``partial`` masquerade that
  reads like "the judge has not scored yet". ``RED-BEFORE``: the pass logged
  ``jev rank partial: 0/6 scored``.

The SECOND live symptom, same profile-life seam (owner run ~04:00):

- **i** — a MANUAL metrics reset drops the results, not the axis set: the
  judge's answer survives in the AI slot, so the next Analyze builds a
  scorecard for those names instead of refusing "no_profile". ``RED-BEFORE``:
  ``04:00:29 reset`` → ``04:00:30 analyze refused: no_profile`` → ``04:00:37``
  the same, twice, on a folder whose judge had named six axes seconds earlier.

Network-free: the transport is a stub that ranks the measured vector it is
given; the REAL vector builder, parser, gate, resume and apply path run.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery import controller as controller_mod
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import (
    AiAxisProposal,
    AiAnalysisResult,
    GalleryItem,
    Mode,
    Series,
)
from tabs.image_gallery.services import ai_cache, jev_cache, profile_cache, vlm_cache
from tabs.image_gallery.services.jev_client import (
    build_measured_vector,
    rank_series_jev_detailed,
)
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.use_cases import analysis_batch
from tabs.image_gallery.use_cases import pipeline_stages as ps
from tabs.image_gallery.use_cases import triage_run
from core.log_names import APP_LOGGER_NAME

#: The six axes the owner's judge named (the live log line). Not one of them is
#: a registry id — that is the whole point.
FREE = (
    "line_crispness",
    "denoise_smoothness",
    "color_saturation",
    "gradient_banding",
    "detail_preservation",
    "halo_artifacts",
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _free_profile() -> MetricProfile:
    """The judge's answer: six named axes, no registry half (``axes=-``)."""
    return MetricProfile(
        axis_ids=(),
        mode="camera",
        source="vlm",
        axis_entries=tuple(
            AiAxisProposal(
                name=name,
                definition=f"{name} as the judge reads it, 0 = worst, 100 = best",
                direction="higher-is-better",
            )
            for name in FREE
        ),
    )


def _scored_item(name: str, **scores) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(scores)
    )
    return it


def _free_items(count: int = 6) -> list[GalleryItem]:
    """``count`` cards, each carrying a reading for every judge-named axis."""
    return [
        _scored_item(
            f"img_{i}.png",
            **{name: 55 + i + k for k, name in enumerate(FREE)},
        )
        for i in range(count)
    ]


def _series(*items) -> Series:
    return Series(id="series_1", members=list(items))


def _chat(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


class _Sig:
    """Minimal Qt-signal double (connect/emit, no Qt)."""

    def __init__(self) -> None:
        self._cbs: list = []

    def connect(self, cb) -> None:
        self._cbs.append(cb)

    def emit(self, *args) -> None:
        for cb in list(self._cbs):
            cb(*args)


class _FakeWorker:
    """``GenericWorker`` double: captures the job, delivers signals on ``run``."""

    instances: list = []

    def __init__(self, fn, *args, **kwargs) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = SimpleNamespace(result=_Sig(), error=_Sig(), finished=_Sig())
        _FakeWorker.instances.append(self)

    def run(self) -> None:
        try:
            out = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 — mirrors GenericWorker
            self.signals.error.emit((type(exc), exc, "traceback"))
        else:
            if out is not None:
                self.signals.result.emit(out)
        finally:
            self.signals.finished.emit()


@pytest.fixture()
def fake_workers(monkeypatch):
    _FakeWorker.instances.clear()
    monkeypatch.setattr(controller_mod, "GenericWorker", _FakeWorker)
    return _FakeWorker


class _FreeRankCtrl:
    """Controller surface for the REAL settle → profile → rank chain on the AI domain.

    Every seam that decides anything is the REAL controller use case
    (``_settle_metrics_pass``, ``_run_profile_select_on_settle``,
    ``_apply_profile_outcome``, ``_resume_settle_after_profile``,
    ``_run_jev_ranks``, ``_apply_jev_outcome``); only the transport, the pool and
    the analysis WORK are doubles.
    """

    def __init__(self, items, groups, *, cache_dir, ai_profile=None, mode=Mode.CAMERA):
        self.state = SimpleNamespace(
            items=list(items),
            series=list(groups),
            mode=mode,
            ai_profile=ai_profile,
            algorithms_profile=None,
            rank_domain="ai",
        )
        self._judgment_domain = "ai"
        self._folder_gen = 0
        self._domain_epoch = 0
        self._stage_gate = ps.StageGate()
        self._AI_VISIBLE_CAP = 12
        self._metrics_settled_gen = -1
        self._profile_settle_pending_gen = None
        # analysis ledger (use_cases.analysis_batch reads plain ints)
        self._ai_batch_gen = 0
        self._ai_batch_pending = 0
        self._sched_pending = 0
        self.widget = SimpleNamespace(
            visible_paths=lambda: [],
            refresh_card=lambda it: None,
            refresh_cards=lambda its: None,
            set_ranks_visible=lambda visible: None,
            set_rank_provenance=lambda source=None, domain=None: None,
            set_triage_done=lambda: None,
        )
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True,
                api_key="k",
                model="m",
                base_url="http://h",
                reasoning_effort="auto",
            )
        )
        # -- observations ---------------------------------------------------
        self.profile_kicks = 0
        self.launched_workers: list = []
        self.analysis_tail_calls = 0
        self.analysis_tail_begins = 0
        self.launches: list = []
        self.vectors: list = []
        self.applied: list = []
        self._cache = jev_cache.JevRankCache(cache_dir)
        self._client = self._reply
        # -- harness knobs --------------------------------------------------
        self.run_worker_inline = False

    # -- transport ---------------------------------------------------------
    def _reply(self, payload: dict) -> dict:
        body = json.loads(payload["messages"][-1]["content"][0]["text"])

        def _mean(entry) -> float:
            values = list((entry.get("scores") or {}).values())
            return (sum(values) / len(values)) if values else -1.0

        ordered = sorted(body["items"], key=lambda e: (-_mean(e), e["alias"]))
        return _chat({"ranking": [e["alias"] for e in ordered]})

    # -- real controller primitives ---------------------------------------
    def _is_current_folder_gen(self, gen) -> bool:
        return GalleryController._is_current_folder_gen(self, gen)

    def _find_item(self, path):
        return GalleryController._find_item(self, path)

    def _refresh_ranks_visible(self) -> None:
        return GalleryController._refresh_ranks_visible(self)

    def _refresh_rank_provenance(self) -> None:
        return GalleryController._refresh_rank_provenance(self)

    def _apply_fusion_ranks(self, series, *, mode=None, pairwise_order=None) -> None:
        return GalleryController._apply_fusion_ranks(
            self, series, mode=mode, pairwise_order=pairwise_order
        )

    def _run_profile_select_on_settle(self) -> None:
        self.profile_kicks += 1
        return GalleryController._run_profile_select_on_settle(self)

    def _apply_profile_outcome(self, profile, gen) -> None:
        return GalleryController._apply_profile_outcome(self, profile, gen)

    def _resume_settle_after_profile(self, gen: int) -> None:
        return GalleryController._resume_settle_after_profile(self, gen)

    def _run_jev_ranks(self) -> None:
        return GalleryController._run_jev_ranks(self)

    def _launch_jev_batch(self, ready, scope) -> None:
        return GalleryController._launch_jev_batch(self, ready, scope)

    def _apply_jev_outcome(self, members, outcome) -> None:
        return GalleryController._apply_jev_outcome(self, members, outcome)

    # -- pool / worker -----------------------------------------------------
    def _pool_start(self, worker, priority) -> None:
        self.launched_workers.append(worker)
        if self.run_worker_inline:
            worker.run()

    # -- thin seams owned by the real widget / use cases --------------------
    def _mark_local_pass(self, items, phase) -> None:
        return None

    def refresh_metric_profile(self) -> None:
        return None

    def _hydrate_ai_cache(self, items) -> None:
        return None

    def _clear_series_priority(self) -> None:
        return None

    def _run_ai_for_visible(self, *, cache_only: bool = False) -> None:
        """The analysis tail: open (and here: close) one batch per cold card."""
        self.analysis_tail_calls += 1
        for it in list(self.state.items):
            if getattr(it, "analysis", None) is not None:
                continue
            self.analysis_tail_begins += 1
            analysis_batch.begin(self)
            analysis_batch.end(self)

    def _run_jev_rank_for_series(self, members, *, on_complete=None) -> None:
        snapshot = list(members or ())
        self.launches.append([str(getattr(m, "path", "")) for m in snapshot])
        self.vectors.append(
            build_measured_vector(
                snapshot,
                mode=self.state.mode,
                domain="ai",
                profile=self.state.ai_profile,
            )
        )
        outcome = rank_series_jev_detailed(
            snapshot,
            mode=self.state.mode,
            client=self._client,
            cache=self._cache,
            domain="ai",
            profile=self.state.ai_profile,
        )
        if outcome.ranks:
            GalleryController._apply_jev_outcome(self, snapshot, outcome)
            self.applied.append(dict(outcome.ranks))
        if callable(on_complete):
            on_complete(GalleryController._jev_outcome_ok(outcome))


def _selector_returning(profile):
    def _sel(items, mode=None, settings=None):
        return profile

    return _sel


def _selector_raising(exc):
    def _sel(items, mode=None, settings=None):
        raise exc

    return _sel


# ---------------------------------------------------------------------------
# (a) a profile with ZERO registry axes still ranks
# ---------------------------------------------------------------------------


def test_a_judge_only_profile_builds_a_complete_vector_and_ranks(tmp_path) -> None:
    items = _free_items()
    profile = _free_profile()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path, ai_profile=profile)

    ctrl._run_jev_ranks()

    assert len(ctrl.launches) == 1, (
        "a profile whose axes are ALL judge-named must still reach the ranker; "
        f"launches={ctrl.launches}"
    )
    scored, total, why = ps.rank_completeness(items, ctrl.vectors[0])
    assert (scored, total, why) == (6, 6, ""), (
        f"the vector must read the six judge-named axes from item.analysis; got "
        f"{scored}/{total} ({why}): {ctrl.vectors[0]['items'][0]}"
    )
    assert set(ctrl.vectors[0]["items"][0]["scores"]) == set(FREE)
    assert sorted(ctrl.applied[-1].values()) == [1, 2, 3, 4, 5, 6]
    assert {it.rank_source for it in items} == {"jev"}, (
        "the AI domain's order is Jev's: the rank provenance must say so"
    )


# ---------------------------------------------------------------------------
# (b) the settle's deferred tail resumes under the RESOLVED profile
# ---------------------------------------------------------------------------


def test_the_deferred_tail_ranks_after_the_profile_resolves(
    tmp_path, monkeypatch, fake_workers
) -> None:
    items = _free_items()
    profile = _free_profile()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path)
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(profile)
    )

    # The metrics pass settles BEFORE the judge answered: the tails must wait.
    triage_run._settle_metrics_pass(ctrl, items)
    assert ctrl.launches == [], "no rank may be dispatched before the axis set is final"
    assert ctrl._profile_settle_pending_gen == 0
    assert len(ctrl.launched_workers) == 1

    ctrl.launched_workers[0].run()  # the judge's answer lands

    assert ctrl.state.ai_profile is not None and ctrl.state.ai_profile.source == "vlm"
    assert len(ctrl.launches) == 1, (
        "the deferred tail must be resumed by the profile's release — the rank "
        "never ran on the resolved (judge-only) axis set"
    )
    scored, total, _why = ps.rank_completeness(items, ctrl.vectors[0])
    assert (scored, total) == (6, 6)
    assert {it.rank_source for it in items} == {"jev"}


def test_the_resume_is_idempotent_exactly_once_per_arming(
    tmp_path, monkeypatch, fake_workers
) -> None:
    """One arming (one settle that deferred) resumes the tails exactly once.

    The marker is consumed by the resume, so a duplicated release of the same
    deferral is a no-op — the "exactly once" half of the P5 contract.
    """
    items = _free_items()
    profile = _free_profile()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path)
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(profile)
    )
    triage_run._settle_metrics_pass(ctrl, items)
    ctrl.launched_workers[0].run()
    assert len(ctrl.launches) == 1

    # A second release of the SAME deferral (a duplicated selector signal).
    ctrl._resume_settle_after_profile(0)

    assert ctrl.analysis_tail_calls == 1, (
        "the deferred tails are resumed ONCE per arming, never per release"
    )
    assert len(ctrl.launches) == 1, "a second release must not spawn a second batch"


def test_a_selector_fault_still_resumes_the_tail(tmp_path, monkeypatch, fake_workers) -> None:
    """A fault released the gate — the tails must not be swallowed by it.

    The run continues under the profile already stored (the AI slot keeps the
    judge's answer, or stays empty with the named ``no AI profile`` line), but
    the settle still owes its analysis/rank pass. Red-before this was the same
    shared-``try`` hazard as (c); the assertion here guards the release path.
    """
    items = _free_items()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path)
    monkeypatch.setattr(
        controller_mod,
        "_profile_selector",
        lambda: _selector_raising(RuntimeError("selector exploded")),
    )

    triage_run._settle_metrics_pass(ctrl, items)
    assert ctrl._profile_settle_pending_gen == 0
    ctrl.launched_workers[0].run()  # error signal -> release(False) -> resume

    assert ctrl.analysis_tail_calls == 1, "the settle's tails still run after a fault"
    assert ctrl._profile_settle_pending_gen is None, "the marker is consumed"


# ---------------------------------------------------------------------------
# (c) one raising tail cannot strand the rank
# ---------------------------------------------------------------------------


def test_a_failing_fusion_tail_cannot_strand_the_rank(
    tmp_path, monkeypatch, fake_workers, caplog
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _free_items()
    profile = _free_profile()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path)

    def _boom(series, *, mode=None, pairwise_order=None) -> None:
        raise RuntimeError("fusion re-mark exploded")

    ctrl._apply_fusion_ranks = _boom  # type: ignore[method-assign]
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(profile)
    )

    triage_run._settle_metrics_pass(ctrl, items)
    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        ctrl.launched_workers[0].run()

    assert len(ctrl.launches) == 1, (
        "the rank tail shares the settle with the fusion re-mark and must survive "
        "its fault — the deferred marker is already cleared, so a stranded rank "
        "is never re-triggered"
    )
    assert "settle tail failed: fusion" in caplog.text, (
        "the fault must be NAMED per tail, not swallowed as one resume failure"
    )
    assert sorted(ctrl.applied[-1].values()) == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# (d) the marker is armed BEFORE the launch
# ---------------------------------------------------------------------------


def test_a_reply_that_lands_during_the_launch_still_resumes_the_tail(
    tmp_path, monkeypatch, fake_workers
) -> None:
    items = _free_items()
    profile = _free_profile()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path)
    ctrl.run_worker_inline = True  # a pool that answers before _pool_start returns
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(profile)
    )

    triage_run._settle_metrics_pass(ctrl, items)

    assert len(ctrl.launches) == 1, (
        "the reply was released before the deferral marker was written, so the "
        "resume found nothing pending and the rank was lost"
    )
    assert ctrl._profile_settle_pending_gen is None, (
        "the marker must not stay armed on a generation whose profile is final — "
        "every later settle would defer forever"
    )


# ---------------------------------------------------------------------------
# (f) a lost rank is NAMED in the plain log, with the profile's axis set
# ---------------------------------------------------------------------------


def test_a_partial_refusal_is_named_in_the_plain_log_with_the_profile_axes(
    tmp_path, caplog
) -> None:
    """The live 2026-10-27 loss left NOTHING in log.txt after the profile line.

    Every rank line of this pass went through ``_ai_debug`` (``IMGSLI_AI_DEBUG``
    gated), so a default-level log could not say whether the rank was refused,
    unscheduled or never triggered — the owner's report ("метрики есть, ранга
    нет") had no corresponding log line. A refused series now says WHICH axis
    set was asked and how many members carried a reading, without the gate.
    """
    items = [_scored_item(f"img_{i}.png", sharpness=60 + i) for i in range(3)]
    profile = _free_profile()  # six judge axes; the cards are scored on none
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path, ai_profile=profile)

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        ctrl._run_jev_ranks()

    assert ctrl.launches == [], "a matrix scored on other axes must not be ranked"
    assert "jev rank partial: 0/3 scored" in caplog.text
    assert "axes=line_crispness," in caplog.text, (
        "the refused rank must name the axis set it was built from — "
        f"'axes=-' described a six-axis profile as empty; got {caplog.text}"
    )


def test_a_judge_only_complete_matrix_names_its_axes_in_the_trace(
    tmp_path, caplog, monkeypatch
) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    items = _free_items()
    ctrl = _FreeRankCtrl(
        items, [_series(*items)], cache_dir=tmp_path, ai_profile=_free_profile()
    )

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        ctrl._run_jev_ranks()

    assert "jev rank complete=6/6 (profile=vlm axes=line_crispness," in caplog.text, (
        f"a judge-filled profile must be reported by its own names: {caplog.text}"
    )


def test_an_algorithms_vector_still_uses_its_own_mode_mapping() -> None:
    """The guard against over-widening: the local domain is unchanged."""
    items = []
    for i in range(3):
        it = GalleryItem(path=Path(f"/gallery/img_{i}.png"), mtime_ns=0)
        it.metrics = {"ssim": 0.9 - i * 0.1, "sharpness": 1.2 - i * 0.2}
        items.append(it)

    vector = build_measured_vector(items, mode=Mode.CAMERA, domain="algorithms")
    assert vector["mode"] == "camera"
    assert any(entry["scores"] for entry in vector["items"])


# ---------------------------------------------------------------------------
# (g) a model-proposed axis IS a dimension the vector carries
# ---------------------------------------------------------------------------


def _proposal_item(name: str, scores: dict[str, int]) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={},
        axis_proposals=tuple(
            AiAxisProposal(
                name=axis,
                definition=f"{axis} as the model reads it",
                direction="higher-is-better",
                score=value,
            )
            for axis, value in scores.items()
        ),
    )
    return it


def test_a_matrix_scored_only_on_proposed_axes_is_complete() -> None:
    items = [
        _proposal_item(
            f"img_{i}.png", {"line_crispness": 55 + i, "halo_artifacts": 70 - i}
        )
        for i in range(3)
    ]
    vector = build_measured_vector(items, mode=Mode.CAMERA, domain="ai", profile=None)

    assert len(vector.get("proposed_axes") or ()) == 2, (
        "the payload carries both proposed axes by name"
    )
    scored, total, why = ps.rank_completeness(items, vector)
    assert (scored, total, why) == (3, 3, ""), (
        "every member carries both of its readings in the payload, so the matrix "
        f"is complete; got {scored}/{total} ({why})"
    )


def test_rank_completeness_still_names_the_real_loss() -> None:
    """A member with NO reading anywhere is still a partial matrix."""
    scored_items = [
        _proposal_item(f"img_{i}.png", {"line_crispness": 55 + i}) for i in range(2)
    ]
    mute = GalleryItem(path=Path("/gallery/img_2.png"), mtime_ns=0)
    members = [*scored_items, mute]
    vector = build_measured_vector(
        scored_items, mode=Mode.CAMERA, domain="ai", profile=None
    )

    scored, total, why = ps.rank_completeness(members, vector)
    assert (scored, total) == (2, 3)
    assert why, "the loss must be named"


# ---------------------------------------------------------------------------
# (h) no AI profile is a NAMED fact, not a silent "partial"
# ---------------------------------------------------------------------------


def test_a_missing_ai_profile_is_named_not_silently_partial(tmp_path, caplog) -> None:
    """Without the judge's axis set the vector is the mode mapping — say so.

    The rank of a profile-less generation falls back to the local mode axis
    names (the vector still reads the AI store, so no local NUMBER is used), and
    the cards are usually unscored on those names: the pass then refuses as
    "partial" — a loss that reads like "the judge has not scored yet". The one
    fact that explains it (no profile in the AI slot) must be in the plain log.
    """
    items = _free_items()
    ctrl = _FreeRankCtrl(items, [_series(*items)], cache_dir=tmp_path, ai_profile=None)

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        ctrl._run_jev_ranks()

    assert ctrl.launches == [], "the six free axes are not in the mode mapping"
    assert "no AI profile" in caplog.text, (
        "the missing axis set must be named at the default log level; got "
        f"{caplog.text}"
    )


# ---------------------------------------------------------------------------
# (i) a manual reset drops RESULTS, not the judge's axes
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_caches(tmp_path, monkeypatch):
    """Redirect every measured store the reset really deletes."""
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: ai_dir)
    pins = tmp_path / "pins"
    pins.mkdir()
    monkeypatch.setattr(profile_cache, "_default_cache", profile_cache.ProfileCache(pins))
    jev_dir = tmp_path / "jev"
    jev_dir.mkdir()
    monkeypatch.setattr(jev_cache, "jev_cache_dir", lambda: jev_dir)
    vlm_dir = tmp_path / "vlm"
    vlm_dir.mkdir()
    monkeypatch.setattr(vlm_cache, "vlm_cache_dir", lambda: vlm_dir)
    return ai_dir, pins, jev_dir, vlm_dir


class _ResetAnalyzeCtrl(_FreeRankCtrl):
    """The same controller surface, plus what the reset/analyze seams touch."""

    def __init__(self, items, groups, *, cache_dir, ai_profile=None, mode=Mode.CAMERA):
        super().__init__(items, groups, cache_dir=cache_dir, ai_profile=ai_profile, mode=mode)
        self.state.folder = Path("/gallery")
        self._last_analysis_fingerprint = ("stale",)
        self.profile_clears = 0
        self.built: list = []
        self.widget = SimpleNamespace(
            visible_paths=lambda: [],
            refresh_card=lambda it: None,
            refresh_cards=lambda its: None,
            set_ranks_visible=lambda visible: None,
            set_rank_provenance=lambda source=None, domain=None: None,
            set_triage_done=lambda: None,
            toolbar=None,
        )

    def clear_metric_profile(self) -> None:
        self.profile_clears += 1
        self.state.algorithms_profile = None
        self.state.ai_profile = None

    def _begin_analysis(self, ctx, item) -> None:
        self.built.append((ctx, item))


def test_a_manual_reset_keeps_the_judges_axis_set(tmp_path, isolated_caches) -> None:
    from tabs.image_gallery.use_cases import cache_reset

    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    item = GalleryItem(path=img, mtime_ns=img.stat().st_mtime_ns)
    item.metrics = {"ssim": 0.9}
    owner = _ResetAnalyzeCtrl(
        [item], [_series(item)], cache_dir=tmp_path, ai_profile=_free_profile()
    )

    summary = cache_reset.clear_metrics_caches(owner, paths=[str(img)])

    assert summary["items"] == 1, "the card's measurements are still dropped"
    assert item.metrics == {}, "a reset IS a reset: the numbers go"
    assert owner.state.algorithms_profile is None, (
        "the local offer is derived FROM the dropped measurements"
    )
    kept = owner.state.ai_profile
    assert kept is not None and kept.source == "vlm", (
        "the judge's axis set is a JUDGMENT, not a measurement — dropping it with "
        "the scorecards is what made the next Analyze refuse no_profile"
    )
    assert set(getattr(kept, "axis_ids", ())) | {
        str(getattr(e, "name", "")) for e in kept.axis_entries
    } == set(FREE)


def test_analyze_right_after_a_manual_reset_sends_the_scorecard_by_the_names(
    tmp_path, isolated_caches
) -> None:
    """The owner's expectation: manual reset → Analyze works, on those axes."""
    from tabs.image_gallery.use_cases import ai_analyze, cache_reset
    from tabs.image_gallery.use_cases.action_context import (
        BACKEND_AI,
        ORIGIN_ACTION,
        ActionContext,
    )
    from tabs.image_gallery.services.ai_client.prompt import build_prompt

    img = tmp_path / "a.jpg"
    img.write_bytes(b"\x00")
    item = GalleryItem(path=img, mtime_ns=img.stat().st_mtime_ns)
    owner = _ResetAnalyzeCtrl(
        [item], [_series(item)], cache_dir=tmp_path, ai_profile=_free_profile()
    )
    cache_reset.clear_metrics_caches(owner, paths=[str(img)])

    # The context the action builds carries the ACTIVE profile of the domain.
    from tabs.image_gallery.use_cases.profile_select import active_profile

    profile = active_profile(owner.state, domain=BACKEND_AI)
    assert profile is not None, "the AI slot is empty right after its own reset"
    ctx = ActionContext(
        targets=(img,),
        origin=ORIGIN_ACTION,
        backend=BACKEND_AI,
        profile=profile,
        mode=owner.state.mode,
        effort=None,
    )

    refusal = ai_analyze.analyze(owner, ctx)

    assert refusal is None, (
        "Analyze must not refuse no_profile because of its own reset: "
        f"{getattr(refusal, 'reason', None)} ({getattr(refusal, 'detail', '')})"
    )
    assert len(owner.built) == 1, "a scorecard payload was built for the card"
    built_ctx, _built_item = owner.built[0]
    prompt = build_prompt(
        str(getattr(built_ctx.mode, "value", built_ctx.mode)),
        profile=built_ctx.profile,
        measured_block="",
    )
    for axis in FREE:
        assert axis in prompt, (
            f"the scorecard must ask for the judge's axis '{axis}'; prompt={prompt}"
        )
