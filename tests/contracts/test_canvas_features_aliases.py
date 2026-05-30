"""Shared code must use ``get_canvas_feature_command_by_alias``, not
``get_canvas_feature_command("feature_name", "cmd")`` with literal strings.

Parameterized forwarding (where ``feature_name`` comes from a variable —
e.g. a feature-declared binding) is allowed.

Dogma source: docs/dev/CANVAS_FEATURES.md ("Shared code must not use
get_canvas_feature_command(...). Instead: ... use the capability alias").
"""

from __future__ import annotations

import ast

import pytest

from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_command_aliases,
    get_canvas_feature_command_by_alias,
)

from ._framework import (
    CANVAS_FEATURES,
    CANVAS_INFRA,
    SRC,
    iter_py,
    read,
    rel,
)

def test_no_hardcoded_feature_name_in_get_canvas_feature_command():
    leaks: list[str] = []
    for py in iter_py(SRC):
        if str(py).startswith(str(CANVAS_INFRA)):
            continue
        if str(py).startswith(str(CANVAS_FEATURES)):
            continue
        try:
            tree = ast.parse(read(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            fname = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else None
            )
            if fname != "get_canvas_feature_command":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                leaks.append(
                    f"{rel(py)}:{node.lineno} hardcodes feature name "
                    f"'{first.value}' (use get_canvas_feature_command_by_alias)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)

_ALIASES = sorted(get_canvas_feature_command_aliases().items())
_ALIAS_IDS = [cap for cap, _ in _ALIASES]

def test_some_aliases_are_declared():
    assert _ALIASES, "expected at least one declared capability alias"

@pytest.mark.parametrize("alias", _ALIASES, ids=_ALIAS_IDS)
def test_declared_alias_resolves_to_callable(alias):
    """Every declared alias must point at a real, callable command.

    A typo in the alias' target command_id otherwise produces a silent ``None``
    at the call site (graceful degradation hides the bug). This catches the
    broken alias at test time.

    Dogma source: docs/dev/CONTRACTS.md §CanvasFeatureCommandAlias.
    """
    capability_id, (feature_name, command_id) = alias
    resolved = get_canvas_feature_command_by_alias(capability_id)
    assert resolved is not None, (
        f"alias '{capability_id}' targets {feature_name}.{command_id} "
        f"which does not resolve to a command (broken target?)"
    )
    assert callable(resolved), (
        f"alias '{capability_id}' resolves to a non-callable {resolved!r}"
    )
