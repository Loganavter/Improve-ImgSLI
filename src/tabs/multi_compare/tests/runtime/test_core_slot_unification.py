"""multi_compare session state through the core Dispatcher (state-unification)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from core.session_blueprints import SessionBlueprint, SessionSlotBlueprint
from core.state_management.dispatcher import Dispatcher
from core.store import Store
from tabs.multi_compare.bootstrap_reducers import register_multi_compare_reducers
from tabs.multi_compare.models import MultiCompareDividerSettings
from tabs.multi_compare.scene.store import actions
from tabs.multi_compare.use_cases.persistence import _STATE_SLOT, _fresh_default_state


def _make_store_with_mc_session():
    register_multi_compare_reducers()
    store = Store()
    store.create_workspace_session(
        session_type="multi_compare",
        blueprint=SessionBlueprint(
            session_type="multi_compare",
            plugin_name="multi_compare",
            title="Multi Compare",
            state_slots=(
                SessionSlotBlueprint(name=_STATE_SLOT, factory=_fresh_default_state),
            ),
        ),
    )
    dispatcher = Dispatcher(store)
    store.set_dispatcher(dispatcher)
    return store, dispatcher


def test_multi_compare_state_flows_through_core_dispatcher():
    store, dispatcher = _make_store_with_mc_session()
    session = store.get_active_workspace_session()
    assert session.session_type == "multi_compare"
    assert store.get_session_state_slot(_STATE_SLOT) is not None

    dispatcher.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(1, 2, 3, 4))
        ),
        scope="multi_compare",
    )

    slot = store.get_session_state_slot(_STATE_SLOT)
    assert slot.divider_settings.color_rgba == (1, 2, 3, 4)
    assert session.state_slots[_STATE_SLOT] is slot, "active session re-pointed to new slot"


def test_ic_action_does_not_touch_multi_compare_slot():
    from core.state_management.actions import SetSplitPositionAction

    store, dispatcher = _make_store_with_mc_session()
    before = store.get_session_state_slot(_STATE_SLOT)

    dispatcher.dispatch(SetSplitPositionAction(0.5))

    assert store.get_session_state_slot(_STATE_SLOT) is before


def test_multi_compare_undo_redo_through_core_dispatcher(monkeypatch):
    # These tests target undo/redo mechanics, not burst grouping — disable
    # the rapid-same-type window so the two dispatches stay separate steps.
    from core.state_management import dispatcher as _dispatcher_module

    monkeypatch.setattr(_dispatcher_module, "_RAPID_ACTION_GROUP_MS", 0)
    store, dispatcher = _make_store_with_mc_session()

    dispatcher.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(1, 2, 3, 4))
        ),
        scope="multi_compare",
    )
    assert store.get_session_state_slot(_STATE_SLOT).divider_settings.color_rgba == (1, 2, 3, 4)

    dispatcher.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(5, 6, 7, 8))
        ),
        scope="multi_compare",
    )
    assert store.get_session_state_slot(_STATE_SLOT).divider_settings.color_rgba == (5, 6, 7, 8)

    assert dispatcher.can_undo()
    dispatcher.undo()
    assert store.get_session_state_slot(_STATE_SLOT).divider_settings.color_rgba == (1, 2, 3, 4)

    assert dispatcher.can_redo()
    dispatcher.redo()
    assert store.get_session_state_slot(_STATE_SLOT).divider_settings.color_rgba == (5, 6, 7, 8)


def test_undo_notifies_bound_facade_subscribers(monkeypatch):
    from core.state_management import dispatcher as _dispatcher_module

    monkeypatch.setattr(_dispatcher_module, "_RAPID_ACTION_GROUP_MS", 0)
    """Undo/redo emit core scope "viewport"; the bound facade must still notify
    its subscribers (so the canvas repaints the restored slot). Regression for
    "undo doesn't work in Multi Compare"."""
    from tabs.multi_compare.scene.store import MultiCompareStore

    store, dispatcher = _make_store_with_mc_session()
    facade = MultiCompareStore(core_store=store)
    seen: list[tuple] = []
    facade.subscribe(lambda action, state: seen.append((action.type, state.divider_settings.color_rgba)))

    facade.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(1, 2, 3, 4))
        )
    )
    facade.dispatch(
        actions.set_divider_settings(
            MultiCompareDividerSettings(visible=True, thickness=4, color_rgba=(5, 6, 7, 8))
        )
    )
    assert seen == [
        ("multi_compare/set_divider_settings", (1, 2, 3, 4)),
        ("multi_compare/set_divider_settings", (5, 6, 7, 8)),
    ]

    seen.clear()
    dispatcher.undo()
    assert seen == [("multi_compare/replace_state", (1, 2, 3, 4))], (
        "undo must notify subscribers with the restored state (synthetic action)"
    )

    seen.clear()
    dispatcher.redo()
    assert seen == [("multi_compare/replace_state", (5, 6, 7, 8))]


def test_focus_toggle_through_core_dispatcher():
    """Enter/exit single-image focus through the real core Dispatcher: the
    slot's focused_slot_id flips and the bound facade notifies each way."""
    from tabs.multi_compare.scene.store import MultiCompareStore

    store, dispatcher = _make_store_with_mc_session()
    facade = MultiCompareStore(core_store=store)
    seen: list[tuple] = []
    facade.subscribe(lambda action, state: seen.append((action.type, state.focused_slot_id)))

    facade.dispatch(actions.set_focus(3))
    assert store.get_session_state_slot(_STATE_SLOT).focused_slot_id == 3
    assert seen == [("multi_compare/set_focus", 3)]

    seen.clear()
    facade.dispatch(actions.set_focus(None))
    assert store.get_session_state_slot(_STATE_SLOT).focused_slot_id is None
    assert seen == [("multi_compare/set_focus", None)]


def test_remove_slot_undo_keeps_store_open(tmp_path):
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    store, dispatcher = _make_store_with_mc_session()

    store1 = TiledPixelStore.from_pil(
        Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA"),
        tmp_dir=str(tmp_path),
    )
    store2 = TiledPixelStore.from_pil(
        Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA"),
        tmp_dir=str(tmp_path),
    )

    dispatcher.dispatch(
        actions.add_slot(__import__("pathlib").Path("a.png"), store1, "A"),
        scope="multi_compare",
    )
    dispatcher.dispatch(
        actions.add_slot(__import__("pathlib").Path("b.png"), store2, "B"),
        scope="multi_compare",
    )
    slot_b = None
    for slot in store.get_session_state_slot(_STATE_SLOT).slots:
        if slot.image is store2:
            slot_b = slot
    assert slot_b is not None
    slot_b_id = slot_b.id

    dispatcher.dispatch(actions.remove_slot(slot_b_id), scope="multi_compare")
    assert store2.is_open, "removed slot store stays open (deferred closing)"

    dispatcher.undo()
    restored = store.get_session_state_slot(_STATE_SLOT)
    restored_b = [s for s in restored.slots if s.id == slot_b_id][0]
    assert restored_b.image is store2, "undo restores the same store reference"
    assert restored_b.image.is_open, "restored store is still open and usable"