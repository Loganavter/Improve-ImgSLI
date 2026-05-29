"""Tests for feature state API — direct state access without aliases."""

from __future__ import annotations

import pytest

from ui.canvas_infra.scene.feature_state_api import (
    execute_feature_command,
    has_feature_command,
    has_feature_query,
    query_feature_state,
)
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_state_commands,
    get_canvas_feature_state_queries,
)
from core.store import Store

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
        assert has_feature_query("magnifier", "active_state") is True
        assert has_feature_query("magnifier", "nonexistent_query") is False
        assert has_feature_query("nonexistent_feature", "active_state") is False

    def test_has_feature_command(self):
        """Check if feature has a command."""
        assert has_feature_command("magnifier", "toggle_enabled") is True
        assert has_feature_command("magnifier", "nonexistent_command") is False
        assert has_feature_command("nonexistent_feature", "toggle_enabled") is False

    def test_query_feature_state_missing_feature(self, caplog):
        """Query on missing feature should log warning and return None."""
        result = query_feature_state(None, "nonexistent_feature", "some_query")
        assert result is None
        assert "nonexistent_feature" in caplog.text

    def test_query_feature_state_missing_query(self, caplog):
        """Query on missing query should log warning and return None."""
        result = query_feature_state(None, "magnifier", "nonexistent_query")
        assert result is None
        assert "nonexistent_query" in caplog.text

    def test_execute_feature_command_missing_feature(self, caplog):
        """Command on missing feature should log warning."""
        execute_feature_command(None, "nonexistent_feature", "some_command")
        assert "nonexistent_feature" in caplog.text

    def test_execute_feature_command_missing_command(self, caplog):
        """Command on missing command should log warning."""
        execute_feature_command(None, "magnifier", "nonexistent_command")
        assert "nonexistent_command" in caplog.text

class TestFeatureStateAPIErrorHandling:
    """Test error handling in feature state API."""

    def test_query_handler_exception(self, caplog):
        """If query handler raises, exception should be logged and None returned."""

        def failing_query(store):
            raise ValueError("Query failed")

        result = query_feature_state(None, "magnifier", "active_state")

    def test_command_handler_exception(self, caplog):
        """If command handler raises, exception should be logged."""

        def failing_command(store):
            raise ValueError("Command failed")

        execute_feature_command(None, "magnifier", "toggle_enabled")


def test_multi_instance_feature_command_writes_canvas_widget_state():
    """CANVAS_FEATURES.md: multi-instance feature state lives under canvas_widget_state."""
    store = Store()

    execute_feature_command(store, "magnifier", "add_instance")
    execute_feature_command(store, "magnifier", "set_active_visibility_parts", left=False)

    state = store.viewport.view_state.canvas_widget_state["magnifier"]
    active = state.models[state.active_id]
    assert active.visible_left is False
    assert not hasattr(store.viewport.view_state, "visible_left")


def test_missing_feature_command_is_explicit_none_and_does_not_mutate(caplog):
    """CANVAS_FEATURES.md: missing feature commands must not silently write fallback state."""
    store = Store()
    before = dict(store.viewport.view_state.canvas_widget_state)

    result = execute_feature_command(store, "magnifier", "definitely_missing")

    assert result is None
    assert store.viewport.view_state.canvas_widget_state == before
    assert "definitely_missing" in caplog.text
