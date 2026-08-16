"""Tests for feature state API — direct state access without aliases."""

from __future__ import annotations

import pytest

from ui.canvas_infra.scene.feature_state_api import (
    execute_feature_command,
    has_feature_command,
    has_feature_query,
    query_feature_state,
)
from ui.canvas_infra.scene.registry import get_canvas_registry
from core.store import Store


def get_canvas_feature_state_commands():
    return get_canvas_registry("image_compare").get_feature_state_commands()


def get_canvas_feature_state_queries():
    return get_canvas_registry("image_compare").get_feature_state_queries()


@pytest.fixture(autouse=True)
def _register_image_compare_canvas_features():
    from tabs.image_compare.tab import ImageCompareTab

    ImageCompareTab().register_canvas_features()


def _image_compare_store() -> Store:
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    return store

class TestFeatureStateRegistry:
    """Test that features register state queries and commands."""

    def test_magnifier_has_state_queries(self):
        """Magnifier should register state queries."""
        queries = get_canvas_feature_state_queries()
        assert "magnifier" in queries
        magnifier_queries = queries["magnifier"]
        assert len(magnifier_queries) > 0

        query_ids = {q.query_id for q in magnifier_queries}
        assert "active_state" in query_ids
        assert "all_states" in query_ids
        assert "total_count" in query_ids

    def test_magnifier_has_state_commands(self):
        """Magnifier should register state commands."""
        commands = get_canvas_feature_state_commands()
        assert "magnifier" in commands
        magnifier_commands = commands["magnifier"]
        assert len(magnifier_commands) > 0

        command_ids = {c.command_id for c in magnifier_commands}
        assert "toggle_enabled" in command_ids
        assert "set_internal_split" in command_ids
        assert "add_instance" in command_ids

class TestFeatureStateAPI:
    """Test feature state API public interface."""

    def test_has_feature_query(self):
        """Check if feature has a query."""
        assert has_feature_query("image_compare", "magnifier", "active_state") is True
        assert has_feature_query("image_compare", "magnifier", "nonexistent_query") is False
        assert has_feature_query("image_compare", "nonexistent_feature", "active_state") is False

    def test_has_feature_command(self):
        """Check if feature has a command."""
        assert has_feature_command("image_compare", "magnifier", "toggle_enabled") is True
        assert has_feature_command("image_compare", "magnifier", "nonexistent_command") is False
        assert has_feature_command("image_compare", "nonexistent_feature", "toggle_enabled") is False

    def test_query_feature_state_missing_feature(self, caplog):
        """Query on missing feature should log warning and return None."""
        result = query_feature_state(_image_compare_store(), "nonexistent_feature", "some_query")
        assert result is None
        assert "nonexistent_feature" in caplog.text

    def test_query_feature_state_missing_query(self, caplog):
        """Query on missing query should log warning and return None."""
        result = query_feature_state(_image_compare_store(), "magnifier", "nonexistent_query")
        assert result is None
        assert "nonexistent_query" in caplog.text

    def test_execute_feature_command_missing_feature(self, caplog):
        """Command on missing feature should log warning."""
        execute_feature_command(_image_compare_store(), "nonexistent_feature", "some_command")
        assert "nonexistent_feature" in caplog.text

    def test_execute_feature_command_missing_command(self, caplog):
        """Command on missing command should log warning."""
        execute_feature_command(_image_compare_store(), "magnifier", "nonexistent_command")
        assert "nonexistent_command" in caplog.text

class TestFeatureStateAPIErrorHandling:
    """Error handling in feature state API: handler exceptions are swallowed
    (logged, never propagated) and the API returns None for failed queries."""

    def test_query_handler_exception(self, caplog, monkeypatch):
        """If a registered query handler raises, the exception is logged and
        None returned — the API must not propagate handler errors."""
        from ui.canvas_infra.scene.widget_contract import CanvasFeatureStateQuery

        registry = get_canvas_registry("image_compare")

        def failing_handler(store):
            raise ValueError("Query failed")

        monkeypatch.setattr(
            registry,
            "get_feature_state_queries",
            lambda: {
                "magnifier": (
                    CanvasFeatureStateQuery(
                        query_id="active_state", handler=failing_handler
                    ),
                )
            },
        )

        result = query_feature_state(_image_compare_store(), "magnifier", "active_state")

        assert result is None
        assert "Query failed" in caplog.text

    def test_command_handler_exception(self, caplog, monkeypatch):
        """If a registered command handler raises, the exception is logged and
        execution swallowed — the API must not propagate handler errors."""
        from ui.canvas_infra.scene.widget_contract import CanvasFeatureStateCommand

        registry = get_canvas_registry("image_compare")

        def failing_handler(store):
            raise ValueError("Command failed")

        monkeypatch.setattr(
            registry,
            "get_feature_state_commands",
            lambda: {
                "magnifier": (
                    CanvasFeatureStateCommand(
                        command_id="toggle_enabled", handler=failing_handler
                    ),
                )
            },
        )

        execute_feature_command(_image_compare_store(), "magnifier", "toggle_enabled")

        assert "Command failed" in caplog.text

def test_multi_instance_feature_command_writes_canvas_widget_state():
    """QRHI_CANVAS_FEATURES.md: multi-instance feature state lives under canvas_widget_state."""
    store = _image_compare_store()

    execute_feature_command(store, "magnifier", "add_instance")
    execute_feature_command(store, "magnifier", "set_active_visibility_parts", left=False)

    state = store.viewport.view_state.canvas_widget_state["magnifier"]
    active = state.models[state.active_id]
    assert active.visible_left is False
    assert not hasattr(store.viewport.view_state, "visible_left")

def test_missing_feature_command_is_explicit_none_and_does_not_mutate(caplog):
    """QRHI_CANVAS_FEATURES.md: missing feature commands must not silently write fallback state."""
    store = _image_compare_store()
    before = dict(store.viewport.view_state.canvas_widget_state)

    result = execute_feature_command(store, "magnifier", "definitely_missing")

    assert result is None
    assert store.viewport.view_state.canvas_widget_state == before
    assert "definitely_missing" in caplog.text