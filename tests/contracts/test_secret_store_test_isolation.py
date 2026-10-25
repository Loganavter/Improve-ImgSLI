"""A test that writes the AI provider key must say how it is isolated.

``core.secret_store`` execs the host's ``secret-tool``, so a test that saves or
clears the key reaches the user's login keyring: the 2026-10-25 incident was
``src/tabs/image_gallery/tests/runtime/test_ai_settings_store.py`` writing an
11-char stub over the owner's real provider key while the suite stayed green.
The runtime half of the fix is the sandbox + guard in
``tests/helpers/secret_store_isolation.py``; this contract is the static half,
so a NEW test cannot re-introduce the call without naming the isolation.

Two shapes are flagged in every ``test_*.py`` under ``tests/`` and
``src/**/tests/``:

* ``....save_field("api_key", …)`` / ``....save("api_key", …)`` — the key's
  write path through ``AiSettingsStore``;
* ``secret_store.store(…)`` / ``secret_store.clear(…)`` — the store's own
  mutators (``clear`` deletes BOTH keyring identities, which is the worse half
  of the incident).

A module is clean when it names the isolation somewhere real: the opt-in
fixture (``secret_store_keyring``), the sandbox fixtures, ``usefixtures(…)``
with those names, or an import from ``tests/helpers/secret_store_isolation.py``.
Prose does not count — docstrings are ignored on purpose, so quoting this rule
in a module docstring cannot satisfy it.

``SELF_MANAGED`` names the modules that install their own recording
``secret-tool`` (``tmp_path / "secret-tool"``): they answer the keyring
themselves, so they are isolated by construction and must not be forced onto
the shared sandbox. Each entry states why; a stale entry fails the contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import ROOT, rel

from tests.helpers.secret_store_isolation import (
    ISOLATION_MARKERS,
    KEYRING_OPT_IN_FIXTURE,
)

TESTS_ROOT = ROOT / "tests"
SRC_TABS = ROOT / "src" / "tabs"

#: Method names whose first argument is the field being written.
FIELD_WRITERS = frozenset({"save_field", "save", "set_field", "set_value"})
#: The field whose value is the provider key.
SECRET_FIELD = "api_key"
#: ``core.secret_store`` methods that mutate the stored secret.
STORE_MUTATORS = frozenset({"store", "clear"})
#: The helper module that owns the sandbox; importing it is a declaration.
HELPER_MODULE = "secret_store_isolation"

#: rel path -> why this module does not need the shared sandbox. It installs its
#: own recording fake, so its keyring traffic never reaches the shared sandbox.
SELF_MANAGED: dict[str, str] = {
    "src/tabs/image_gallery/tests/plugins/test_ai_key_storage.py": (
        "builds its own recording `secret-tool` per test (and patches the "
        "backend probe) to drive all three backends explicitly — the origin of "
        "the sandbox helper's design"
    ),
    "src/tabs/image_gallery/tests/plugins/test_ai_key_page_refresh.py": (
        "builds its own recording `secret-tool` + throwaway XDG_DATA_HOME to "
        "pin the page's re-probe read-back"
    ),
    "tests/plugins/test_secret_store_machine_id_windows.py": (
        "exercises only the encrypted-file backend: it pins "
        "`keyring_available` to False and writes into a tmp XDG_DATA_HOME, so "
        "no keyring call is made at all"
    ),
}


def _test_modules() -> list[Path]:
    """Every test module the suite can run, wherever it lives."""
    found: list[Path] = []
    for root in (TESTS_ROOT, SRC_TABS):
        if not root.is_dir():
            continue
        for path in root.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            if "tests" not in path.parts:
                continue
            found.append(path)
    return sorted(set(found))


def _declared_isolation(tree: ast.Module) -> set[str]:
    """Identifiers the module really uses to declare its isolation."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            # ``def test_x(secret_store_keyring)`` — a fixture is requested by
            # parameter name, which the AST records as ``ast.arg``.
            names.add(node.arg)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            if node.module and HELPER_MODULE in node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            attr = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if attr == "usefixtures":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        names.add(arg.value)
    return names


def _declares_isolation(tree: ast.Module) -> bool:
    declared = _declared_isolation(tree)
    if declared & ISOLATION_MARKERS:
        return True
    return any(HELPER_MODULE in name for name in declared)


def _field_written(call: ast.Call) -> str:
    """The constant field name a ``save_field``-style call writes, or ``""``."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in FIELD_WRITERS:
        return ""
    for arg in call.args[:1]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for keyword in call.keywords:
        if keyword.arg in ("name", "field", "key") and isinstance(
            keyword.value, ast.Constant
        ):
            return str(keyword.value.value)
    return ""


def _mutates_secret_store(call: ast.Call) -> str:
    """``"store"``/``"clear"`` when the call mutates ``secret_store``, else ``""``."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in STORE_MUTATORS:
        return ""
    value = func.value
    if isinstance(value, ast.Name) and value.id == "secret_store":
        return func.attr
    if isinstance(value, ast.Attribute) and value.attr == "secret_store":
        return func.attr
    return ""


def violations_in_source(source: str) -> list[str]:
    """Why *source* writes the secret without declaring isolation (empty = clean)."""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        field = _field_written(node)
        if field:
            if field == SECRET_FIELD:
                found.append(f"line {node.lineno}: writes the `{SECRET_FIELD}` field")
            continue
        mutator = _mutates_secret_store(node)
        if mutator:
            found.append(f"line {node.lineno}: calls `secret_store.{mutator}()`")
    if found and _declares_isolation(tree):
        return []
    return found


def violations(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        return violations_in_source(source)
    except SyntaxError:  # pragma: no cover - a broken file fails its own import
        return []


def test_no_test_writes_the_provider_key_without_isolation() -> None:
    modules = _test_modules()
    assert len(modules) > 50, (
        f"the scan found only {len(modules)} test modules — the discovery is "
        "broken, and a broken scan is a silent pass"
    )

    offenders: list[str] = []
    for path in modules:
        name = rel(path)
        problems = violations(path)
        if not problems or name in SELF_MANAGED:
            continue
        offenders.append(
            f"{name}: " + "; ".join(problems) + f" — name the `{KEYRING_OPT_IN_FIXTURE}` "
            "fixture (or import tests/helpers/secret_store_isolation.py), or add a "
            "SELF_MANAGED entry here stating why this module answers the keyring itself"
        )

    assert not offenders, "unisolated secret-store writers:\n  " + "\n  ".join(offenders)


def test_the_self_managed_allowlist_has_no_stale_entries() -> None:
    """An allowlist that outlives its module silently widens the rule."""
    stale = [name for name in SELF_MANAGED if not (ROOT / name).is_file()]
    assert not stale, f"drop the stale SELF_MANAGED entries: {stale}"


def test_every_self_managed_entry_is_still_a_writer() -> None:
    """An entry for a module that no longer writes just hides a future writer."""
    quiet = [name for name in SELF_MANAGED if not violations(ROOT / name)]
    assert not quiet, f"these no longer need an allowlist entry: {quiet}"


# ---------------------------------------------------------------------------
# The detector must discriminate: a scan that matches nothing is the failure
# mode this contract exists to prevent.
# ---------------------------------------------------------------------------

UNDECLARED_KEY_WRITE = '''
def test_round_trip(monkeypatch):
    store = AiSettingsStore()
    store.save_field("api_key", "sk-test-123")
'''

DECLARED_KEY_WRITE = '''
import pytest

def test_round_trip(monkeypatch, secret_store_keyring):
    store = AiSettingsStore()
    store.save_field("api_key", "sk-test-123")
'''

UNDECLARED_STORE_CLEAR = '''
from core import secret_store

def test_cleanup():
    secret_store.clear()
'''

PROSE_ONLY_DECLARATION = '''
"""This module names secret_store_keyring only in prose."""

from core import secret_store

def test_cleanup():
    secret_store.clear()
'''


def test_the_detector_flags_an_undeclared_key_write() -> None:
    problems = violations_in_source(UNDECLARED_KEY_WRITE)
    assert problems and "api_key" in problems[0], problems


def test_the_detector_flags_an_undeclared_store_clear() -> None:
    problems = violations_in_source(UNDECLARED_STORE_CLEAR)
    assert problems and "secret_store.clear()" in problems[0], problems


def test_the_detector_accepts_a_declared_writer() -> None:
    assert violations_in_source(DECLARED_KEY_WRITE) == []


def test_prose_is_not_a_declaration() -> None:
    assert violations_in_source(PROSE_ONLY_DECLARATION), (
        "a docstring that merely mentions the fixture must not satisfy the rule"
    )


def test_the_detector_ignores_unrelated_saves() -> None:
    source = '''
def test_enabled(store):
    store.save_field("enabled", True)
'''
    assert violations_in_source(source) == []
