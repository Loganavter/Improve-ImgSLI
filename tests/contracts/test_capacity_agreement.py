"""C3 gate: the tile-array capacity and the service that allocates it agree.

Dogma: each compare tab sizes the texture array its SRB binds
(``tile_arrays[0]`` only — ``engine/gpu/array_resources.py`` binds index 0) from
a per-tab ``_ARRAY_CAPACITY`` constant. ``TileTextureService`` — the object that
decides when to open the *next* array — is constructed elsewhere and *defaults*
to ``DEFAULT_MAX_ARRAY_SIZE = 2048``, so a default-constructed service can hand
out layers the bound array cannot address: ``_ARRAY_CAPACITY`` is a per-tab
derivation (byte budget / expected tile count), not the service default. The
renderer must pass the same per-tab capacity at every construction site.

Rule:

(a) behavioural — construct each tab's real array-resource owner against a fake
    QRhi and record the ``layerCount`` argument passed to
    ``newTextureArray`` for ``tile_arrays[0]``; it must equal the
    ``max_array_size`` the renderer's own ``TileTextureService`` carries.
    Compared as created, never constant-vs-constant: a third copy of the number
    would still drift alongside the array it is supposed to describe.

(b) AST — every ``TileTextureService(...)`` call in non-test source, in a module
    that also references an array-capacity surface (``_ARRAY_*``,
    ``_TILE_CACHE_BUDGET_BYTES``, ``SLOT_*``, ``DEFAULT_MAX_ARRAY_SIZE``,
    ``max_array_size``), must pass ``max_array_size=`` explicitly. In the two
    renderer modules that own a tab's SRB-bound array the argument must name
    that tab's ``_ARRAY_CAPACITY`` and import it from the module that sizes the
    array — never a re-derived literal (that is exactly the drift this gate
    exists to catch). The correct pattern for an already-computed local value
    exists at ``engine/gpu/tiled_image_view.py``; export-only fallbacks that
    never touch an array are outside the rule by construction.

The gate walks every module in ``src/`` and every call site — it does not pin
the one renderer it knows about.

Allowlist: none (C3 drained the five entries this gate shipped with).
"""

from __future__ import annotations

import ast
import re
from types import SimpleNamespace

from tests.contracts._framework import SRC, iter_py, rel
from tests.contracts.canvas_gates_allowlist import (
    Finding,
    allowlist_problems,
    format_findings,
    unexplained,
)

GATE = "test_capacity_agreement.py"

CAPACITY_SYMBOL = "_ARRAY_CAPACITY"

#: Renderer module -> (module suffix its ``_ARRAY_CAPACITY`` is imported from,
#: the module that actually sizes the array). ``max_array_size`` at a
#: ``TileTextureService`` site in one of these modules must name the tab's
#: constant, imported from the owning module.
ARRAY_CAPACITY_OWNERS: dict[str, tuple[str, str]] = {
    "src/tabs/image_compare/canvas/rhi_renderer/renderer.py": (
        "resources",
        "src/tabs/image_compare/canvas/rhi_renderer/resources.py",
    ),
    "src/tabs/multi_compare/scene/renderer.py": (
        "base_images",
        "src/tabs/multi_compare/scene/passes/base_images.py",
    ),
}

#: Names that mark a module as living on the tile-array path (so a default
#: service there is a real capacity disagreement, not an unrelated pool).
CAPACITY_SURFACE = re.compile(
    r"(array_capacity|array_layer|tile_cache_budget|max_array_size|^slot_)",
    re.IGNORECASE,
)

SERVICE = "TileTextureService"
EXPLICIT_KWARG = "max_array_size"


# ---------------------------------------------------------------------------
# (a) behavioural: the array as created vs the service that allocates it
# ---------------------------------------------------------------------------


class _FakeTexture:
    def __init__(self) -> None:
        self.name = b""

    def setName(self, name) -> None:
        self.name = name

    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        pass


class _RecordingFakeRhi:
    """Fake QRhi that records the ``layerCount`` of every texture array."""

    def __init__(self) -> None:
        self.texture_array_layer_counts: list[int] = []

    def newTextureArray(self, _fmt, layer_count, _size, _samples, _flags):
        self.texture_array_layer_counts.append(int(layer_count))
        return _FakeTexture()


def _image_compare_array_probe() -> tuple[int, int, int]:
    """``(layerCount, service max_array_size, array_capacity)`` for IC."""
    from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer

    renderer = RhiCanvasRenderer()
    rhi = _RecordingFakeRhi()
    renderer.resources.rhi = rhi
    # The real construction path the renderer's SRB goes through.
    renderer.resources.array_resources._ensure_tile_array(0)
    layer_count = rhi.texture_array_layer_counts[0]
    service_capacity = int(renderer.tile_service._slot_allocator._max_array_size)
    array_capacity = int(renderer.resources.array_resources._array_capacity)
    return layer_count, service_capacity, array_capacity


def _multi_compare_array_probe() -> tuple[int, int, int]:
    """``(layerCount, service max_array_size, array_capacity)`` for MC."""
    from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer

    renderer = MultiCompareRhiRenderer(SimpleNamespace())
    # BaseImagesPass is a manifest singleton (RENDER_PASSES), so a previous
    # probe may already have built its array resources against another fake.
    renderer.image_pass.release()
    try:
        rhi = _RecordingFakeRhi()
        renderer.rhi = rhi
        renderer.sampler = object()
        # The real lazy construction path BaseImagesPass uses each frame.
        renderer.image_pass._ensure_array_resources(renderer)
        assert renderer.image_pass.array_resources is not None
        renderer.image_pass.array_resources._ensure_tile_array(0)
        layer_count = rhi.texture_array_layer_counts[0]
        service_capacity = int(renderer.tile_service._slot_allocator._max_array_size)
        array_capacity = int(renderer.image_pass.array_resources._array_capacity)
        return layer_count, service_capacity, array_capacity
    finally:
        renderer.image_pass.release()


_ARRAY_PROBES = (
    (
        "image-compare",
        "src/tabs/image_compare/canvas/rhi_renderer/renderer.py",
        _image_compare_array_probe,
    ),
    (
        "multi-compare",
        "src/tabs/multi_compare/scene/renderer.py",
        _multi_compare_array_probe,
    ),
)


def capacity_findings() -> list[Finding]:
    findings: list[Finding] = []
    for label, renderer_path, probe in _ARRAY_PROBES:
        layer_count, service_capacity, array_capacity = probe()
        if layer_count == service_capacity:
            continue
        findings.append(
            Finding(
                renderer_path,
                "",
                f"{label}: `tile_arrays[0]` is created for {layer_count} layers "
                f"(ArrayResources._array_capacity={array_capacity}) but the "
                f"renderer's {SERVICE} allocates up to {service_capacity} — "
                f"{service_capacity - layer_count} layers the SRB-bound array "
                "cannot address; pass the tab's _ARRAY_CAPACITY at the site that "
                f"constructs the {SERVICE}",
            )
        )
    return findings


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


def _explicit_kwarg(call: ast.Call) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == EXPLICIT_KWARG:
            return keyword.value
    return None


def _imports_symbol_from(tree: ast.Module, name: str, module_suffix: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.module.rsplit(".", 1)[-1] != module_suffix:
            continue
        if any(alias.name == name for alias in node.names):
            return True
    return False


def call_site_findings_for_source(path_text: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [Finding(path_text, "", "unparseable source — gate is blind")]
    if not _references_capacity_surface(tree):
        return []
    symbols = _call_symbols(tree)
    owner = ARRAY_CAPACITY_OWNERS.get(path_text)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != SERVICE:
            continue
        symbol = symbols.get(id(node), "")
        value = _explicit_kwarg(node)
        if value is None:
            findings.append(
                Finding(
                    path_text,
                    symbol,
                    f"constructs {SERVICE}(...) at line {node.lineno} without "
                    f"`{EXPLICIT_KWARG}=` — it inherits the {SERVICE} default and "
                    "disagrees with the capacity this module's array uses",
                )
            )
            continue
        if owner is None:
            continue
        module_suffix, owner_path = owner
        if not (isinstance(value, ast.Name) and value.id == CAPACITY_SYMBOL):
            findings.append(
                Finding(
                    path_text,
                    symbol,
                    f"constructs {SERVICE}(...) at line {node.lineno} with "
                    f"`{EXPLICIT_KWARG}={ast.unparse(value)}` — it must pass the "
                    f"tab's `{CAPACITY_SYMBOL}` (the constant {owner_path} sizes "
                    "the array from), never a re-derived number",
                )
            )
        if not _imports_symbol_from(tree, CAPACITY_SYMBOL, module_suffix):
            findings.append(
                Finding(
                    path_text,
                    symbol,
                    f"uses `{CAPACITY_SYMBOL}` at line {node.lineno} without "
                    f"importing it from the module that sizes the array "
                    f"(`{module_suffix}`) — a local re-derivation drifts",
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
    return capacity_findings() + call_site_findings()


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_created_array_capacity_agrees_with_the_tile_service():
    open_findings = unexplained(GATE, findings())
    assert not open_findings, (
        "The tile-array capacity and every TileTextureService that allocates it "
        "must agree: a service that keeps its own `max_array_size` can fill "
        "layers the SRB-bound `tile_arrays[0]` cannot address. Offenders:\n"
        + format_findings(open_findings)
        + "\n\nPass the tab's _ARRAY_CAPACITY at every construction site."
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


def test_rederived_capacity_in_an_array_owner_is_flagged():
    """Falsification: `max_array_size=2048` is not the tab's shared constant."""
    source = '''
from .resources import _ARRAY_CAPACITY
from engine.cache.tile_texture_service import TileTextureService


class RhiCanvasRenderer:
    def __init__(self):
        self.tile_service = TileTextureService(max_array_size=2048)
'''
    flagged = call_site_findings_for_source(
        "src/tabs/image_compare/canvas/rhi_renderer/renderer.py", source
    )
    assert len(flagged) == 1, [finding.detail for finding in flagged]
    assert "re-derived number" in flagged[0].detail
