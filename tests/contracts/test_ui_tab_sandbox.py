"""Contract: src/ui/ must not reference specific tab concepts.

Tabs are sandboxed in ``src/tabs/*``.  The host tree ``src/ui/`` must not
contain tab-specific identifiers — in imports, method/class/attribute names,
variable names, function parameters, string literals, service IDs, or
settings keys.

Enforced tab concepts (must not appear in src/ui/ except in comments,
docstrings, or i18n keys that document the boundary):

- ``magnifier`` — image_compare-specific canvas feature. Enforced as a
  *word*, so any compound built on it (``magnifier_instances``,
  ``clear_magnifier``, ``MagnifierVisibilityFlyout``, ...) counts. Other
  canvas feature names (``divider``, ``guides``, ``capture``, ...) are NOT
  enforced here — they are generic UI words shared with host code, unlike
  ``magnifier`` which docs/dev/tabs/isolation.md names explicitly.
- Tab ``session_type`` values — discovered live from
  :class:`tabs.registry.TabRegistry` rather than hardcoded, so this list
  can't drift from what tabs actually register. As of writing:
  image_compare, multi_compare, session_picker, image_gallery.

Legitimate exceptions:
- ``from tabs.contract`` / ``from tabs.registry`` — shared tab infrastructure.
- Action IDs and i18n keys that are part of the public product catalog
  (e.g. ``workspace.new_image_compare``) — dotted-key-shaped strings,
  documented in platform.py.
- Translations / docstrings / comments that mention tab names for context.

Dogma source: docs/dev/tabs/isolation.md, docs/dev/tabs/capability-mechanisms.md
"""

from __future__ import annotations

import ast
import re

from tabs.registry import TabRegistry

from tests.contracts._framework import SRC, iter_py, rel

UI_DIR = SRC / "ui"


def _discover_session_types() -> tuple[str, ...]:
    """Live session_type catalog — not a hardcoded guess at tab names."""
    registry = TabRegistry()
    registry.discover()
    return tuple(sorted({tab.session_type for tab in registry.list_tabs()}))


_SESSION_TYPES = _discover_session_types()
assert _SESSION_TYPES, "no tabs discovered — TabRegistry.discover() found nothing"

# "magnifier" is the one canvas-feature name the isolation dogma calls out
# explicitly (see module docstring) — not every canvas feature.
_CONCEPT_ROOTS = _SESSION_TYPES + ("magnifier",)


def _normalize(identifier: str) -> str:
    """snake_case-ify (incl. PascalCase/camelCase) and lowercase."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", identifier)
    return s.lower()


def _concept_pattern(root: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(root)}(?![a-z0-9])")


_CONCEPT_PATTERNS = {root: _concept_pattern(root) for root in _CONCEPT_ROOTS}


def _matched_concepts(raw_identifier: str) -> list[str]:
    """Concept roots present as whole word-components of *raw_identifier*."""
    normalized = _normalize(raw_identifier)
    return [root for root, pat in _CONCEPT_PATTERNS.items() if pat.search(normalized)]


# ---------------------------------------------------------------------------
# Allowlist — host-side workspace-action catalog wiring.
#
# The host owns exactly one job that legitimately has to name concrete tabs:
# opening the landing ``session_picker`` tab and registering the "new
# image_compare / new multi_compare" workspace actions (Find Action /
# titlebar menu entries whose action IDs are literally
# ``workspace.new_image_compare`` etc. — the public product catalog the
# module docstring's "Action IDs" exception already names). This is
# distinct from — and much narrower than — a host manager reaching into a
# tab's *internal* feature (see the un-allowlisted ``magnifier`` wiring
# below, which this contract intentionally still fails on).
#
# Entries are (repo-relative path, identifier-or-string-literal). Adding an
# entry here should point at genuine action-catalog/landing-tab wiring, not
# be used to silence a fresh leak — new entries should be reviewed like any
# other contract exception.
# ---------------------------------------------------------------------------
_ALLOWLISTED_IDENTIFIERS: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/ui/main_window/menu_controller.py", "_wire_session_picker_recent"),
        ("src/ui/main_window/menu_controller.py", "_open_session_picker"),
        ("src/ui/main_window/menu_controller.py", "wire_session_picker_recent"),
        ("src/ui/main_window/menu_controller.py", "open_session_picker"),
        ("src/ui/main_window/project_io.py", "resolve_session_picker_host_chrome"),
        ("src/ui/main_window/project_io.py", "refresh_session_picker_recent"),
        ("src/ui/main_window/project_io.py", "wire_session_picker_recent"),
        ("src/ui/actions/workspace_new_sessions.py", "image_compare_runner"),
        ("src/ui/actions/workspace_new_sessions.py", "multi_compare_runner"),
        ("src/ui/actions/workspace_new_sessions.py", "image_compare_target"),
        ("src/ui/actions/workspace_new_sessions.py", "multi_compare_target"),
        ("src/ui/actions/platform.py", "open_session_picker"),
        ("src/ui/actions/platform.py", "new_image_compare"),
        ("src/ui/actions/platform.py", "new_multi_compare"),
        ("src/ui/actions/platform.py", "open_session_picker_target"),
        ("src/ui/actions/platform.py", "new_image_compare_target"),
        ("src/ui/actions/platform.py", "new_multi_compare_target"),
        ("src/ui/main_window/use_cases/platform_actions.py", "open_session_picker"),
        ("src/ui/main_window/use_cases/platform_actions.py", "_wire_session_picker_recent"),
        ("src/ui/main_window/use_cases/platform_actions.py", "_open_session_picker"),
        ("src/ui/presenters/main_window/workspace.py", "ensure_session_picker_visible"),
    }
)

_ALLOWLISTED_STRING_LITERALS: frozenset[tuple[str, str]] = frozenset(
    {
        ("src/ui/main_window/ui.py", "multi_compare"),
        ("src/ui/main_window/ui.py", "session_picker"),
        ("src/ui/main_window/startup.py", "session_picker"),
        ("src/ui/actions/workspace_new_sessions.py", "image_compare"),
        ("src/ui/actions/workspace_new_sessions.py", "multi_compare"),
    }
)


# Dotted, identifier-shaped strings are i18n/action keys (e.g.
# "workspace.new_image_compare", "session_picker.types.{session_type}") —
# the documented "public product catalog" / translation-key exception.
# Prose sentences that merely happen to contain a period don't match this
# shape (spaces aren't allowed), so they still fall through to the check.
_I18N_KEY_SHAPE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_{}]*(\.[a-zA-Z_][a-zA-Z0-9_{}]*)+$")


def _docstring_const_ids(tree: ast.AST) -> set[int]:
    """id() of every Constant node that is a bare string-statement docstring.

    Covers module/class/function docstrings *and* the PEP 257 "trailing
    attribute docstring" idiom used throughout this codebase's dataclasses
    (a bare string literal after a field, documenting that field) — any
    standalone ``Expr(Constant(str))`` statement is prose, never logic, so
    none of them can carry a real tab-concept leak.
    """
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def _iter_defined_identifiers(tree: ast.AST):
    """Yield (lineno, kind, name) for every identifier src/ui/ *defines or
    references* — functions, classes, assigned/annotated names, attribute
    access (both read and write), and function parameters."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.lineno, "defines function", node.name
            for arg in (
                node.args.posonlyargs
                + node.args.args
                + node.args.kwonlyargs
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            ):
                yield arg.lineno, "declares parameter", arg.arg
        elif isinstance(node, ast.ClassDef):
            yield node.lineno, "defines class", node.name
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    yield node.lineno, "assigns", target.id
        elif isinstance(node, ast.Attribute):
            yield node.lineno, "references attribute", node.attr


def test_ui_no_tab_specific_identifiers():
    """src/ui/ must not define or reference identifiers built on a tab concept."""
    offenders: list[str] = []
    for path in iter_py(UI_DIR):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        for lineno, kind, name in _iter_defined_identifiers(tree):
            if (rel_path, name) in _ALLOWLISTED_IDENTIFIERS:
                continue
            concepts = _matched_concepts(name)
            if concepts:
                offenders.append(
                    f"{rel_path}:{lineno} {kind} '{name}' (concept: {', '.join(concepts)})"
                )
    assert not offenders, (
        "src/ui/ references tab-specific identifiers:\n  " + "\n  ".join(offenders)
    )


def test_ui_no_tab_session_type_string_literals():
    """src/ui/ must not contain tab session_type/magnifier string literals in logic."""
    offenders: list[str] = []
    for path in iter_py(UI_DIR):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        skip_ids = _docstring_const_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in skip_ids:
                continue
            value = node.value
            if _I18N_KEY_SHAPE.match(value):
                continue
            if (rel_path, value) in _ALLOWLISTED_STRING_LITERALS:
                continue
            if value in _SESSION_TYPES:
                offenders.append(f"{rel_path}:{node.lineno} session_type literal '{value}'")
                continue
            if _CONCEPT_PATTERNS["magnifier"].search(_normalize(value)):
                offenders.append(f"{rel_path}:{node.lineno} magnifier literal '{value}'")
    assert not offenders, (
        "src/ui/ contains tab session_type/magnifier string literals:\n  "
        + "\n  ".join(offenders)
    )


_ALLOWED_TAB_SUBMODULES = ("contract", "registry")
_TAB_IMPORT_RE = re.compile(
    r"^(?:src\.)?tabs\.(?!(?:" + "|".join(_ALLOWED_TAB_SUBMODULES) + r")\b)[^.]+"
)


def test_ui_does_not_import_tab_internals():
    """src/ui/ may only import ``tabs.contract`` / ``tabs.registry`` — the
    shared tab infrastructure — never a concrete tab's own package."""
    offenders: list[str] = []
    for path in iter_py(UI_DIR):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if _TAB_IMPORT_RE.match(node.module):
                    offenders.append(f"{rel_path}:{node.lineno} imports '{node.module}'")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _TAB_IMPORT_RE.match(alias.name):
                        offenders.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")
    assert not offenders, (
        "src/ui/ imports a concrete tab's internals:\n  " + "\n  ".join(offenders)
    )
