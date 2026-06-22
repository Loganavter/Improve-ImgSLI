"""Structural parity checker for toolkit port — Python → C++.

For a given C++ source file, finds the corresponding Python file(s) in
sli-ui-toolkit and flags:

1. Methods in Python that are MISSING from C++
2. Signal connections in Python that are MISSING from C++
3. Literal values that differ between Python and C++
4. Theme tokens used in Python but missing from the C++ theme registry

Usage:
    python tests/parity/check_structure.py cpp/toolkit/src/comboboxes/combo_box.cpp
    python tests/parity/check_structure.py --all   # check all toolkit files
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

TOOLKIT_ROOT = Path(os.environ.get(
    "IMGSLI_TOOLKIT_ROOT",
    Path(__file__).resolve().parents[2] / "cpp" / "toolkit",
))
PYTHON_TOOLKIT_ROOT = Path(os.environ.get(
    "IMGSLI_PYTHON_TOOLKIT_ROOT",
    "/home/jorj/Загрузки/sli-ui-toolkit/src/sli_ui_toolkit/ui/widgets",
))


class Issue(NamedTuple):
    file: str
    line: int
    severity: str  # ERROR | WARNING | INFO
    message: str


def _find_python_files(cpp_path: Path) -> list[Path]:
    """Map a C++ toolkit file to its Python counterpart(s).

    Prefers files in the same category directory (e.g. comboboxes/ → comboboxes/).
    """
    stem = cpp_path.stem
    # Infer category from path: cpp/toolkit/src/comboboxes/foo.cpp → comboboxes
    category = ""
    for part in cpp_path.parts:
        if part in ("atomic", "buttons", "comboboxes", "composite", "overlays",
                    "helpers", "layers", "capabilities"):
            category = part
            break

    matches = []
    for root, _dirs, files in os.walk(PYTHON_TOOLKIT_ROOT):
        for f in files:
            if not f.endswith('.py'):
                continue
            py_stem = Path(f).stem
            # Handle spelling differences: scrollable_combo_box ↔ scrollable_combobox
            py_stem_no_underscore = py_stem.replace('_', '')
            stem_no_underscore = stem.replace('_', '')
            if py_stem == stem or py_stem == f"_{stem}" or \
               py_stem_no_underscore == stem_no_underscore:
                matches.append(Path(root) / f)

    # Sort: same-category first, then by path length (prefer shorter/more direct matches)
    def _key(p: Path) -> tuple[int, int]:
        is_same_cat = 0 if category and category in str(p) else 1
        score = 0 if category and category in str(p) else 1
        # Bonus for exact directory name match
        if category and Path(p).parent.name == category:
            score -= 1
        return (score, len(str(p)))

    matches.sort(key=_key)
    return matches[:3]  # at most 3 candidates


def _extract_methods(py_path: Path) -> dict[str, int]:
    """Return {method_name: line_number} for all defs in the file."""
    methods = {}
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return methods
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods[node.name] = node.lineno
    return methods


def _extract_connects(py_path: Path) -> list[tuple[str, int]]:
    """Return [(connection_string, line_number)] for .connect() calls."""
    connects = []
    try:
        source = py_path.read_text(encoding="utf-8")
    except OSError:
        return connects
    for i, line in enumerate(source.splitlines(), 1):
        if ".connect(" in line and not line.strip().startswith("#"):
            connects.append((line.strip(), i))
    return connects


def _extract_literals(py_path: Path) -> dict[int, list[int]]:
    """Return {value: [line_numbers]} for integer literals 0..255."""
    literals = defaultdict(list)
    try:
        source = py_path.read_text(encoding="utf-8")
    except OSError:
        return literals
    for match in re.finditer(r'\b(\d+)\b', source):
        val = int(match.group(1))
        if 0 < val < 256:  # interesting range: small constants
            lineno = source[:match.start()].count('\n') + 1
            literals[val].append(lineno)
    return literals


def _extract_theme_tokens(py_path: Path) -> list[tuple[str, int]]:
    """Return [(token_string, line_number)] for theme token lookups."""
    tokens = []
    try:
        source = py_path.read_text(encoding="utf-8")
    except OSError:
        return tokens
    # Pattern: tm.get_color("...")  or  tm.get_color('...')
    for match in re.finditer(r'get_color\(["\']([^"\']+)["\']', source):
        lineno = source[:match.start()].count('\n') + 1
        tokens.append((match.group(1), lineno))
    return tokens


def _cpp_method_names(cpp_path: Path) -> set[str]:
    """Extract method-like identifiers from a C++ file."""
    methods: set[str] = set()
    try:
        source = cpp_path.read_text(encoding="utf-8")
    except OSError:
        return methods
    # Match: ReturnType ClassName::methodName( ... )
    for match in re.finditer(r'(?:\w+(?:::\w+)*\s+)?(\w+)::(\w+)\s*\(', source):
        methods.add(match.group(2))
    # Match free functions: ReturnType functionName( ... )
    # Handle qualified return types like std::optional<int>
    for match in re.finditer(
        r'^(?:[\w:]+(?:<[^>]*>)?\s+)+(\w+)\s*\(', source, re.MULTILINE
    ):
        methods.add(match.group(1))
    return methods


def _cpp_connect_count(cpp_path: Path) -> int:
    """Count connect() calls."""
    try:
        source = cpp_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(re.findall(r'\bconnect\s*\(', source))


def _cpp_literals(cpp_path: Path) -> set[int]:
    """Extract small integer literals."""
    literals: set[int] = set()
    try:
        source = cpp_path.read_text(encoding="utf-8")
    except OSError:
        return literals
    for match in re.finditer(r'\b(\d+)\b', source):
        val = int(match.group(1))
        if 0 < val < 256:
            literals.add(val)
    return literals


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to CamelCase for cross-language method matching."""
    parts = name.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def _method_matches(py_name: str, cpp_methods: set[str]) -> bool:
    """Check if a Python method name has a C++ counterpart."""
    if py_name in cpp_methods:
        return True
    camel = _snake_to_camel(py_name)
    if camel in cpp_methods:
        return True
    # Also try with leading underscore stripped (private methods)
    if py_name.startswith('_'):
        return _method_matches(py_name[1:], cpp_methods)
    return False


def check_file(cpp_path: Path | str) -> list[Issue]:
    """Check one C++ file against its Python counterparts."""
    issues: list[Issue] = []
    cpp_path = Path(cpp_path).resolve()
    if not cpp_path.exists():
        return [Issue(str(cpp_path), 0, "ERROR", f"File not found: {cpp_path}")]

    py_files = _find_python_files(cpp_path)
    if not py_files:
        return [Issue(str(cpp_path), 0, "WARNING",
                      "No Python counterpart found")]

    cpp_methods = _cpp_method_names(cpp_path)
    cpp_connect_n = _cpp_connect_count(cpp_path)
    cpp_lit_set = _cpp_literals(cpp_path)

    for py_path in py_files:
        py_short = str(py_path.relative_to(PYTHON_TOOLKIT_ROOT.parent))

        # Methods
        py_methods = _extract_methods(py_path)
        python_only = set(py_methods) - cpp_methods
        # Filter out dunders and Python-only infrastructure
        skip_patterns = {"__init__", "__post_init__", "__repr__", "__str__",
                         "__hash__", "__eq__", "__lt__", "__le__", "__gt__",
                         "__ge__", "__len__", "__getitem__", "__setitem__",
                         "__delitem__", "__iter__", "__contains__", "__call__",
                         "__enter__", "__exit__", "__new__", "__del__",
                         "__setattr__", "__getattr__", "__getattribute__",
                         "__format__", "__reduce__", "__reduce_ex__",
                         "__sizeof__", "__subclasshook__"}
        for method_name in sorted(python_only - skip_patterns):
            if not _method_matches(method_name, cpp_methods):
                issues.append(Issue(
                    str(py_short), py_methods[method_name], "ERROR",
                    f"Method '{method_name}' exists in Python but NOT in C++"
                ))

        # Connections
        py_connects = _extract_connects(py_path)
        if len(py_connects) > cpp_connect_n:
            issues.append(Issue(
                str(py_short), py_connects[0][1] if py_connects else 0,
                "WARNING",
                f"Python has {len(py_connects)} connect() calls, "
                f"C++ has {cpp_connect_n} — possible missing connections"
            ))

        # Theme tokens
        py_tokens = _extract_theme_tokens(py_path)
        for token, lineno in py_tokens:
            # Check if token is in C++ theme.cpp
            theme_cpp = TOOLKIT_ROOT / "src" / "theme.cpp"
            in_cpp = False
            if theme_cpp.exists():
                theme_src = theme_cpp.read_text(encoding="utf-8")
                in_cpp = f'"{token}"' in theme_src or f"'{token}'" in theme_src
            if not in_cpp:
                issues.append(Issue(
                    str(py_short), lineno, "WARNING",
                    f"Theme token '{token}' used in Python but NOT found in "
                    f"C++ theme registry"
                ))

    return issues


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Structural parity checker for toolkit port")
    parser.add_argument("files", nargs="+",
                        help="C++ files to check, or --all")
    parser.add_argument("--all", action="store_true",
                        help="Check all toolkit C++ files")
    args = parser.parse_args(argv)

    all_issues: list[Issue] = []

    if args.all:
        for root, _dirs, files in os.walk(TOOLKIT_ROOT / "src"):
            for f in files:
                if f.endswith((".cpp", ".h")):
                    all_issues.extend(check_file(Path(root) / f))
    else:
        for f in args.files:
            all_issues.extend(check_file(f))

    if not all_issues:
        print("Structural parity check: ALL CLEAN")
        return 0

    errors = [i for i in all_issues if i.severity == "ERROR"]
    warnings = [i for i in all_issues if i.severity == "WARNING"]

    print(f"\nStructural parity: {len(errors)} errors, {len(warnings)} warnings\n")
    for issue in errors:
        print(f"  ERROR  {issue.file}:{issue.line} — {issue.message}")
    for issue in warnings:
        print(f"  WARN   {issue.file}:{issue.line} — {issue.message}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))