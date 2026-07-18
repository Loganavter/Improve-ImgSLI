#!/usr/bin/env python3
"""Ensure Windows PyInstaller bundles ship QRhi *.qsb shaders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bundle_roots(bundle_root: Path) -> tuple[Path, ...]:
    # PyInstaller 6 onedir puts datas under _internal/; older layouts use root.
    internal = bundle_root / "_internal"
    if internal.is_dir():
        return (internal, bundle_root)
    return (bundle_root,)


def expected_qsb_relpaths(repo_root: Path) -> list[Path]:
    src = repo_root / "src"
    rels: list[Path] = []
    for path in sorted(src.rglob("*.qsb")):
        try:
            rels.append(path.relative_to(src))
        except ValueError:
            continue
    return rels


def missing_shaders(*, repo_root: Path, bundle_root: Path) -> list[str]:
    expected = expected_qsb_relpaths(repo_root)
    if not expected:
        return ["no *.qsb files found under src/ (compile shaders before packaging)"]

    roots = _bundle_roots(bundle_root)
    missing: list[str] = []
    for rel in expected:
        if any((root / rel).is_file() for root in roots):
            continue
        missing.append(str(rel).replace("\\", "/"))
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--windows-bundle",
        type=Path,
        required=True,
        help="Path to dist/Improve_ImgSLI (onedir bundle root)",
    )
    args = parser.parse_args(argv)

    bundle = args.windows_bundle
    if not bundle.is_dir():
        print(f"ERROR: Windows bundle not found: {bundle}", file=sys.stderr)
        return 1

    missing = missing_shaders(repo_root=args.repo_root.resolve(), bundle_root=bundle.resolve())
    if missing:
        print("ERROR: missing QRhi shaders in Windows bundle:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 1

    print(f"OK: {len(expected_qsb_relpaths(args.repo_root.resolve()))} *.qsb present in {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
