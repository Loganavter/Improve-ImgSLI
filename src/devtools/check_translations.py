#!/usr/bin/env python3
"""Find gaps in localization files.

Compares non-reference locales against the reference (default: ``en``) and
reports missing keys and empty values. Designed to be run from the project
root.

Usage:
    python src/devtools/check_translations.py
    python src/devtools/check_translations.py --root src/resources/i18n --reference en
    python src/devtools/check_translations.py --root src/resources/i18n --root src/tabs/image_compare/resources/i18n
    python src/devtools/check_translations.py --json     # machine-readable output
    python src/devtools/check_translations.py --strict   # exit 1 if any gap found
    python src/devtools/check_translations.py --code-keys # keys used in code exist in a catalog

With no ``--root``, every ``resources/i18n`` tree under ``src/`` is checked
(host + tabs + plugins fan-out); each root is compared against its own
reference locale independently.
"""

from __future__ import annotations

import argparse
import json
import re
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


def discover_i18n_roots(src_root: Path | None = None) -> list[Path]:
    """Every ``resources/i18n`` tree under ``src/`` (host + tabs + plugins).

    i18n files are scattered (``src/resources/i18n`` plus per-tab and
    per-plugin ``resources/i18n`` trees, including nested ones such as the
    magnifier feature's) — checking only the host root silently misses
    tab/plugin gaps. The host root sorts first; the rest follow in path
    order for stable reports.
    """
    base = src_root if src_root is not None else Path(__file__).resolve().parents[1]
    found = sorted(
        (p for p in base.rglob("resources/i18n") if p.is_dir()),
        key=lambda p: p.as_posix(),
    )
    host = base / "resources" / "i18n"
    ordered = [host] if host in found else []
    ordered.extend(p for p in found if p != host)
    return ordered


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


# ---------------------------------------------------------------------------
# Code keys: every literal key a widget asks for must exist in a catalog
# ---------------------------------------------------------------------------

#: Calls whose FIRST string literal is a catalog key. ``tr(key, language, default)``,
#: the app's ``_tr(key, default)``, the toolkit's ``_translate_key(key, lang, fallback)``
#: and ``translatable_callback(key, ...)`` all start with the key.
_CODE_KEY_CALLS = ("tr", "_tr", "_translate_key", "translatable_callback", "translatable")

_CODE_KEY_RE = re.compile(
    r"\b(?:" + "|".join(map(re.escape, _CODE_KEY_CALLS)) + r")\(\s*[\"']([A-Za-z0-9_.\-]+)[\"']"
)

#: Default allowlist, next to this script.
CODE_KEY_ALLOWLIST = Path(__file__).resolve().parent / "i18n_code_keys_allowlist.txt"


def _flatten_keys(value: Any, prefix: str, out: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten_keys(child, f"{prefix}.{key}" if prefix else str(key), out)
    else:
        out.add(prefix)


def catalog_keys(roots: Iterable[Path]) -> set[str]:
    """Every key any catalog (any locale, any root) defines."""
    keys: set[str] = set()
    for root in roots:
        for path in root.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            _flatten_keys(data, "", keys)
    return keys


def code_sources(src_root: Path) -> list[Path]:
    """The app's ``src`` plus the sibling toolkit's, when it is checked out."""
    sources = [src_root]
    sibling = src_root.parent.parent / "sli-ui-toolkit" / "src"
    if sibling.is_dir():
        sources.append(sibling)
    return sources


def scan_code_keys(sources: Iterable[Path]) -> dict[str, list[str]]:
    """{key: ["file:line", ...]} for every literal key asked for in *sources*."""
    found: dict[str, list[str]] = {}
    for source in sources:
        for path in source.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _CODE_KEY_RE.finditer(text):
                key = match.group(1)
                line = text.count("\n", 0, match.start()) + 1
                found.setdefault(key, []).append(f"{path}:{line}")
    return found


def load_code_key_allowlist(path: Path | None) -> dict[str, str]:
    """``{key: reason}`` from ``key  # reason`` lines; missing file is empty."""
    allowed: dict[str, str] = {}
    if path is None or not path.is_file():
        return allowed
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _sep, reason = raw.partition("#")
        allowed[key.strip()] = reason.strip() or "(no reason given)"
    return allowed


def report_code_keys(
    roots: Iterable[Path],
    sources: Iterable[Path],
    allowlist: dict[str, str],
) -> int:
    """Print code-key findings; returns the number of UNALLOWLISTED misses."""
    keys = catalog_keys(roots)
    used = scan_code_keys(sources)
    missing = {k: v for k, v in used.items() if k not in keys}
    waived = {k: v for k, v in missing.items() if k in allowlist}
    failures = {k: v for k, v in missing.items() if k not in allowlist}

    print(
        f"code keys: {sum(len(v) for v in used.values())} literal call(s), "
        f"{len(used)} distinct key(s), {len(keys)} catalog key(s)"
    )
    for key, where in sorted(waived.items()):
        print(f"  allowed   {key}  ({allowlist[key]})")
    for key, where in sorted(failures.items()):
        print(f"  MISSING   {key}")
        for location in where[:5]:
            print(f"              {location}")
        if len(where) > 5:
            print(f"              ... {len(where) - 5} more")
    if not failures:
        print("code keys OK: every literal key exists in a catalog (or is allowlisted)")
    return len(failures)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        help=(
            "i18n root to check (repeatable). When omitted, every "
            "resources/i18n tree under src/ is checked (host + tabs + "
            "plugins fan-out)."
        ),
    )
    parser.add_argument(
        "--reference",
        default="en",
        help="Reference locale to compare other locales against.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--code-keys",
        action="store_true",
        help=(
            "Also check that every literal key used in code (tr/_tr/_translate_key/"
            "translatable_callback) exists in a catalog. Scans this repo's src and the "
            "sibling sli-ui-toolkit/src when it is present."
        ),
    )
    parser.add_argument(
        "--code-src",
        type=Path,
        action="append",
        default=None,
        help=(
            "Source tree(s) to scan for literal translation keys (repeatable). "
            "Defaults to this repo's src plus the sibling sli-ui-toolkit/src when present."
        ),
    )
    parser.add_argument(
        "--code-allowlist",
        type=Path,
        default=CODE_KEY_ALLOWLIST,
        help="Allowlist of dynamic keys (key  # reason).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any gap is detected.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    roots = list(args.root) if args.root else discover_i18n_roots(here / "src")
    for root in roots:
        if not root.is_dir():
            print(f"ERROR: i18n root not found: {root}", file=sys.stderr)
            return 2

    multi = len(roots) > 1
    grand_total = 0
    json_payload: dict[str, Any] = {}
    for root in roots:
        report = _analyze(root, args.reference)
        if multi and not args.json:
            print(f"== {root} ==")
        if args.json:
            serializable = {
                locale: {
                    "missing": [{"file": rel, "key": key} for rel, key in payload["missing"]],
                    "empty": [{"file": rel, "key": key} for rel, key in payload["empty"]],
                    "extra": [{"file": rel, "key": key} for rel, key in payload["extra"]],
                    "missing_files": payload["missing_files"],
                }
                for locale, payload in report.items()
            }
            if multi:
                json_payload[str(root)] = serializable
            else:
                json_payload = serializable
            grand_total += sum(
                len(payload["missing"]) + len(payload["empty"])
                for payload in report.values()
            )
        else:
            grand_total += _print_report(report, args.reference)

    if args.json:
        print(json.dumps(json_payload, ensure_ascii=False, indent=2))

    code_key_failures = 0
    if args.code_keys:
        if multi and not args.json:
            print()
        sources = (
            list(args.code_src) if args.code_src else code_sources(here / "src")
        )
        code_key_failures = report_code_keys(
            roots,
            sources,
            load_code_key_allowlist(args.code_allowlist),
        )

    if args.strict and (grand_total > 0 or code_key_failures > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
