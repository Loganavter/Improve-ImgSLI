#!/usr/bin/env python3
"""Find gaps in localization files.

Compares non-reference locales against the reference (default: ``en``) and
reports missing keys and empty values. Designed to be run from the project
root.

Usage:
    python scripts/check_translations.py
    python scripts/check_translations.py --root src/resources/i18n --reference en
    python scripts/check_translations.py --json     # machine-readable output
    python scripts/check_translations.py --strict   # exit 1 if any gap found
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten(key, v, out)
    elif isinstance(value, list):
        out[prefix] = "\n".join(str(x) for x in value)
    else:
        out[prefix] = "" if value is None else str(value)


def _load_locale(locale_dir: Path) -> dict[str, dict[str, str]]:
    """Returns {relative_file_path: {flat_key: value}}."""
    result: dict[str, dict[str, str]] = {}
    for path in sorted(locale_dir.rglob("*.json")):
        rel = path.relative_to(locale_dir).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"ERROR: invalid JSON in {path}: {exc}", file=sys.stderr)
            continue
        flat: dict[str, str] = {}
        _flatten("", data, flat)
        result[rel] = flat
    return result


def _list_locales(root: Path) -> list[str]:
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def _is_empty(value: str) -> bool:
    return not value.strip()


def _analyze(root: Path, reference: str) -> dict[str, dict[str, Any]]:
    locales = _list_locales(root)
    if reference not in locales:
        raise SystemExit(f"Reference locale '{reference}' not found under {root}")

    ref_data = _load_locale(root / reference)

    ref_files = set(ref_data.keys())

    report: dict[str, dict[str, Any]] = {}
    for locale in locales:
        if locale == reference:

            data = ref_data
        else:
            data = _load_locale(root / locale)

        missing: list[tuple[str, str]] = []
        empty: list[tuple[str, str]] = []
        extra: list[tuple[str, str]] = []
        missing_files: list[str] = []

        for rel in sorted(ref_files):
            ref_flat = ref_data[rel]
            loc_flat = data.get(rel)
            if loc_flat is None:
                missing_files.append(rel)
                for key in ref_flat:
                    missing.append((rel, key))
                continue
            for key, ref_value in ref_flat.items():
                if key not in loc_flat:
                    missing.append((rel, key))
                elif _is_empty(loc_flat[key]) and not _is_empty(ref_value):
                    empty.append((rel, key))

        for rel in sorted(set(data.keys()) - ref_files):
            for key in data[rel]:
                extra.append((rel, key))

        if locale == reference:
            for rel, flat in data.items():
                for key, value in flat.items():
                    if _is_empty(value):
                        empty.append((rel, key))

        report[locale] = {
            "missing": missing,
            "empty": empty,
            "extra": extra,
            "missing_files": missing_files,
        }
    return report


def _print_report(report: dict[str, dict[str, Any]], reference: str) -> int:
    total_gaps = 0
    for locale, payload in report.items():
        missing = payload["missing"]
        empty = payload["empty"]
        extra = payload["extra"]
        missing_files = payload["missing_files"]
        gap_count = len(missing) + len(empty)
        total_gaps += gap_count

        header = f"[{locale}]"
        if locale == reference:
            header += " (reference)"
        print(header)
        print(f"  missing keys:  {len(missing)}")
        print(f"  empty values:  {len(empty)}")
        print(f"  extra keys:    {len(extra)}")
        if missing_files:
            print(f"  missing files: {len(missing_files)} ({', '.join(missing_files)})")

        if missing:
            by_file = Counter(rel for rel, _ in missing)
            print("    missing by file:")
            for rel, count in sorted(by_file.items()):
                print(f"      {rel}: {count}")
            for rel, key in missing[:10]:
                print(f"      - {rel}: {key}")
            if len(missing) > 10:
                print(f"      ... and {len(missing) - 10} more")

        if empty:
            by_file = Counter(rel for rel, _ in empty)
            print("    empty by file:")
            for rel, count in sorted(by_file.items()):
                print(f"      {rel}: {count}")
            for rel, key in empty[:10]:
                print(f"      - {rel}: {key}")
            if len(empty) > 10:
                print(f"      ... and {len(empty) - 10} more")
        print()

    print(f"TOTAL gaps (missing + empty across all locales): {total_gaps}")
    return total_gaps


def _print_json(report: dict[str, dict[str, Any]]) -> int:
    serializable = {
        locale: {
            "missing": [{"file": rel, "key": key} for rel, key in payload["missing"]],
            "empty": [{"file": rel, "key": key} for rel, key in payload["empty"]],
            "extra": [{"file": rel, "key": key} for rel, key in payload["extra"]],
            "missing_files": payload["missing_files"],
        }
        for locale, payload in report.items()
    }
    print(json.dumps(serializable, ensure_ascii=False, indent=2))
    total = sum(
        len(payload["missing"]) + len(payload["empty"]) for payload in report.values()
    )
    return total


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--root",
        type=Path,
        default=here / "src" / "resources" / "i18n",
        help="Path to the i18n root directory.",
    )
    parser.add_argument(
        "--reference",
        default="en",
        help="Reference locale to compare other locales against.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any gap is detected.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.root.is_dir():
        print(f"ERROR: i18n root not found: {args.root}", file=sys.stderr)
        return 2

    report = _analyze(args.root, args.reference)
    total = _print_json(report) if args.json else _print_report(report, args.reference)

    if args.strict and total > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
