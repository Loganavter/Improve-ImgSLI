"""Reducers return new state, never mutate the previous store, and do no I/O.

Dogma source: docs/dev/ARCHITECTURE.md §State Model.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass

from core.state_management.reducers import RootReducer
from core.state_management.viewport_actions import SetDiffModeAction, SetSplitPositionAction
from core.store import Store
from domain.types import Point
from tabs.image_compare.canvas.features.divider.actions import SetDividerThicknessAction
from tabs.image_compare.canvas.features.guides.actions import SetGuidesThicknessAction
from tabs.image_compare.canvas.features.magnifier.actions import (
    SetMagnifierPositionAction,
    ToggleMagnifierAction,
)


def _image_compare_store() -> Store:
    from tabs.image_compare.tab import ImageCompareTab

    ImageCompareTab().register_canvas_features()
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    return store


def _snapshot(value):
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__slots__"):
        return {
            slot: _snapshot(getattr(value, slot))
            for slot in value.__slots__
            if hasattr(value, slot)
        }
    if isinstance(value, dict):
        return {key: _snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_snapshot(item) for item in value)
    if isinstance(value, set):
        return set(value)
    return deepcopy(value)

def test_root_reducer_does_not_mutate_previous_store_for_representative_actions():
    """ARCHITECTURE.md: reducers return new state and leave previous state untouched."""
    cases = [
        (SetDiffModeAction("highlight"), None),
        (SetSplitPositionAction(0.25), None),
        (SetDividerThicknessAction(5), None),
        (SetGuidesThicknessAction(4), None),
        (ToggleMagnifierAction(True), None),
        (
            SetMagnifierPositionAction(Point(0.25, 0.75)),
            lambda store: setattr(
                store,
                "viewport",
                RootReducer().reduce(store, ToggleMagnifierAction(True)).viewport,
            ),
        ),
    ]

    for action, prepare in cases:
        reducer = RootReducer()
        old_store = _image_compare_store()
        if prepare is not None:
            prepare(old_store)
        before = {
            "viewport": _snapshot(old_store.viewport),
            "document": _snapshot(old_store.document),
            "settings": _snapshot(old_store.settings),
        }

        new_store = reducer.reduce(old_store, action)

        assert new_store is not old_store
        assert _snapshot(old_store.viewport) == before["viewport"]
        assert _snapshot(old_store.document) == before["document"]
        assert _snapshot(old_store.settings) == before["settings"]

def test_reducers_do_not_access_io(monkeypatch):
    """ARCHITECTURE.md: reducers are pure state transforms without I/O side effects."""
    def _blocked_open(*_args, **_kwargs):
        raise AssertionError("reducers must not open files")

    monkeypatch.setattr("builtins.open", _blocked_open)

    reducer = RootReducer()
    old_store = _image_compare_store()
    new_store = reducer.reduce(old_store, SetDiffModeAction("ssim"))

    assert new_store.viewport.view_state.diff_mode == "ssim"
