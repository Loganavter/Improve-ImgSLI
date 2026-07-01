from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ImproveImgSLI")


def execute_canvas_feature_command(
    feature_name: str,
    command_id: str,
    *args: Any,
) -> Any:
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    return registry.create_service(
        "canvas_feature_command",
        feature_name,
        command_id,
        *args,
    )


def execute_canvas_feature_alias(alias: str, *args: Any) -> Any:
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    result = registry.create_service("canvas_feature_command_alias", alias, *args)
    if result is None:
        logger.warning("Canvas feature command unavailable: %s", alias)
    return result
