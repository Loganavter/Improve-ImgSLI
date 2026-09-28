"""Frame-assurance present ledger: one debt record per source generation.

Like the Chromium cc SchedulerStateMachine, opening a new frame (begin_source)
bumps a sequence number and only repeated downstream acks (note_presented) mark
it ready; acks from an older sequence never unblock the current one, and the
fire gate (should_fire) runs only for the current, unsettled generation.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.cache.first_frame_gate import FIRST_PRESENT_SETTLE_COUNT

__all__ = [
    "FIRST_PRESENT_SETTLE_COUNT",
    "PresentDebt",
    "begin_source",
    "note_presented",
    "should_fire",
]


@dataclass
class PresentDebt:
    """Ledger for one source generation's outstanding presents."""

    generation: int = 0
    presented: int = 0
    pumped: bool = False
    settled: bool = False


def begin_source(debt: PresentDebt | None) -> PresentDebt:
    """Open a new generation; fail-open (never raises)."""
    try:
        if debt is None:
            old = 0
        else:
            try:
                old = int(getattr(debt, "generation", 0))
            except (TypeError, ValueError):
                old = 0
        generation = old + 1 if old >= 1 else 1
    except Exception:
        generation = 1
    return PresentDebt(generation=generation)


def note_presented(
    debt: PresentDebt, settle_count: int = FIRST_PRESENT_SETTLE_COUNT
) -> str:
    """Record one present; fail-open, never mutates generation."""
    try:
        if debt is None or not isinstance(debt, PresentDebt):
            return "waiting"
        try:
            target = int(settle_count)
        except (TypeError, ValueError):
            target = FIRST_PRESENT_SETTLE_COUNT
        if target < 1:
            target = 1
        try:
            debt.presented = int(debt.presented) + 1
        except (TypeError, ValueError):
            debt.presented = 1
        if debt.settled:
            return "settled"
        if debt.presented >= target:
            debt.settled = True
            debt.pumped = True
            return "settled"
        if not debt.pumped:
            debt.pumped = True
            return "pumped"
        return "waiting"
    except Exception:
        return "waiting"


def should_fire(timer_generation: int, debt: PresentDebt) -> bool:
    """True only for the current, unsettled generation; fail-open False."""
    try:
        if debt is None or not isinstance(debt, PresentDebt):
            return False
        if debt.settled:
            return False
        try:
            want = int(timer_generation)
        except (TypeError, ValueError):
            return False
        try:
            have = int(debt.generation)
        except (TypeError, ValueError):
            return False
        return want == have
    except Exception:
        return False
