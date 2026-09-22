"""Single whole-image texture-upload queue owner (eng-total R5, pin not unify).

A supervisor recon on the merge base proved exactly ONE live owner of
whole-image texture-upload queueing exists: the image_compare surface
staging key-QImage-slot triples (``queue_texture_upload`` /
``queue_prepared_texture_upload`` in
``src/tabs/image_compare/canvas/texture_parts/upload_queue.py``,
PIL/store-to-QImage conversion with uid-dedup staging into
``widget.runtime_state._pending_texture_uploads``, flushed by the rhi
apply path with retention in the engine host cache).

The multi_compare ``pending_uploads`` list is a different stage -- a
sid-plus-pixel-source swap-decision intake
(``list[tuple[int, TiledPixelStore | QImage]]``) draining through the
engine swap machine (``resolve_swap_spec`` pure decision /
``apply_swap_spec`` orchestration), sharing no code path with the
image_compare staging list. Unify lost; this contract pins the single
owner so no second queue may appear:

* ``queue_texture_upload`` + ``queue_prepared_texture_upload`` are
  defined ONLY in the IC ``upload_queue`` module.
* the MC ``base_images`` module never mentions
  ``_pending_texture_uploads`` or ``queue_texture_upload``.
* the MC ``pending_uploads`` annotation stays the swap-feed shape and
  drains via ``resolve_swap_spec`` + ``apply_swap_spec``
  (through the pass-local ``_upload_slot`` orchestrator).
* no class with ``UploadQueue`` in its name exists under ``src``
  (in particular: no ``src/engine/gpu/upload_queue.py`` -- unify
  lost, the single owner above is already proven).
"""

from __future__ import annotations

import ast

import pytest

from ._framework import ROOT, iter_py, read, rel

pytestmark = pytest.mark.slow

IC_UPLOAD_QUEUE = (
    ROOT
    / "src"
    / "tabs"
    / "image_compare"
    / "canvas"
    / "texture_parts"
    / "upload_queue.py"
)
MC_BASE_IMAGES = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "base_images.py"
)

_QUEUE_FNS = ("queue_texture_upload", "queue_prepared_texture_upload")


def _parse(path):
    return ast.parse(read(path))


def _definers_of(*names):
    """Map each function name to the set of src files defining it."""
    definers: dict[str, set] = {name: set() for name in names}
    for path in iter_py(ROOT / "src"):
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        defined = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        for name in names:
            if name in defined:
                definers[name].add(path)
    return definers


def _method_node(tree: ast.Module, class_name: str, method: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == method:
                    return stmt
    return None


def _calls_self_method(func: ast.FunctionDef, target: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == target
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        for node in ast.walk(func)
    )


def _reads_self_attr(func: ast.FunctionDef, attr: str) -> bool:
    return any(
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        for node in ast.walk(func)
    )


def test_queue_fns_defined_only_in_ic_upload_queue():
    assert IC_UPLOAD_QUEUE.is_file(), (
        f"missing single upload-queue owner: {rel(IC_UPLOAD_QUEUE)}"
    )
    definers = _definers_of(*_QUEUE_FNS)
    for name in _QUEUE_FNS:
        assert definers[name] == {IC_UPLOAD_QUEUE}, (
            f"{name} must be defined ONLY in {rel(IC_UPLOAD_QUEUE)} "
            f"(single whole-image staging owner): "
            f"{sorted(rel(p) for p in definers[name])}"
        )


def test_mc_base_images_never_names_ic_queue():
    assert MC_BASE_IMAGES.is_file(), f"missing MC pass: {rel(MC_BASE_IMAGES)}"
    src = read(MC_BASE_IMAGES)
    assert "_pending_texture_uploads" not in src, (
        f"{rel(MC_BASE_IMAGES)} mentions _pending_texture_uploads: the MC "
        f"pending_uploads intake is a different stage (swap decisions), "
        f"never the IC staging list"
    )
    assert "queue_texture_upload" not in src, (
        f"{rel(MC_BASE_IMAGES)} mentions queue_texture_upload: MC must not "
        f"share the IC staging code path"
    )
    assert "queue_prepared_texture_upload" not in src, (
        f"{rel(MC_BASE_IMAGES)} mentions queue_prepared_texture_upload: MC "
        f"must not share the IC staging code path"
    )


def test_mc_pending_uploads_stays_swap_feed():
    tree = _parse(MC_BASE_IMAGES)
    annotations = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "pending_uploads"
        ):
            try:
                annotations[node.lineno] = ast.unparse(node.annotation).strip()
            except Exception:
                annotations[node.lineno] = ""
    assert annotations, (
        f"{rel(MC_BASE_IMAGES)} lost the pending_uploads annotation "
        f"(swap-feed shape pin)"
    )
    for lineno, annotation in annotations.items():
        assert "tuple[int" in annotation and "QImage" in annotation, (
            f"{rel(MC_BASE_IMAGES)}:{lineno} pending_uploads annotation drift: "
            f"got {annotation!r} (must stay the sid-plus-pixel-source "
            f"swap-feed shape)"
        )
    drain = _method_node(tree, "BaseImagesPass", "apply_pending_texture_ops")
    assert drain is not None, (
        f"{rel(MC_BASE_IMAGES)} lost apply_pending_texture_ops "
        f"(the swap-feed drain)"
    )
    assert _reads_self_attr(drain, "pending_uploads"), (
        "apply_pending_texture_ops must drain self.pending_uploads"
    )
    assert _calls_self_method(drain, "_upload_slot"), (
        "apply_pending_texture_ops must funnel each intake entry through "
        "the _upload_slot orchestrator"
    )
    upload_slot = _method_node(tree, "BaseImagesPass", "_upload_slot")
    assert upload_slot is not None, (
        f"{rel(MC_BASE_IMAGES)} lost _upload_slot (resolve-then-apply seam)"
    )
    assert _calls_self_method(upload_slot, "resolve_swap_spec"), (
        "_upload_slot must resolve each entry via resolve_swap_spec "
        "(engine pure decision)"
    )
    assert _calls_self_method(upload_slot, "_apply_swap_spec"), (
        "_upload_slot must apply each spec via _apply_swap_spec "
        "(engine apply_swap_spec orchestration)"
    )


def test_no_upload_queue_class_under_src():
    offenders = []
    for path in iter_py(ROOT / "src"):
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "UploadQueue" in node.name:
                offenders.append(f"{rel(path)}:{node.name}")
    assert offenders == [], (
        "UploadQueue classes must not exist under src (unify lost -- the "
        "IC upload_queue module is the single proven owner; in particular "
        "do NOT create src/engine/gpu/upload_queue.py): "
        f"{offenders}"
    )
