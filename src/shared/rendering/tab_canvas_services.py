"""Neutral tab-canvas service lookup helpers."""

from __future__ import annotations


def get_canvas_widget_class():
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    widget_cls = registry.create_service("canvas_widget_class")
    if widget_cls is None:
        raise RuntimeError("No tab provides a canvas widget class")
    return widget_cls


def create_canvas_widget(*args, **kwargs):
    widget_cls = get_canvas_widget_class()
    return widget_cls(*args, **kwargs)


def call_canvas_service(service_id: str, *args, **kwargs):
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    result = registry.create_service(service_id, *args, **kwargs)
    if result is None:
        raise RuntimeError(f"No tab provides canvas service: {service_id}")
    return result


def build_gl_render_scene(*args, **kwargs):
    return call_canvas_service(
        "canvas_gl_render_scene",
        *args,
        **kwargs,
    )


def reset_canvas_overlays(canvas) -> None:
    call_canvas_service("canvas_reset_overlays", canvas)
