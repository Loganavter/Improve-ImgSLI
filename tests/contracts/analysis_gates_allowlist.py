"""Shared shrink-only allowlist for the gallery analysis-engine gates (W2).

``plan-gallery-analysis-engine-2026-10-20`` §Gates asks for gates that start
green on today's tree and can only ever shrink: every entry below is a site the
plan's later waves (W5 AI producers, P9 deletion) must remove, and
the gate fails just as loudly for a **stale** entry (code fixed, list not
updated) as for a **new** violation. That is the property that makes "a ratchet"
mean something — an allowlist that can silently rot is a comment with extra
steps.

Key shape (deliberately not a line number)::

    "<repo-relative path>|<stripped offending source line>"

Lines move when a module grows; the offending source line does not. The current
line number is reported in the failure message (``hits``), never used for
identity, so an unrelated edit above the site cannot turn one entry into a
"new violation" plus a "stale entry".

Value shape: a short reason naming which wave removes the entry (or why it is
not a violation at all). ``assert_ratchet`` rejects an empty reason — an
allowlist entry without a justification is how a gate becomes a rubber stamp.

Data lives here so the three W2 gate modules share one mechanism and one
convention (same idiom as ``tests/contracts/drain_guard_allowlist.py``). This
module contains data + helpers only; the tests live in ``test_analysis_*``.
"""

from __future__ import annotations

from collections.abc import Iterable

#: ``path|stripped source line`` — see the module docstring for why not a line.
HitKey = str

#: key -> "why this is still allowed / which wave deletes it".
Allowlist = dict[str, str]

#: key -> one entry per occurrence, formatted ``path:lineno — note``.
Hits = dict[str, tuple[str, ...]]


def make_key(path: str, line: str) -> HitKey:
    """Identity of a violation: path plus the stripped source line."""
    return f"{path}|{line.strip()}"


def add_hit(
    hits: Hits,
    *,
    path: str,
    lineno: int,
    line: str,
    note: str = "",
) -> None:
    """Record one occurrence under its line-text key.

    A single line can carry the same violation twice (``x == "ai" and y == "ai"``);
    the occurrence list keeps both line numbers so the message stays exact.
    """
    key = make_key(path, line)
    where = f"{path}:{lineno}"
    if note:
        where = f"{where} — {note}"
    hits[key] = (*hits.get(key, ()), where)


def source_line(source: str, lineno: int) -> str:
    """The stripped source text of ``lineno`` (1-based); ``""`` when out of range."""
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def _format_new(hits: Hits, new: Iterable[HitKey]) -> list[str]:
    lines: list[str] = []
    for key in sorted(new):
        path, _, text = key.partition("|")
        lines.append(f"  + {path}")
        lines.append(f"      {text}")
        for where in hits[key]:
            lines.append(f"      at {where}")
    return lines


def _format_stale(allowlist: Allowlist, stale: Iterable[HitKey]) -> list[str]:
    lines: list[str] = []
    for key in sorted(stale):
        path, _, text = key.partition("|")
        lines.append(f"  - {path}")
        lines.append(f"      {text}")
        lines.append(f"      reason was: {allowlist[key]}")
    return lines


def assert_ratchet(
    name: str,
    allowlist: Allowlist,
    hits: Hits,
) -> None:
    """Fail on any NEW hit, and on any allowlist entry that no longer hits.

    ``hits`` is the full scan result (not a delta): the allowlist is only
    allowed to name keys that are still in it. A fixed site therefore has to be
    deleted from the list in the same commit that fixes it.
    """
    empty = sorted(key for key, reason in allowlist.items() if not reason.strip())
    new = [key for key in hits if key not in allowlist]
    stale = [key for key in allowlist if key not in hits]

    problems: list[str] = []
    if empty:
        problems.append(
            f"{name}: {len(empty)} allowlist entr(y/ies) without a reason — "
            "every entry says why it is still allowed and which wave removes it:"
        )
        problems.extend(f"  ? {key}" for key in empty)
    if new:
        problems.append(
            f"{name}: {len(new)} NEW violation(s) — fix the code, or add a "
            "reasoned allowlist entry naming the wave that removes it:"
        )
        problems.extend(_format_new(hits, new))
    if stale:
        problems.append(
            f"{name}: {len(stale)} STALE allowlist entr(y/ies) — the code was "
            "fixed; delete the entry (shrink-only ratchet):"
        )
        problems.extend(_format_stale(allowlist, stale))
    if problems:
        raise AssertionError("\n".join(problems))
