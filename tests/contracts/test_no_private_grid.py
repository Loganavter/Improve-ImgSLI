"""Tabs own no tile grid/cache lattice and allocate no tile texture privately.

The grid + slot lattice lives only in ``TileTextureService``
(``src/engine/cache/tile_texture_service.py``): tabs read grids via
``grid_for``/``register_source`` and slots via ``slot_for``, and every
per-tile ``QRhiTexture`` allocation happens in a known resource owner
(whole-image 1x1 path, plain-path slot textures, overlay/placeholder
surfaces — enumerated below). A tab module that builds its own
``UniformTileGrid``, its own slot allocator, its own ``register_source``/
``slot_for`` bookkeeping, or a new ``newTexture*`` call site breaks this
seal.

Dogma source: task-engine-1a-seal-2026-09-14 (Engine W1A: seal),
invariant (a).
"""

from __future__ import annotations

import ast

from ._framework import ROOT, iter_py, parse, rel

TABS = ROOT / "src" / "tabs"

# Grid/slot-lattice symbols owned exclusively by TileTextureService. Matched
# as CODE identifiers (imports + Name/Attribute use) via AST — comments or
# docstrings that merely mention the service's own class (e.g. explaining
# that the allocator opens a new array) are documentation, not a private
# lattice, and stay allowed.
_LATTICE_NAMES = frozenset(
    {
        "UniformTileGrid",
        "build_uniform_tile_grid",
        "TileSlotAllocator",
        "_TileSlotAllocator",
    }
)

# Non-tile classes that legitimately define a ``slot_for`` of their own,
# unrelated to TileTextureService's tile-slot lattice. Scoped by class name so
# the rule still fails on any *new* tab-local tile bookkeeping.
_SLOT_FOR_UNRELATED_CLASSES = frozenset({"GlyphAtlas"})

# Tab modules allowed to call newTexture/newTextureArray, and why:
# - rhi_renderer/resources.py: whole-image 1x1 upload path + placeholder.
# - slot_resources.py: plain (non-array) path per-slot textures, residency
#   still decided by the service (BaseImagesPass._realize_tile_residency).
# - scene/renderer.py, magnifier_pass.py,
#   filename_overlay gpu_resources.py: 1x1 placeholders / overlay surfaces /
#   render targets — never tile-content grids.
# R3b: both */rhi_overlay_pass_base.py mirrors retired (their overlay
# surfaces moved into engine.overlay.TexturedOverlayShell) -- entries
# removed deliberately, not by accident.
_ALLOWED_TEXTURE_OWNERS = frozenset(
    {
        "src/tabs/image_compare/canvas/rhi_renderer/resources.py",
        "src/tabs/multi_compare/scene/passes/slot_resources.py",
        "src/tabs/multi_compare/scene/renderer.py",
        "src/tabs/image_compare/canvas/features/magnifier/render/magnifier_pass.py",
        "src/tabs/image_compare/canvas/features/filename_overlay/render/gpu_resources.py",
    }
)


def _tab_py() -> list:
    return iter_py(TABS)


def _lattice_uses_in(path) -> list[tuple[int, str]]:
    tree = parse(path)
    if tree is None:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[-1] in _LATTICE_NAMES:
                hits.append((node.lineno, node.module))
            for alias in node.names:
                if alias.name in _LATTICE_NAMES:
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] in _LATTICE_NAMES:
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.Name):
            if node.id in _LATTICE_NAMES:
                hits.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute):
            if node.attr in _LATTICE_NAMES:
                hits.append((node.lineno, node.attr))
    return hits


def test_tabs_build_no_tile_grids():
    leaks: list[str] = []
    for py in _tab_py():
        for lineno, name in _lattice_uses_in(py):
            leaks.append(
                f"{rel(py)}:{lineno} uses grid/slot lattice {name!r} in code — "
                f"grids and slots live only in TileTextureService "
                f"(tabs read via grid_for/register_source/slot_for)"
            )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_tabs_define_no_grid_or_slot_bookkeeping():
    leaks: list[str] = []
    for py in _tab_py():
        tree = parse(py)
        if tree is None:
            continue
        # A few non-tile classes legitimately use the name ``slot_for`` for
        # their own unrelated lookup (the filename_overlay SDF glyph atlas:
        # ``GlyphAtlas.slot_for(ch) -> GlyphSlot``). The dogmas here are about
        # TileTextureService tile-slot bookkeeping, so allowlist those classes
        # explicitly rather than weakening the rule.
        allowed_methods: set[int] = set()
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name in _SLOT_FOR_UNRELATED_CLASSES:
                for stmt in cls.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        allowed_methods.add(id(stmt))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in ("register_source", "slot_for")
                and id(node) not in allowed_methods
            ):
                leaks.append(
                    f"{rel(py)}:{node.lineno} defines '{node.name}' "
                    f"(grid/slot bookkeeping is owned by "
                    f"TileTextureService; tabs call, never define)"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_tile_texture_allocation_stays_in_known_owners():
    offenders: list[str] = []
    for py in _tab_py():
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "newTexture" in line and rel(py) not in _ALLOWED_TEXTURE_OWNERS:
                offenders.append(
                    f"{rel(py)}:{lineno} allocates a QRhi texture outside "
                    f"the known resource owners ({line.strip()[:100]!r})"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_allowed_texture_owners_are_current():
    actual = {
        rel(py)
        for py in _tab_py()
        if "newTexture" in py.read_text(encoding="utf-8")
    }
    assert actual == set(_ALLOWED_TEXTURE_OWNERS), (
        "texture-owner set drifted:\n"
        f"  added: {sorted(actual - set(_ALLOWED_TEXTURE_OWNERS))}\n"
        f"  removed: {sorted(set(_ALLOWED_TEXTURE_OWNERS) - actual)}\n"
        "update the allowlist deliberately, not by accident"
    )
