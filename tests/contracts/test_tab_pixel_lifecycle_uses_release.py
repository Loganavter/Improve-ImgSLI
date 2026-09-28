"""Tab pixel-store lifecycle uses the shared registry (plan_shared_pixel_registry wave 3).

Tab-owned full-res stores come from the ``load_pixel_store`` funnel and may
be shared registry views: their lifecycle must end via
``engine.store.shared_pixel_registry.release_store``, never via
``close_pixel_store``/bare ``close`` on the tab side. Direct ``close`` on a
view stays safe (``_SharedView.close`` self-releases), but the explicit seam
keeps ownership greppable and future-proof.

Scope: ``image_compare`` + ``multi_compare`` production code (``/tests/``
excluded — tests decode directly and own their stores). Gallery QuickLook
coarse path and video-export direct ``from_path`` decodes are excluded by
design (never funnel-sourced).
"""

from __future__ import annotations

import ast

from ._framework import ROOT, iter_py, parse, rel

TABS = [ROOT / "src" / "tabs" / "image_compare", ROOT / "src" / "tabs" / "multi_compare"]


def _uses_close_pixel_store(path):
    tree = parse(path)
    if tree is None:
        return []
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            if "close_pixel_store" in names:
                hits.append(f"{rel(path)}:{node.lineno} imports close_pixel_store")
        elif isinstance(node, ast.Import):
            if any(a.name.endswith("close_pixel_store") for a in node.names):
                hits.append(f"{rel(path)}:{node.lineno} imports close_pixel_store")
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "close_pixel_store":
                hits.append(f"{rel(path)}:{node.lineno} calls close_pixel_store()")
    return hits


def _prod_py():
    for tab in TABS:
        for py in iter_py(tab):
            if "__pycache__" in py.parts:
                continue
            if "tests" in py.parts:
                continue
            yield py


def test_tab_lifecycle_uses_release_store():
    offenders: list[str] = []
    for py in sorted(_prod_py()):
        offenders.extend(_uses_close_pixel_store(py))
    assert not offenders, (
        "Tab-owned pixel stores must end via shared_pixel_registry.release_store, "
        "not close_pixel_store (shared views; plan_shared_pixel_registry wave 3):\n  - "
        + "\n  - ".join(offenders)
    )
