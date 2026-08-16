"""AST contract: materialize_full / to_real_pil_copy / to_pil stay in allowlisted modules.

``to_pil`` was a full-frame store escape hatch (alias of
``materialize_full``); it used to leak into ``base_images.letterbox_pil``
(see pyvips-streaming-plan Phase 3) where a cache miss momentarily left a
full-res ``TiledPixelStore`` in the "stored" role and letterboxing
materialized the whole frame just to downscale it. The alias itself has
been deleted (no call sites left in ``src/``); the name stays in the
scanner so a reintroduced ``to_pil``/``materialize_full``/``to_real_pil_copy``
call outside the allowlist fails the suite.
"""

from __future__ import annotations

import ast

from tests.contracts._framework import ROOT, iter_py, rel

ALLOWLIST = {
    "src/shared/image_processing/tiled_pixel_store.py",
    # memmap-failure fallback in the unify large path (`to_real_pil_copy`).
    "src/shared/image_processing/pixel_ops/unify.py",
}

_FULL_FRAME_CALLS = {"materialize_full", "to_real_pil_copy", "to_pil"}


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
        if name in _FULL_FRAME_CALLS:
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
    assert not offenders, "Unexpected materialize/to_real_pil_copy/to_pil calls:\n" + "\n".join(
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