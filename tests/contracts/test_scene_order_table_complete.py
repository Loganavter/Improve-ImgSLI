"""C1 gate: both stacking tables are complete and resolve without defaults.

Dogma: ``ui/canvas_infra/scene/stacking_policy.py`` is the SINGLE source of
truth for draw order (see its module docstring). A pass or scene object
declares a semantic ``CanvasStackRole``; the policy maps it to a concrete
``(layer, priority)`` pair. Two failure modes are invisible at runtime:

* **A missing key.** ``_SCENE_OBJECT_ORDER`` has no ``HUD_INTERACTION_OVERLAY``
  entry today, so the role silently resolves through
  ``_SCENE_OBJECT_DEFAULT`` = ``(CanvasStackLayer.OBJECT, 0)`` — the exact pair
  ``IMAGE_OVERLAY_CONTENT`` already owns. Two different roles then draw at the
  same layer/priority and the stable sort decides by list order: the HUD
  interaction overlay can land underneath the image overlay.
* **A default in the resolver.** ``resolve_*_order`` uses
  ``table.get(role, default)``, so a *newly added* ``CanvasStackRole`` member
  without a table row compiles, lints, and renders at the default — no error,
  no test failure. ``__getitem__`` turns that into a ``KeyError`` at the first
  frame instead.

Rule: for BOTH ``_RENDER_PASS_ORDER`` and ``_SCENE_OBJECT_ORDER``

1. every ``CanvasStackRole`` member is a key;
2. the resolver uses ``__getitem__`` (no ``.get(role, default)``);
3. no two roles resolve to the same ``(layer, phase)`` pair — checked on the
   *resolved* values, so a missing key's fallback collision counts too.

Allowlist: three entries (both resolvers and the missing scene role — C2).
"""

from __future__ import annotations

import ast

from tests.contracts._framework import ROOT, parse
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_scene_order_table_complete.py"

PATH = "src/ui/canvas_infra/scene/stacking_policy.py"

RESOLVERS = {
    "_RENDER_PASS_ORDER": "resolve_render_pass_order",
    "_SCENE_OBJECT_ORDER": "resolve_scene_object_order",
}


def _module():
    from ui.canvas_infra.scene import stacking_policy

    return stacking_policy


def missing_role_findings() -> list[Finding]:
    """Every ``CanvasStackRole`` member without a row in either table."""
    policy = _module()
    findings: list[Finding] = []
    for table_name in RESOLVERS:
        table = getattr(policy, table_name)
        for role in policy.CanvasStackRole:
            if role in table:
                continue
            findings.append(
                Finding(
                    PATH,
                    f"{table_name}.{role.name}",
                    f"`{role.name}` has no row — it falls through to the "
                    "resolver's default pair instead of a declared order",
                )
            )
    return findings


def _resolver_uses_get(function: ast.AST) -> bool:
    """True when the resolver body calls ``<table>.get(...)``."""
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ):
            return True
    return False


def resolver_findings() -> list[Finding]:
    """Every resolver that hides a missing role behind a default."""
    tree = parse(ROOT / PATH)
    if tree is None:
        return [Finding(PATH, "", "stacking_policy.py is unparseable — gate is blind")]
    findings: list[Finding] = []
    found = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in RESOLVERS.values():
            continue
        found += 1
        if _resolver_uses_get(node):
            findings.append(
                Finding(
                    PATH,
                    node.name,
                    "resolves with `.get(role, default)` — a missing role becomes a "
                    "silent default instead of a KeyError at the first frame",
                )
            )
    if found != len(RESOLVERS):
        findings.append(
            Finding(PATH, "", f"expected {len(RESOLVERS)} resolvers, found {found}")
        )
    return findings


def collision_findings() -> list[Finding]:
    """Roles that resolve to the same pair, keyed on the fallback side.

    A collision caused by a *missing* row is attributed to the missing role
    (the row to add); a collision between two explicit rows is attributed to
    both, because either row may be wrong.
    """
    policy = _module()
    findings: list[Finding] = []
    for table_name, resolver_name in RESOLVERS.items():
        table = getattr(policy, table_name)
        resolver = getattr(policy, resolver_name)
        resolved: dict[object, list] = {}
        for role in policy.CanvasStackRole:
            resolved.setdefault(tuple(resolver(role)), []).append(role)
        for pair, roles in resolved.items():
            if len(roles) < 2:
                continue
            fallback = [role for role in roles if role not in table]
            for role in fallback or roles:
                findings.append(
                    Finding(
                        PATH,
                        f"{table_name}.{role.name}",
                        f"resolves to {pair} together with "
                        f"{[other.name for other in roles if other is not role]} "
                        "— two roles share one draw position",
                    )
                )
    return findings


def findings() -> list[Finding]:
    return missing_role_findings() + resolver_findings() + collision_findings()


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_both_stacking_tables_are_complete_and_strict():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        "Every CanvasStackRole member must be a key in BOTH "
        "`_RENDER_PASS_ORDER` and `_SCENE_OBJECT_ORDER`, both resolvers must "
        "use `__getitem__` (no `.get(role, default)`), and no two roles may "
        "resolve to the same (layer, priority) pair. Offenders:\n"
        + format_findings(open_findings)
    )


def test_allowlist_entries_are_documented_and_current():
    current = findings()
    problems = allowlist_problems(GATE, current)
    for finding in unexplained(GATE, current):
        problems.append(f"{finding.key}: uncovered finding — {finding.detail}")
    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_tables_are_not_vacuous():
    """Non-vacuity: both tables cover the enum members they do have."""
    policy = _module()
    roles = list(policy.CanvasStackRole)
    assert len(roles) >= 10, f"CanvasStackRole shrank to {len(roles)} members"
    for table_name in RESOLVERS:
        table = getattr(policy, table_name)
        assert len(table) >= len(roles) - 1, (
            f"{table_name} has {len(table)} rows for {len(roles)} roles — the "
            "completeness check would be near-blind"
        )


def test_missing_role_and_get_resolver_are_flagged():
    """Falsification: both halves fire on a synthetic incomplete table."""
    policy = _module()
    role = policy.CanvasStackRole.HUD_INTERACTION_OVERLAY
    table = dict(policy._SCENE_OBJECT_ORDER)
    table.pop(role, None)
    assert role not in table, "the synthetic table still holds the role"
    # A missing role must be a finding for the table that lacks it.
    incomplete = [
        finding
        for finding in missing_role_findings()
        if finding.symbol == f"_SCENE_OBJECT_ORDER.{role.name}"
    ]
    assert incomplete, "the real missing HUD role was not flagged"

    with_get = ast.parse("def resolve_x(role):\n    return _T.get(role, DEFAULT)\n")
    assert _resolver_uses_get(with_get.body[0]), "a `.get` resolver was not flagged"
    strict = ast.parse("def resolve_x(role):\n    return _T[role]\n")
    assert not _resolver_uses_get(strict.body[0]), "a `__getitem__` resolver was flagged"


def test_collision_is_flagged_on_the_fallback_role():
    """Falsification: a fallback collision is attributed to the missing role."""
    collisions = collision_findings()
    symbols = {finding.symbol for finding in collisions}
    assert "_SCENE_OBJECT_ORDER.HUD_INTERACTION_OVERLAY" in symbols, (
        "the HUD_INTERACTION_OVERLAY fallback collision with "
        f"IMAGE_OVERLAY_CONTENT was not reported: {sorted(symbols)}"
    )
    assert "_RENDER_PASS_ORDER.HUD_INTERACTION_OVERLAY" not in symbols, (
        "the render-pass table has the row — it must not report a fallback collision"
    )
