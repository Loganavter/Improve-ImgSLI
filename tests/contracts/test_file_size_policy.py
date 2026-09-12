"""File-size policy dogma — Audit-Meta registry.

Large src/*.py files (>500 lines, >400 for canvas features) must carry an
Audit-Meta: / File-Size-Exempt: marker explaining why they aren't split.
The central registry docs/dev/file_size_registry.json must be in sync.

Dogma source: docs/dev/FILE_SIZE_POLICY.md, docs/dev/CODE_PATTERNS.md.

Enforcement: mirrors src/devtools/file_meta.py logic so CI fails without
needing to run the tool separately.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
REGISTRY_PATH = REPO_ROOT / "docs" / "dev" / "file_size_registry.json"
POLICY_DOC = REPO_ROOT / "docs" / "dev" / "FILE_SIZE_POLICY.md"

AUDIT_LIMIT = 500
CANVAS_LIMIT = 400

_AUDIT_RE = re.compile(r"^\s*#?\s*Audit-Meta:\s*(.*)", re.MULTILINE)
_CANVAS_RE = re.compile(r"^\s*#?\s*File-Size-Exempt:\s*(.*)", re.MULTILINE)

EXCLUDE_PARTS = {"__pycache__", "tests", "venv", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _has_marker(text: str) -> bool:
    return bool(_AUDIT_RE.search(text) or _CANVAS_RE.search(text))


def _is_excluded(rel: Path) -> bool:
    return any(part in EXCLUDE_PARTS for part in rel.parts)


def _collect_violations():
    violations: list[str] = []
    for p in sorted(SRC_ROOT.rglob("*.py")):
        rel = p.relative_to(REPO_ROOT)
        if _is_excluded(rel):
            continue
        is_canvas = "canvas/features" in rel.as_posix()
        limit = CANVAS_LIMIT if is_canvas else AUDIT_LIMIT
        lines = _line_count(p)
        if lines <= limit:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if _has_marker(text):
            continue
        violations.append(f"{rel.as_posix()} ({lines} lines, limit {limit})")
    return violations


def test_oversized_files_have_audit_meta():
    violations = _collect_violations()
    assert not violations, (
        f"{len(violations)} file(s) over size limit without Audit-Meta:/File-Size-Exempt: — "
        f"split via use_cases/ per CODE_PATTERNS.md or add Audit-Meta: pattern=... reason=\"...\" "
        f"and run python src/devtools/file_meta.py --write-registry:\n  - "
        + "\n  - ".join(violations)
    )


def test_registry_exists_and_in_sync():
    assert POLICY_DOC.exists(), f"Missing policy doc: {POLICY_DOC}"
    assert REGISTRY_PATH.exists(), f"Missing registry: {REGISTRY_PATH} — run python src/devtools/file_meta.py --write-registry"

    # Rebuild expected registry via same logic as file_meta.py
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from devtools.file_meta import build_registry
    except ImportError:
        pytest.skip("file_meta module not importable")

    expected = build_registry()
    existing = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    assert existing == expected, (
        "file_size_registry.json is stale — run python src/devtools/file_meta.py --write-registry\n"
        f"expected {len(expected['entries'])} entries, got {len(existing.get('entries', []))}"
    )


def test_registry_entries_have_pattern():
    if not REGISTRY_PATH.exists():
        pytest.skip("no registry")
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    missing: list[str] = []
    for e in data.get("entries", []):
        # Canvas legacy File-Size-Exempt entries may be free-form reason — allow
        if e.get("marker") == "File-Size-Exempt:":
            continue
        raw = e.get("raw") or ""
        parsed = e.get("parsed") or {}
        if "pattern" not in parsed and "pattern=" not in raw:
            missing.append(f"{e['path']}: {raw!r}")
    assert not missing, (
        "Registry entries should contain pattern= — add pattern=state-machine|thin-owner|... per FILE_SIZE_POLICY.md:\n  - "
        + "\n  - ".join(missing)
    )
