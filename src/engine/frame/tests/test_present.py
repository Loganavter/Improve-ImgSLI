"""Pins for the frame-assurance present ledger (engine.frame.present).

Covers generation bumps, stale-generation ignore, settle-at-count (default
and custom), pumped-once, the should_fire matrix, fresh-debt defaults, and
fail-open bad-input behavior (nothing here may ever raise).
"""

from __future__ import annotations

import pytest

from engine.cache.first_frame_gate import (
    FIRST_PRESENT_SETTLE_COUNT as GATE_COUNT,
)
from engine.frame.present import (
    FIRST_PRESENT_SETTLE_COUNT,
    PresentDebt,
    begin_source,
    note_presented,
    should_fire,
)


def test_settle_constant_reexported_from_gate():
    assert FIRST_PRESENT_SETTLE_COUNT == GATE_COUNT == 10


def test_fresh_debt_defaults():
    debt = PresentDebt()
    assert (debt.generation, debt.presented) == (0, 0)
    assert debt.pumped is False
    assert debt.settled is False


def test_begin_source_from_none_gives_generation_one():
    debt = begin_source(None)
    assert isinstance(debt, PresentDebt)
    assert debt.generation == 1
    assert (debt.presented, debt.pumped, debt.settled) == (0, False, False)


def test_begin_source_from_fresh_debt_gives_generation_one():
    assert begin_source(PresentDebt()).generation == 1


def test_begin_source_bumps_generation():
    first = begin_source(None)
    second = begin_source(first)
    assert second.generation == first.generation + 1 == 2
    assert begin_source(second).generation == 3


def test_begin_source_resets_counters_and_flags():
    old = PresentDebt(generation=4, presented=9, pumped=True, settled=True)
    new = begin_source(old)
    assert new.generation == 5
    assert (new.presented, new.pumped, new.settled) == (0, False, False)


def test_begin_source_does_not_mutate_input():
    old = PresentDebt(generation=2, presented=7, pumped=True, settled=False)
    snapshot = PresentDebt(**vars(old))
    begin_source(old)
    assert old == snapshot


def test_first_present_pumps_then_waits_until_settle():
    debt = begin_source(None)
    assert note_presented(debt) == "pumped"
    assert debt.pumped is True
    assert debt.settled is False
    for _ in range(GATE_COUNT - 2):
        assert note_presented(debt) == "waiting"
    assert debt.settled is False
    assert note_presented(debt) == "settled"
    assert debt.settled is True
    assert debt.presented == GATE_COUNT


def test_pumped_returned_exactly_once():
    debt = begin_source(None)
    outcomes = [note_presented(debt) for _ in range(GATE_COUNT + 2)]
    assert outcomes[0] == "pumped"
    assert "pumped" not in outcomes[1:]
    assert outcomes[GATE_COUNT - 1] == "settled"
    assert outcomes[GATE_COUNT] == "settled"


def test_settle_with_custom_count():
    debt = begin_source(None)
    assert note_presented(debt, 3) == "pumped"
    assert note_presented(debt, 3) == "waiting"
    assert note_presented(debt, 3) == "settled"
    assert debt.settled is True


def test_custom_count_of_one_settles_immediately():
    debt = begin_source(None)
    assert note_presented(debt, 1) == "settled"
    assert debt.pumped is True
    assert debt.settled is True


def test_note_presented_never_mutates_generation():
    debt = begin_source(None)
    gen = debt.generation
    for _ in range(GATE_COUNT + 3):
        note_presented(debt)
    assert debt.generation == gen


def test_should_fire_current_unsettled_generation():
    debt = begin_source(None)
    assert should_fire(debt.generation, debt) is True


def test_should_fire_ignores_stale_generation():
    old = begin_source(None)
    new = begin_source(old)
    assert should_fire(old.generation, new) is False
    assert should_fire(new.generation, new) is True


def test_should_fire_rejects_future_generation():
    debt = begin_source(None)
    assert should_fire(debt.generation + 1, debt) is False


def test_should_fire_rejects_settled_generation():
    debt = begin_source(None)
    for _ in range(GATE_COUNT):
        note_presented(debt)
    assert debt.settled is True
    assert should_fire(debt.generation, debt) is False


@pytest.mark.parametrize(
    ("timer_gen", "settled", "expected"),
    [(1, False, True), (0, False, False), (2, False, False), (1, True, False)],
)
def test_should_fire_matrix(timer_gen, settled, expected):
    debt = PresentDebt(generation=1, settled=settled)
    assert should_fire(timer_gen, debt) is expected


def test_should_fire_coerces_timer_generation():
    debt = PresentDebt(generation=2)
    assert should_fire("2", debt) is True
    assert should_fire("nope", debt) is False


def test_bad_input_never_raises():
    assert begin_source(None).generation == 1
    assert begin_source("junk").generation == 1  # type: ignore[arg-type]
    assert note_presented(None) == "waiting"  # type: ignore[arg-type]
    assert note_presented("junk") == "waiting"  # type: ignore[arg-type]
    assert note_presented(begin_source(None), "junk") in (
        "pumped",
        "waiting",
        "settled",
    )
    assert should_fire(None, None) is False  # type: ignore[arg-type]
    assert should_fire("x", "y") is False  # type: ignore[arg-type]
    assert should_fire(1, None) is False  # type: ignore[arg-type]
    assert should_fire(object(), PresentDebt()) is False  # type: ignore[arg-type]
