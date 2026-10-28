#!/usr/bin/env python3
"""Pick the tests a change can actually break, from the import graph.

Why this exists: the suite is ~10.5k tests / ~9 min (measured 2026-10-27,
`docs/dev/TESTING.md` § Tiers), so "run everything" is the wrong default for a
one-module edit. This tool reads the *imports* (`ast`, no imports executed, no
plugins, no network) and answers "which test files import what I touched",
transitively.

Usage
-----
    python3 tools/test_affected.py src/tabs/image_gallery/services/folder_scanner.py
    python3 tools/test_affected.py --since origin/main
    python3 tools/test_affected.py --since HEAD --explain

Contract (what callers may rely on)
-----------------------------------
- stdout: one repo-relative test path per line, sorted. With ``--explain`` each
  path is followed by indented ``why:`` lines (import chain) — parse plain mode
  from scripts, read explain mode with eyes.
- exit 0: list is the affected set (possibly empty; the reason for each skip is
  on stderr).
- exit 2: **full tier required** — a shared module is touched (fail-closed),
  or the graph cannot bound the blast radius confidently. stdout then starts
  with a ``full-tier:`` line. Callers must treat 2 as "run everything".
- exit 1: usage / git error.

Fail-closed rule
----------------
Some files are imported by so much of the tree that any list would be a lie
with a comforting shape: ``src/core/**``, ``src/engine/**``, ``src/shared/**``,
``src/main*.py``, ``src/__main__.py``, any ``conftest.py``, any
``pytest.ini``, ``requirements*.txt``, ``tests/helpers/**``,
``tests/fixtures/**``, and this tool itself. Touching one prints the full-tier
line and exits 2. Everything else is bounded by imports, which is exactly what
the test sees at runtime.

Limitations (documented, not hidden)
------------------------------------
- Dynamic imports (``importlib.import_module("x")``) and string references are
  invisible to ``ast``. ``tests/devtools/test_docs_link_graph.py`` scans
  ``docs/**`` and ``src/tabs/*/docs/**`` without importing them, so a docs
  change is mapped by an explicit path rule instead.
- Resource files (``.json``/``.qss``/``.md``) are not imported at all; a path
  with no rule prints a ``note:`` on stderr and contributes nothing.
- Qt's plugin/fixture discovery (``conftest.py``, ``qtbot``) is why every
  ``conftest.py`` is fail-closed rather than graph-resolved.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import subprocess
import sys
from pathlib import Path

# Directories that never contain app/test modules we care about.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "venv",
        ".venv",
        "node_modules",
        "site-packages",
    }
)

# Import roots: dotted module names are resolved against these prefixes.
# ``""`` means "relative to the repository root" (``tests.*``, ``scripts.*``,
# ``tools.*``, top-level ``launcher``).
_MODULE_ROOTS = ("src", "")

# Fail-closed patterns, matched against the repo-relative POSIX path.
_FULL_TIER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("prefix", "src/core/"),
    ("prefix", "src/engine/"),
    ("prefix", "src/shared/"),
    ("glob", "src/main*.py"),
    ("glob", "src/__main__.py"),
    ("glob", "*/conftest.py"),
    ("glob", "conftest.py"),
    ("glob", "*/pytest.ini"),
    ("glob", "pytest.ini"),
    ("glob", "requirements*.txt"),
    ("prefix", "tests/helpers/"),
    ("prefix", "tests/fixtures/"),
    ("glob", "tools/test_affected.py"),
)

# Non-Python changed paths whose effect is real but not an import:
# test_docs_link_graph.py walks docs/ and src/tabs/*/docs/ as text and fails on
# a broken or stale link, so a docs edit must pull that test in by rule.
_DOCS_TEST = "tests/devtools/test_docs_link_graph.py"
_DOCS_PREFIXES = ("docs/",)


def _is_test_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py")


def _iter_python_files(root: Path):
    for base, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(base) / filename


def _dotted(path_rel: str, prefix: str) -> str:
    without_suffix = path_rel[: -len(".py")]
    if prefix:
        without_suffix = without_suffix[len(prefix) :]
    parts = without_suffix.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(p for p in parts if p)


def _module_names(path: Path, root: Path) -> set[str]:
    """Dotted names under which ``path`` can be imported (one per root)."""
    rel = path.relative_to(root).as_posix()
    names: set[str] = set()
    if rel.startswith("src/"):
        names.add(_dotted(rel, "src/"))
    names.add(_dotted(rel, ""))
    return {n for n in names if n}


def _package_of(module: str, is_package: bool) -> str:
    if is_package:
        return module
    return module.rpartition(".")[0]


def _raw_import_targets(tree: ast.AST, module: str, is_package: bool) -> set[str]:
    """Dotted module names this file imports (relative imports resolved)."""
    package = _package_of(module, is_package)
    package_parts = [p for p in package.split(".") if p]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level 1 == this package; each extra level climbs one up.
                keep = len(package_parts) - (node.level - 1)
                if keep < 0:
                    continue
                base_parts = package_parts[:keep]
            else:
                base_parts = []
            base = ".".join(base_parts)
            if node.module:
                base = f"{base}.{node.module}" if base else node.module
            if base:
                targets.add(base)
            for alias in node.names:
                if alias.name == "*" or not base:
                    continue
                # ``from a.b import c`` may name a submodule.
                targets.add(f"{base}.{alias.name}")
    return targets


class ImportGraph:
    """File -> files it imports, and the reverse, over one repository tree."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.file_modules: dict[Path, set[str]] = {}
        self.name_to_file: dict[str, Path] = {}
        self.edges: dict[Path, set[Path]] = {}
        self.reverse: dict[Path, set[Path]] = {}
        self.parse_failures: list[Path] = []
        self._build()

    def _build(self) -> None:
        root = self.root
        files = list(_iter_python_files(root))
        for path in files:
            names = _module_names(path, root)
            if not names:
                continue
            self.file_modules[path] = names
            for name in names:
                # src/ wins over the repo root when both could claim a name.
                existing = self.name_to_file.get(name)
                if existing is None or existing.relative_to(root).as_posix().startswith("tests/"):
                    self.name_to_file[name] = path

        for path, names in self.file_modules.items():
            primary = min(names, key=len) if len(names) > 1 else next(iter(names))
            is_package = path.name == "__init__.py"
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                self.parse_failures.append(path)
                continue
            targets: set[Path] = set()
            for dotted in _raw_import_targets(tree, primary, is_package):
                for resolved in self._resolve(dotted):
                    if resolved != path:
                        targets.add(resolved)
            self.edges[path] = targets
            for target in targets:
                self.reverse.setdefault(target, set()).add(path)

    def _resolve(self, dotted: str) -> set[Path]:
        """Resolve a dotted name to files, including every ancestor package."""
        found: set[Path] = set()
        parts = dotted.split(".")
        for index in range(1, len(parts) + 1):
            path = self.name_to_file.get(".".join(parts[:index]))
            if path is not None:
                found.add(path)
        return found

    def affected(self, changed: Path, depth: int) -> dict[Path, list[Path]]:
        """Map test file -> import chain (changed ... -> test), hops <= depth."""
        seeds = {changed}
        # A package __init__ affects every module inside it.
        for name in self.file_modules.get(changed, ()):
            for other, names in self.file_modules.items():
                if other is changed:
                    continue
                if any(n.startswith(name + ".") for n in names):
                    seeds.add(other)

        result: dict[Path, list[Path]] = {}
        for seed in seeds:
            if seed != changed and _is_test_path(self._rel(seed)) and seed not in result:
                result[seed] = [changed, seed]
        frontier: dict[Path, list[Path]] = {
            seed: ([changed] if seed is changed else [changed, seed]) for seed in seeds
        }
        for hop in range(1, depth + 1):
            next_frontier: dict[Path, list[Path]] = {}
            for node, chain in frontier.items():
                for importer in self.reverse.get(node, ()):
                    if importer in frontier or importer in result:
                        continue
                    importer_chain = chain + [importer]
                    if _is_test_path(self._rel(importer)):
                        result[importer] = importer_chain
                    else:
                        next_frontier[importer] = importer_chain
            frontier = next_frontier
            if not frontier:
                break
        return result

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


def _full_tier_reason(rel: str) -> str | None:
    for kind, pattern in _FULL_TIER_PATTERNS:
        if kind == "prefix" and rel.startswith(pattern):
            return f"{pattern} is shared"
        if kind == "glob" and fnmatch.fnmatch(rel, pattern):
            return f"{pattern} is shared"
    return None


def _path_rule_tests(rel: str) -> tuple[str, ...]:
    if rel.startswith(_DOCS_PREFIXES):
        return (_DOCS_TEST,)
    if rel.startswith("src/tabs/") and "/docs/" in rel:
        return (_DOCS_TEST,)
    return ()


def _normalize(raw: str, root: Path) -> str:
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root).as_posix()
        except ValueError:
            return candidate.as_posix()
    rel = os.path.normpath(raw).replace(os.sep, "/")
    return rel.lstrip("./")


def _changed_from_git(root: Path, rev: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", rev],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"git diff --name-only {rev} failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return Path.cwd().resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the test files affected by a set of changed files.",
    )
    parser.add_argument("paths", nargs="*", help="changed files (repo-relative or absolute)")
    parser.add_argument("--since", help="use `git diff --name-only <rev>` as the changed set")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print the import chain that pulled each test in",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="import hops to walk upwards (default 2: module -> importer -> test)",
    )
    parser.add_argument("--root", help="repository root (default: git toplevel / cwd)")
    args = parser.parse_args(argv)

    root = _repo_root(args.root)
    if not root.is_dir():
        print(f"error: root {root} is not a directory", file=sys.stderr)
        return 1

    changed = [_normalize(p, root) for p in args.paths]
    if args.since:
        changed.extend(_changed_from_git(root, args.since))
    if not changed:
        print("error: no changed paths (pass paths or --since REV)", file=sys.stderr)
        return 1

    deduped: list[str] = []
    for rel in changed:
        if rel not in deduped:
            deduped.append(rel)

    reasons: list[str] = []
    hits: dict[str, list[str]] = {}
    for rel in deduped:
        reason = _full_tier_reason(rel)
        if reason is not None:
            reasons.append(f"{rel}: {reason}")
            continue
        if not (root / rel).exists():
            print(f"skip: {rel} does not exist in the tree", file=sys.stderr)
            continue
        if _is_test_path(rel):
            hits.setdefault(rel, [f"{rel} (changed directly)"])
            continue
        rule_tests = _path_rule_tests(rel)
        for rule_test in rule_tests:
            hits.setdefault(rule_test, [f"{rule_test} (path rule for {rel})"])
        if not rel.endswith(".py") and not rule_tests:
            print(f"note: no test maps to {rel} (non-Python path, no rule)", file=sys.stderr)

    if reasons:
        print("full-tier: shared module touched, run the whole suite")
        for line in reasons:
            print(f"full-tier: {line}")
        return 2

    graph = ImportGraph(root)
    if graph.parse_failures:
        for path in graph.parse_failures:
            print(
                f"note: could not parse {graph._rel(path)} — its importers are unknown",
                file=sys.stderr,
            )

    for rel in deduped:
        if _is_test_path(rel) or _path_rule_tests(rel):
            continue
        path = (root / rel).resolve()
        if not path.exists() or path.suffix != ".py":
            continue
        found = graph.affected(path, max(args.depth, 1))
        if not found:
            print(f"note: no test imports {rel}", file=sys.stderr)
        for test_path, chain in found.items():
            test_rel = graph._rel(test_path)
            rendered = " -> ".join(graph._rel(p) for p in chain)
            hits.setdefault(test_rel, []).append(rendered)

    if not hits:
        print("no affected tests", file=sys.stderr)
        return 0

    for test_rel in sorted(hits):
        print(test_rel)
        if args.explain:
            for why in hits[test_rel]:
                print(f"    why: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
