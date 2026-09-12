"""Preview-at-load stays on the display tier (PIL only, never TiledPixelStore)."""

from __future__ import annotations

import ast
import inspect

from PIL import Image

from shared.image_processing.progressive_loader import load_preview_image
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.state.document import DocumentModel
from tests.contracts._framework import ROOT, iter_py, rel


def test_document_preview_fields_are_pil_only():
    hints = DocumentModel.__annotations__
    assert hints["preview_image1"] == "Optional[Image.Image]"
    assert hints["preview_image2"] == "Optional[Image.Image]"
    assert "TiledPixelStore" not in hints["preview_image1"]
    assert "TiledPixelStore" not in hints["preview_image2"]


def test_load_preview_image_is_display_tier_pil():
    sig = inspect.signature(load_preview_image)
    assert sig.return_annotation in {Image.Image | None, "Image.Image | None"}


def test_load_preview_image_never_returns_tiled_store(tmp_path):
    path = tmp_path / "tiny.png"
    Image.new("RGBA", (32, 24), (1, 2, 3, 255)).save(path)
    preview = load_preview_image(str(path))
    assert preview is not None
    assert isinstance(preview, Image.Image)
    assert not isinstance(preview, TiledPixelStore)


def _maybe_wrap_calls_in_preview_true_branch(path) -> list[tuple[str, int]]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.get_source_segment(text, node.test) or ""
        if "is_preview" not in test_src:
            continue
        for child in ast.walk(node):
            if child is node:
                continue
            # Only inspect the true branch (preview path), not else/elif.
            if not any(child is stmt or child in ast.walk(stmt) for stmt in node.body):
                continue
            if not isinstance(child, ast.Call):
                continue
            name = None
            if isinstance(child.func, ast.Attribute):
                name = child.func.attr
            elif isinstance(child.func, ast.Name):
                name = child.func.id
            if name == "maybe_wrap_pixel_store":
                hits.append((rel(path), child.lineno))
    return hits


def test_maybe_wrap_never_runs_on_preview_branch():
    targets = [
        ROOT / "src/tabs/image_compare/_session_controller.py",
        ROOT / "src/tabs/image_compare/use_cases/loading.py",
    ]
    offenders: list[str] = []
    for path in targets:
        hits = _maybe_wrap_calls_in_preview_true_branch(path)
        if hits:
            offenders.extend(f"{hit[0]}:{hit[1]}" for hit in hits)
    assert not offenders, (
        "maybe_wrap_pixel_store must not run inside is_preview branches:\n"
        + "\n".join(offenders)
    )


def test_preview_image_assignments_never_use_maybe_wrap():
    offenders: list[str] = []
    for path in iter_py(ROOT / "src"):
        rel_path = rel(path)
        if "/tests/" in rel_path:
            continue
        text = path.read_text(encoding="utf-8")
        if "preview_image" not in text or "maybe_wrap_pixel_store" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [
                t.id
                for t in node.targets
                if isinstance(t, ast.Name) and t.id.startswith("preview_image")
            ]
            if not targets:
                continue
            for child in ast.walk(node.value):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id == "maybe_wrap_pixel_store":
                        offenders.append(f"{rel_path}:{node.lineno} {targets}")
    assert not offenders, (
        "preview_image* must not be assigned from maybe_wrap_pixel_store:\n"
        + "\n".join(offenders)
    )
