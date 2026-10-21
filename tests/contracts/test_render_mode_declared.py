"""C1 gate: the export-canvas objectName has exactly one definition.

Dogma: the export mode of the canvas is resolved from ONE signal — the
``objectName`` the exporter stamps on its offscreen widget. Before C1 that
string was repeated in the render context and in the frame setup, so a rename
in the exporter would leave both consumers silently reading ``"preview"`` (an
export frame rendered as interactive: wrong LOD, wrong pass set) with no test
noticing.

Rule: the string literal ``"gpu_export_canvas"`` exists only in
``src/ui/canvas_infra/rhi/render_mode.py`` (the definition) and the exporter
(``src/plugins/export/services/gpu_export_proxy.py``, which stamps it). Tests
may repeat it (they assert the contract). Every other ``src/`` copy is a
finding, docstrings included — a docstring that names the wire value is the
same second source of truth.

The two consumers must *reference* ``EXPORT_CANVAS_OBJECT_NAME`` and import it
from the definitions module, instead of comparing against a literal.

Allowlist: none — after C1 the tree has exactly two non-test copies (a
transfer, not a third copy).
"""

from __future__ import annotations

import ast

from tests.contracts._framework import ROOT, SRC, iter_py, parse, rel
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_render_mode_declared.py"

#: The one signal. Changing it is a two-file change (definition + exporter).
LITERAL = "gpu_export_canvas"
CONSTANT = "EXPORT_CANVAS_OBJECT_NAME"

DEFINITIONS = "src/ui/canvas_infra/rhi/render_mode.py"
DEFINITIONS_MODULE = "ui.canvas_infra.rhi.render_mode"
EXPORTER = "src/plugins/export/services/gpu_export_proxy.py"

#: Consumers that must go through the constant. Both resolve "am I drawing the
#: export canvas?" from this signal (render mode + LOD canvas-size input).
CONSUMERS: tuple[str, ...] = (
    "src/tabs/image_compare/canvas/render_context.py",
    "src/tabs/image_compare/canvas/rhi_renderer/use_cases/frame_setup.py",
)

#: Files allowed to hold the literal (the exporter stamps it, the definition
#: defines it). ``tests/`` is outside ``iter_py(SRC)`` by construction.
ALLOWED_COPIES = frozenset({DEFINITIONS, EXPORTER})


def _source_paths() -> list:
    return iter_py(SRC)


def literal_copies(sources: dict[str, str]) -> list[Finding]:
    """Every non-definition, non-exporter copy of the literal in *sources*."""
    findings: list[Finding] = []
    for path_text, source in sources.items():
        if path_text in ALLOWED_COPIES:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value == LITERAL
            ):
                findings.append(
                    Finding(
                        path_text,
                        "",
                        f"repeats the export-canvas objectName at line {node.lineno}; "
                        f"import {CONSTANT} from {DEFINITIONS_MODULE} instead",
                    )
                )
    return findings


def _references_constant(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Name) and node.id == CONSTANT for node in ast.walk(tree)
    )


def _imports_constant(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != DEFINITIONS_MODULE:
            continue
        if any(alias.name == CONSTANT for alias in node.names):
            return True
    return False


def consumer_findings() -> list[Finding]:
    findings: list[Finding] = []
    for path_text in CONSUMERS:
        tree = parse(ROOT / path_text)
        if tree is None:
            findings.append(Finding(path_text, "", "file disappeared — gate is blind"))
            continue
        if not _references_constant(tree):
            findings.append(
                Finding(
                    path_text,
                    "",
                    f"does not reference {CONSTANT} — it still decides export mode "
                    "from its own copy of the objectName",
                )
            )
        elif not _imports_constant(tree):
            findings.append(
                Finding(
                    path_text,
                    "",
                    f"references {CONSTANT} without importing it from "
                    f"{DEFINITIONS_MODULE} (a local re-definition is a third copy)",
                )
            )
    return findings


def findings() -> list[Finding]:
    sources = {rel(path): path.read_text(encoding="utf-8") for path in _source_paths()}
    return literal_copies(sources) + consumer_findings()


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_export_object_name_has_one_definition():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        f"`{LITERAL}` must exist only in {DEFINITIONS} (the definition) and the "
        f"exporter {EXPORTER} (which stamps it); every other consumer imports "
        f"`{CONSTANT}`. Offending copies:\n" + format_findings(open_findings)
    )


def test_allowlist_entries_are_documented_and_current():
    current = findings()
    problems = allowlist_problems(GATE, current)
    for finding in unexplained(GATE, current):
        problems.append(f"{finding.key}: uncovered finding — {finding.detail}")
    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_definition_and_exporter_still_hold_the_signal():
    """Non-vacuity: a rename of the constant must not make the gate blind.

    The gate's worth depends on the literal still being the real wire value
    and on the exporter still stamping it — otherwise "no copies found" would
    be indistinguishable from "the signal moved somewhere the scan cannot see".
    """
    definitions = parse(ROOT / DEFINITIONS)
    assert definitions is not None, f"{DEFINITIONS} is missing"
    assigned = [
        node.value.value
        for node in ast.walk(definitions)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == CONSTANT
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    assert assigned == [LITERAL], (
        f"{DEFINITIONS} must assign {LITERAL!r} to {CONSTANT}; found {assigned!r}. "
        "Update this gate with the rename."
    )

    exporter = parse(ROOT / EXPORTER)
    assert exporter is not None, f"{EXPORTER} is missing"
    assert any(
        isinstance(node, ast.Constant) and node.value == LITERAL
        for node in ast.walk(exporter)
    ), f"{EXPORTER} no longer stamps {LITERAL!r} — the single signal moved"

    assert any(rel(path) == EXPORTER for path in _source_paths()), (
        "the src scan does not see the exporter — the corpus root is wrong"
    )


def test_synthetic_third_copy_is_flagged():
    """Falsification: a consumer that repeats the literal is a finding."""
    synthetic = {CONSUMERS[0]: 'OBJECT = "gpu_export_canvas"\n'}
    flagged = literal_copies(synthetic)
    assert flagged, "a repeated objectName literal was not flagged"
    assert flagged[0].path == CONSUMERS[0]
    assert "line 1" in flagged[0].detail

    allowed = literal_copies({EXPORTER: f'widget.setObjectName("{LITERAL}")\n'})
    assert allowed == [], "the exporter's own stamp must stay allowed"


def test_consumer_without_the_constant_is_flagged():
    """Falsification: the consumer half cannot pass on a literal comparison."""
    assert not _references_constant(
        ast.parse('mode = "export" if name == "gpu_export_canvas" else "preview"\n')
    ), "a literal comparison was reported as a constant reference"
    assert _references_constant(
        ast.parse('mode = "export" if name == EXPORT_CANVAS_OBJECT_NAME else "preview"\n')
    ), "the constant reference predicate does not see a plain Name load"
    assert not _imports_constant(
        ast.parse("from ui.canvas_infra.rhi.render_mode import OTHER\n")
    ), "a different import was accepted as the constant import"
