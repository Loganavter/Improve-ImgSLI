"""Frozen-build import safety: no shape a PyInstaller bundle cannot resolve.

Why this contract exists (owner report 2026-10-28, a packaged Windows build):

    Failed to create page for tab 'image_gallery': cannot import name
    'GALLERY_CARD_H' from 'tabs.image_gallery.ui.card'

The gallery was **unopenable in the shipped build** while every test passed.
Cause: `ui/card.py` and `ui/card/` existed side by side, and because a package
shadows a file of the same name, `ui/card/__init__.py` loaded the sibling file
through `importlib.util.spec_from_file_location` — a *path-based* load that
PyInstaller's static analysis cannot see, wrapped in `except Exception: pass`, so
a missing file became an EMPTY namespace instead of an error. `ui/quick_look.py`
had the same shape, one import away from the same failure.

The three rules below are the shapes that make this possible. They are cheap to
keep and expensive to rediscover: a green suite cannot see them, because in a
source checkout the dynamic load works.

An exception must be DELIBERATE: the module carries the marker
``Frozen-Import-OK: <reason>`` in its docstring. There is no allowlist file to
rot — a deliberate exception is readable next to the code it excuses.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
SKIP_DIRS = {"__pycache__", "venv", ".venv"}

#: The inline marker a module must carry to be excused (see the docstring).
MARKER = "Frozen-Import-OK:"

#: Calls that load a module BY FILE PATH. PyInstaller collects imports
#: statically; a path load is invisible, so the file may not be bundled at all.
_PATH_LOAD_ATTRS = {
    ("importlib.util", "spec_from_file_location"),
    ("importlib.machinery", "SourceFileLoader"),
    ("importlib.machinery", "SourcelessFileLoader"),
    ("imp", "load_source"),
}


def _modules() -> list[Path]:
    out: list[Path] = []
    for path in sorted(SRC.rglob("*.py")):
        if SKIP_DIRS & set(path.relative_to(SRC).parts):
            continue
        out.append(path)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _excused(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _call_name(node: ast.Call) -> set[tuple[str, str]]:
    """The (module, attribute) pairs a call could name, best effort."""
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
        inner = func.value
        if isinstance(inner.value, ast.Name):
            return {(f"{inner.value.id}.{inner.attr}", func.attr)}
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return {(func.value.id, func.attr)}
    return set()


def test_no_module_is_shadowed_by_a_package_of_the_same_name():
    """`x.py` next to `x/` is the shape that forces a dynamic loader."""
    shadows: list[str] = []
    for package in SRC.rglob("*"):
        if not package.is_dir() or package.name in SKIP_DIRS:
            continue
        if not (package / "__init__.py").is_file():
            continue
        sibling = package.with_suffix(".py")
        if sibling.is_file():
            shadows.append(f"{_rel(sibling)} + {_rel(package)}/__init__.py")
    assert not shadows, (
        "a module and a package share a name — the package shadows the file, so "
        "importing the file needs a path-based loader a frozen build cannot "
        "follow (the packaged Windows app could not open the gallery, 2026-10-28). "
        "Move the implementation INSIDE the package (ui/list/card.py is the "
        "shape to copy):\n  - " + "\n  - ".join(shadows)
    )


def test_no_module_is_loaded_by_file_path():
    """A `spec_from_file_location` load is invisible to a frozen bundler."""
    offenders: list[str] = []
    for path in _modules():
        if _excused(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for pair in _call_name(node):
                if pair in _PATH_LOAD_ATTRS:
                    offenders.append(f"{_rel(path)}:{node.lineno} {pair[0]}.{pair[1]}")
    assert not offenders, (
        "a module is loaded by FILE PATH, which PyInstaller cannot see — the "
        "file may be missing from the bundle and the import fails only in the "
        "shipped build. Use a normal import (`from .impl import X`), or, when the "
        f"load is genuinely unavoidable, mark the module '{MARKER} <reason>':"
        "\n  - " + "\n  - ".join(offenders)
    )


def test_nothing_rewrites_path_but_a_package_init():
    """A plain module faking `__path__` is how a file pretends to be a package."""
    offenders: list[str] = []
    for path in _modules():
        if path.name == "__init__.py" or _excused(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "setattr" and len(node.args) >= 2:
                    key = node.args[1]
                    if isinstance(key, ast.Constant) and key.value == "__path__":
                        offenders.append(f"{_rel(path)}:{node.lineno} setattr(__path__)")
            for target in targets:
                if isinstance(target, ast.Name) and target.id == "__path__":
                    offenders.append(f"{_rel(path)}:{node.lineno} __path__ = ...")
    assert not offenders, (
        "a non-package module rewrites `__path__` to expose a subpackage — that "
        "trick only works in a source checkout (it is what the gallery's card "
        "and quick_look proxies did). Move the implementation into the package "
        "instead, so the package owns its `__path__`:\n  - " + "\n  - ".join(offenders)
    )
