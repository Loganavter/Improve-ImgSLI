"""Shared primitives for image_compare architecture contract tests.

These tests verify *structural* dogmas from docs/dev/{CANVAS_FEATURES,
CONTRACTS,ARCHITECTURE}.md — they scan source files rather than execute
runtime code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "src"
CANVAS_FEATURES = SRC / "tabs" / "image_compare" / "canvas" / "features"
CANVAS_INFRA = SRC / "ui" / "canvas_infra"
CANVAS_PRESENTATION = SRC / "ui" / "canvas_presentation"
SHADER_SOURCES = SRC / "ui" / "widgets" / "canvas" / "shader_sources"
PLUGINS = SRC / "plugins"

def iter_py(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and "tests" not in p.parts
    ]

def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)

def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

def module_imports(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out

def list_canvas_features() -> list[Path]:
    if not CANVAS_FEATURES.is_dir():
        return []
    return sorted(
        d
        for d in CANVAS_FEATURES.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and d.name != "__pycache__"
    )

def list_plugins() -> list[Path]:
    if not PLUGINS.is_dir():
        return []
    return sorted(
        d
        for d in PLUGINS.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and d.name != "__pycache__"
    )

def feature_name(feature_dir: Path) -> str | None:
    for fname in ("widget.py", "feature.py", "manifest.py"):
        f = feature_dir / fname
        if not f.exists():
            continue
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', read(f))
        if m:
            return m.group(1)
    return None
