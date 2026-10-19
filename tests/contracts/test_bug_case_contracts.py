"""Contract: target-bug evidence sites obey the frozen ``target_bug`` vocabulary.

Frozen seam: ``docs/dev/EVIDENCE.md`` (three evidence kinds) + ADR-008.
Every probe under ``tests/target_bug/`` records with ``record_evidence``;
this scan keeps the vocabulary honest without executing the probes:

- a ``bug.<case>`` site must pass ``kind="target_bug"``;
- its ``verdict`` must be a literal ``reproduced`` or ``fixed`` (the two
  frozen ``target_bug`` verdicts; no ``ok``);
- ``signal`` must be present (the derivation guard);
- each case file must carry BOTH sites - a ``fixed``-only file never saw the
  bug and is rejected by the coverage gate (EVIDENCE.md, coverage rule 4).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_BUG_DIR = ROOT / "tests" / "target_bug"
TARGET_BUG_VERDICTS = {"reproduced", "fixed"}


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _target_bug_sites() -> list[tuple[Path, ast.Call]]:
    sites: list[tuple[Path, ast.Call]] = []
    for path in sorted(TARGET_BUG_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node.func) != "record_evidence":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.startswith("bug.")
            ):
                continue
            sites.append((path, node))
    return sites


def test_bug_evidence_sites_use_frozen_target_bug_vocabulary() -> None:
    sites = _target_bug_sites()
    assert sites, "no bug.<case> record_evidence sites found under tests/target_bug"

    problems: list[str] = []
    verdicts_per_file: dict[Path, set[str]] = {}

    for path, node in sites:
        where = f"{path.name}:{node.lineno}"
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}

        kind = kwargs.get("kind")
        if not (isinstance(kind, ast.Constant) and kind.value == "target_bug"):
            problems.append(f'{where}: kind must be the literal "target_bug"')

        verdict_node = kwargs.get("verdict")
        if not (
            isinstance(verdict_node, ast.Constant)
            and verdict_node.value in TARGET_BUG_VERDICTS
        ):
            problems.append(
                f"{where}: verdict must be a literal reproduced|fixed (got "
                f"{ast.dump(verdict_node) if verdict_node is not None else 'missing'})"
            )
        else:
            verdicts_per_file.setdefault(path, set()).add(verdict_node.value)

        signal_node = kwargs.get("signal")
        if signal_node is None or (
            isinstance(signal_node, ast.Constant) and not str(signal_node.value).strip()
        ):
            problems.append(f"{where}: signal is required (derived observation)")

    for path, seen in verdicts_per_file.items():
        if seen != TARGET_BUG_VERDICTS:
            problems.append(
                f"{path.name}: needs both reproduced (red-before) and fixed sites, "
                f"saw {sorted(seen)}"
            )

    assert not problems, "\n".join(problems)
