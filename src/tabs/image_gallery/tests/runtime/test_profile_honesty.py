"""P5 — the adaptive profile must stay truthful to the judgment domain.

Audit-Meta: pattern=regression source=live-2026-10-20

Live evidence (2026-10-20, toolbar on **Algorithms**)::

    19:15:09 [gallery] metric profile: axes=sharpness,exposure,clipping,noise,
             white_balance,detail_gain,aesthetic,brisque source=heuristic
    19:15:21 [gallery] metric profile: axes=sharpness,noise source=vlm

The VLM profile selector had no judgment-domain gate, so an Algorithms
folder's profile was replaced by a model-chosen subset the Algorithms
pipeline must never use; the late replacement also invalidated the identity
of AI requests that were already in flight (the analysis cache stores a
scorecard under ``(mode, profile, model, …)``).

A profile IS a subset of the fixed pool chosen per context
(``docs/investigations/plan-adaptive-metric-profiles-2026-10-17.md``
§General model) — a narrow vlm selection is intended, not a downgrade. What it
may never do is leave the pool, name an axis this context cannot measure, or
fabricate one.

Falsification story (what each test would catch):

- the selector kicking — and spending an API call — in the Algorithms domain
  (the toggle changing the ranking axes it does not own);
- the settle starting the AI pass BEFORE the profile that will replace it
  exists: every in-flight request identity would be the pre-replacement one,
  so the scorecards land under an identity the next open never reads (the
  visible symptom is a guaranteed API re-charge on every visit), and a late
  reply applied after the calls began must be dropped, not applied;
- a VLM reply that widens or invents the vocabulary (a free-form id, or an
  axis whose detector needs a source hub in a folder without one), or a reply
  of only-unusable ids silently becoming a profile instead of the honest
  heuristic fallback.

(The chip/provenance-label assertions that used to live here were deleted with
the stats-strip metric-profile chip and the manual domain pin — owner decision
2026-10-20, plan ``plan-gallery-analysis-engine-2026-10-20`` §Product
decision. What the chip said is now carried per axis by provenance, and the
automatic profile path asserted below is unchanged.)

Qt-free controller fakes and one offscreen ``StatsStrip`` (real widget).
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery import controller as controller_mod
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, Mode, Series
from tabs.image_gallery.services.metric_profile import (
    MetricProfile,
    profile_for_mode,
)
from tabs.image_gallery.use_cases import pipeline_stages as ps
from tabs.image_gallery.use_cases import profile_ai, triage_run
from core.log_names import APP_LOGGER_NAME


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _vlm_profile(axis_ids=("sharpness", "noise")) -> MetricProfile:
    return MetricProfile(
        axis_ids=tuple(axis_ids),
        mode="camera",
        source="vlm",
        salient_axes=tuple(axis_ids),
    )


def _selector_returning(profile, *, calls=None):
    def _sel(items, mode=None, settings=None):
        if calls is not None:
            calls.append((list(items), mode))
        return profile

    return _sel


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
    """``GenericWorker`` double: captures the job, delivers signals on ``run``.

    Mirrors ``sl_ui_toolkit.workers.GenericWorker.run`` — a None reply emits no
    ``result`` (only ``finished``), an exception emits ``error`` then
    ``finished``.
    """

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


class _ProfileCtrl:
    """Minimal controller surface for the real P2 selector + settle path."""

    def __init__(self, items, *, mode=Mode.CAMERA, series=None, domain="ai", gen=0) -> None:
        self.state = SimpleNamespace(
            items=list(items),
            series=list(series or []),
            mode=mode,
            metric_profile=None,
        )
        self._judgment_domain = domain
        self._folder_gen = gen
        self._metrics_settled_gen = -1
        self._stage_gate = ps.StageGate()
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True,
                api_key="k",
                model="m",
                base_url="http://h",
            )
        )
        self.widget = SimpleNamespace(
            refresh_cards=lambda its: None,
            refresh_card=lambda it: None,
        )
        #: ``state.metric_profile`` as the AI pass saw it, one entry per start.
        self.ai_starts: list = []
        self.jev_starts: list = []
        self.launched: list = []

    # Real primitives, bound to this fake.
    def _is_current_folder_gen(self, gen):
        return GalleryController._is_current_folder_gen(self, gen)

    def _pool_start(self, worker, priority):
        # Never runs the worker: tests drive ``worker.run()`` explicitly so the
        # in-flight vs completed states are both observable.
        self.launched.append(worker)

    def refresh_metric_profile(self):
        return GalleryController.refresh_metric_profile(self)

    def _run_profile_select_on_settle(self):
        return GalleryController._run_profile_select_on_settle(self)

    def _apply_profile_outcome(self, profile, gen):
        return GalleryController._apply_profile_outcome(self, profile, gen)

    def _resume_settle_after_profile(self, gen):
        return GalleryController._resume_settle_after_profile(self, gen)

    def _mark_profile_consumed(self):
        return GalleryController._mark_profile_consumed(self)

    def _run_ai_for_visible(self):
        GalleryController._mark_profile_consumed(self)
        self.ai_starts.append(getattr(self.state, "metric_profile", None))

    def _run_jev_ranks(self):
        self.jev_starts.append(getattr(self.state, "metric_profile", None))

    # Thin primitives ``_settle_metrics_pass`` touches (no-ops here).
    def _mark_local_pass(self, items, phase):
        return None

    def _apply_fusion_ranks(self, series, *, mode=None):
        return None


# --------------------------------------------------------------------------
# (1) the judgment-domain gate — Algorithms never runs the selector
# --------------------------------------------------------------------------


def test_profile_selector_does_not_run_in_the_algorithms_domain(
    monkeypatch, fake_workers
) -> None:
    """The toggle means what it means: Algorithms owns no VLM profile pick.

    Red today: the kick had no domain gate, so a settle in the Algorithms
    domain launched (and paid for) a VLM profile call and then replaced the
    Algorithms profile with it.
    """
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], domain="algorithms")
    calls: list = []
    monkeypatch.setattr(
        controller_mod,
        "_profile_selector",
        lambda: _selector_returning(_vlm_profile(), calls=calls),
    )
    ctrl.refresh_metric_profile()
    heuristic = ctrl.state.metric_profile

    ctrl._run_profile_select_on_settle()

    assert calls == [], "the Algorithms domain must not spend a VLM profile call"
    assert ctrl.launched == [], "no selector worker may start off the AI domain"
    assert ctrl.state.metric_profile == heuristic


def test_settle_in_the_algorithms_domain_never_touches_the_profile(
    monkeypatch, fake_workers
) -> None:
    """The settle path (not only the kick) stays profile-stable off the AI domain."""
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], domain="algorithms", series=[Series(id="s", members=[a, b])])
    calls: list = []
    monkeypatch.setattr(
        controller_mod,
        "_profile_selector",
        lambda: _selector_returning(_vlm_profile(), calls=calls),
    )

    triage_run._settle_metrics_pass(ctrl, [a, b])

    assert calls == []
    assert ctrl.launched == []
    assert ctrl.state.metric_profile.source == "heuristic"
    assert ctrl.ai_starts == [], "the AI pass stays off in the Algorithms domain"


def test_late_vlm_reply_does_not_replace_the_profile_after_a_domain_switch(
    monkeypatch, fake_workers
) -> None:
    """A switch back to Algorithms mid-flight wins over the landing reply."""
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], domain="ai")
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl.refresh_metric_profile()
    heuristic = ctrl.state.metric_profile

    ctrl._run_profile_select_on_settle()  # in flight
    ctrl._judgment_domain = "algorithms"  # the toolbar flips back
    ctrl.launched[0].run()

    assert ctrl.state.metric_profile == heuristic, (
        "the Algorithms domain must not receive a VLM-chosen profile"
    )


# --------------------------------------------------------------------------
# (2) the profile is resolved BEFORE any AI request of the generation
# --------------------------------------------------------------------------


def test_settle_does_not_start_ai_under_a_profile_that_is_replaced_after_the_call(
    monkeypatch, fake_workers
) -> None:
    """One identity per folder generation: the AI pass starts under the FINAL profile.

    Red today: the selector and the AI pass start side by side, so the
    requests carry the heuristic profile while the state is then replaced by
    the vlm one — every scorecard is cached under an identity the next open
    will not look up.
    """
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b], series=[Series(id="s", members=[a, b])])
    vlm = _vlm_profile(("sharpness", "noise"))
    monkeypatch.setattr(controller_mod, "_profile_selector", lambda: _selector_returning(vlm))

    triage_run._settle_metrics_pass(ctrl, [a, b])

    assert ctrl.launched, "the selector must still be kicked on the AI domain"
    assert ctrl.ai_starts == [], (
        "the AI pass must wait for the profile it will be analysed under"
    )
    assert ctrl.jev_starts == []

    ctrl.launched[0].run()

    assert ctrl.state.metric_profile is not None
    assert ctrl.state.metric_profile.source == "vlm"
    assert ctrl.ai_starts == [vlm], "the analysis identity is the resolved profile"
    assert ctrl.jev_starts == [vlm]


def test_late_vlm_reply_is_dropped_once_analysis_started(
    monkeypatch, fake_workers, caplog
) -> None:
    """A reply landing after an AI call began may not rewrite that generation.

    Falsification: without the freeze the state profile changes mid-flight;
    the scorecards already requested cannot be re-keyed, so the replacement
    is a silent miss on every later visit (the state then claims axes the
    cached scorecards do not carry).
    """
    a, b = _item("a.png", ssim=0.9), _item("b.png", ssim=0.4)
    ctrl = _ProfileCtrl([a, b])
    monkeypatch.setattr(
        controller_mod, "_profile_selector", lambda: _selector_returning(_vlm_profile())
    )
    ctrl.refresh_metric_profile()
    heuristic = ctrl.state.metric_profile
    assert heuristic.source == "heuristic"

    ctrl._run_profile_select_on_settle()  # in flight
    ctrl._run_ai_for_visible()  # an analysis of this generation begins now
    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        ctrl.launched[0].run()  # ...and only then the vlm reply lands

    assert ctrl.state.metric_profile == heuristic, "a late reply must not be applied"
    assert any(
        "late" in rec.getMessage().lower() and "profile" in rec.getMessage().lower()
        for rec in caplog.records
    ), "the dropped reply must be visible in the debug log"


# --------------------------------------------------------------------------
# (3) a VLM reply is constrained to the pool axes this context can measure
# --------------------------------------------------------------------------


def test_vlm_profile_is_constrained_to_the_available_pool(caplog) -> None:
    """A reply is a set of neo axes or pool picks — never an invention.

    Superseded wording (2026-10-22, plan-gallery-ai-judgement §OWNER REVISION):
    the model NAMES the axes, so an id outside the pool is no longer dropped — a
    bare name with no definition still is (it cannot be measured), and a pool id
    the context cannot measure locally is KEPT (the judge measures it itself).
    """
    base = profile_for_mode("camera")
    assert "sharpness" in base.axis_ids and "ssim" not in base.axis_ids

    profile = profile_ai.parse_profile_reply(
        '{"axes": ["sharpness", "ssim", "invented"]}', mode="camera"
    )

    assert profile is not None and profile.source == "vlm"
    assert profile.axis_ids == ("sharpness", "ssim"), (
        "registry ids are kept even where no local detector runs (the judge "
        "measures them); only a bare name with no meaning is refused"
    )
    assert "invented" not in profile.axis_ids
    assert profile.axis_entries == (), "a bare id carries no definition"


def test_vlm_reply_of_only_unusable_ids_falls_back_to_the_heuristic(
    monkeypatch, caplog, tmp_path
) -> None:
    """No usable axis → ``None`` (the caller's heuristic), with a debug line.

    Falsification: a hollow "vlm" profile would claim a model pick over an
    empty axis set; the honest answer is the deterministic fallback.
    """
    assert profile_ai.parse_profile_reply('{"axes": ["made_up"]}', mode="camera") is None
    assert profile_ai.parse_profile_reply('{"axes": []}', mode="camera") is None
    # P7-A: a registry id is kept even where no local detector runs — the judge
    # measures it. Only a bare NAME with no definition is refused.
    assert profile_ai.parse_profile_reply('{"axes": ["halo_delta"]}', mode="camera")

    from tabs.image_gallery.services.profile_cache import ProfileCache
    from tabs.image_gallery.use_cases import profile_probe

    # Probe members exist (the transport IS reached); only the reply is junk.
    monkeypatch.setattr(
        profile_probe, "probe_members", lambda items, reference_path=None: [object()]
    )
    settings = SimpleNamespace(
        enabled=True, api_key="k", model="m", base_url="http://h", reasoning_effort="auto"
    )
    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        profile = profile_ai.choose_profile_sync(
            [_item("a.png", ssim=0.9), _item("b.png", ssim=0.4)],
            mode="camera",
            settings=settings,
            cache=ProfileCache(tmp_path),
            client_call=lambda *a, **k: {
                "choices": [{"message": {"content": '{"axes": ["made_up"]}'}}]
            },
        )
    assert profile.source == "heuristic"
    assert any(
        "no usable axis" in rec.getMessage().lower() for rec in caplog.records
    ), "the heuristic fallback must say so in the debug log"
