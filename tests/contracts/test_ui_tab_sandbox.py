"""Contract: src/ui/ must not reference specific tab concepts.

Tabs are sandboxed in ``src/tabs/*``.  The host tree ``src/ui/`` must not
contain tab-specific identifiers — in imports, method names, variable names,
string literals, service IDs, or settings keys.

Enforced tab concepts (must not appear in src/ui/ except in comments/strings
that document the boundary):

- ``magnifier`` — image_compare-specific canvas feature
- ``image_compare`` / ``multi_compare`` / ``session_picker`` / ``image_gallery``
  — tab session_type names

Legitimate exceptions:
- ``from tabs.contract`` / ``from tabs.registry`` — shared tab infrastructure
- Action IDs and i18n keys that are part of the public product catalog
  (e.g. ``workspace.new_image_compare``) — documented in platform.py
- Translations / docstrings that mention tab names for context

Dogma source: docs/dev/tabs/isolation.md, docs/dev/tabs/capability-mechanisms.md
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.contracts._framework import SRC, iter_py, rel

# Tab-specific terms that must NOT appear as identifiers in src/ui/
# (method names, variable names, attribute names, class names).
_TAB_IDENTIFIER_PATTERNS = re.compile(
    r"(?:magnifier_visibility|magnifier_instances|magnifier_settings|"
    r"image_compare_widget|image_compare_session|multi_compare_session|"
    r"session_picker_host|image_gallery_session|"
    r"clear_magnifier|optimize_magnifier)"
)

# Tab session_type strings that must NOT appear as string literals
# in src/ui/ (excluding comments, docstrings, and i18n keys).
_TAB_SESSION_TYPE_STRINGS = re.compile(
    r"""(?:"|')(?:image_compare|multi_compare|session_picker|image_gallery)(?:"|')"""
)


def test_ui_no_tab_specific_method_names():
    """src/ui/ must not define methods/variables with tab-specific names."""
    offenders: list[str] = []
    ui_dir = SRC / "ui"
    for path in iter_py(ui_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        for node in ast.walk(tree):
            # Check function/method names
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _TAB_IDENTIFIER_PATTERNS.search(node.name):
                    offenders.append(
                        f"{rel_path}:{node.lineno} defines '{node.name}'"
                    )
            # Check variable assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and _TAB_IDENTIFIER_PATTERNS.search(target.id):
                        offenders.append(
                            f"{rel_path}:{node.lineno} assigns '{target.id}'"
                        )
            # Check class names
            if isinstance(node, ast.ClassDef):
                if _TAB_IDENTIFIER_PATTERNS.search(node.name):
                    offenders.append(
                        f"{rel_path}:{node.lineno} defines class '{node.name}'"
                    )
    assert not offenders, (
        "src/ui/ defines tab-specific identifiers:\n  "
        + "\n  ".join(offenders)
    )


def test_ui_no_tab_session_type_string_literals():
    """src/ui/ must not contain tab session_type string literals in logic."""
    offenders: list[str] = []
    ui_dir = SRC / "ui"
    for path in iter_py(ui_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str):
                continue
            if _TAB_SESSION_TYPE_STRINGS.search(node.value):
                # Exclude i18n keys (contain dots like "workspace.session_types.multi_compare")
                if "." in node.value:
                    continue
                # Exclude translation key patterns
                if "session_types" in node.value or "tab_name" in node.value:
                    continue
                offenders.append(
                    f"{rel_path}:{node.lineno} string '{node.value}'"
                )
    assert not offenders, (
        "src/ui/ contains tab session_type string literals:\n  "
        + "\n  ".join(offenders)
    )


def test_ui_no_magnifier_settings_in_dialog_manager():
    """DialogManager must not contain magnifier-specific settings logic."""
    dm_path = SRC / "ui" / "managers" / "dialog_manager.py"
    if not dm_path.exists():
        return
    text = dm_path.read_text(encoding="utf-8")
    # Check for magnifier in method/function definitions
    tree = ast.parse(text)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if "magnifier" in node.name.lower():
                violations.append(f"method '{node.name}' at line {node.lineno}")
    # Also check for magnifier in string constants that are settings keys
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "magnifier" in node.value.lower() and "." not in node.value:
                violations.append(f"string '{node.value}' at line {node.lineno}")
    assert not violations, (
        "DialogManager contains magnifier-specific code:\n  "
        + "\n  ".join(violations)
    )
