"""Tests for shared presentation isolation (Phase 5).

Verifies that shared ui/ and plugin presentation code does not use
direct feature-name lookups via get_canvas_feature_command("feature", ...).
The only acceptable callers are:
  - widget_registry.py (definition and alias resolver)
  - feature-owned code inside canvas_features/
"""

from __future__ import annotations

import os
import re
import pytest

SRC = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")

_SHARED_DIRS = [
    "ui/presenters",
    "ui/canvas_presentation",
    "ui/widgets",
    "ui/managers",
    "events",
]

_ALLOWLIST = {
    os.path.normpath("ui/canvas_infra/scene/widget_registry.py"),
}

_DIRECT_CALL_PATTERN = re.compile(
    r'get_canvas_feature_command\(\s*["\']'
)

def _collect_python_files(rel_dir: str):
    """Yield (rel_path, abs_path) for all .py files under rel_dir."""
    abs_dir = os.path.join(SRC, rel_dir)
    if not os.path.isdir(abs_dir):
        return
    for root, _dirs, files in os.walk(abs_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, SRC)
            yield rel_path, abs_path

class TestNoDirectFeatureLookups:

    @pytest.mark.parametrize("rel_dir", _SHARED_DIRS)
    def test_shared_dir_uses_aliases_only(self, rel_dir: str):
        violations = []
        for rel_path, abs_path in _collect_python_files(rel_dir):
            if os.path.normpath(rel_path) in _ALLOWLIST:
                continue
            with open(abs_path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    if _DIRECT_CALL_PATTERN.search(line):
                        violations.append(f"{rel_path}:{lineno}: {line.strip()}")
        assert not violations, (
            f"Direct get_canvas_feature_command(\"feature\", ...) calls in {rel_dir}/:\n"
            + "\n".join(violations)
            + "\n\nUse get_canvas_feature_command_by_alias() instead."
        )

class TestPluginsUseAliasesForFeatureCommands:
    """Plugin code (except settings controller generic dispatch) should use aliases."""

    def test_plugin_dirs_use_aliases(self):
        violations = []
        plugins_dir = os.path.join(SRC, "plugins")
        if not os.path.isdir(plugins_dir):
            pytest.skip("plugins/ not found")
        for root, _dirs, files in os.walk(plugins_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, SRC)
                if os.path.normpath(rel_path) in _ALLOWLIST:
                    continue
                with open(abs_path, encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if _DIRECT_CALL_PATTERN.search(line):
                            violations.append(f"{rel_path}:{lineno}: {line.strip()}")
        assert not violations, (
            "Direct get_canvas_feature_command(\"feature\", ...) calls in plugins/:\n"
            + "\n".join(violations)
            + "\n\nUse get_canvas_feature_command_by_alias() instead."
        )

class TestNewAliasesExist:

    @pytest.mark.parametrize(
        "alias",
        [
            "splitter.sync_split_position",
            "overlay.request_cached_diff",
            "overlay.settings.apply_behavior",
        ],
    )
    def test_phase5_aliases_resolve(self, alias: str):
        from ui.canvas_infra.scene.widget_registry import (
            get_canvas_feature_command_by_alias,
        )

        cmd = get_canvas_feature_command_by_alias(alias)
        assert cmd is not None, f"Alias {alias} did not resolve"
        assert callable(cmd), f"Alias {alias} resolved to non-callable"
