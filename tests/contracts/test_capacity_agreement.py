"""C1 gate: the tile-array capacity and the service that allocates it agree.

Dogma: the array texture the image-compare pool builds is sized from
``resources._ARRAY_CAPACITY`` (derived from the byte budget and the expected
canvas tile count), but ``TileTextureService`` — the object that decides when
to open the *next* array — is constructed elsewhere with its own default
``max_array_size`` (``DEFAULT_MAX_ARRAY_SIZE = 2048``). Today those two numbers
disagree: ``_ARRAY_CAPACITY`` is 2032 (``_TILE_CACHE_BUDGET_BYTES //
_ARRAY_LAYER_BYTES``), so the service believes it may fill 2048 layers of the
array the SRB binds at index 0 (``engine/gpu/array_resources.py`` binds only
``tile_arrays[0]``) — 16 layers that the bound array cannot address. Nothing
crashes: the extra layers are simply never sampled, or a second array is opened
late.

Rule:

(a) numeric — ``resources._ARRAY_CAPACITY == TileTextureService()._max_array_size``;
(b) AST — every ``TileTextureService(...)`` call in non-test source, in a module
    that also references an array-capacity surface (``_ARRAY_*``,
    ``_TILE_CACHE_BUDGET_BYTES``, ``SLOT_*``, ``DEFAULT_MAX_ARRAY_SIZE``,
    ``max_array_size``), must pass ``max_array_size=`` explicitly. The correct
    pattern already exists at ``engine/gpu/tiled_image_view.py`` (the streaming
    view passes the capacity it computed); export-only fallbacks that never
    touch an array are outside the rule by construction.

The gate walks every module in ``src/`` and every call site — it does not pin
the one renderer it knows about.

Allowlist: one entry per call site plus the numeric mismatch (C3).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.contracts._framework import SRC, iter_py, rel
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_capacity_agreement.py"

RESOURCES = "src/tabs/image_compare/canvas/rhi_renderer/resources.py"
CAPACITY_SYMBOL = "_ARRAY_CAPACITY"

#: Names that mark a module as living on the tile-array path (so a default
#: service there is a real capacity disagreement, not an unrelated pool).
CAPACITY_SURFACE = re.compile(
    r"(array_capacity|array_layer|tile_cache_budget|max_array_size|^slot_)",
    re.IGNORECASE,
)

SERVICE = "TileTextureService"
EXPLICIT_KWARG = "max_array_size"


# ---------------------------------------------------------------------------
# (a) numeric
# ---------------------------------------------------------------------------


def numeric_findings() -> list[Finding]:
    from engine.cache.tile_texture_service import TileTextureService
    from tabs.image_compare.canvas.rhi_renderer import resources

    pool_capacity = int(resources._ARRAY_CAPACITY)
    # The service keeps the limit on its slot allocator (the object that
    # actually opens the next array); there is no public accessor.
    service_capacity = int(TileTextureService()._slot_allocator._max_array_size)
    if pool_capacity == service_capacity:
        return []
    return [
        Finding(
            RESOURCES,
            CAPACITY_SYMBOL,
            f"the pool sizes its array for {pool_capacity} layers but a "
            f"default-constructed {SERVICE} allocates up to {service_capacity} — "
            f"{service_capacity - pool_capacity} layers the SRB-bound "
            "`tile_arrays[0]` cannot address",
        )
    ]


# ---------------------------------------------------------------------------
# (b) call sites
# ---------------------------------------------------------------------------


def _references_capacity_surface(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        name = ""
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.alias):
            name = node.name.rsplit(".", 1)[-1]
        if name and CAPACITY_SURFACE.search(name):
            return True
    return False


def _call_symbols(tree: ast.Module) -> dict[int, str]:
    """``id(call) -> enclosing symbol`` (module-level calls map to ``""``)."""
    symbols: dict[int, str] = {}

    def walk(node: ast.AST, prefix: str):
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol = f"{prefix}{child.name}"
                for inner in ast.walk(child):
                    if isinstance(inner, ast.Call):
                        symbols.setdefault(id(inner), symbol)
                walk(child, f"{symbol}.")

    walk(tree, "")
    return symbols


def _missing_explicit_kwarg(call: ast.Call) -> bool:
    return not any(
        keyword.arg == EXPLICIT_KWARG for keyword in call.keywords
    )


def call_site_findings_for_source(path_text: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [Finding(path_text, "", "unparseable source — gate is blind")]
    if not _references_capacity_surface(tree):
        return []
    symbols = _call_symbols(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != SERVICE:
            continue
        if not _missing_explicit_kwarg(node):
            continue
        symbol = symbols.get(id(node), "")
        findings.append(
            Finding(
                path_text,
                symbol,
                f"constructs {SERVICE}(...) at line {node.lineno} without "
                f"`{EXPLICIT_KWARG}=` — it inherits the {SERVICE} default and "
                "disagrees with the capacity this module's array uses",
            )
        )
    return findings


def call_site_findings() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_py(SRC):
        findings.extend(
            call_site_findings_for_source(
                rel(path), path.read_text(encoding="utf-8")
            )
        )
    return findings


def findings() -> list[Finding]:
    return numeric_findings() + call_site_findings()


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_array_capacity_agrees_with_the_tile_service():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        "The tile-array capacity and every TileTextureService that allocates it "
        "must agree: a service that defaults `max_array_size` can fill layers "
        "the SRB-bound `tile_arrays[0]` cannot address. Offenders:\n"
        + format_findings(open_findings)
        + "\n\nC3 passes the computed capacity through to every call site."
    )


def test_allowlist_entries_are_documented_and_current():
    current = findings()
    problems = allowlist_problems(GATE, current)
    for finding in unexplained(GATE, current):
        problems.append(f"{finding.key}: uncovered finding — {finding.detail}")
    assert not problems, "Allowlist problems:\n" + "\n".join(
        f"  {problem}" for problem in problems
    )


def test_correct_pattern_is_already_visible():
    """Non-vacuity: the sanctioned call site is in the corpus and passes the rule.

    ``engine/gpu/tiled_image_view.py`` passes ``max_array_size=`` explicitly —
    if the scan cannot see that module (or the predicate stops distinguishing
    compliant from non-compliant calls), every green here is false.
    """
    path = "src/engine/gpu/tiled_image_view.py"
    source = (SRC / "engine" / "gpu" / "tiled_image_view.py").read_text(encoding="utf-8")
    assert _references_capacity_surface(ast.parse(source)), (
        f"{path} no longer references an array-capacity surface — the rule's "
        "scope detection regressed"
    )
    assert call_site_findings_for_source(path, source) == [], (
        f"{path} passes `{EXPLICIT_KWARG}=` and must stay clean"
    )


def test_default_constructed_service_in_an_array_module_is_flagged():
    """Falsification: a default service next to a capacity constant is a finding."""
    source = '''
from .resources import _ARRAY_CAPACITY
from engine.cache.tile_texture_service import TileTextureService


class Renderer:
    def __init__(self):
        self.tile_service = TileTextureService()

    def initialize(self, rhi):
        self.tile_service = TileTextureService(max_tile_extent=2048,
                                                max_array_size=_ARRAY_CAPACITY)
'''
    flagged = call_site_findings_for_source("synthetic_renderer.py", source)
    assert len(flagged) == 1, [finding.detail for finding in flagged]
    assert flagged[0].symbol == "Renderer.__init__"
    assert "line 8" in flagged[0].detail

    unrelated = "from x import y\nservice = TileTextureService()\n"
    assert call_site_findings_for_source("synthetic_pool.py", unrelated) == [], (
        "a module without an array-capacity surface must not be flagged"
    )
