"""Tests for interaction handle contracts (Phase 4).

Verifies that the interaction/event layer does not contain feature-specific
branching and that all interaction dispatch goes through capability aliases.
"""

from __future__ import annotations

import ast
import os
import re
import pytest

SRC = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")

import tabs.image_compare.canvas.features as image_compare_features
from ui.canvas_infra.scene.registry import get_canvas_registry

get_canvas_registry("image_compare").register_package(image_compare_features)

_SHARED_EVENT_FILES = [
    "events/image_label/mouse.py",
    "events/image_label/keyboard.py",
    "events/image_label/geometry.py",
    "events/image_label/preview.py",
    "events/image_label_event_handler.py",
    "events/canvas_input/session_service.py",
]

_FEATURE_IMPORT_PATTERN = re.compile(
    r"from\s+ui\.canvas_features\.(magnifier|divider|capture|guides)\b"
    r"|import\s+ui\.canvas_features\.(magnifier|divider|capture|guides)\b"
)

class TestSharedEventLayerIsolation:

    @pytest.mark.parametrize("rel_path", _SHARED_EVENT_FILES)
    def test_no_feature_imports_in_event_handler(self, rel_path: str):
        path = os.path.join(SRC, rel_path)
        if not os.path.isfile(path):
            pytest.skip(f"{rel_path} not found")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        matches = _FEATURE_IMPORT_PATTERN.findall(content)
        assert not matches, (
            f"{rel_path} imports feature modules directly: {matches}"
        )

    @pytest.mark.parametrize("rel_path", _SHARED_EVENT_FILES)
    def test_no_feature_name_string_checks(self, rel_path: str):
        """Event handlers should not contain if-feature-name branching."""
        path = os.path.join(SRC, rel_path)
        if not os.path.isfile(path):
            pytest.skip(f"{rel_path} not found")
        with open(path, encoding="utf-8") as f:
            content = f.read()

        feature_name_pattern = re.compile(
            r"""if\s+.*['"](magnifier|divider|capture|guides)['"]"""
        )
        matches = feature_name_pattern.findall(content)
        assert not matches, (
            f"{rel_path} contains feature-name branching: {matches}"
        )

class TestInteractionCommandAliases:

    def test_overlay_interaction_aliases_registered(self):
        aliases = get_canvas_registry("image_compare").get_feature_command_aliases()
        expected = [
            "overlay.begin_capture_drag",
            "overlay.update_capture_drag",
            "overlay.end_capture_drag",
        ]
        for alias in expected:
            assert alias in aliases, f"Missing interaction alias: {alias}"

    def test_splitter_interaction_aliases_registered(self):
        aliases = get_canvas_registry("image_compare").get_feature_command_aliases()
        expected = [
            "splitter.begin_drag",
            "splitter.update_drag",
            "splitter.end_drag",
        ]
        for alias in expected:
            assert alias in aliases, f"Missing interaction alias: {alias}"

    def test_all_interaction_aliases_resolve_to_callable(self):
        get_canvas_feature_command_by_alias = get_canvas_registry(
            "image_compare"
        ).get_feature_command_by_alias

        interaction_aliases = [
            "overlay.begin_capture_drag",
            "overlay.update_capture_drag",
            "overlay.end_capture_drag",
            "splitter.begin_drag",
            "splitter.update_drag",
            "splitter.end_drag",
        ]
        for alias in interaction_aliases:
            cmd = get_canvas_feature_command_by_alias(alias)
            assert cmd is not None, f"Alias {alias} did not resolve"
            assert callable(cmd), f"Alias {alias} resolved to non-callable: {type(cmd)}"

class TestHitTestPipeline:

    def test_hit_test_pipeline_has_entries(self):
        from ui.canvas_infra.scene.pipeline import get_scene_hit_testers

        assert len(get_scene_hit_testers("image_compare")) >= 1, "No hit testers registered"

    def test_hit_testers_are_callable(self):
        from ui.canvas_infra.scene.pipeline import get_scene_hit_testers

        for tester in get_scene_hit_testers("image_compare"):
            assert callable(tester), f"Hit tester {tester} is not callable"
