"""Neutral tab-canvas service lookup helpers."""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


def get_canvas_widget_class():
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    widget_cls = registry.create_service("canvas_widget_class")
    if widget_cls is None:
        # Expected for non-canvas tabs (session_picker) — don't log per call.
        return None
    return widget_cls


def create_canvas_widget(*args, **kwargs):
    widget_cls = get_canvas_widget_class()
    if widget_cls is None:
        logger.debug("create_canvas_widget skipped: no canvas provider for active tab")
        return None
    return widget_cls(*args, **kwargs)


def call_canvas_service(service_id: str, *args, **kwargs):
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    result = registry.create_service(service_id, *args, **kwargs)
    if result is None:
        # Expected for tabs without that canvas capability — silent degrade.
        return None
    return result


def build_render_scene(*args, **kwargs):
    result = call_canvas_service(
        "canvas_render_scene",
        *args,
        **kwargs,
    )
    if result is None:
        logger.debug("build_render_scene skipped: no provider for active tab")
        return None
    return result


def reset_canvas_overlays(canvas) -> None:
    result = call_canvas_service("canvas_reset_overlays", canvas)
    if result is None:
        logger.debug("reset_canvas_overlays skipped: no provider for active tab")
        return None
    return result