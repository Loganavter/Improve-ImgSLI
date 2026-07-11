"""Shared primitives for architecture contract tests.

These tests verify *structural* dogmas from docs/dev/{CANVAS_FEATURES,
CONTRACTS,ARCHITECTURE}.md — they scan source files rather than execute
runtime code. For behavioral contract tests, see ``tests/test_*_contracts.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
CANVAS_FEATURES = SRC / "tabs" / "image_compare" / "canvas" / "features"
MULTI_COMPARE_CANVAS_FEATURES = SRC / "tabs" / "multi_compare" / "canvas" / "features"
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

def _list_features_under(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and d.name != "__pycache__"
    )

def list_canvas_features() -> list[Path]:
    return _list_features_under(CANVAS_FEATURES)

def list_multi_compare_canvas_features() -> list[Path]:
    return _list_features_under(MULTI_COMPARE_CANVAS_FEATURES)

def list_all_canvas_features() -> list[Path]:
    """Every tab's canvas feature package — not just ``image_compare``'s.

    ``multi_compare`` participates in the same feature-package discovery
    contract (manifest/passes auto-registration) as ``image_compare`` — see
    docs/dev/QRHI_CANVAS_FEATURES.md's Current Feature Status table — so
    structural dogma checks (stack_role, no hardcoded layer/priority, etc.)
    should apply to both, not just the tab that happened to be decomposed
    first.
    """
    return list_canvas_features() + list_multi_compare_canvas_features()

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
