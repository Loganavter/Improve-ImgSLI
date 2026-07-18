#!/usr/bin/env python3
"""Report Help figure coverage across host + tab packages.

Each Help package owns ``figures.json`` + ``assets/``:

- host: ``src/resources/help/``
- tabs: ``src/tabs/<tab>/resources/help/``

A figure is a **stub** when its bytes match the host canonical
``assets/_stub.jpg`` (overwrite stubs with real screenshots in place).

Usage:
    python src/devtools/check_help_figures.py
    python src/devtools/check_help_figures.py --json
    python src/devtools/check_help_figures.py --strict   # exit 1 if missing/stub
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

_IMG_TOKEN_RE = re.compile(r"\{\{img:([a-zA-Z0-9_.]+)\}\}")
_STUB_NAME = "_stub.jpg"
_SKIP_ASSET_NAMES = {_STUB_NAME}


@dataclass(frozen=True, slots=True)
class FigureRow:
    package: str
    slot: str
    rel_path: str
    status: str  # ready | stub | missing
    used_in: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HelpFiguresReport:
    rows: tuple[FigureRow, ...]
    orphans: tuple[tuple[str, str], ...]  # (package, rel)
    unknown_tokens: tuple[tuple[str, str], ...]  # (body_rel, slot)
    stub_digest: str | None
    conflicts: tuple[tuple[str, str, str], ...]  # (slot, pkg_a, pkg_b)

    @property
    def ready(self) -> tuple[FigureRow, ...]:
        return tuple(r for r in self.rows if r.status == "ready")

    @property
    def stubs(self) -> tuple[FigureRow, ...]:
        return tuple(r for r in self.rows if r.status == "stub")

    @property
    def missing(self) -> tuple[FigureRow, ...]:
        return tuple(r for r in self.rows if r.status == "missing")

    @property
    def gap_count(self) -> int:
        return (
            len(self.stubs)
            + len(self.missing)
            + len(self.unknown_tokens)
            + len(self.conflicts)
        )


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_host_help_root() -> Path:
    return default_repo_root() / "src" / "resources" / "help"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_figures(figures_path: Path) -> dict[str, str]:
    raw = json.loads(figures_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"figures.json must be an object: {figures_path}")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str) and key and value:
            out[key] = value
    return out


def _package_label(help_root: Path, *, repo_root: Path) -> str:
    try:
        return help_root.relative_to(repo_root).as_posix()
    except ValueError:
        return help_root.as_posix()


def discover_help_packages(repo_root: Path) -> list[Path]:
    """Host help root first, then each tab ``resources/help`` package."""
    packages: list[Path] = []
    host = repo_root / "src" / "resources" / "help"
    if host.is_dir():
        packages.append(host)
    tabs = repo_root / "src" / "tabs"
    if tabs.is_dir():
        for path in sorted(tabs.glob("*/resources/help")):
            if path.is_dir():
                packages.append(path)
    return packages


def _iter_help_bodies(packages: Iterable[Path]) -> list[Path]:
    bodies: list[Path] = []
    for root in packages:
        for path in sorted(root.rglob("*.md")):
            if "assets" in path.parts:
                continue
            bodies.append(path)
    return bodies


def _collect_img_usage(bodies: Iterable[Path], *, repo_root: Path) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    for path in bodies:
        text = path.read_text(encoding="utf-8")
        try:
            rel = path.relative_to(repo_root).as_posix()
        except ValueError:
            rel = path.as_posix()
        for match in _IMG_TOKEN_RE.finditer(text):
            slot = match.group(1)
            usage.setdefault(slot, []).append(rel)
    return usage


def _iter_asset_files(assets_root: Path) -> list[Path]:
    if not assets_root.is_dir():
        return []
    return sorted(
        p
        for p in assets_root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )


def analyze_help_figures(
    *,
    repo_root: Path | None = None,
    packages: Iterable[Path] | None = None,
    stub_path: Path | None = None,
) -> HelpFiguresReport:
    """Build a coverage report across Help packages."""
    root = repo_root if repo_root is not None else default_repo_root()
    pkgs = list(packages) if packages is not None else discover_help_packages(root)
    if not pkgs:
        raise SystemExit("No Help packages found")

    host_stub = stub_path
    if host_stub is None:
        host_stub = (root / "src" / "resources" / "help" / "assets" / _STUB_NAME)
    stub_digest = _sha256(host_stub) if host_stub.is_file() else None

    usage = _collect_img_usage(_iter_help_bodies(pkgs), repo_root=root)

    slot_owners: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    rows: list[FigureRow] = []
    orphans: list[tuple[str, str]] = []
    declared_slots: set[str] = set()

    for pkg in pkgs:
        label = _package_label(pkg, repo_root=root)
        figures_path = pkg / "figures.json"
        assets_root = pkg / "assets"
        figures = _load_figures(figures_path) if figures_path.is_file() else {}
        declared_paths: set[str] = set()

        for slot, rel in sorted(figures.items()):
            declared_slots.add(slot)
            declared_paths.add(rel)
            if slot in slot_owners and slot_owners[slot] != label:
                conflicts.append((slot, slot_owners[slot], label))
            else:
                slot_owners[slot] = label

            abs_path = assets_root / rel
            used = tuple(sorted(set(usage.get(slot, ()))))
            if not abs_path.is_file():
                rows.append(
                    FigureRow(
                        package=label,
                        slot=slot,
                        rel_path=rel,
                        status="missing",
                        used_in=used,
                    )
                )
                continue
            digest = _sha256(abs_path)
            status = "stub" if stub_digest is not None and digest == stub_digest else "ready"
            rows.append(
                FigureRow(
                    package=label,
                    slot=slot,
                    rel_path=rel,
                    status=status,
                    used_in=used,
                )
            )

        for path in _iter_asset_files(assets_root):
            rel = path.relative_to(assets_root).as_posix()
            if path.name in _SKIP_ASSET_NAMES:
                continue
            if rel not in declared_paths:
                orphans.append((label, rel))

    unknown: list[tuple[str, str]] = []
    for slot, bodies in sorted(usage.items()):
        if slot in declared_slots:
            continue
        for body in bodies:
            unknown.append((body, slot))

    return HelpFiguresReport(
        rows=tuple(rows),
        orphans=tuple(orphans),
        unknown_tokens=tuple(unknown),
        stub_digest=stub_digest,
        conflicts=tuple(conflicts),
    )


def _print_report(report: HelpFiguresReport) -> int:
    print("Help figures (host + tab packages)")
    print(f"  ready:     {len(report.ready)}")
    print(f"  stub:      {len(report.stubs)}  ← need real screenshots")
    print(f"  missing:   {len(report.missing)}")
    print(f"  orphans:   {len(report.orphans)}  (assets not in package figures.json)")
    print(f"  unknown:   {len(report.unknown_tokens)}  ({{{{img:}}}} not in any figures.json)")
    print(f"  conflicts: {len(report.conflicts)}  (same slot in two packages)")
    if report.stub_digest is None:
        print("  warning: host assets/_stub.jpg missing — stub detection disabled")
    print()

    if report.stubs:
        print("Need screenshots (bytes == host assets/_stub.jpg):")
        for row in report.stubs:
            where = ", ".join(row.used_in[:2]) if row.used_in else "(unused in md)"
            more = f" +{len(row.used_in) - 2}" if len(row.used_in) > 2 else ""
            print(f"  - [{row.package}] {row.slot}")
            print(f"      → assets/{row.rel_path}")
            print(f"      used: {where}{more}")
        print()

    if report.missing:
        print("Missing files:")
        for row in report.missing:
            print(f"  - [{row.package}] {row.slot} → assets/{row.rel_path}")
        print()

    if report.ready:
        print("Ready:")
        for row in report.ready:
            print(f"  - [{row.package}] {row.slot} → assets/{row.rel_path}")
        print()

    if report.orphans:
        print("Orphan assets:")
        for pkg, rel in report.orphans:
            print(f"  - [{pkg}] assets/{rel}")
        print()

    if report.unknown_tokens:
        print("Unknown {{img:}} tokens in markdown:")
        for body, slot in report.unknown_tokens:
            print(f"  - {body}: {{{{img:{slot}}}}}")
        print()

    if report.conflicts:
        print("Slot conflicts (duplicate ids across packages):")
        for slot, a, b in report.conflicts:
            print(f"  - {slot}: {a} vs {b}")
        print()

    print(
        f"TOTAL still to draw/fix: {len(report.stubs) + len(report.missing)} "
        f"slot(s); unknown: {len(report.unknown_tokens)}; "
        f"conflicts: {len(report.conflicts)}"
    )
    return report.gap_count


def _print_json(report: HelpFiguresReport) -> int:
    payload: dict[str, Any] = {
        "ready": [asdict(r) for r in report.ready],
        "stub": [asdict(r) for r in report.stubs],
        "missing": [asdict(r) for r in report.missing],
        "orphans": [{"package": pkg, "path": rel} for pkg, rel in report.orphans],
        "unknown_tokens": [
            {"file": body, "slot": slot} for body, slot in report.unknown_tokens
        ],
        "conflicts": [
            {"slot": slot, "a": a, "b": b} for slot, a, b in report.conflicts
        ],
        "stub_digest": report.stub_digest,
        "counts": {
            "ready": len(report.ready),
            "stub": len(report.stubs),
            "missing": len(report.missing),
            "orphans": len(report.orphans),
            "unknown": len(report.unknown_tokens),
            "conflicts": len(report.conflicts),
            "gaps": report.gap_count,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return report.gap_count


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = default_repo_root()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=here,
        help="Repository root (discovers host + tabs/*/resources/help).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any stub, missing file, unknown token, or conflict.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = analyze_help_figures(repo_root=args.repo_root)
    total = _print_json(report) if args.json else _print_report(report)
    if args.strict and total > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
