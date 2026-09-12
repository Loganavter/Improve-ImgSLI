from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ImproveImgSLI")


def execute_canvas_feature_command(
    feature_name: str,
    command_id: str,
    *args: Any,
) -> Any:
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    return registry.create_service(
        "canvas_feature_command",
        feature_name,
        command_id,
        *args,
    )


def execute_canvas_feature_alias(alias: str, *args: Any) -> Any:
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    result = registry.create_service("canvas_feature_command_alias", alias, *args)
    if result is None:
        # Callers often probe optional aliases — degrade silently, don't warn per call.
        logger.debug("Canvas feature alias not provided: %s", alias)
    return result
