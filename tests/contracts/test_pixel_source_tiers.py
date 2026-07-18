"""AST contract: materialize_full / to_real_pil_copy stay in allowlisted modules."""

from __future__ import annotations

import ast

from tests.contracts._framework import ROOT, iter_py, rel

ALLOWLIST = {
    "src/shared/image_processing/tiled_pixel_store.py",
    "src/shared/image_processing/pixel_ops/unify.py",
    # Escape hatch: ``load_full_image`` spills via ``from_path`` then materializes.
    "src/shared/image_processing/progressive_loader.py",
    "src/tabs/image_compare/services/image_export/context_builder.py",
    "src/tabs/image_compare/services/image_export/service.py",
}


def _calls_materialize_or_to_real(path) -> list[tuple[str, int]]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = None
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        if name in {"materialize_full", "to_real_pil_copy"}:
            hits.append((name, node.lineno))
    return hits


def _receiver_chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return list(reversed(parts))


def _calls_resize_on_full_res(path) -> list[tuple[str, int]]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "resize":
            continue
        chain = _receiver_chain(node.func.value)
        if any(part.startswith("full_res_") for part in chain):
            hits.append((".".join(chain), node.lineno))
        elif chain and chain[0].startswith("full_res_"):
            hits.append((".".join(chain), node.lineno))
    return hits


def test_materialize_full_confined_to_allowlist():
    offenders: list[str] = []
    for path in iter_py(ROOT / "src"):
        rel_path = rel(path)
        if rel_path in ALLOWLIST or "/tests/" in rel_path:
            continue
        hits = _calls_materialize_or_to_real(path)
        if hits:
            offenders.append(f"{rel_path}: {hits}")
    assert not offenders, "Unexpected materialize/to_real_pil_copy calls:\n" + "\n".join(
        offenders
    )


def test_no_resize_on_full_res_identifiers():
    offenders: list[str] = []
    for path in iter_py(ROOT / "src"):
        rel_path = rel(path)
        if "/tests/" in rel_path:
            continue
        hits = _calls_resize_on_full_res(path)
        if hits:
            offenders.append(f"{rel_path}: {hits}")
    assert not offenders, "Unexpected .resize() on full_res_*:\n" + "\n".join(offenders)
