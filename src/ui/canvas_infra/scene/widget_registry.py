from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from .widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasFeatureGestureBinding,
    CanvasFeatureProperty,
    CanvasFeatureSettingsEventBinding,
    CanvasFeatureStateCommand,
    CanvasFeatureStateQuery,
    CanvasFeatureToolbarBinding,
    CanvasWidgetFeature,
)
from resources.translations import add_i18n_root

_FEATURE_PACKAGES: list[ModuleType] = []


def register_canvas_widget_feature_package(package: ModuleType) -> None:
    if package not in _FEATURE_PACKAGES:
        _FEATURE_PACKAGES.append(package)
        _clear_feature_caches()


def _clear_feature_caches() -> None:
    get_canvas_widget_features.cache_clear()
    get_canvas_feature_properties.cache_clear()
    get_canvas_feature_commands.cache_clear()
    get_canvas_feature_command_aliases.cache_clear()
    get_canvas_feature_settings_event_bindings.cache_clear()
    get_canvas_feature_toolbar_bindings.cache_clear()
    get_canvas_feature_gesture_bindings.cache_clear()
    get_canvas_feature_toolbar_binding.cache_clear()
    get_canvas_feature_command.cache_clear()
    get_canvas_feature_command_by_alias.cache_clear()
    get_canvas_feature_commands_by_id.cache_clear()
    get_canvas_feature_state_queries.cache_clear()
    get_canvas_feature_state_commands.cache_clear()
    get_canvas_feature_i18n_namespaces.cache_clear()


@lru_cache(maxsize=1)
def get_canvas_widget_features() -> tuple[CanvasWidgetFeature, ...]:
    features: list[CanvasWidgetFeature] = []
    for features_pkg in _FEATURE_PACKAGES:
        features_path = Path(features_pkg.__path__[0])
        for module_info in sorted(pkgutil.iter_modules(features_pkg.__path__), key=lambda item: item.name):
            if module_info.name.startswith("_"):
                continue

            module = None
            try:
                module = importlib.import_module(
                    f"{features_pkg.__name__}.{module_info.name}.manifest"
                )
            except ModuleNotFoundError as exc:
                if exc.name != f"{features_pkg.__name__}.{module_info.name}.manifest":
                    raise
            if module is None:
                try:
                    module = importlib.import_module(
                        f"{features_pkg.__name__}.{module_info.name}.widget"
                    )
                except ModuleNotFoundError as exc:
                    if exc.name == f"{features_pkg.__name__}.{module_info.name}.widget":
                        continue
                    raise

            feature = getattr(module, "WIDGET_FEATURE", None)
            if isinstance(feature, CanvasWidgetFeature):
                features.append(feature)

                feature_i18n = features_path / module_info.name / "resources" / "i18n"
                if feature_i18n.is_dir():
                    add_i18n_root(feature_i18n)

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
            key=lambda item: (item.order, item.group_id or "", item.id),
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
def get_canvas_feature_command_aliases() -> dict[str, tuple[str, str]]:
    aliases: dict[str, tuple[str, str]] = {}
    for feature in get_canvas_widget_features():
        for alias in feature.command_aliases:
            if not isinstance(alias, CanvasFeatureCommandAlias):
                continue
            existing = aliases.get(alias.capability_id)
            if existing is not None and existing != (feature.name, alias.command_id):
                raise ValueError(
                    f"Canvas feature command capability '{alias.capability_id}' "
                    f"is already registered by {existing[0]}.{existing[1]}"
                )
            aliases[alias.capability_id] = (feature.name, alias.command_id)
    return aliases

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

def prepare_canvas_feature_worker_viewport(source_store, worker_viewport) -> None:
    for feature in get_canvas_widget_features():
        if feature.prepare_worker_viewport is None:
            continue
        feature.prepare_worker_viewport(source_store, worker_viewport)

def apply_canvas_feature_plan_runtime_overlays(canvas, plan) -> None:
    for feature in get_canvas_widget_features():
        if feature.apply_plan_runtime_overlay is None:
            continue
        feature.apply_plan_runtime_overlay(canvas, plan)

def apply_canvas_feature_live_runtime_overlays(store, canvas) -> bool:
    applied = False
    for feature in get_canvas_widget_features():
        if feature.apply_live_runtime_overlay is None:
            continue
        applied = bool(feature.apply_live_runtime_overlay(store, canvas)) or applied
    return applied

def has_canvas_feature_live_runtime_overlays() -> bool:
    return any(
        feature.apply_live_runtime_overlay is not None
        for feature in get_canvas_widget_features()
    )

def build_canvas_feature_render_payloads(store) -> dict[str, object]:
    payloads: dict[str, object] = {}
    for feature_name, commands in get_canvas_feature_commands().items():
        payload_command = commands.get("render.canvas_payload")
        if payload_command is None:
            continue
        payloads[feature_name] = payload_command(store)
    return payloads

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

@lru_cache(maxsize=1)
def get_canvas_feature_gesture_bindings() -> tuple[CanvasFeatureGestureBinding, ...]:
    bindings: list[CanvasFeatureGestureBinding] = []
    for feature in sorted(
        get_canvas_widget_features(),
        key=lambda item: (item.property_order, item.name),
    ):
        if feature.build_gesture_bindings is None:
            continue
        bindings.extend(feature.build_gesture_bindings())
    return tuple(sorted(bindings, key=lambda b: (b.priority, b.gesture_id)))

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

@lru_cache(maxsize=128)
def get_canvas_feature_command_by_alias(capability_id: str):
    target = get_canvas_feature_command_aliases().get(capability_id)
    if target is None:
        return None
    feature_name, command_id = target
    return get_canvas_feature_command(feature_name, command_id)

@lru_cache(maxsize=128)
def get_canvas_feature_commands_by_id(command_id: str) -> tuple[object, ...]:
    commands: list[object] = []
    for feature_commands in get_canvas_feature_commands().values():
        command = feature_commands.get(command_id)
        if command is not None:
            commands.append(command)
    return tuple(commands)

@lru_cache(maxsize=1)
def get_canvas_feature_state_queries() -> dict[str, tuple[CanvasFeatureStateQuery, ...]]:
    """Return {feature_name: tuple[CanvasFeatureStateQuery, ...]} for features."""
    queries: dict[str, tuple[CanvasFeatureStateQuery, ...]] = {}
    for feature in get_canvas_widget_features():
        if feature.build_state_queries is None:
            continue
        queries[feature.name] = tuple(feature.build_state_queries())
    return queries

@lru_cache(maxsize=1)
def get_canvas_feature_state_commands() -> dict[str, tuple[CanvasFeatureStateCommand, ...]]:
    """Return {feature_name: tuple[CanvasFeatureStateCommand, ...]} for features."""
    commands: dict[str, tuple[CanvasFeatureStateCommand, ...]] = {}
    for feature in get_canvas_widget_features():
        if feature.build_state_commands is None:
            continue
        commands[feature.name] = tuple(feature.build_state_commands())
    return commands

@lru_cache(maxsize=1)
def get_canvas_feature_i18n_namespaces() -> dict[str, str]:
    """Return {feature_name: i18n_namespace} for features that declare one."""
    return {
        feature.name: feature.i18n_namespace
        for feature in get_canvas_widget_features()
        if feature.i18n_namespace is not None
    }
