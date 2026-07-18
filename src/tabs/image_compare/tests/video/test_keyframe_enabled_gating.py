"""Per-instance keyframes do not resurrect a disabled feature; they apply only
when the feature is globally enabled.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md §Keyframing Rules.
"""

from __future__ import annotations

import pytest

from core.store import Store
from tabs.image_compare.plugins.video_editor.services.keyframing.adapters.magnifier import (
    DynamicMagnifierAdapter,
)
from tabs.image_compare.plugins.video_editor.services.keyframing.types import FrameSnapshot
from ui.canvas_infra.scene.feature_state_api import execute_feature_command


@pytest.fixture(autouse=True)
def _register_image_compare_canvas_features():
    from tabs.image_compare.tab import ImageCompareTab
    from tabs.registry import get_shared_tab_registry

    ImageCompareTab().register_canvas_features()

    # `execute_canvas_feature_alias` (used by the magnifier keyframing
    # adapter under test) goes through
    # `TabRegistry.create_service("canvas_feature_command_alias", ...)`,
    # which resolves strictly against the shared registry's active session
    # type (see docs/dev/tabs/isolation.md). `store.create_workspace_session`
    # only updates the `Store`'s own workspace bookkeeping — it never
    # touches the registry (that only happens via real UI event routing) —
    # so force the shared singleton's active tab directly for the duration
    # of each test.
    registry = get_shared_tab_registry()
    previous_active = registry._active_session_type
    registry._active_session_type = "image_compare"
    try:
        yield
    finally:
        registry._active_session_type = previous_active


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
    """QRHI_CANVAS_FEATURES.md: enabled=false gates per-instance keyframe tracks."""
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
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
    """QRHI_CANVAS_FEATURES.md: global enabled track controls per-instance track application."""
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    execute_feature_command(store, "magnifier", "add_instance")
    execute_feature_command(store, "magnifier", "toggle_enabled", True)
    snapshot = _snapshot(store)
    adapter = DynamicMagnifierAdapter()
    tool = adapter.describe_tools(snapshot)[0]
    track_ids = {track.id for track in tool.tracks}
    assert "magnifier.default.position" in track_ids
    assert "magnifier.default.offset" in track_ids

    adapter.apply_tool_values(
        snapshot,
        tool,
        {
            "magnifier.default.size": {"value": 0.8},
            "magnifier.default.offset": {"x": 0.12, "y": -0.05},
        },
    )

    model = store.viewport.view_state.canvas_widget_state["magnifier"].models["default"]
    assert model.size_relative == 0.8
    assert abs(model.offset_relative.x - 0.12) < 1e-6
    assert abs(model.offset_relative.y + 0.05) < 1e-6
