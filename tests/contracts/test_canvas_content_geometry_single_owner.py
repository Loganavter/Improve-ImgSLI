"""Guard against reintroducing hand-rolled canvas-bounds/split-position math.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md, "Mechanical
duplication guard". Three independent call sites (``gpu_export_scene.py``,
``magnifier/snapshot_store.py``, ``divider/commands.py``) each hand-rolled a
copy of "recombine split-position with padded-canvas geometry" before that
refactor — twice within the same working session, despite the doc already
stating the single-owner rule in prose. A design doc alone didn't stop it;
this test scans source so a fourth copy fails CI instead of drifting silently
from ``viewport/zoom.py``'s formula.

Two independent rules, both grep/AST-based (no runtime execution):

1. ``VirtualCanvasLayout.canvas_bounds`` / ``.content_bounds`` attribute
   access is allowlisted. Any other file reading these fields directly is
   reconstructing canvas-bounds math by hand instead of calling
   ``resolve_canvas_content_geometry(_for_store)`` /
   ``resolve_canvas_clip_rect_px`` (``ui/canvas_infra/scene/frame_geometry.py``).

   The allowlist historically included the CPU-pixel-baking video-export chain
   (``snapshot_render_plan_builder.py``, ``video_snapshot_rendering/``) when
   that path baked padding into PIL. Snapshot prepare now keeps unpadded
   stores and expresses pads in geometry (see
   ``docs/dev/rendering/rendering-model.md``); those modules remain allowlisted
   only where they still read ``canvas_bounds`` to *derive* clip/geometry, not
   to reintroduce pixel bake.

2. ``split_position_visual`` (or ``split_visual``) must never be combined via
   arithmetic (``BinOp``) with ``content_rect``/``canvas_bounds``/
   ``content_offset``/``canvas_w``/``canvas_h``-shaped names in the same
   function body, outside ``viewport/zoom.py`` and ``viewport/pipeline.py``
   (the doc-endorsed single owner of split-position math) and their tests.
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, read, rel

_DOC = "docs/dev/QRHI_CANVAS_FEATURES.md"

_BOUNDS_ALLOWLIST = {
    # Producer side: the single owner of canvas-bounds -> widget-px / clip-rect
    # resolution.
    "src/ui/canvas_infra/scene/frame_geometry.py",
    "src/ui/canvas_infra/scene/layout_requirements.py",
    # Defines VirtualCanvasLayout/NormalizedBounds themselves.
    "src/shared/rendering/layout_contract.py",
    # Snapshot prepare / headless export still read canvas_bounds to derive
    # geometry and clip (unpadded stores + CanvasGeometry), not to bake
    # padding into pixels. Keep allowlisted so this guard stays about
    # split-position duplication, not prepare.
    "src/tabs/image_compare/services/snapshot_render_plan_builder.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/geometry.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/prepare.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/prepare_hit.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/prepare_miss.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/store_rebuild.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/plan_build.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/render.py",
    "src/tabs/image_compare/services/video_snapshot_rendering/renderer.py",
}

_SPLIT_NAMES = {"split_position_visual", "split_visual"}
_GEOMETRY_NAMES = {
    "content_rect",
    "canvas_bounds",
    "content_offset",
    "canvas_w",
    "canvas_h",
}

_SPLIT_OWNER_ALLOWLIST = {
    "src/ui/canvas_infra/viewport/zoom.py",
    "src/ui/canvas_infra/viewport/pipeline.py",
}


def _is_allowlisted(path_rel: str, allowlist: set[str]) -> bool:
    if path_rel in allowlist:
        return True
    # Test files for an allowlisted module, or anything under tests/, are not
    # part of the production single-owner surface.
    if path_rel.startswith("tests/"):
        return True
    return False


def _name_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _bounds_access_violations() -> list[str]:
    out: list[str] = []
    for path in iter_py(SRC):
        path_rel = rel(path)
        if _is_allowlisted(path_rel, _BOUNDS_ALLOWLIST):
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in (
                "canvas_bounds",
                "content_bounds",
            ):
                out.append(
                    f"{path_rel}:{node.lineno} accesses .{node.attr} directly "
                    f"(call resolve_canvas_content_geometry(_for_store) / "
                    f"resolve_canvas_clip_rect_px in ui/canvas_infra/scene/"
                    f"frame_geometry.py instead — see {_DOC})"
                )
    return out


def _collects_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        name = _name_of(sub)
        if name:
            names.add(name)
    return names


def _split_arithmetic_violations() -> list[str]:
    out: list[str] = []
    for path in iter_py(SRC):
        path_rel = rel(path)
        if _is_allowlisted(path_rel, _SPLIT_OWNER_ALLOWLIST):
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.BinOp):
                    continue
                operand_names = _collects_names(node.left) | _collects_names(node.right)
                has_split = bool(operand_names & _SPLIT_NAMES)
                has_geometry = bool(operand_names & _GEOMETRY_NAMES)
                if has_split and has_geometry:
                    out.append(
                        f"{path_rel}:{node.lineno} in {func.name}() combines "
                        f"split_position_visual/split_visual with canvas/content "
                        f"geometry via arithmetic — this is the exact shape of the "
                        f"three deleted duplicates (gpu_export_scene.py, "
                        f"snapshot_store.py, divider/commands.py); route through "
                        f"viewport/zoom.py's formula or resolve_axis_position instead "
                        f"(see {_DOC})"
                    )
    return out


def test_no_direct_canvas_bounds_access_outside_allowlist():
    violations = _bounds_access_violations()
    assert not violations, "\n  - " + "\n  - ".join(violations)


def test_no_hand_rolled_split_position_geometry_arithmetic():
    violations = _split_arithmetic_violations()
    assert not violations, "\n  - " + "\n  - ".join(violations)
