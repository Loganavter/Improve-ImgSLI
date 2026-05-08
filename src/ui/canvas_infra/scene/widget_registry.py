from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

from .widget_contract import (
    CanvasFeatureProperty,
    CanvasFeatureSettingsEventBinding,
    CanvasFeatureToolbarBinding,
    CanvasWidgetFeature,
)
import ui.canvas_features as features_pkg

@lru_cache(maxsize=1)
def get_canvas_widget_features() -> tuple[CanvasWidgetFeature, ...]:
    features: list[CanvasWidgetFeature] = []
    for module_info in sorted(pkgutil.iter_modules(features_pkg.__path__), key=lambda item: item.name):
        try:
            module = importlib.import_module(f"{features_pkg.__name__}.{module_info.name}.widget")
        except ModuleNotFoundError as exc:
            if exc.name == f"{features_pkg.__name__}.{module_info.name}.widget":
                continue
            raise
        feature = getattr(module, "WIDGET_FEATURE", None)
        if isinstance(feature, CanvasWidgetFeature):
            features.append(feature)
    return tuple(features)

@lru_cache(maxsize=1)
def get_canvas_feature_properties() -> tuple[CanvasFeatureProperty, ...]:
    properties: list[CanvasFeatureProperty] = []
    for feature in sorted(
        get_canvas_widget_features(),
        key=lambda item: (item.property_order, item.name),
    ):
        if feature.build_properties is None:
            continue
        properties.extend(feature.build_properties())
    return tuple(
        sorted(
            properties,
            key=lambda item: (item.order, item.group_id, item.id),
        )
    )

@lru_cache(maxsize=1)
def get_canvas_feature_commands() -> dict[str, dict[str, object]]:
    commands: dict[str, dict[str, object]] = {}
    for feature in get_canvas_widget_features():
        if feature.build_commands is None:
            continue
        commands[feature.name] = dict(feature.build_commands())
    return commands

@lru_cache(maxsize=1)
def get_canvas_feature_settings_event_bindings() -> dict[str, tuple[CanvasFeatureSettingsEventBinding, ...]]:
    bindings: dict[str, tuple[CanvasFeatureSettingsEventBinding, ...]] = {}
    for feature in get_canvas_widget_features():
        if feature.build_settings_event_bindings is None:
            continue
        bindings[feature.name] = tuple(feature.build_settings_event_bindings())
    return bindings

def build_canvas_feature_render_scene_overrides(store) -> dict[str, object]:
    overrides: dict[str, object] = {}
    for feature in get_canvas_widget_features():
        if feature.build_render_scene_overrides is None:
            continue
        overrides.update(feature.build_render_scene_overrides(store))
    return overrides

@lru_cache(maxsize=1)
def get_canvas_feature_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    bindings: list[CanvasFeatureToolbarBinding] = []
    for feature in sorted(
        get_canvas_widget_features(),
        key=lambda item: (item.property_order, item.name),
    ):
        if feature.build_toolbar_bindings is None:
            continue
        bindings.extend(feature.build_toolbar_bindings())
    return tuple(sorted(bindings, key=lambda item: item.control_id))

@lru_cache(maxsize=32)
def get_canvas_feature_toolbar_binding(
    control_id: str,
) -> CanvasFeatureToolbarBinding | None:
    for binding in get_canvas_feature_toolbar_bindings():
        if binding.control_id == control_id:
            return binding
    return None

@lru_cache(maxsize=128)
def get_canvas_feature_command(
    feature_name: str,
    command_id: str,
):
    return get_canvas_feature_commands().get(feature_name, {}).get(command_id)
