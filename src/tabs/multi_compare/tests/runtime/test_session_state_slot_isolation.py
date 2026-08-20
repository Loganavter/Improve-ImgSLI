"""multi_compare's own per-session state-slot isolation on session switch."""

from __future__ import annotations

from tabs.multi_compare.models import (
    DEFAULT_DIVIDER_COLOR_RGBA,
    MultiCompareDividerSettings,
)
from tabs.multi_compare.scene.store import MultiCompareStore, actions
from tabs.multi_compare.use_cases.persistence import _STATE_SLOT
from tabs.multi_compare.tests.runtime._session_harness import FakeCoreStore


def test_switch_same_type_snapshots_do_not_cross_contaminate(qapp):
    """Switch A→B→A→B: each session slot keeps its own divider color.

    With the bound facade, the session slot is the single source of truth: a
    dispatch writes the active session's slot (via the core Dispatcher), and
    ``state`` reads whichever session is active.
    """
    core = FakeCoreStore(["a", "b"])
    core.ensure_slot("a")
    core.ensure_slot("b")
    store = MultiCompareStore(core_store=core)

    core.switch_active("a")
    store.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(10, 20, 30, 40))
        )
    )
    assert core.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    core.switch_active("b")
    assert store.state.divider_settings.color_rgba == DEFAULT_DIVIDER_COLOR_RGBA
    assert core.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    store.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(1, 2, 3, 4))
        )
    )
    assert core.sessions["b"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )
    assert core.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    core.switch_active("a")
    assert store.state.divider_settings.color_rgba == (10, 20, 30, 40)
    core.switch_active("b")
    assert store.state.divider_settings.color_rgba == (1, 2, 3, 4)