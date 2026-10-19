"""P2 — offline eval harness for Ask AI answer quality (network-free)."""

from __future__ import annotations

import pytest

from core.evidence.journal import record_evidence, reset_journal, verdict
from tabs.image_gallery.services.ask_eval import (
    load_dataset,
    run_live,
    score_answer,
    score_dataset,
)


@pytest.fixture(autouse=True)
def _reset_evidence_journal():
    """The evidence journal is process-global: reset per probe, never leak."""
    reset_journal()
    yield


def test_dataset_cases_all_match_expected_verdict():
    """The labelled corpus is the ground truth; the probe scores content.

    Falsification: a case whose detector verdict diverges from its label lands
    in ``result["failed"]``; the evidence record then reads ``violated`` with
    ``failed=N`` in ``signal``, so a regression fails here with the measured
    count instead of a bare green flag (TESTING.md rule 7).
    """
    result = score_dataset()
    assert result["total"] >= 8
    assert result["failed"] == [], result["failed"]

    record_evidence("gt.gallery.ask_eval", kind="ground_truth",
                    verdict="ok" if not result["failed"] else "violated",
                    signal=f"total={result['total']} failed={len(result['failed'])}",
                    reason="labelled dataset cases match their expected verdict",
                    ids=tuple(str(f) for f in result["failed"]), area="gallery.ask_eval")
    record = verdict(None, "gt.gallery.ask_eval")
    assert record is not None, "ask-eval ground-truth probe emitted no evidence"
    assert record.verdict == "ok", record.signal
    assert record.kind == "ground_truth"


def test_dataset_covers_both_clean_and_violating_cases():
    cases = load_dataset()
    verdicts = {bool(c.get("expect_ok", True)) for c in cases}
    assert verdicts == {True, False}
    ids = [c.get("id") for c in cases]
    assert len(ids) == len(set(ids))


def test_score_answer_reports_content_not_just_a_flag():
    bad = score_answer("Summary", "img_1 is 88%.", labels=())
    assert bad["ok"] is False
    assert bad["reason"] and "percent" in bad["reason"].lower()

    good = score_answer("Summary", "Prefer img_1; the rest are equivalent.", labels=())
    assert good["ok"] is True
    assert good["reason"] is None


def test_run_live_is_a_noop_without_the_env_gate(monkeypatch):
    monkeypatch.delenv("IMGSLI_ASK_EVAL", raising=False)
    assert run_live() is None
