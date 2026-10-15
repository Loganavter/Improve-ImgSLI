"""J1 — the correct Jev lifecycle (plan-gallery-jev-pipeline).

Falsification story (what each test would catch):

- a Jev call fired for a series whose members carry no applicable MEASURED
  score (the empty/partial vector that only ever abstains — and whose degrade
  must NOT be pinned: a pin on missing inputs poisons the cache);
- a Jev batch not driven by the measured-metrics-pass settle, or driven twice
  over unchanged inputs (the single-flight gate must dedup);
- the settle reading ``state.rank_domain`` (replaced by open_folder/append)
  instead of the durable ``_judgment_domain`` authority — a restored ``ai``
  domain would then never rank;
- a benign non-answer (abstain / low confidence) painting the per-card "error"
  chip while a real transport fault failed to;
- the stats-strip provenance chip not driven from the APPLIED ``rank_source``.

Network-free and Qt-free except the one widget-proxy test (needs the strip).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, Mode, Series
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.jev_client import (
    JEV_REASON_EMPTY,
    JEV_REASON_ERROR,
    JEV_REASON_LOW_CONFIDENCE,
    JEV_REASON_MALFORMED,
    JEV_REASON_NOT_CONFIGURED,
    JEV_REASON_NOUL,
    JevRankOutcome,
    rank_series_jev_detailed,
    reason_is_fault,
)
from tabs.image_gallery.use_cases import pipeline_stages as ps


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _series(*items) -> Series:
    return Series(id="series_1", members=list(items))


def _chat(decision: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(decision)}}]}


class _LifecycleCtrl:
    """Minimal controller surface for the real J1 rank/settle path (no Qt)."""

    def __init__(self, groups, items, *, mode=Mode.FIDELITY, domain="ai", visible=None) -> None:
        self.state = SimpleNamespace(
            series=list(groups), items=list(items), mode=mode, rank_domain="algorithms"
        )
        self._judgment_domain = domain
        self._folder_gen = 0
        self._stage_gate = ps.StageGate()
        self._AI_VISIBLE_CAP = 12
        self.widget = SimpleNamespace(
            visible_paths=lambda: list(visible or []),
            refresh_card=lambda it: None,
            refresh_cards=lambda its: None,
            set_rank_provenance=lambda s=None, domain=None: None,
        )
        self.scheduled: list[list[str]] = []
        self.jev_ranks_calls = 0

    # Real primitives, bound to this fake.
    def _find_item(self, path):
        return GalleryController._find_item(self, path)

    def _mark_local_pass(self, items, phase):
        return GalleryController._mark_local_pass(self, items, phase)

    def _run_jev_ranks(self):
        self.jev_ranks_calls += 1
        return GalleryController._run_jev_ranks(self)

    def _set_judgment_domain(self, domain):
        return GalleryController._set_judgment_domain(self, domain)

    def _apply_fusion_ranks(self, series, *, mode=None):
        return GalleryController._apply_fusion_ranks(self, series, mode=mode)

    def _clear_series_priority(self):
        return None

    def _run_ai_for_visible(self):
        return None

    def _run_series_priority(self):
        return None

    def activate_judgment_domain(self, domain):
        return GalleryController.activate_judgment_domain(self, domain)

    def _run_jev_rank_for_series(self, members, *, on_complete=None):
        """Record the schedule and complete synchronously (no worker)."""
        self.scheduled.append([str(m.path) for m in members])
        if callable(on_complete):
            on_complete(True)


# --------------------------------------------------------------------------
# (1) <2 scored members → no Jev call AND no pin written
# --------------------------------------------------------------------------


def test_empty_vector_is_not_pinned_and_does_not_call_the_transport(tmp_path) -> None:
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"choice": "img_1", "score": 0.9})

    a, b = _item("a.png"), _item("b.png")  # neither carries a measured score
    cache = jev_cache.JevRankCache(tmp_path)
    outcome = rank_series_jev_detailed([a, b], mode="fidelity", client=_client, cache=cache)

    assert outcome.ranks is None
    assert outcome.reason == JEV_REASON_EMPTY
    assert calls == [], "the transport must not be hit for an unscored vector"
    assert not list(tmp_path.glob("rank_*.json")), "a precondition non-answer must NOT be pinned"


def test_partial_vector_is_not_pinned(tmp_path) -> None:
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"choice": "img_1", "score": 0.9})

    a, b = _item("a.png", ssim=0.9), _item("b.png")  # only ONE scored member
    cache = jev_cache.JevRankCache(tmp_path)
    outcome = rank_series_jev_detailed([a, b], mode="fidelity", client=_client, cache=cache)

    assert outcome.ranks is None
    assert outcome.reason == JEV_REASON_EMPTY
    assert calls == []
    assert not list(tmp_path.glob("rank_*.json"))


def test_a_genuine_abstain_from_a_complete_vector_is_still_pinned(tmp_path) -> None:
    """Contrast: the precondition gate must not over-reach — a real ``Noul``
    over ≥2 scored members IS pinned so a re-run is stable."""
    calls: list[dict] = []

    def _client(payload):
        calls.append(payload)
        return _chat({"noul": True})

    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    cache = jev_cache.JevRankCache(tmp_path)
    first = rank_series_jev_detailed([a, b], mode="fidelity", client=_client, cache=cache)
    second = rank_series_jev_detailed([a, b], mode="fidelity", client=_client, cache=cache)

    assert first.reason == JEV_REASON_NOUL
    assert second.cached is True
    assert len(calls) == 1
    assert list(tmp_path.glob("rank_*.json")), "a complete-vector abstain is pinned"


# --------------------------------------------------------------------------
# (2) <2 scored members → Jev not scheduled by the controller
# --------------------------------------------------------------------------


def test_run_jev_ranks_skips_a_series_below_two_scored_members() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png")  # one scored member
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b])
    GalleryController._run_jev_ranks(ctrl)
    assert ctrl.scheduled == [], "a <2-scored series must never reach a Jev worker"


def test_run_jev_ranks_schedules_a_series_with_two_scored_members() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b])
    GalleryController._run_jev_ranks(ctrl)
    assert ctrl.scheduled == [[str(a.path), str(b.path)]]


def test_run_jev_ranks_does_nothing_on_the_algorithms_domain() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b], domain="algorithms")
    GalleryController._run_jev_ranks(ctrl)
    assert ctrl.scheduled == []


# --------------------------------------------------------------------------
# (3) gate: the settle ranks once; a second settle is a no-op
# --------------------------------------------------------------------------


def test_metrics_settle_schedules_jev_once() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b])
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    assert ctrl.scheduled == [[str(a.path), str(b.path)]]
    assert ctrl.jev_ranks_calls == 1


def test_second_settle_over_unchanged_inputs_does_not_reschedule() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b])
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    assert len(ctrl.scheduled) == 1, "the single-flight gate must dedupe the second settle"
    assert ctrl.jev_ranks_calls == 2  # both triggers fired; only one batch ran


def test_second_trigger_before_finish_is_single_flight() -> None:
    """A domain-switch trigger racing the settle must not spawn a second batch."""
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b])

    def _no_complete(members, *, on_complete=None):
        ctrl.scheduled.append([str(m.path) for m in members])  # never completes

    ctrl._run_jev_rank_for_series = _no_complete  # type: ignore[method-assign]
    GalleryController._run_jev_ranks(ctrl)  # in flight
    GalleryController._run_jev_ranks(ctrl)  # same scope → refused
    assert len(ctrl.scheduled) == 1


def test_explicit_domain_toggle_back_to_ai_reopens_the_gate() -> None:
    """Switching Algorithms→AI must re-apply the Jev rank even though the same
    fingerprint completed: the explicit switch re-opens the stage gate (the
    pinned cache makes the re-run free)."""
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b], domain="algorithms")
    ctrl.activate_judgment_domain("ai")
    assert len(ctrl.scheduled) == 1
    ctrl.activate_judgment_domain("algorithms")
    ctrl.activate_judgment_domain("ai")
    assert len(ctrl.scheduled) == 2


def test_folder_change_invalidates_the_gate() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b])
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    assert len(ctrl.scheduled) == 1

    GalleryController._next_folder_gen(ctrl)  # a new folder world
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    assert len(ctrl.scheduled) == 2, "a completed fingerprint must not block the new folder"


# --------------------------------------------------------------------------
# (4) the settle reads the DURABLE domain authority, not state
# --------------------------------------------------------------------------


def test_settle_ranks_when_the_authority_is_ai_even_if_state_says_algorithms() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b], domain="ai")
    ctrl.state.rank_domain = "algorithms"  # a replaced GalleryState projection
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    assert ctrl.scheduled, "the durable authority must drive ranking, not state"


def test_settle_skips_when_the_authority_is_algorithms_even_if_state_says_ai() -> None:
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _LifecycleCtrl([_series(a, b)], [a, b], domain="algorithms")
    ctrl.state.rank_domain = "ai"
    GalleryController._settle_metrics_pass(ctrl, [a, b])
    assert ctrl.scheduled == []


# --------------------------------------------------------------------------
# (5) benign-vs-fault degrade
# --------------------------------------------------------------------------


def test_reason_is_fault_classification() -> None:
    assert reason_is_fault(f"{JEV_REASON_ERROR}: network exploded")
    assert reason_is_fault(JEV_REASON_ERROR)
    assert reason_is_fault(JEV_REASON_NOT_CONFIGURED)
    assert not reason_is_fault(JEV_REASON_NOUL)
    assert not reason_is_fault(JEV_REASON_LOW_CONFIDENCE)
    assert not reason_is_fault(JEV_REASON_EMPTY)
    # A malformed reply is a deterministic "no usable answer", not a transport
    # fault: it must not re-introduce the mass false-error chip.
    assert not reason_is_fault(JEV_REASON_MALFORMED)
    assert not reason_is_fault(None)


def test_benign_degrade_completes_the_badge_ux_but_a_fault_paints_error() -> None:
    it = SimpleNamespace(
        path="/g/a.png", activity_phase="queued", activity_source="ai", activity_at=1e18
    )
    ctrl = SimpleNamespace(
        _find_item=lambda p: it, widget=SimpleNamespace(refresh_card=lambda x: None)
    )
    GalleryController._degrade_jev(ctrl, [it], JEV_REASON_NOUL)
    # Benign: the Jev work FINISHED -> the chip completes (done), not a false error
    # and not an abrupt mid-ux clear.
    assert it.activity_phase == "done"

    GalleryController._degrade_jev(ctrl, [it], JEV_REASON_ERROR, as_error=True)
    assert it.activity_phase == "error"


# --------------------------------------------------------------------------
# (6) provenance from the APPLIED rank_source
# --------------------------------------------------------------------------


def test_apply_jev_outcome_sets_provenance_from_the_applied_source() -> None:
    seen: list[tuple] = []
    a = SimpleNamespace(path="/g/a.png", rank=None, rank_source=None)
    b = SimpleNamespace(path="/g/b.png", rank=None, rank_source=None)
    ctrl = SimpleNamespace(
        state=SimpleNamespace(series=[SimpleNamespace(members=[a, b])], rank_domain="ai"),
        _judgment_domain="ai",
        _find_item=lambda p: None,
        widget=SimpleNamespace(
            refresh_card=lambda x: None,
            set_rank_provenance=lambda s=None, domain=None: seen.append((s, domain)),
        ),
    )
    GalleryController._apply_jev_outcome(
        ctrl, [a, b], JevRankOutcome({"/g/a.png": 1, "/g/b.png": 2})
    )
    assert a.rank_source == "jev"
    assert ("jev", "ai") in seen


def test_degraded_ai_domain_reports_the_algorithms_provenance() -> None:
    seen: list[tuple] = []
    a = SimpleNamespace(path="/g/a.png", rank=1, rank_source="fusion")
    b = SimpleNamespace(path="/g/b.png", rank=2, rank_source="fusion")
    ctrl = SimpleNamespace(
        state=SimpleNamespace(series=[SimpleNamespace(members=[a, b])], rank_domain="ai"),
        _judgment_domain="ai",
        _find_item=lambda p: None,
        _degrade_jev=lambda members, reason, *, as_error=False: GalleryController._degrade_jev(
            ctrl, members, reason, as_error=as_error
        ),
        widget=SimpleNamespace(
            refresh_card=lambda x: None,
            set_rank_provenance=lambda s=None, domain=None: seen.append((s, domain)),
        ),
    )
    GalleryController._apply_jev_outcome(ctrl, [a, b], JevRankOutcome(None, reason=JEV_REASON_NOUL))
    assert ("fusion", "ai") in seen, "a degraded AI domain must not claim AI (Jev)"


def test_widget_proxies_rank_provenance_to_the_strip(qtbot) -> None:
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.set_rank_provenance("jev")
    assert "AI (Jev)" in w.stats_strip.rank_provenance_label.text()
    w.set_rank_provenance("fusion")
    assert "Algorithms" in w.stats_strip.rank_provenance_label.text()


# --------------------------------------------------------------------------
# (7) declared readiness
# --------------------------------------------------------------------------


def test_jev_rank_stage_declares_metrics_ready() -> None:
    assert ps.stage_requires("jev_rank") == ("metrics_ready",)


def test_jev_apply_refreshes_all_members_atomically() -> None:
    """One refresh_cards(members) call, not a per-card loop: a per-card loop
    left a snapshot mixing a Jev rank with a stale fusion rank -> two '#1's."""
    from types import SimpleNamespace

    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.services.jev_client import JevRankOutcome

    refreshed: list = []
    a = SimpleNamespace(path="/g/a.png", rank=None, rank_source=None)
    b = SimpleNamespace(path="/g/b.png", rank=None, rank_source=None)
    ctrl = SimpleNamespace(
        state=SimpleNamespace(series=[], rank_domain="ai"),
        _judgment_domain="ai",
        _find_item=lambda p: None,
        widget=SimpleNamespace(
            refresh_cards=lambda items: refreshed.append(list(items)),
            refresh_card=lambda x: None,
            set_rank_provenance=lambda *a, **k: None,
        ),
    )
    GalleryController._apply_jev_outcome(
        ctrl, [a, b], JevRankOutcome({"/g/a.png": 1, "/g/b.png": 2})
    )
    assert len(refreshed) == 1
    assert {getattr(i, "path", "") for i in refreshed[0]} == {"/g/a.png", "/g/b.png"}
    assert {a.rank, b.rank} == {1, 2}


def test_fusion_defers_best_to_jev_on_the_ai_domain() -> None:
    """★ BEST belongs to the active ranker: on AI, fusion must NOT pre-empt it
    (a provisional fusion leader showed BEST before the analysis ended); on
    Algorithms, fusion's rank 1 is the winner."""
    from types import SimpleNamespace

    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.models import Series

    a = SimpleNamespace(
        path="/g/a.png", metrics={"ssim": 0.9}, rank=None, rank_source=None, is_best=False
    )
    b = SimpleNamespace(
        path="/g/b.png", metrics={"ssim": 0.4}, rank=None, rank_source=None, is_best=False
    )
    series = [Series(id="s", members=[a, b])]
    ctrl = SimpleNamespace(
        _judgment_domain="ai", state=SimpleNamespace(items=[a, b], mode="fidelity")
    )

    GalleryController._apply_fusion_ranks(ctrl, series, mode="fidelity")
    assert not a.is_best and not b.is_best  # deferred to Jev on the AI domain

    ctrl._judgment_domain = "algorithms"
    GalleryController._apply_fusion_ranks(ctrl, series, mode="fidelity")
    assert (a.is_best, b.is_best) == (True, False)  # Algorithms: rank 1 wins
