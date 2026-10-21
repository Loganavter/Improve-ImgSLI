"""C1 gate: no duck-typed argument re-binding in the image-compare frame path.

Dogma: a function signature is the contract. ``submit_array_draw`` used to
accept two call styles at once — the plan-doc positional form
``(renderer, widget, command_buffer, array_draw_plan, base_image, diff_ready)``
and the keyword form — and told them apart by asking ``hasattr(ctx,
"scene_frame")`` / ``hasattr(ctx, "render_list")``, then shuffled the bound
arguments accordingly. That makes the call sites unverifiable by reading the
signature and turns a caller mistake (an argument in the wrong slot) into a
silently different frame instead of a ``TypeError``. A ``**kwargs`` catch-all
has the same effect: a typo'd keyword is accepted and ignored.

Rule (AST over ``src/tabs/image_compare/canvas/rhi_renderer/use_cases/``):

* no ``hasattr(<param>, "scene_frame")`` / ``hasattr(<param>, "render_list")``
  argument probing;
* ``submit_array_draw`` has no ``**kwargs`` catch-all and its
  ``renderer``/``widget``/``command_buffer``/``array_draw_plan`` parameters are
  keyword-only (an explicit ``*`` in the signature).

The gate walks every module in the package and every function body — it never
pins the one function it knows about (a moved shuffle would otherwise escape).

Allowlist: ``canvas_gates_allowlist.ALLOWLIST[GATE]`` (empty — the
``submit_array_draw`` entry was drained in C2).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import SRC, iter_py, parse, rel
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_no_duck_typed_arg_shuffle.py"

USE_CASES = SRC / "tabs" / "image_compare" / "canvas" / "rhi_renderer" / "use_cases"

#: Attributes a frame context carries but a base image does not — probing them
#: is exactly the "which positional style is this?" duck typing.
_PROBED_ATTRIBUTES = frozenset({"scene_frame", "render_list"})

#: The public draw entry point and the parameters that must be keyword-only.
DRAW_FUNCTION = "submit_array_draw"
DRAW_REQUIRED_KEYWORD_ONLY = ("renderer", "widget", "command_buffer", "array_draw_plan")


def _functions(tree: ast.Module):
    """``(enclosing symbol, function node)`` for every function in *tree*.

    The symbol is ``Class.method`` for a method and ``function`` at module
    level, so an allowlist entry names one callable, not a whole file.
    """
    stack: list[str] = []

    def walk(node: ast.AST, prefix: str):
        for child in node.body:
            if isinstance(child, ast.ClassDef):
                yield from walk(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{prefix}{child.name}"
                yield symbol, child
                yield from walk(child, f"{symbol}.")

    yield from walk(tree, "")


def _hasattr_probes(function: ast.AST) -> list[int]:
    """Line numbers of ``hasattr(<param>, "scene_frame"|"render_list")`` calls."""
    lines: list[int] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "hasattr":
            continue
        if len(node.args) < 2:
            continue
        attribute = node.args[1]
        if (
            isinstance(attribute, ast.Constant)
            and isinstance(attribute.value, str)
            and attribute.value in _PROBED_ATTRIBUTES
        ):
            lines.append(node.lineno)
    return sorted(lines)


def _signature_problems(function: ast.FunctionDef) -> list[str]:
    """``**kwargs`` catch-all and/or non-keyword-only plan parameters."""
    problems: list[str] = []
    if function.args.kwarg is not None:
        problems.append(f"accepts **{function.args.kwarg.arg} (a catch-all hides typos)")
    keyword_only = {argument.arg for argument in function.args.kwonlyargs}
    positional = {
        argument.arg
        for argument in (
            list(function.args.posonlyargs) + list(function.args.args)
        )
    }
    for name in DRAW_REQUIRED_KEYWORD_ONLY:
        if name in keyword_only:
            continue
        if name in positional:
            problems.append(f"`{name}` is positional — it must follow an explicit `*`")
        else:
            problems.append(f"`{name}` is neither positional nor keyword-only — rename drift?")
    return problems


def findings_for_source(path_text: str, source: str) -> list[Finding]:
    """Every duck-typing violation in one source string."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [Finding(path_text, "", "unparseable source — gate is blind")]

    findings: list[Finding] = []
    for symbol, function in _functions(tree):
        lines = _hasattr_probes(function)
        if lines:
            findings.append(
                Finding(
                    path_text,
                    symbol,
                    "duck-types its arguments with hasattr(..., "
                    + "/".join(sorted(_PROBED_ATTRIBUTES))
                    + f") at line(s) {lines} — the signature must decide, not a probe",
                )
            )
        if function.name == DRAW_FUNCTION:
            problems = _signature_problems(function)
            if problems:
                findings.append(
                    Finding(path_text, DRAW_FUNCTION, "; ".join(problems))
                )
    return findings


def findings() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_py(USE_CASES):
        findings.extend(findings_for_source(rel(path), path.read_text(encoding="utf-8")))
    return findings


def _draw_function_nodes() -> list[ast.FunctionDef]:
    nodes: list[ast.FunctionDef] = []
    for path in iter_py(USE_CASES):
        tree = parse(path)
        if tree is None:
            continue
        nodes.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == DRAW_FUNCTION
        )
    return nodes


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_no_duck_typed_argument_shuffle():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        "A public draw signature must be decidable from the signature alone: no "
        "`hasattr(<param>, \"scene_frame\"|\"render_list\")` re-binding, no "
        "`**kwargs` catch-all, and the plan inputs keyword-only. Offenders:\n"
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


def test_scan_reaches_the_draw_entry_point():
    """Non-vacuity: the package scan must actually see ``submit_array_draw``."""
    assert USE_CASES.is_dir(), f"{rel(USE_CASES)} is missing — the corpus root moved"
    scanned = list(iter_py(USE_CASES))
    assert len(scanned) >= 5, f"only {len(scanned)} modules under {rel(USE_CASES)}"
    assert _draw_function_nodes(), (
        f"`{DRAW_FUNCTION}` was not found under {rel(USE_CASES)} — the gate is blind"
    )


def test_synthetic_shuffle_and_catch_all_are_flagged():
    """Falsification: both halves fire on a source that has the smell."""
    source = '''
def submit_array_draw(renderer, widget, command_buffer, array_draw_plan, **kwargs):
    ctx = array_draw_plan
    if not hasattr(ctx, "scene_frame") and not hasattr(ctx, "render_list"):
        ctx = kwargs.get("ctx")
    return ctx
'''
    flagged = findings_for_source("synthetic_draw.py", source)
    assert len(flagged) == 2, [finding.detail for finding in flagged]
    details = " ".join(finding.detail for finding in flagged)
    assert "duck-types" in details
    assert "**kwargs" in details
    assert "positional" in details


def test_keyword_only_signature_passes():
    """Control: the sanctioned shape produces no finding."""
    source = '''
def submit_array_draw(*, renderer, widget, command_buffer, array_draw_plan, ctx):
    return ctx
'''
    assert findings_for_source("synthetic_clean.py", source) == []
