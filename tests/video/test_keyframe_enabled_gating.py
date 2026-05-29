"""Per-instance keyframes do not resurrect a disabled feature; they apply only
when the feature is globally enabled.

Dogma source: docs/dev/CANVAS_FEATURES.md §Keyframing Rules.
"""

from __future__ import annotations

from core.store import Store
from plugins.video_editor.services.keyframing.adapters.magnifier import (
    DynamicMagnifierAdapter,
)
from plugins.video_editor.services.keyframing.types import FrameSnapshot
from ui.canvas_infra.scene.feature_state_api import execute_feature_command


def _snapshot(store: Store) -> FrameSnapshot:
    return FrameSnapshot(
        timestamp=0.0,
        viewport_state=store.viewport,
        settings_state=store.settings,
        image1_path=None,
        image2_path=None,
        name1=None,
        name2=None,
    )


def test_magnifier_per_instance_keyframes_do_not_resurrect_disabled_feature():
    """CANVAS_FEATURES.md: enabled=false gates per-instance keyframe tracks."""
    store = Store()
    execute_feature_command(store, "magnifier", "add_instance")
    execute_feature_command(store, "magnifier", "toggle_enabled", False)
    snapshot = _snapshot(store)
    adapter = DynamicMagnifierAdapter()
    tool = adapter.describe_tools(snapshot)[0]

    adapter.apply_tool_values(
        snapshot,
        tool,
        {"magnifier.default.size": {"value": 0.8}},
    )

    model = store.viewport.view_state.canvas_widget_state["magnifier"].models["default"]
    assert model.size_relative != 0.8
    assert store.viewport.view_state.canvas_widget_state["magnifier"].enabled is False


def test_magnifier_per_instance_keyframes_apply_when_globally_enabled():
    """CANVAS_FEATURES.md: global enabled track controls per-instance track application."""
    store = Store()
    execute_feature_command(store, "magnifier", "add_instance")
    execute_feature_command(store, "magnifier", "toggle_enabled", True)
    snapshot = _snapshot(store)
    adapter = DynamicMagnifierAdapter()
    tool = adapter.describe_tools(snapshot)[0]

    adapter.apply_tool_values(
        snapshot,
        tool,
        {"magnifier.default.size": {"value": 0.8}},
    )

    model = store.viewport.view_state.canvas_widget_state["magnifier"].models["default"]
    assert model.size_relative == 0.8
