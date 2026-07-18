from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from resources.translations import add_i18n_root

from .feature_contract import CanvasSceneFeature
from .pass_contract import CanvasRenderPass, CanvasRenderPassBase
from .widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasFeatureContextMenuZone,
    CanvasFeatureGestureBinding,
    CanvasFeatureProperty,
    CanvasFeatureSettingsEventBinding,
    CanvasFeatureStateCommand,
    CanvasFeatureStateQuery,
    CanvasFeatureToolbarBinding,
    CanvasWidgetFeature,
)


class CanvasFeatureRegistry:
    """Auto-discovers and serves canvas features for a single tab type.

    One instance exists per tab type, not per open session/document —
    feature *packages* are registered once at tab startup. See
    docs/dev/CANVAS_FEATURE_REGISTRY_PER_TAB.md.
    """

    def __init__(self, tab_type: str) -> None:
        self.tab_type = tab_type
        self._packages: list[ModuleType] = []

    def register_package(self, package: ModuleType) -> None:
        if package not in self._packages:
            self._packages.append(package)
            self._clear_caches()

    def _clear_caches(self) -> None:
        self.get_widget_features.cache_clear()
        self.get_scene_features.cache_clear()
        self.get_render_pass_bases.cache_clear()
        self.get_render_passes.cache_clear()
        self.get_feature_properties.cache_clear()
        self.get_feature_commands.cache_clear()
        self.get_feature_command_aliases.cache_clear()
        self.get_feature_settings_event_bindings.cache_clear()
        self.get_feature_toolbar_bindings.cache_clear()
        self.get_feature_gesture_bindings.cache_clear()
        self.get_feature_context_menu_zones.cache_clear()
        self.get_feature_toolbar_binding.cache_clear()
        self.get_feature_command.cache_clear()
        self.get_feature_command_by_alias.cache_clear()
        self.get_feature_commands_by_id.cache_clear()
        self.get_feature_state_queries.cache_clear()
        self.get_feature_state_commands.cache_clear()
        self.get_feature_i18n_namespaces.cache_clear()

    def _iter_feature_modules(self, module_name: str):
        for features_pkg in self._packages:
            for module_info in sorted(
                pkgutil.iter_modules(features_pkg.__path__), key=lambda item: item.name
            ):
                if module_info.name.startswith("_"):
                    continue
                try:
                    module = importlib.import_module(
                        f"{features_pkg.__name__}.{module_info.name}.{module_name}"
                    )
                except ModuleNotFoundError:
                    continue
                yield features_pkg, module_info, module

    # -- widget features -------------------------------------------------

    @lru_cache(maxsize=1)
    def get_widget_features(self) -> tuple[CanvasWidgetFeature, ...]:
        features: list[CanvasWidgetFeature] = []
        for features_pkg in self._packages:
            features_path = Path(features_pkg.__path__[0])
            for module_info in sorted(
                pkgutil.iter_modules(features_pkg.__path__), key=lambda item: item.name
            ):
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
    def get_feature_properties(self) -> tuple[CanvasFeatureProperty, ...]:
        properties: list[CanvasFeatureProperty] = []
        for feature in sorted(
            self.get_widget_features(),
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
    def get_feature_commands(self) -> dict[str, dict[str, object]]:
        commands: dict[str, dict[str, object]] = {}
        for feature in self.get_widget_features():
            if feature.build_commands is None:
                continue
            commands[feature.name] = dict(feature.build_commands())
        return commands

    @lru_cache(maxsize=1)
    def get_feature_command_aliases(self) -> dict[str, tuple[str, str]]:
        aliases: dict[str, tuple[str, str]] = {}
        for feature in self.get_widget_features():
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
    def get_feature_settings_event_bindings(
        self,
    ) -> dict[str, tuple[CanvasFeatureSettingsEventBinding, ...]]:
        bindings: dict[str, tuple[CanvasFeatureSettingsEventBinding, ...]] = {}
        for feature in self.get_widget_features():
            if feature.build_settings_event_bindings is None:
                continue
            bindings[feature.name] = tuple(feature.build_settings_event_bindings())
        return bindings

    def build_feature_render_scene_overrides(self, store) -> dict[str, object]:
        overrides: dict[str, object] = {}
        for feature in self.get_widget_features():
            if feature.build_render_scene_overrides is None:
                continue
            overrides.update(feature.build_render_scene_overrides(store))
        return overrides

    def prepare_feature_worker_viewport(self, source_store, worker_viewport) -> None:
        for feature in self.get_widget_features():
            if feature.prepare_worker_viewport is None:
                continue
            feature.prepare_worker_viewport(source_store, worker_viewport)

    def apply_feature_plan_runtime_overlays(self, canvas, plan) -> None:
        for feature in self.get_widget_features():
            if feature.apply_plan_runtime_overlay is None:
                continue
            feature.apply_plan_runtime_overlay(canvas, plan)

    def apply_feature_live_runtime_overlays(self, store, canvas) -> bool:
        applied = False
        for feature in self.get_widget_features():
            if feature.apply_live_runtime_overlay is None:
                continue
            applied = bool(feature.apply_live_runtime_overlay(store, canvas)) or applied
        return applied

    def has_feature_live_runtime_overlays(self) -> bool:
        return any(
            feature.apply_live_runtime_overlay is not None
            for feature in self.get_widget_features()
        )

    def build_feature_render_payloads(self, store) -> dict[str, object]:
        payloads: dict[str, object] = {}
        for feature_name, commands in self.get_feature_commands().items():
            payload_command = commands.get("render.canvas_payload")
            if payload_command is None:
                continue
            payloads[feature_name] = payload_command(store)
        return payloads

    @lru_cache(maxsize=1)
    def get_feature_toolbar_bindings(self) -> tuple[CanvasFeatureToolbarBinding, ...]:
        bindings: list[CanvasFeatureToolbarBinding] = []
        for feature in sorted(
            self.get_widget_features(),
            key=lambda item: (item.property_order, item.name),
        ):
            if feature.build_toolbar_bindings is None:
                continue
            bindings.extend(feature.build_toolbar_bindings())
        return tuple(sorted(bindings, key=lambda item: item.control_id))

    @lru_cache(maxsize=1)
    def get_feature_gesture_bindings(self) -> tuple[CanvasFeatureGestureBinding, ...]:
        bindings: list[CanvasFeatureGestureBinding] = []
        for feature in sorted(
            self.get_widget_features(),
            key=lambda item: (item.property_order, item.name),
        ):
            if feature.build_gesture_bindings is None:
                continue
            bindings.extend(feature.build_gesture_bindings())
        return tuple(sorted(bindings, key=lambda b: (b.priority, b.gesture_id)))

    @lru_cache(maxsize=1)
    def get_feature_context_menu_zones(
        self,
    ) -> tuple[CanvasFeatureContextMenuZone, ...]:
        zones: list[CanvasFeatureContextMenuZone] = []
        for feature in sorted(
            self.get_widget_features(),
            key=lambda item: (item.property_order, item.name),
        ):
            if feature.build_context_menu_zones is None:
                continue
            zones.extend(feature.build_context_menu_zones())
        return tuple(sorted(zones, key=lambda z: (z.priority, z.zone_id)))

    @lru_cache(maxsize=32)
    def get_feature_toolbar_binding(
        self, control_id: str
    ) -> CanvasFeatureToolbarBinding | None:
        for binding in self.get_feature_toolbar_bindings():
            if binding.control_id == control_id:
                return binding
        return None

    @lru_cache(maxsize=128)
    def get_feature_command(self, feature_name: str, command_id: str):
        return self.get_feature_commands().get(feature_name, {}).get(command_id)

    @lru_cache(maxsize=128)
    def get_feature_command_by_alias(self, capability_id: str):
        target = self.get_feature_command_aliases().get(capability_id)
        if target is None:
            return None
        feature_name, command_id = target
        return self.get_feature_command(feature_name, command_id)

    @lru_cache(maxsize=128)
    def get_feature_commands_by_id(self, command_id: str) -> tuple[object, ...]:
        commands: list[object] = []
        for feature_commands in self.get_feature_commands().values():
            command = feature_commands.get(command_id)
            if command is not None:
                commands.append(command)
        return tuple(commands)

    @lru_cache(maxsize=1)
    def get_feature_state_queries(self) -> dict[str, tuple[CanvasFeatureStateQuery, ...]]:
        queries: dict[str, tuple[CanvasFeatureStateQuery, ...]] = {}
        for feature in self.get_widget_features():
            if feature.build_state_queries is None:
                continue
            queries[feature.name] = tuple(feature.build_state_queries())
        return queries

    @lru_cache(maxsize=1)
    def get_feature_state_commands(self) -> dict[str, tuple[CanvasFeatureStateCommand, ...]]:
        commands: dict[str, tuple[CanvasFeatureStateCommand, ...]] = {}
        for feature in self.get_widget_features():
            if feature.build_state_commands is None:
                continue
            commands[feature.name] = tuple(feature.build_state_commands())
        return commands

    @lru_cache(maxsize=1)
    def get_feature_i18n_namespaces(self) -> dict[str, str]:
        return {
            feature.name: feature.i18n_namespace
            for feature in self.get_widget_features()
            if feature.i18n_namespace is not None
        }

    # -- scene features ----------------------------------------------------

    @lru_cache(maxsize=1)
    def get_scene_features(self) -> tuple[CanvasSceneFeature, ...]:
        features: list[CanvasSceneFeature] = []
        for _pkg, _module_info, feature in self._iter_manifest_or(
            "feature", "FEATURE", CanvasSceneFeature
        ):
            features.append(feature)
        return tuple(features)

    def _iter_manifest_or(self, fallback_name: str, attr: str, expected_type: type):
        for features_pkg in self._packages:
            for module_info in sorted(
                pkgutil.iter_modules(features_pkg.__path__), key=lambda item: item.name
            ):
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
                            f"{features_pkg.__name__}.{module_info.name}.{fallback_name}"
                        )
                    except ModuleNotFoundError as exc:
                        if exc.name == f"{features_pkg.__name__}.{module_info.name}.{fallback_name}":
                            continue
                        raise
                value = getattr(module, attr, None)
                if isinstance(value, expected_type):
                    yield features_pkg, module_info, value

    # -- render passes -------------------------------------------------

    @lru_cache(maxsize=1)
    def get_render_pass_bases(self) -> tuple[CanvasRenderPassBase, ...]:
        """Return all discovered feature render passes (any port stage)."""
        passes: list[CanvasRenderPassBase] = []
        for _features_pkg, _module_info, module in self._iter_feature_modules("passes"):
            feature_passes = getattr(module, "RENDER_PASSES", None)
            if isinstance(feature_passes, (list, tuple)):
                passes.extend(feature_passes)
        return tuple(passes)

    @lru_cache(maxsize=1)
    def get_render_passes(self) -> tuple[CanvasRenderPass, ...]:
        """Return feature passes that have completed their QRhi port."""
        passes: list[CanvasRenderPass] = []
        for _features_pkg, _module_info, module in self._iter_feature_modules("passes"):
            feature_passes = getattr(module, "RENDER_PASSES", None)
            if isinstance(feature_passes, (list, tuple)):
                passes.extend(feature_passes)
        return tuple(passes)


_REGISTRIES: dict[str, CanvasFeatureRegistry] = {}


def get_canvas_registry(tab_type: str) -> CanvasFeatureRegistry:
    registry = _REGISTRIES.get(tab_type)
    if registry is None:
        registry = CanvasFeatureRegistry(tab_type)
        _REGISTRIES[tab_type] = registry
    return registry


def register_canvas_feature_package(tab_type: str, package: ModuleType) -> None:
    get_canvas_registry(tab_type).register_package(package)
