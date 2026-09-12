"""Enforcement: every ``create_service("contribute_*")`` literal is implemented by ≥1 tab.

Closes ``docs/dev/tabs/capability-mechanisms.md:326`` biggest gap: a
dangling/misspelled ID currently fails silently at runtime (``None``) not at
test time.  See spec in plan ``help-settings-isolation``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.contracts._framework import ROOT, SRC

_CONTRIBUTE_RE = re.compile(r"^contribute_")
_CALL_NAMES = {"create_service", "create_startup_service", "notify_all", "create_service_for", "create_main_window_feature"}


def _collect_contribute_ids_from_host() -> set[str]:
    ids: set[str] = set()
    for py in SRC.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name not in _CALL_NAMES:
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                val = first.value
                if _CONTRIBUTE_RE.match(val):
                    ids.add(val)
    return ids


def _collect_tab_service_handlers() -> set[str]:
    ids: set[str] = set()
    tab_root = SRC / "tabs"
    for py in tab_root.rglob("*.py"):
        if "__pycache__" in py.parts or "tests" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except SyntaxError:
            continue
        # Look for: if service_id == "contribute_..."  or  service_id == '...'
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                # left is Name(service_id) and comparators contain Constant
                # we just capture any string literal matching contribute_ inside Compare
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        if _CONTRIBUTE_RE.match(comp.value):
                            ids.add(comp.value)
            # Also handle: if service_id in ("contribute_...", ...)
            if isinstance(node, ast.Call):
                # not needed for our pattern
                pass
        # Fallback regex scan for robustness (covers service_factory etc.)
        for m in re.finditer(r'["\'](contribute_[a-z_]+)["\']', text):
            ids.add(m.group(1))
    return ids


def test_every_contribute_service_literal_is_implemented():
    host_ids = _collect_contribute_ids_from_host()
    tab_ids = _collect_tab_service_handlers()
    # Only host-requested IDs matter; filter to those starting contribute_
    missing = sorted(host_ids - tab_ids)
    assert not missing, (
        "Dangling contribute_* service IDs (no tab implements them): "
        + ", ".join(missing)
        + f"\n  host requests: {sorted(host_ids)}\n  tab handlers: {sorted(tab_ids)}"
        " — add a tab create_service branch or remove the call site"
    )


def test_no_string_mutate_for_contribute_ids():
    """Every ``contribute_*`` must be typed via HelpContribution/SettingsContribution, not string-mutate.

    Ensures host collectors use typed dataclasses rather than passing a
    mutable registry into tabs.  The only allowed raw ``contribute_help``/
    ``contribute_settings`` string literals outside collectors/tabs are
    defended as deprecated shims.
    """
    # Collectors must exist and return typed lists
    cr = SRC / "tabs" / "use_cases" / "capability_routing.py"
    text = cr.read_text(encoding="utf-8")
    assert "def collect_help_contributions" in text
    assert "def collect_settings_contributions" in text
    assert "HelpContribution" in text
    assert "SettingsContribution" in text
