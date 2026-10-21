"""C1 gate: no ``except NameError`` in the render path.

Dogma: an ``except NameError`` handler in this tree wraps a name that the
author believed could be unbound. It turns "this name is missing" into a
silent fallback: the frame renders with a default instead of failing at the
seam that is wrong. The two live cases in ``coverage.py`` were even worse than
that — the guarded names were *parameters of the enclosing function*, so the
handler could never fire and only hid the fact that the parameter WAS the
decision (see ``src/tabs/image_compare/tests/render/
test_coverage_first_paint_hold.py``). C2 deleted both.

Rule (AST): no ``except NameError`` handler in
``src/ui/canvas_infra/**``, ``src/tabs/image_compare/canvas/**``,
``src/tabs/multi_compare/scene/**``, ``src/engine/gpu/**``. The gate walks
every module under those roots — a moved handler is still a finding.

Allowlist: ``canvas_gates_allowlist.ALLOWLIST[GATE]`` (empty — both
``coverage.py`` handlers were drained in C2).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC, iter_py, rel
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_no_except_nameerror.py"

#: The render path. A handler outside these roots is not this gate's business
#: (host-side adapters legitimately probe optional editor APIs).
ROOTS: tuple[Path, ...] = (
    SRC / "ui" / "canvas_infra",
    SRC / "tabs" / "image_compare" / "canvas",
    SRC / "tabs" / "multi_compare" / "scene",
    SRC / "engine" / "gpu",
)

_BANNED = "NameError"


def _own_handlers(function: ast.AST) -> list[ast.ExceptHandler]:
    """Handlers whose ``try`` lives directly in *function* (not a nested def)."""
    out: list[ast.ExceptHandler] = []
    stack: list[ast.AST] = list(getattr(function, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.ExceptHandler) and _catches_name_error(node):
            out.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return sorted(out, key=lambda handler: handler.lineno)


def _catches_name_error(handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    if caught is None:
        return False
    names = [caught] if not isinstance(caught, ast.Tuple) else list(caught.elts)
    return any(isinstance(item, ast.Name) and item.id == _BANNED for item in names)


def _annotated_functions(tree: ast.Module) -> list[tuple[str, ast.ExceptHandler]]:
    """``(enclosing symbol, handler)``; symbol ``""`` for module level."""
    out: list[tuple[str, ast.ExceptHandler]] = []

    def walk(node: ast.AST, prefix: str):
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{prefix}{child.name}"
                for handler in _own_handlers(child):
                    out.append((symbol, handler))
                walk(child, f"{symbol}.")

    for handler in _own_handlers(tree):
        out.append(("", handler))
    walk(tree, "")
    return out


def findings_for_source(path_text: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [Finding(path_text, "", "unparseable source — gate is blind")]
    return [
        Finding(
            path_text,
            symbol,
            f"catches {_BANNED} at line {handler.lineno} — name the optional "
            "field instead of falling back silently",
        )
        for symbol, handler in _annotated_functions(tree)
    ]


def findings() -> list[Finding]:
    findings: list[Finding] = []
    for root in ROOTS:
        for path in iter_py(root):
            findings.extend(
                findings_for_source(rel(path), path.read_text(encoding="utf-8"))
            )
    return findings


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_no_except_nameerror_on_the_render_path():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        f"No `except {_BANNED}` handler may exist on the render path "
        "(ui/canvas_infra, image_compare/canvas, multi_compare/scene, "
        "engine/gpu): it turns a missing field into a silent default frame. "
        "Offenders:\n" + format_findings(open_findings)
    )


def test_allowlist_entries_are_documented_and_current():
    current = findings()
    problems = allowlist_problems(GATE, current)
    for finding in unexplained(GATE, current):
        problems.append(f"{finding.key}: uncovered finding — {finding.detail}")
    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_scan_reaches_the_known_sites():
    """Non-vacuity: the corpus must include the module that carries today's sites."""
    scanned = [rel(path) for root in ROOTS for path in iter_py(root)]
    assert len(scanned) >= 100, f"only {len(scanned)} modules scanned"
    coverage = "src/tabs/image_compare/canvas/rhi_renderer/use_cases/coverage.py"
    assert coverage in scanned, f"{coverage} is not in the render-path corpus"


def test_synthetic_handler_is_flagged():
    """Falsification: a handler that swallows NameError is reported by symbol."""
    source = '''
def evaluate_coverage(ctx):
    try:
        return ctx.metrics.coverage
    except NameError:
        return None
'''
    flagged = findings_for_source("synthetic_coverage.py", source)
    assert flagged, "an `except NameError` handler was not flagged"
    assert flagged[0].symbol == "evaluate_coverage"
    assert "line 5" in flagged[0].detail


def test_other_exceptions_are_not_flagged():
    """Control: the gate is about NameError, not exception handling in general."""
    source = '''
def evaluate_coverage(ctx):
    try:
        return ctx.metrics.coverage
    except AttributeError:
        return None
'''
    assert findings_for_source("synthetic_attribute.py", source) == []
