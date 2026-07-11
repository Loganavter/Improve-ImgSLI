"""Tests for feature onboarding path (Phase 6).

Verifies that:
- auto-discovery works without central registration
- _template is excluded from production discovery
- all discovered features have required contracts
- adding a new feature is purely local
"""

from __future__ import annotations

import os
import pytest

SRC = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, os.pardir)
FEATURES_DIR = os.path.join(SRC, "tabs", "image_compare", "canvas", "features")

class TestAutoDiscovery:

    def test_template_excluded_from_widget_features(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry

        registry = get_canvas_registry("image_compare")
        registry.get_widget_features.cache_clear()
        names = [f.name for f in registry.get_widget_features()]
        assert "_template" not in names

    def test_template_excluded_from_scene_features(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry

        registry = get_canvas_registry("image_compare")
        registry.get_scene_features.cache_clear()
        names = [f.name for f in registry.get_scene_features()]
        assert "_template" not in names

    def test_template_excluded_from_render_passes(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry

        registry = get_canvas_registry("image_compare")
        registry.get_render_passes.cache_clear()
        passes = registry.get_render_passes()

        for p in passes:
            assert "_template" not in type(p).__module__

    def test_all_production_features_discovered(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry

        registry = get_canvas_registry("image_compare")
        registry.get_widget_features.cache_clear()
        names = {f.name for f in registry.get_widget_features()}
        expected = {
            "capture",
            "divider",
            "filename_overlay",
            "guides",
            "magnifier",
            "paste_overlay",
        }
        assert expected <= names, f"Missing features: {expected - names}"

    def test_no_central_registration_lists(self):
        """Registries must not contain hardcoded feature name lists."""
        import re

        registry_files = [
            "ui/canvas_infra/scene/registry.py",
        ]
        feature_list_pattern = re.compile(
            r"""["'](capture|divider|guides|magnifier|filename_overlay)["']"""
        )
        violations = []
        for rel_path in registry_files:
            path = os.path.join(SRC, rel_path)
            with open(path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    if feature_list_pattern.search(line):
                        violations.append(f"{rel_path}:{lineno}: {line.strip()}")
        assert not violations, (
            "Registry files contain hardcoded feature names:\n"
            + "\n".join(violations)
        )

class TestFeatureContracts:

    def test_all_widget_features_have_name(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry

        registry = get_canvas_registry("image_compare")
        registry.get_widget_features.cache_clear()
        for f in registry.get_widget_features():
            assert f.name, f"Feature has empty name: {f}"
            assert not f.name.startswith("_"), f"Feature name starts with _: {f.name}"

    def test_all_widget_features_have_reducers(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry

        registry = get_canvas_registry("image_compare")
        registry.get_widget_features.cache_clear()
        for f in registry.get_widget_features():
            assert callable(f.reduce_view_state), f"{f.name}: missing reduce_view_state"
            assert callable(f.reduce_render_config), f"{f.name}: missing reduce_render_config"

    def test_all_render_passes_have_stack_role(self):
        from ui.canvas_infra.scene.registry import get_canvas_registry
        from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

        registry = get_canvas_registry("image_compare")
        registry.get_render_passes.cache_clear()
        for p in registry.get_render_passes():
            assert p.stack_role is not None, (
                f"{type(p).__name__} missing stack_role"
            )
            assert isinstance(p.stack_role, CanvasStackRole), (
                f"{type(p).__name__}.stack_role is {type(p.stack_role)}"
            )

class TestTemplateIsValid:

    def test_template_manifest_importable(self):
        import importlib

        mod = importlib.import_module("tabs.image_compare.canvas.features._template.manifest")
        assert hasattr(mod, "WIDGET_FEATURE")

    def test_template_widget_feature_valid(self):
        from tabs.image_compare.canvas.features._template.manifest import WIDGET_FEATURE
        from ui.canvas_infra.scene.widget_contract import CanvasWidgetFeature

        assert isinstance(WIDGET_FEATURE, CanvasWidgetFeature)
        assert WIDGET_FEATURE.name == "_template"
        assert callable(WIDGET_FEATURE.reduce_view_state)
        assert callable(WIDGET_FEATURE.reduce_render_config)

    def test_template_passes_importable(self):
        import importlib

        mod = importlib.import_module("tabs.image_compare.canvas.features._template.passes")
        passes = getattr(mod, "RENDER_PASSES", None)
        assert isinstance(passes, list)

class TestFeaturePackageCompleteness:

    def test_every_feature_has_manifest(self):
        for entry in os.scandir(FEATURES_DIR):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            manifest = os.path.join(entry.path, "manifest.py")
            assert os.path.isfile(manifest), (
                f"Feature {entry.name} missing manifest.py"
            )
