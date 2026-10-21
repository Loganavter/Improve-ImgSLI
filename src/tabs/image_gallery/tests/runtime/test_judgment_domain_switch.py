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
