# Audit-Meta: pattern=leaf-collector reason="Evidence layer E1: append-only journal + derived verdict + fail-open trace emission; stdlib-only, no Qt/toolkit imports"
"""Evidence journal — append-only, machine-readable proof per requirement/bug.

Frozen seam: ``docs/dev/EVIDENCE.md`` / ADR-008 (private sibling repo). This
module is deliberately content-free: it knows record *shape*, never requirement
text.

Why the shape exists:

- A "green suite" is not acceptance. A probe may only claim a verdict that an
  observed ``signal`` decided — precedent ``_verdict`` in
  ``core/control/nav_keys.py`` ("derived, never guessed"). Hence
  ``record_evidence(verdict="ok")`` with a blank signal raises ``ValueError``:
  the derivation guard, the anti-reward-hacking rule, not a style check.
- The journal is append-only so a sequence stays readable (a ``target_bug`` must
  show ``reproduced`` before ``fixed``; a hidden reset on import would erase
  that history — tests call :func:`reset_journal` explicitly).
- Records also go to the trace (``kind="evidence"``) so existing instruments
  (``read_log`` / ``query_trace`` / ``trace.jsonl``) read them; that emission is
  fail-open — tracing must never break a probe.

No Qt / toolkit imports at module level (and none at all here): this file is
importable in a bare interpreter.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_KIND_VERDICTS: dict[str, frozenset[str]] = {
    # Requirement / RFC / CR probe.
    "spec": frozenset({"ok", "violated", "skipped", "unmeasured"}),
    # Real failure case: "reproduced" is red-before (bug present), "fixed" after.
    "target_bug": frozenset({"reproduced", "fixed"}),
    # Human labels / external dataset.
    "ground_truth": frozenset({"ok", "violated", "skipped", "unmeasured"}),
}

_TRACE_KIND = "evidence"

_JOURNAL: list["EvidenceRecord"] = []
_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """One evidence fact. ``signal`` is the derived observation, never a guess."""

    spec_id: str
    kind: str
    verdict: str
    signal: str
    reason: str
    ids: tuple[str, ...] = ()
    area: str = ""


def record_evidence(
    spec_id: str,
    *,
    kind: str,
    verdict: str,
    signal: str,
    reason: str,
    ids: tuple[str, ...] = (),
    area: str = "",
) -> None:
    """Append one evidence record to the in-process journal (thread-safe).

    Validates ``kind``/``verdict`` against the frozen vocabulary and rejects a
    blank ``signal`` — a verdict must be derived from an observation. Emits a
    fail-open ``evidence`` trace record when the tracer is enabled.
    """
    allowed = _KIND_VERDICTS.get(kind)
    if allowed is None:
        raise ValueError(
            f"unknown evidence kind {kind!r}; expected one of {sorted(_KIND_VERDICTS)}"
        )
    if verdict not in allowed:
        raise ValueError(
            f"invalid verdict {verdict!r} for kind {kind!r}; expected one of {sorted(allowed)}"
        )
    if not signal.strip():
        raise ValueError(
            f"evidence {spec_id!r} ({kind}/{verdict}) requires a non-empty signal: "
            "a verdict must be derived from an observation, never guessed"
        )

    record = EvidenceRecord(
        spec_id=spec_id,
        kind=kind,
        verdict=verdict,
        signal=signal,
        reason=reason,
        ids=tuple(ids),
        area=area,
    )
    with _LOCK:
        _JOURNAL.append(record)

    _emit_trace(record)


def verdict(source: Any, spec_id: str) -> EvidenceRecord | None:
    """Latest evidence record for ``spec_id`` from ``source``; ``None`` if absent.

    ``source`` is ``None`` (the in-process journal), a path to a JSONL/trace
    file (``type: evidence`` lines; the real ``trace.jsonl`` shape with
    ``kind: "evidence"`` + nested ``payload`` is accepted too), or an iterable
    of :class:`EvidenceRecord` / dicts. Pure read: never mutates the journal.
    """
    found: EvidenceRecord | None = None
    for record in _iter_records(source):
        if record is not None and record.spec_id == spec_id:
            found = record
    return found


def reset_journal() -> None:
    """Clear the in-process journal. For tests only — never called on import."""
    with _LOCK:
        _JOURNAL.clear()


def _emit_trace(record: EvidenceRecord) -> None:
    """Best-effort trace emission. Fail-open by contract."""
    try:
        from core.tracing.tracer import Tracer

        if not Tracer.enabled():
            return
        Tracer.instance().record(
            _TRACE_KIND,
            f"{record.spec_id} {record.verdict}",
            payload={
                "spec_id": record.spec_id,
                "kind": record.kind,
                "verdict": record.verdict,
                "signal": record.signal,
                "reason": record.reason,
                "ids": list(record.ids),
                "area": record.area,
            },
        )
    except Exception:
        # Tracing is an observation channel, never a dependency of the probe.
        return


def _iter_records(source: Any) -> Iterable[EvidenceRecord | None]:
    if source is None:
        with _LOCK:
            return list(_JOURNAL)
    if isinstance(source, (str, os.PathLike)):
        return _read_jsonl(Path(source))
    return (_coerce(entry) for entry in source)


def _read_jsonl(path: Path) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue  # partial crash tail / unrelated noise
                if not _marks_evidence(entry):
                    continue
                coerced = _coerce(entry)
                if coerced is not None:
                    records.append(coerced)
    except OSError:
        return []
    return records


def _marks_evidence(entry: Any) -> bool:
    if not isinstance(entry, Mapping):
        return False
    if entry.get("type") == _TRACE_KIND:
        return True
    # Real trace.jsonl shape: TraceRecord.to_dict() -> {"kind": "evidence", "payload": {...}}
    return entry.get("kind") == _TRACE_KIND and isinstance(entry.get("payload"), Mapping)


def _coerce(entry: Any) -> EvidenceRecord | None:
    """Tolerantly read one record (dataclass / flat dict / trace-shaped dict)."""
    if isinstance(entry, EvidenceRecord):
        return entry
    if not isinstance(entry, Mapping):
        return None

    payload = entry.get("payload")
    data: Mapping[str, Any] = entry
    if isinstance(payload, Mapping) and payload.get("spec_id"):
        data = payload
    elif not entry.get("spec_id"):
        return None

    kind = data.get("kind")
    record_verdict = data.get("verdict")
    if kind not in _KIND_VERDICTS or record_verdict not in _KIND_VERDICTS[kind]:
        return None

    spec_id = data.get("spec_id")
    if not isinstance(spec_id, str) or not spec_id:
        return None

    ids_raw = data.get("ids") or ()
    if isinstance(ids_raw, str):
        ids: tuple[str, ...] = (ids_raw,)
    else:
        ids = tuple(ids_raw)

    return EvidenceRecord(
        spec_id=spec_id,
        kind=kind,
        verdict=record_verdict,
        signal=str(data.get("signal") or ""),
        reason=str(data.get("reason") or ""),
        ids=ids,
        area=str(data.get("area") or ""),
    )
