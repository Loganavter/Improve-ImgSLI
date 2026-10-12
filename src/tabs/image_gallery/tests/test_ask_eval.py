"""P2 — offline eval harness for Ask AI answer quality (network-free)."""

from __future__ import annotations

from tabs.image_gallery.services.ask_eval import (
    load_dataset,
    run_live,
    score_answer,
    score_dataset,
)


def test_dataset_cases_all_match_expected_verdict():
    result = score_dataset()
    assert result["total"] >= 8
    assert result["failed"] == [], result["failed"]


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
