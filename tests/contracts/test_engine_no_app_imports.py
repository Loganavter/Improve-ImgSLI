"""Engine/app-layer seal: ``src/engine`` never references app layers.

The tile engine (``src/engine/`` since the Phase-2 mechanical move from
``src/shared/rendering/``) must NEVER reference ``tabs.*``, ``plugins.*``,
or ``core/store`` — in code OR in string literals/comments/docstrings. Tabs call into the engine; the
engine never names its callers.

Two legacy service-locator shims (``tab_canvas_services.py``,
``live_snapshot.py``) still hold lazy function-level
``from tabs.registry import get_shared_tab_registry`` imports pending DI
extraction. They are pinned below at their exact current size — the seal
forbids NEW references anywhere and any growth of the exempted ones.

Dogma source: task-engine-1a-seal-2026-09-14 (Engine W1A: seal).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize

from ._framework import ROOT, iter_py, rel

ENGINE = ROOT / "src" / "engine"

# Dotted module references / paths the engine must never name. The trailing
# identifier class keeps generic English ("both canvas tabs.") out of scope:
# only real module paths (tabs.<name>, plugins.<name>) are forbidden.
_FORBIDDEN_TEXT_RES = [
    re.compile(r"tabs\.[A-Za-z_]"),
    re.compile(r"plugins\.[A-Za-z_]"),
    re.compile(r"src/tabs"),
    re.compile(r"src/plugins"),
    re.compile(r"core/store"),
    re.compile(r"core\.store"),
]

# Lazy service-locator imports grandfathered pending DI extraction:
# filename -> exact expected count of `from tabs.registry import ...` lines.
# Any other tabs.* import, or any growth here, fails the seal.
_LEGACY_SHIM_IMPORTS = {
    "tab_canvas_services.py": 2,
    "live_snapshot.py": 1,
}
_LEGACY_IMPORT_RE = re.compile(
    r"^\s*from\s+tabs\.registry\s+import\s+get_shared_tab_registry\s*$"
)


def _engine_py() -> list:
    return sorted(ENGINE.rglob("*.py"))


def _import_modules(path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


def _is_forbidden_import(module: str) -> bool:
    top = module.split(".")[0]
    if top in ("tabs", "plugins"):
        return True
    if module == "core.store" or module.startswith("core.store."):
        return True
    return False


def test_engine_has_no_app_imports():
    leaks: list[str] = []
    for py in _engine_py():
        if "__pycache__" in py.parts:
            continue
        legacy_expected = _LEGACY_SHIM_IMPORTS.get(py.name)
        legacy_seen = 0
        for module, lineno in _import_modules(py):
            if not _is_forbidden_import(module):
                continue
            if legacy_expected is not None and module == "tabs.registry":
                legacy_seen += 1
                continue
            leaks.append(
                f"{rel(py)}:{lineno} imports '{module}' "
                f"(engine must not reference tabs.*/plugins.*/core.store)"
            )
        if legacy_expected is not None and legacy_seen != legacy_expected:
            leaks.append(
                f"{rel(py)} has {legacy_seen} tabs.registry imports, "
                f"expected exactly {legacy_expected} "
                f"(legacy shim must not grow)"
            )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_legacy_shims_hold_only_the_pinned_import():
    for name in _LEGACY_SHIM_IMPORTS:
        py = ENGINE / "cache" / name
        assert py.is_file(), f"legacy shim {name} moved without updating the seal"
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "tabs." in line and not _LEGACY_IMPORT_RE.match(line):
                raise AssertionError(
                    f"{rel(py)}:{lineno} holds a non-pinned tabs.* reference: "
                    f"{line.strip()!r} (only the pinned tabs.registry "
                    f"import is grandfathered)"
                )


def _string_spans(path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return []
    return [
        (getattr(node, "lineno", 0), node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _comment_spans(path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
    except (tokenize.TokenError, SyntaxError):
        pass
    return out


def test_engine_strings_and_comments_name_no_app_layer():
    leaks: list[str] = []
    for py in _engine_py():
        if "__pycache__" in py.parts:
            continue
        for lineno, content in _string_spans(py) + _comment_spans(py):
            for rx in _FORBIDDEN_TEXT_RES:
                if rx.search(content):
                    leaks.append(
                        f"{rel(py)}:{lineno} literal references app layer "
                        f"({rx.pattern!r}): {content.strip()[:120]!r}"
                    )
                    break
    assert not leaks, "\n  - " + "\n  - ".join(leaks)
