"""Public API for direct feature state access without aliases."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass

_log = logging.getLogger("ImproveImgSLI.canvas.feature_state")


def query_feature_state(
    store: Any,
    feature_name: str,
    query_id: str,
    *args,
    **kwargs,
) -> Any:
    """Query feature state directly.

    Args:
        store: Application store
        feature_name: Name of the feature (e.g., "magnifier", "divider")
        query_id: Query identifier (e.g., "active_state", "all_states")
        *args, **kwargs: Arguments passed to the query handler

    Returns:
        Query result or None if feature/query not found

    Example:
        state = query_feature_state(store, "magnifier", "active_state")
    """
    from .widget_registry import get_canvas_feature_state_queries

    queries = get_canvas_feature_state_queries()
    feature_queries = queries.get(feature_name)
    if feature_queries is None:
        _log.warning(
            "Feature '%s' has no registered queries. Available features: %s",
            feature_name,
            tuple(queries.keys()),
        )
        return None

    for query in feature_queries:
        if query.query_id == query_id:
            try:
                return query.handler(store, *args, **kwargs)
            except Exception as exc:
                _log.exception(
                    "Error executing query '%s.%s': %s",
                    feature_name,
                    query_id,
                    exc,
                )
                return None

    available_queries = tuple(q.query_id for q in feature_queries)
    _log.warning(
        "Query '%s.%s' not found. Available: %s",
        feature_name,
        query_id,
        available_queries,
    )
    return None


def execute_feature_command(
    store: Any,
    feature_name: str,
    command_id: str,
    *args,
    **kwargs,
) -> None:
    """Execute feature command directly.

    Args:
        store: Application store
        feature_name: Name of the feature (e.g., "magnifier", "divider")
        command_id: Command identifier (e.g., "set_internal_split", "set_freeze")
        *args, **kwargs: Arguments passed to the command handler

    Raises:
        ValueError: If feature or command not found and strict=True

    Example:
        execute_feature_command(store, "magnifier", "set_internal_split", 0.5)
    """
    from .widget_registry import get_canvas_feature_state_commands

    commands = get_canvas_feature_state_commands()
    feature_commands = commands.get(feature_name)
    if feature_commands is None:
        _log.warning(
            "Feature '%s' has no registered commands. Available features: %s",
            feature_name,
            tuple(commands.keys()),
        )
        return

    for command in feature_commands:
        if command.command_id == command_id:
            try:
                command.handler(store, *args, **kwargs)
                return
            except Exception as exc:
                _log.exception(
                    "Error executing command '%s.%s': %s",
                    feature_name,
                    command_id,
                    exc,
                )
                return

    available_commands = tuple(c.command_id for c in feature_commands)
    _log.warning(
        "Command '%s.%s' not found. Available: %s",
        feature_name,
        command_id,
        available_commands,
    )


def has_feature_command(
    feature_name: str,
    command_id: str,
) -> bool:
    """Check if feature has a specific command."""
    from .widget_registry import get_canvas_feature_state_commands

    commands = get_canvas_feature_state_commands()
    feature_commands = commands.get(feature_name)
    if feature_commands is None:
        return False

    return any(c.command_id == command_id for c in feature_commands)


def has_feature_query(
    feature_name: str,
    query_id: str,
) -> bool:
    """Check if feature has a specific query."""
    from .widget_registry import get_canvas_feature_state_queries

    queries = get_canvas_feature_state_queries()
    feature_queries = queries.get(feature_name)
    if feature_queries is None:
        return False

    return any(q.query_id == query_id for q in feature_queries)
