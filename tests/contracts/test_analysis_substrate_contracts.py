"""Contract tests: the analysis substrate's records hold their invariants.

Dogma source: ``PLAN.md`` §Invariants (I1 provenance per axis, I3 declared
automatic runs) and §Gates (G7 budget declared) in
``plan-gallery-analysis-engine-2026-10-20``. The plan is the only written home
of these rules until it graduates into ``docs/dev/`` — if a rule here changes,
the plan changed first.

Every case asserts a construction that MUST fail, so deleting the matching
``__post_init__`` check turns the test red instead of leaving it vacuously
green (a permissive record type would pass no case below).
"""

from __future__ import annotations

import dataclasses

import pytest

from engine.analysis.contracts import (
    AnalysisPlan,
    AxisValue,
    BackendRef,
    Budget,
    JournalEntry,
    ProducerSpec,
    RunJournal,
)


def _ref(**overrides) -> BackendRef:
    kwargs: dict[str, object] = {
        "provider": "openrouter",
        "model": "some-model",
        "base_url": "https://example.invalid/v1",
    }
    kwargs.update(overrides)
    return BackendRef(**kwargs)


def _spec(**overrides) -> ProducerSpec:
    kwargs: dict[str, object] = {
        "id": "local",
        "provides": {"sharpness": "measured"},
    }
    kwargs.update(overrides)
    return ProducerSpec(**kwargs)


# -- AxisValue: a gap is never filled with a number -------------------------


def test_ok_status_requires_a_value():
    with pytest.raises(ValueError, match="requires a value"):
        AxisValue(axis="sharpness", value=None, producer="local")
    assert AxisValue(axis="sharpness", value=0.0, producer="local").value == 0.0


@pytest.mark.parametrize("status", ["gap", "error"])
def test_gap_and_error_forbid_a_value(status: str):
    with pytest.raises(ValueError, match="must not carry a value"):
        AxisValue(axis="ssim", value=0.91, producer="local", status=status)
    empty = AxisValue(
        axis="ssim", value=None, producer="local", status=status, reason="no reference"
    )
    assert empty.value is None
    assert empty.reason == "no reference"


def test_stale_keeps_its_last_value():
    # Stale is NOT a gap: the number is real, only its generation is superseded.
    stale = AxisValue(
        axis="sharpness",
        value=42.0,
        producer="local",
        status="stale",
        reason="policy changed",
    )
    assert stale.value == 42.0


def test_producer_is_mandatory_for_provenance():
    with pytest.raises(ValueError, match="producer"):
        AxisValue(axis="sharpness", value=1.0, producer="  ")


def test_unknown_status_is_refused():
    with pytest.raises(ValueError, match="status"):
        AxisValue(axis="sharpness", value=1.0, producer="local", status="maybe")


def test_echo_names_the_backend_it_repeats():
    with pytest.raises(ValueError, match="echo"):
        AxisValue(axis="ssim", value=0.9, producer="vlm", status="echo")
    echoed = AxisValue(
        axis="ssim",
        value=0.9,
        producer="vlm",
        status="echo",
        backend=_ref(),
    )
    assert echoed.backend is not None


# -- BackendRef: identity parts and hashability ------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("field", ["provider", "model", "base_url"])
def test_backend_ref_rejects_empty_parts(field: str, blank: str):
    with pytest.raises(ValueError, match=field):
        _ref(**{field: blank})


def test_backend_ref_is_hashable_and_immutable():
    ref = _ref(params={"temperature": 0.2, "nested": {"a": 1}})
    assert hash(ref) == hash(_ref(params={"temperature": 0.2, "nested": {"a": 1}}))
    with pytest.raises(TypeError):
        ref.params["temperature"] = 0.9  # type: ignore[index]


# -- ProducerSpec: an automatic producer is bounded -------------------------


def test_automatic_producer_requires_a_cap():
    with pytest.raises(ValueError, match="max_per_run"):
        _spec(id="vlm", provides={"aesthetic": "judgment"}, automatic=True)
    capped = _spec(
        id="vlm",
        provides={"aesthetic": "judgment"},
        cost="per_image",
        automatic=True,
        max_per_run=3,
    )
    assert capped.max_per_run == 3


def test_manual_producer_may_leave_the_cap_unset():
    assert _spec(automatic=False).max_per_run is None


def test_producer_spec_rejects_unknown_axis_kind():
    with pytest.raises(ValueError, match="unknown axis kind"):
        _spec(provides={"sharpness": "vibes"})


def test_producer_spec_rejects_empty_axes_and_unknown_cost():
    with pytest.raises(ValueError, match="no axes"):
        _spec(provides={})
    with pytest.raises(ValueError, match="cost"):
        _spec(cost="sometimes")


def test_producer_spec_coerces_requires_to_a_frozenset():
    spec = _spec(requires={"reference", "proxy"})
    assert spec.requires == frozenset({"reference", "proxy"})


# -- Budget: declared, cap, spent ------------------------------------------


def test_budget_ordering_is_spent_cap_declared():
    assert Budget(declared=4, cap=2, spent=1).spent == 1
    with pytest.raises(ValueError, match="spent <= cap <= declared"):
        Budget(declared=2, cap=3, spent=0)
    with pytest.raises(ValueError, match="spent <= cap <= declared"):
        Budget(declared=2, cap=2, spent=3)
    with pytest.raises(ValueError, match=">= 0"):
        Budget(declared=2, cap=2, spent=-1)


# -- Plan / journal shapes -------------------------------------------------


def test_plan_needs_an_id_policy_and_ordered_runs():
    with pytest.raises(ValueError, match="policy"):
        AnalysisPlan(id="p1", generation=0, policy="")
    plan = AnalysisPlan(id="p1", generation=2, policy="algorithms-local", runs=["a", "b"])
    assert plan.runs == ("a", "b")


def test_journal_entry_validates_status_and_count():
    with pytest.raises(ValueError, match="status"):
        JournalEntry(producer="local", status="fine")
    with pytest.raises(ValueError, match="items"):
        JournalEntry(producer="local", status="ok", items=-1)
    journal = RunJournal(entries=[JournalEntry(producer="local", status="skipped")])
    assert isinstance(journal.entries, tuple)


# -- Everything is frozen --------------------------------------------------


def test_records_are_frozen():
    instances = [
        _ref(),
        AxisValue(axis="sharpness", value=1.0, producer="local"),
        _spec(),
        AnalysisPlan(id="p1", generation=0, policy="algorithms-local"),
        Budget(declared=1, cap=1),
        JournalEntry(producer="local", status="ok"),
        RunJournal(),
    ]
    for instance in instances:
        field = dataclasses.fields(instance)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field, None)
