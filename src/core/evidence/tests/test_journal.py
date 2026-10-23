"""Behavioural tests for the evidence journal (E1).

Dogma: ``docs/dev/EVIDENCE.md`` § Anti-reward-hacking rules + ADR-008. A
verdict must be *derived* from an observation (precedent: ``_verdict`` in
``core/control/nav_keys.py``), evidence is append-only, and reads are pure.

Falsification story (TESTING.md § Rules for writing new tests, rule 7) — each
test names the mutation it catches:

- ``test_derivation_guard_rejects_blank_signal`` fails if the empty-signal
  ``ValueError`` is removed (the anti-reward-hacking guard) and also if
  validation happens *after* the append (the journal would gain a record).
- ``test_latest_record_wins`` fails if ``verdict`` returns first-match instead
  of the latest append.
- ``test_reset_journal_clears_in_process_only`` fails if reads mutate the
  journal or if reset stops clearing it.
- ``test_validates_kind_and_verdict`` fails if the frozen vocabulary check is
  dropped (e.g. ``target_bug`` accepting ``ok``).
- ``test_file_source_reads_flat_and_trace_shaped_lines`` fails if the reader
  stops tolerating the real ``trace.jsonl`` shape (record ``kind`` +
  ``payload``) or starts treating non-evidence lines as evidence.
- ``test_trace_emission_is_fail_open`` fails if a raising tracer propagates out
  of ``record_evidence`` (tracing would break a probe) or if the emitted
  payload loses the derived ``signal``.
"""

# stale-test-refs: synthetic-ids — this file tests the journal reader, so every
# spec id below is a placeholder, not a requirement in docs/spec/registry.yaml.
# The private gate `scripts/check_stale_test_refs.py` honours this marker.

from __future__ import annotations

import json
import os
import threading
from dataclasses import FrozenInstanceError

import pytest

from core.evidence import journal as journal_module
from core.evidence.journal import (
    EvidenceRecord,
    record_evidence,
    reset_journal,
    verdict,
)


@pytest.fixture(autouse=True)
def _clean_journal():
    reset_journal()
    yield
    reset_journal()


# --------------------------------------------------------------------------- #
# Derivation guard (the anti-reward-hacking rule)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_derivation_guard_rejects_blank_signal(blank):
    with pytest.raises(ValueError, match="non-empty signal"):
        record_evidence(
            "spec.demo.blank",
            kind="spec",
            verdict="ok",
            signal=blank,
            reason="would be a guessed verdict",
        )
    # Validation happens before the append: a rejected claim leaves no record.
    assert verdict(None, "spec.demo.blank") is None


def test_derivation_guard_applies_beyond_ok():
    with pytest.raises(ValueError, match="non-empty signal"):
        record_evidence(
            "bug.demo.blank",
            kind="target_bug",
            verdict="fixed",
            signal="",
            reason="no observation",
        )
    assert verdict(None, "bug.demo.blank") is None


# --------------------------------------------------------------------------- #
# Append-only + latest semantics
# --------------------------------------------------------------------------- #


def test_latest_record_wins():
    record_evidence(
        "bug.demo.recur",
        kind="target_bug",
        verdict="reproduced",
        signal="preview pixel differs at (3,7)",
        reason="red before the fix",
        ids=("frame=42",),
        area="demo.canvas",
    )
    record_evidence(
        "bug.demo.recur",
        kind="target_bug",
        verdict="fixed",
        signal="preview pixel equals export at (3,7)",
        reason="green after the fix",
        ids=("frame=99",),
        area="demo.canvas",
    )

    latest = verdict(None, "bug.demo.recur")
    assert latest is not None
    assert latest.verdict == "fixed"
    assert latest.signal == "preview pixel equals export at (3,7)"
    assert latest.ids == ("frame=99",)

    # The earlier record is still in the journal (append-only): only the read
    # picks the last one.
    assert [r.verdict for r in journal_module._JOURNAL] == ["reproduced", "fixed"]


def test_latest_record_wins_per_spec_id_only():
    record_evidence("spec.a", kind="spec", verdict="ok", signal="a=1", reason="")
    record_evidence("spec.b", kind="spec", verdict="violated", signal="b=0", reason="")
    assert verdict(None, "spec.a").verdict == "ok"
    assert verdict(None, "spec.b").verdict == "violated"
    assert verdict(None, "spec.c") is None


def test_reset_journal_clears_in_process_only():
    record_evidence("spec.demo.reset", kind="spec", verdict="ok", signal="s=1", reason="")
    before = len(journal_module._JOURNAL)
    # Reads are pure: no append, no mutation.
    assert verdict(None, "spec.demo.reset") is not None
    assert verdict(None, "spec.demo.reset") is not None
    assert len(journal_module._JOURNAL) == before

    reset_journal()
    assert verdict(None, "spec.demo.reset") is None
    assert journal_module._JOURNAL == []


def test_records_are_immutable_and_default_shape_is_empty():
    record_evidence("spec.demo.shape", kind="spec", verdict="ok", signal="s=1", reason="")
    record = verdict(None, "spec.demo.shape")
    assert record == EvidenceRecord(
        spec_id="spec.demo.shape",
        kind="spec",
        verdict="ok",
        signal="s=1",
        reason="",
    )
    assert record.ids == ()
    assert record.area == ""
    with pytest.raises(FrozenInstanceError):
        record.verdict = "violated"


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("kind", "bad_verdict"),
    [
        ("spec", "fixed"),
        ("spec", "reproduced"),
        ("ground_truth", "fixed"),
        ("target_bug", "ok"),
        ("target_bug", "violated"),
        ("unknown", "ok"),
    ],
)
def test_validates_kind_and_verdict(kind, bad_verdict):
    with pytest.raises(ValueError):
        record_evidence(
            "spec.demo.bad",
            kind=kind,
            verdict=bad_verdict,
            signal="observed",
            reason="",
        )
    assert verdict(None, "spec.demo.bad") is None


def test_target_bug_and_ground_truth_vocabularies_are_accepted():
    record_evidence("bug.demo.ok", kind="target_bug", verdict="reproduced", signal="s", reason="")
    record_evidence("gt.demo.ok", kind="ground_truth", verdict="unmeasured", signal="n=0", reason="")
    assert verdict(None, "bug.demo.ok").verdict == "reproduced"
    assert verdict(None, "gt.demo.ok").verdict == "unmeasured"


# --------------------------------------------------------------------------- #
# Sources: file / iterable
# --------------------------------------------------------------------------- #


def test_file_source_reads_flat_and_trace_shaped_lines(tmp_path):
    path = tmp_path / "trace.jsonl"
    rows = [
        # Real trace.jsonl shape (TraceRecord.to_dict() + kind="evidence").
        {
            "seq": 1,
            "ts": 1.0,
            "kind": "evidence",
            "payload": {
                "spec_id": "bug.demo.file",
                "kind": "target_bug",
                "verdict": "reproduced",
                "signal": "red-before",
                "reason": "",
                "ids": ["frame=1"],
                "area": "canvas",
            },
        },
        # Unrelated trace traffic must not be mistaken for evidence.
        {"seq": 2, "ts": 2.0, "kind": "render", "payload": {"spec_id": "bug.demo.file"}},
        {"seq": 3, "ts": 3.0, "kind": "evidence", "payload": {"arbitrary": True}},
        # Frozen JSONL line shape: type + flat fields.
        {
            "ts": "2026-10-19T15:00:00Z",
            "type": "evidence",
            "spec_id": "bug.demo.file",
            "kind": "target_bug",
            "verdict": "fixed",
            "signal": "green-after",
            "reason": "fixed",
            "ids": ["frame=2"],
            "area": "canvas",
        },
        "not-json-at-all {",
    ]
    path.write_text("\n".join(json.dumps(r) if not isinstance(r, str) else r for r in rows), encoding="utf-8")

    latest = verdict(str(path), "bug.demo.file")
    assert latest is not None
    assert latest.verdict == "fixed"
    assert latest.signal == "green-after"
    assert latest.ids == ("frame=2",)

    # Path objects work too, and reading a file does not populate the journal.
    assert verdict(path, "bug.demo.file").verdict == "fixed"
    assert verdict(None, "bug.demo.file") is None
    assert os.path.exists(path)


def test_missing_file_source_is_empty_not_an_error(tmp_path):
    assert verdict(tmp_path / "absent.jsonl", "spec.any") is None


def test_iterable_source_of_records_and_dicts():
    records = [
        EvidenceRecord("spec.it", "spec", "violated", "v=0", ""),
        {
            "spec_id": "spec.it",
            "kind": "spec",
            "verdict": "ok",
            "signal": "v=1",
            "reason": "re-derived",
        },
    ]
    latest = verdict(iter(records), "spec.it")
    assert latest is not None and latest.verdict == "ok" and latest.signal == "v=1"


# --------------------------------------------------------------------------- #
# Trace emission (fail-open)
# --------------------------------------------------------------------------- #


class _FakeTracer:
    enabled_value = True

    def __init__(self):
        self.calls = []

    def record(self, kind, summary, payload=None, **_kwargs):
        self.calls.append((kind, summary, payload))

    @classmethod
    def enabled(cls):
        return cls.enabled_value

    @classmethod
    def instance(cls):
        return _FAKE


_FAKE = _FakeTracer()


class _ExplodingTracer:
    def record(self, *_args, **_kwargs):
        raise RuntimeError("tracer exploded")


def test_trace_emission_is_fail_open(monkeypatch):
    from core.tracing import tracer as tracer_module

    _FAKE.calls.clear()
    monkeypatch.setattr(tracer_module.Tracer, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(tracer_module.Tracer, "instance", classmethod(lambda cls: _FAKE))

    record_evidence(
        "spec.demo.trace",
        kind="spec",
        verdict="ok",
        signal="x=1",
        reason="observed",
        ids=("a", "b"),
        area="demo",
    )

    assert len(_FAKE.calls) == 1
    kind, summary, payload = _FAKE.calls[0]
    assert kind == "evidence"
    assert summary == "spec.demo.trace ok"
    assert payload == {
        "spec_id": "spec.demo.trace",
        "kind": "spec",
        "verdict": "ok",
        "signal": "x=1",
        "reason": "observed",
        "ids": ["a", "b"],
        "area": "demo",
    }

    # A broken tracer must never break the probe: the journal still gets it.
    monkeypatch.setattr(tracer_module.Tracer, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(tracer_module.Tracer, "instance", classmethod(lambda cls: _ExplodingTracer()))
    record_evidence("spec.demo.trace2", kind="spec", verdict="ok", signal="x=2", reason="")
    assert verdict(None, "spec.demo.trace2") is not None


def test_trace_emission_skipped_when_disabled(monkeypatch):
    from core.tracing import tracer as tracer_module

    _FAKE.calls.clear()
    monkeypatch.setattr(tracer_module.Tracer, "enabled", classmethod(lambda cls: False))
    monkeypatch.setattr(tracer_module.Tracer, "instance", classmethod(lambda cls: _FAKE))
    record_evidence("spec.demo.off", kind="spec", verdict="ok", signal="x=1", reason="")
    assert _FAKE.calls == []
    assert verdict(None, "spec.demo.off") is not None


# --------------------------------------------------------------------------- #
# Thread safety
# --------------------------------------------------------------------------- #


def test_concurrent_appends_are_all_recorded():
    def worker(n: int):
        for i in range(50):
            record_evidence(
                f"spec.demo.thread{n}.{i}",
                kind="spec",
                verdict="ok",
                signal=f"i={i}",
                reason="",
            )

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(journal_module._JOURNAL) == 8 * 50
    assert verdict(None, "spec.demo.thread7.49").signal == "i=49"
