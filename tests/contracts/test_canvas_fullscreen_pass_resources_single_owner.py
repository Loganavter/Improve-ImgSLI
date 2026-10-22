"""Guard against reimplementing FullscreenUniformPassResources.

Dogma source: docs/dev/rendering/render-pass-contract.md (a pass owns its own
persistent QRhi resources — created in ``initialize()``, destroyed in
``release()``; every pass is a ``CanvasRenderPass``) plus
docs/dev/rendering/checklist.md.

Concrete incident: ``magnifier/passes.py`` had a ``_BorderDiskResources``
class that was a near-verbatim structural copy of
``rhi_feature_common.py::FullscreenUniformPassResources`` (same vertex
buffer, same blend factors, same 2xFloat2 vertex layout, same
initialize/ensure_items/prepare_vertex_buffer/release method shape) —
~100 lines of duplicated QRhi boilerplate that should have been a call to
the existing shared class parameterized with a different shader stem. This
test fingerprints that exact shape (a class defining
initialize/ensure_items/release methods plus self.uniform_buffers/self.srbs
list attributes) so a second hand-rolled copy fails CI instead of quietly
inflating a feature's passes.py again.

Not a ban on all custom render-pass resource classes — only on ones that
replicate this specific fullscreen-quad-with-per-item-uniform-buffer shape.
A pass that legitimately needs a different resource shape (e.g. per-item
texture bindings, like MagnifierPass's own mag_pipeline) does not match this
fingerprint and is not flagged.

R3b re-point (textured shape): the fullscreen-TEXTURED resource shape
(raster-upload overlay: vertex buffer + 64B uniform + sampler + RGBA8
texture + SRB + pipeline, ``initialize`` / ``prepare`` / ``record`` /
``release``) was owned tab-side by two ``FullscreenOverlayTexturePass``
mirrors until R3b mounted their last consumers (3 MC passes + IC drag)
onto ``engine.overlay.TexturedOverlayShell`` and retired both mirrors
atomically. The engine shell is now the SINGLE owner of that shape:
``_TEXTURED_OWNER`` below allowlists only the engine module, and
``test_textured_shape_has_single_engine_owner`` fails if any tab-side
class reintroduces the mirror. The uniform-shape guard above is untouched
(``rhi_feature_common.py`` still owns it until magnifier/arcs/filename
migrate -- out of R3b scope).
"""

from __future__ import annotations

import ast

import pytest

from ._framework import SRC, iter_py, parse, rel

pytestmark = pytest.mark.slow

_DOC = "docs/dev/rendering/render-pass-contract.md"

_ALLOWLIST = {
    # The single owner of this resource shape.
    "src/tabs/image_compare/canvas/rhi_feature_common.py",
}

_REQUIRED_METHODS = {"initialize", "ensure_items", "release"}
_REQUIRED_SELF_ATTRS = {"uniform_buffers", "srbs"}


def _self_attr_names(class_node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(class_node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "self":
                names.add(node.attr)
    return names


def _method_names(class_node: ast.ClassDef) -> set[str]:
    return {
        node.name
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _duplicate_resource_class_violations() -> list[str]:
    out: list[str] = []
    for path in iter_py(SRC):
        path_rel = rel(path)
        if path_rel in _ALLOWLIST:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = _method_names(node)
            if not _REQUIRED_METHODS.issubset(methods):
                continue
            attrs = _self_attr_names(node)
            if not _REQUIRED_SELF_ATTRS.issubset(attrs):
                continue
            out.append(
                f"{path_rel}:{node.lineno} class {node.name} reimplements the "
                f"initialize/ensure_items/release + uniform_buffers/srbs shape of "
                f"FullscreenUniformPassResources ({_ALLOWLIST!r}) — instantiate "
                f"that shared class (parameterized with your shader stem) instead "
                f"of hand-rolling a new resource-manager class (see {_DOC})"
            )
    return out


def test_no_duplicate_fullscreen_pass_resource_classes():
    violations = _duplicate_resource_class_violations()
    assert not violations, "\n  - " + "\n  - ".join(violations)


# ---------------------------------------------------------------------------
# R3b: textured shape has a single ENGINE owner (no tab-side mirrors).
# ---------------------------------------------------------------------------

# The single owner of the fullscreen-textured resource shape (engine only).
_TEXTURED_OWNER = "src/engine/overlay/textured.py"

# Retired tab-side mirror names: reintroducing any of them fails.
_RETIRED_TEXTURED_MIRRORS = frozenset({"FullscreenOverlayTexturePass"})


def test_textured_shape_has_single_engine_owner():
    """The textured overlay shape lives only in the engine shell.

    R3b retired both tab-side ``FullscreenOverlayTexturePass`` mirrors
    (IC + MC ``canvas/rhi_overlay_pass_base.py``) atomically with the
    last MC mount. Any class under ``src/`` reintroducing the mirror
    name fails here -- new raster passes mount
    ``engine.overlay.TexturedOverlayShell`` instead of hand-rolling
    (or mirroring) the texture/sampler/pipeline set.
    """
    violations: list[str] = []
    for path in iter_py(SRC):
        path_rel = rel(path)
        if path_rel == _TEXTURED_OWNER:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name in _RETIRED_TEXTURED_MIRRORS:
                violations.append(
                    f"{path_rel}:{node.lineno} class {node.name} reintroduces the "
                    f"retired tab-side textured mirror -- the single owner is "
                    f"{_TEXTURED_OWNER} (mount TexturedOverlayShell instead)"
                )
    assert not violations, "\n  - " + "\n  - ".join(violations)


def test_textured_owner_is_engine_only():
    """The textured-shape allowlist points at the engine shell only."""
    assert _TEXTURED_OWNER == "src/engine/overlay/textured.py", (
        f"textured single-owner drifted: {_TEXTURED_OWNER} -- re-pointing "
        f"it tab-side reopens the mirror the R3b retire closed"
    )
