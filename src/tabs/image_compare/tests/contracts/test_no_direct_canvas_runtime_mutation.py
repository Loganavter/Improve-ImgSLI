"""No direct CanvasRuntimeState mutation outside DerivedGpuState barrier.

Dogma for systemic Store→GPU divergence (left-on-both, log lie, 0.001 bbox):
CanvasRuntimeState (widget.runtime_state._stored_pil_images etc.) must only be
written via DerivedGpuState commit (derived_gpu_state.py) → upload_pil_images,
not by ad-hoc `state._stored_pil_images =` in use_cases/presenters.

Enforced via AST scan like test_no_direct_store_mutation.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import SRC, iter_py, read, rel

# Attributes of CanvasRuntimeState that are GPU shadow caches
CANVAS_RUNTIME_ATTRS = {
    "_stored_pil_images",
    "_source_pil_images",
    "_stored_image_ids",
    "_source_image_ids",
    "_letterbox_params",
    "_texture_upload_cache",
    "_qimage_by_uid_cache",
}

# Files allowed to write them (the barrier) — all canvas infra is part of barrier
ALLOWED_WRITERS = {
    "src/tabs/image_compare/canvas/texture_parts/base_images.py",
    "src/tabs/image_compare/canvas/presentation/derived_gpu_state.py",
    "src/tabs/image_compare/canvas/state.py",  # definition
    "src/tabs/image_compare/canvas/render_context.py",
    "src/tabs/image_compare/canvas/texture_parts/upload_queue.py",
    "src/tabs/image_compare/canvas/texture_parts/layers.py",
    "src/tabs/image_compare/canvas/presentation/plan_applicator.py",
    "src/shared/rendering/host_texture_cache.py",
    "src/ui/canvas_infra/rhi/rhi_render.py",
}


def _is_canvas_runtime_write(node: ast.AST) -> str | None:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign) and node.target is not None:
        targets = [node.target]
    else:
        return None
    for t in targets:
        if isinstance(t, ast.Attribute) and t.attr in CANVAS_RUNTIME_ATTRS:
            # check base is something like state._stored_pil_images or widget.runtime_state._*
            return t.attr
        if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute) and t.value.attr in CANVAS_RUNTIME_ATTRS:
            return t.value.attr
    return None


def test_no_direct_canvas_runtime_mutation():
    offenders = []
    for p in iter_py(SRC):
        rp = rel(p)
        if rp in ALLOWED_WRITERS:
            continue
        if "tests" in rp or "__pycache__" in rp:
            continue
        try:
            tree = ast.parse(read(p))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            attr = _is_canvas_runtime_write(node)
            if attr:
                offenders.append(f"{rp}:{node.lineno} — {attr} = ...")
    assert not offenders, (
        "Direct CanvasRuntimeState mutation outside DerivedGpuState barrier — "
        "use DerivedGpuState → upload_pil_images instead:\n  " + "\n  ".join(offenders)
    )
