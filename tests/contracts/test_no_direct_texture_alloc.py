"""No direct GPU texture allocation outside the engine tile service.

``src/engine/store/`` owns CPU-side pixel storage (memmap-backed
``TiledPixelStore``, pyramid levels, tile grids, tile-native pixel ops) and
must never allocate GPU textures itself — every ``QRhiTexture`` for tile
content is created by the engine tile services (``engine/cache`` residency,
``engine/gpu`` array/plain resources) or by the pinned tab-side resource
owners below. A tab module that calls ``newTexture*`` outside that owner set,
or that grows its own per-tile texture allocator helper, bypasses the
central residency/draw-plan agreement (see
docs/dev/rendering/tile-rendering-system.md "Summary of the invariant").

Dogma source: plan-engine-tab-migration-2026-09-14 Phase A1 (store-move).
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, iter_py, parse, rel

TABS = ROOT / "src" / "tabs"
STORE = ROOT / "src" / "engine" / "store"

# Tab modules allowed to call newTexture/newTextureArray, and why (mirrors
# test_no_private_grid's owner set; this test pins the subset direction only
# so the two files never fight over currency):
# - rhi_renderer/resources.py: whole-image 1x1 upload path + placeholder.
# - slot_resources.py: plain (non-array) path per-slot textures, residency
#   still decided by the service (BaseImagesPass._realize_tile_residency).
# - scene/renderer.py, */rhi_overlay_pass_base.py, magnifier_pass.py,
#   filename_overlay gpu_resources.py: 1x1 placeholders / overlay surfaces /
#   render targets — never tile-content grids.
_ALLOWED_TEXTURE_OWNERS = frozenset(
    {
        "src/tabs/image_compare/canvas/rhi_renderer/resources.py",
        "src/tabs/multi_compare/scene/passes/slot_resources.py",
        "src/tabs/multi_compare/scene/renderer.py",
        "src/tabs/image_compare/canvas/rhi_overlay_pass_base.py",
        "src/tabs/multi_compare/canvas/rhi_overlay_pass_base.py",
        "src/tabs/image_compare/canvas/features/magnifier/render/magnifier_pass.py",
        "src/tabs/image_compare/canvas/features/filename_overlay/render/gpu_resources.py",
    }
)

_TILE_ALLOCATOR_RE = re.compile(
    r"(tile.*texture|texture.*tile|alloc.*tile|tile.*alloc)", re.IGNORECASE
)


def _store_py() -> list:
    return sorted(STORE.rglob("*.py"))


def _code_names_and_attrs(path) -> list[tuple[int, str]]:
    tree = parse(path)
    if tree is None:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            hits.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute):
            hits.append((node.lineno, node.attr))
        elif isinstance(node, ast.ImportFrom) and node.module:
            hits.append((node.lineno, node.module.split(".")[-1]))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                hits.append((node.lineno, alias.name.split(".")[-1]))
    return hits


def test_engine_store_allocates_no_gpu_textures():
    """CPU-pixel ownership: engine/store never mints QRhi textures."""
    offenders: list[str] = []
    for py in _store_py():
        if "__pycache__" in py.parts:
            continue
        for lineno, name in _code_names_and_attrs(py):
            if "newTexture" in name or name == "QRhiTexture":
                offenders.append(
                    f"{rel(py)}:{lineno} references GPU allocator {name!r} "
                    f"(engine/store is CPU-pixel storage; GPU allocation "
                    f"lives in engine/cache + engine/gpu services)"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_tabs_allocate_textures_only_in_known_owners():
    """No tab-local newTexture* outside the pinned resource owners."""
    offenders: list[str] = []
    for py in iter_py(TABS):
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


def test_tabs_define_no_tile_texture_allocators():
    """Tabs never grow their own per-tile texture allocator helpers."""
    offenders: list[str] = []
    for py in iter_py(TABS):
        tree = parse(py)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                _TILE_ALLOCATOR_RE.search(node.name)
            ):
                offenders.append(
                    f"{rel(py)}:{node.lineno} defines tile-texture helper "
                    f"'{node.name}' (per-tile texture allocation is owned "
                    f"by the engine tile service)"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)
