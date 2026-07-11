"""Guard against reimplementing FullscreenUniformPassResources.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md, "Anti-patterns" ->
"Creating persistent QRhi resources ... anywhere except inside a
CanvasRenderPass's own initialize()/release() pair" plus the render-pass
resource-lifetime contract in general.

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
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, read, rel

_DOC = "docs/dev/QRHI_CANVAS_FEATURES.md"

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
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
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
