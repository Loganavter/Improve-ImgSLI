from __future__ import annotations

from typing import Any


def execute_canvas_feature_alias(alias: str, *args: Any, default=None, **kwargs: Any):
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    result = registry.create_service(
        "canvas_feature_command_alias",
        alias,
        *args,
        **kwargs,
    )
    return default if result is None else result
