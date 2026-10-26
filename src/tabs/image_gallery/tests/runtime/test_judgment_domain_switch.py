"""The judgment domain SWITCHES, is CONFIGURABLE, and the judge's axes never
leak into the ALGORITHMS path (3 cases).

Measured gap (2026-10-22): the domain switch and its persistence existed, but
NO test covered either end of it - the QSettings route
(``image_gallery/chrome`` -> ``judgment_domain``) had no test at all, and
nothing asserted that the axes the JUDGE names stay out of the algorithms
vector (they cannot be measured there - they must be omitted, never
fabricated).

Case 1 - the CONFIG route: the app's own persistence (``SessionState`` ->
QSettings ``image_gallery/chrome``, a JSON string) seeds a NEW session, so a
domain chosen in a previous run survives a restart.
Case 2 - the SWITCH: the toolbar switch normalizes the value (``"AI"`` ->
``"ai"``) and fails OPEN on nonsense (``"algorithms"``), and it drives the
controller's ``activate_judgment_domain`` every time.
Case 3 - the ALGORITHMS path: with a profile that carries a judge-named axis,
the algorithms vector carries ONLY the axes the local detectors can measure -
the free axis is omitted, never fabricated - and the local rank still orders
the variants by the measured axis.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.models import AiAxisProposal
from tabs.image_gallery.services import jev_client, rank_fusion
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.ui.widget_parts import view_prefs


@pytest.fixture(autouse=True)
def _memory_qsettings(monkeypatch):
    """In-memory QSettings: never touch the real user config."""
    mem: dict = {}

    class _FakeQSettings:
        def __init__(self, *_args):
            pass

        def value(self, key, default=None):
            return mem.get(key, default)

        def setValue(self, key, value):
            mem[key] = value

        def sync(self):
            pass

    from tabs.use_cases import session_state as _mod

    monkeypatch.setattr(_mod, "QSettings", _FakeQSettings)
    return mem


def _judge_profile() -> MetricProfile:
    """A profile whose judge half names an axis the local detectors cannot measure."""
    judge = AiAxisProposal(
        name="jpeg_noise",
        definition="8x8 block edges; 0 = none, 100 = heavy",
        scale="0-100",
        score=40,
        producer="vlm",
        kind="candidate",
        direction="lower-is-better",
    )
    return MetricProfile(
        axis_ids=("sharpness",),
        mode="camera",
        source="vlm",
        salient_axes=("sharpness",),
        axis_entries=(judge,),
    )


def _local_item(name: str, sharpness: int) -> SimpleNamespace:
    """An item the ALGORITHMS domain can read (the local detector's raw metric)."""
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"),
        metrics={"sharpness": sharpness},
        analysis=None,
    )


def test_the_config_route_seeds_the_judgment_domain(_memory_qsettings):
    """A domain chosen in a previous run survives a restart (the QSettings route)."""
    _memory_qsettings["image_gallery/chrome"] = json.dumps(
        {"view_list": False, "judgment_domain": "ai"}
    )

    from tabs.use_cases.session_state import SessionState

    applied: dict = {}
    state = SessionState.bind(
        SimpleNamespace(),
        namespace="image_gallery",
        fields={"view_list": (bool, False), "judgment_domain": (str, "algorithms")},
        apply=lambda values: applied.update(values),
    )
    state.apply_from_slot(None, "session-1")

    assert applied.get("judgment_domain") == "ai", applied
    assert applied.get("view_list") is False, applied


def test_the_switch_normalizes_and_fails_open():
    """``"AI"`` normalizes; nonsense fails OPEN to the algorithms domain."""
    driven: list[str] = []

    class _Ctrl:
        class state:
            judgment_domain = "algorithms"

        def activate_judgment_domain(self, dom):
            driven.append(dom)
            _Ctrl.state.judgment_domain = dom

    owner = SimpleNamespace(
        _judgment_domain="algorithms",
        _controller=_Ctrl(),
        _persist_view_prefs=lambda: None,
    )

    view_prefs._on_domain_changed(owner, "ai")
    assert owner._judgment_domain == "ai"
    assert _Ctrl.state.judgment_domain == "ai"

    view_prefs._on_domain_changed(owner, "AI")
    assert owner._judgment_domain == "ai", "the switch must normalize the case"

    view_prefs._on_domain_changed(owner, " nonsense ")
    assert owner._judgment_domain == "algorithms", "an unknown domain fails OPEN"

    view_prefs._on_domain_changed(owner, None)
    assert owner._judgment_domain == "algorithms"

    assert driven == ["ai", "ai", "algorithms", "algorithms"], driven


def test_the_judges_axes_never_leak_into_the_algorithms_vector():
    """The algorithms path measures only what the local detectors can measure."""
    profile = _judge_profile()
    items = [
        _local_item("a.png", 40),
        _local_item("b.png", 85),
        _local_item("c.png", 61),
    ]

    order = rank_fusion.rank_series(items, mode="camera", profile=profile)
    assert order, order
    assert order["/gallery/b.png"] == 1, "the sharpest must lead the local rank"
    assert order["/gallery/a.png"] == 3, order

    vector = jev_client.build_measured_vector(
        items, mode="camera", domain="algorithms", profile=profile
    )
    scored = jev_client.scored_axis_names(vector)
    assert "jpeg_noise" not in scored, f"the judge's axis was fabricated: {scored}"
    assert "sharpness" in scored, scored
    payload_axes = [entry.get("name") for entry in vector.get("axes", [])]
    assert "jpeg_noise" not in payload_axes, payload_axes
    assert "sharpness" in payload_axes, payload_axes


def test_a_new_session_inherits_the_last_used_domain_even_when_the_slot_exists(
    _memory_qsettings,
):
    """The CONFIG route, end to end: a NEW session takes the last-used chrome.

    MEASURED gap (found by the live binding, 2026-10-22): the blueprint
    auto-allocates the gallery's session slot at the factory defaults, and
    ``seed_slot`` treated that slot as an existing value - so the QSettings
    fallback was never read and a config carrying ``judgment_domain="ai"`` was
    IGNORED (the live app restored "algorithms"). The slot that holds only the
    defaults carries nothing the user chose, so the last-used value wins.
    """
    from core.state_management.slot_reducers import iter_state_slot_reducers
    from tabs.use_cases.session_state import SessionState

    class _Session(SimpleNamespace):
        pass

    class _Store:
        def __init__(self):
            self.sessions: dict = {}

        def add(self, sid):
            # the blueprint auto-allocates the PLAIN namespace slot at the
            # factory defaults - that auto-allocated slot is what used to
            # block the last-used inheritance
            self.sessions[sid] = _Session(
                id=sid,
                session_type="image_gallery",
                state_slots={
                    "image_gallery": {
                        "view_list": False,
                        "judgment_domain": "algorithms",
                    }
                },
            )
            return sid

        def get_workspace_session(self, sid):
            return self.sessions.get(sid)

        def get_active_workspace_session(self):
            return None

        def get_session_state_slot(self, name, session_id=None, default=None):
            sess = self.sessions.get(session_id)
            return default if sess is None else sess.state_slots.get(name, default)

        def set_session_state_slot(self, name, value, session_id=None, emit_scope=None):
            self.sessions[session_id].state_slots[name] = value

        def get_dispatcher(self):
            return _Dispatcher(self)

    class _Dispatcher:
        def __init__(self, store):
            self._store = store

        def dispatch(self, action, scope="viewport", session_id=None):
            target = session_id or self._store.active
            for name, reducer in iter_state_slot_reducers():
                if name != action.namespace:
                    continue
                cur = self._store.get_session_state_slot(name, session_id=target)
                new = reducer(cur, action)
                if new is not cur:
                    self._store.set_session_state_slot(name, new, session_id=target)

    _memory_qsettings["image_gallery/chrome"] = json.dumps(
        {"view_list": False, "judgment_domain": "ai"}
    )

    applied: dict = {}
    state = SessionState.bind(
        SimpleNamespace(),
        namespace="image_gallery",
        fields={"view_list": (bool, False), "judgment_domain": (str, "algorithms")},
        apply=lambda values: applied.update(values),
    )
    store = _Store()
    sid = store.add("S1")
    ctx = SimpleNamespace(store=store)
    state.seed_slot(ctx, sid)
    # the tab applies the chrome when the session becomes active - THIS is the
    # path the app really takes (the live binding showed the restore path is
    # the one that ignored the config)
    state.apply_from_slot(ctx, sid)
    assert applied.get("judgment_domain") == "ai", applied
    # and the restore path on its own (a defaults-only slot must not shadow it)
    applied.clear()
    state2 = SessionState.bind(
        SimpleNamespace(),
        namespace="image_gallery",
        fields={"view_list": (bool, False), "judgment_domain": (str, "algorithms")},
        apply=lambda values: applied.update(values),
    )
    # a FRESH session whose slot is still at the defaults (the restore path)
    sid2 = store.add("S2")
    state2.apply_from_slot(ctx, sid2)
    assert applied.get("judgment_domain") == "ai", applied
    # and the slot now carries the inherited value (not the factory defaults)
    slot = store.get_session_state_slot("image_gallery", session_id=sid) or {}
    assert slot.get("judgment_domain") == "ai", slot


def test_the_ai_switch_asks_for_the_axes_before_it_analyzes(monkeypatch):
    """Owner rule 2026-10-26 (measured live, 07:05): the axis set comes FIRST.

    The switch used to call ``_run_ai_for_visible`` immediately; the first MISS
    stamped the profile as consumed ("frozen for gen N"), so the selector was
    skipped afterwards and the folder kept the heuristic-camera axes forever.
    Red-before: ``analyzed == 1`` and no profile kick.
    """
    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.use_cases import ai_analysis

    analyzed: list = []
    kicked: list = []

    class _Ctrl:
        def __init__(self, defer: bool) -> None:
            self.state = SimpleNamespace(items=[], series=[], metric_profile=None)
            self._judgment_domain = "algorithms"
            self._folder_gen = 7
            self._defer = defer
            self.widget = SimpleNamespace(refresh_cards=lambda its: None, refresh_card=lambda it: None)

        # -- the switch's collaborators ------------------------------------
        def activate_judgment_domain(self, domain):
            return GalleryController.activate_judgment_domain(self, domain)

        def _run_profile_select_on_settle(self):
            kicked.append(1)
            if self._defer:
                self._profile_settle_pending_gen = self._folder_gen

        def _run_ai_for_visible(self, cache_only=False):
            analyzed.append(cache_only)

        def _run_series_priority(self):
            pass

        def _clear_series_priority(self):
            pass

        def _apply_fusion_ranks(self, series, **_kw):
            pass

    monkeypatch.setattr(ai_analysis, "_dispatch_terminal_rank", lambda owner: None)

    deferring = _Ctrl(defer=True)
    deferring.activate_judgment_domain("ai")
    assert kicked, "the switch must ask for the axis profile"
    assert analyzed == [], (
        "no analysis may start before the profile resolves — that freezes the "
        "heuristic axis set for the whole generation"
    )

    ready = _Ctrl(defer=False)  # profile already resolved (vlm pin / consumed)
    ready.activate_judgment_domain("ai")
    assert analyzed == [False], "with the profile resolved the analysis runs at once"
