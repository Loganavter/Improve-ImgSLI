"""Offline eval harness for Ask AI answer quality.

Network-free by default: :func:`score_answer` runs the deterministic guard over
a fixture dataset, so the suite proves the scoring *rules* — not a live model's
whim (green counts are not correctness). :func:`run_live` is a human-gated
runner (env ``IMGSLI_ASK_EVAL=1``) for a real backend; it is never part of CI.

Why a dataset and not only unit tests: the prompt is a build artifact
(DSPy/GEPA-style, plan-gallery-ask-ai-answer-quality); a fixture set with
expected verdicts makes prompt changes measurable and gives a future optimizer
something to target.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from tabs.image_gallery.services.ask_answer_guard import (
    answer_violation,
    is_numeric_question,
)

#: Fixture cases live next to this module.
DATASET_PATH = Path(__file__).with_name("ask_eval_dataset.json")

#: The env gate for the live, human-run eval (never set in CI).
LIVE_ENV = "IMGSLI_ASK_EVAL"


def load_dataset(path: str | Path | None = None) -> list[dict]:
    """Load the fixture dataset (list of cases)."""
    p = Path(path) if path is not None else DATASET_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ask eval dataset must be a list of cases")
    return [c for c in data if isinstance(c, dict)]


def score_answer(
    question: str,
    answer: str,
    *,
    labels: tuple[str, ...] | list[str] = (),
    numeric: bool | None = None,
) -> dict:
    """Score one answer: ``{"ok", "reason", "numeric"}`` (``ok`` = no violation)."""
    if numeric is None:
        numeric = is_numeric_question(question)
    reason = answer_violation(answer, numeric=numeric, labels=labels)
    return {"ok": reason is None, "reason": reason, "numeric": numeric}


def score_dataset(dataset: list[dict] | None = None) -> dict:
    """Score every fixture; report total / failures (content, not counts only)."""
    cases = dataset if dataset is not None else load_dataset()
    failed = []
    for case in cases:
        verdict = score_answer(
            case.get("question", ""),
            case.get("answer", ""),
            labels=case.get("labels", ()),
            numeric=case.get("numeric"),
        )
        expect_ok = bool(case.get("expect_ok", True))
        if verdict["ok"] != expect_ok:
            failed.append(
                {
                    "id": case.get("id"),
                    "expected_ok": expect_ok,
                    "got_ok": verdict["ok"],
                    "reason": verdict["reason"],
                }
            )
    return {"total": len(cases), "failed": failed}


def run_live(*_, **__) -> None:
    """Human-gated live runner — a deliberate no-op unless ``IMGSLI_ASK_EVAL=1``.

    Not wired to a provider on purpose; when used it should call
    :func:`ask_router.answer` over each dataset question with a real transport
    and print :func:`score_answer` verdicts for human review. Kept out of CI.
    """
    if str(os.environ.get(LIVE_ENV, "")).strip() not in ("1", "true", "yes"):
        return None
    # Intentionally minimal: a live run needs a configured backend + network,
    # so it stays a manual step (see plan P2). No silent network in tests.
    return None


__all__ = [
    "DATASET_PATH",
    "LIVE_ENV",
    "load_dataset",
    "run_live",
    "score_answer",
    "score_dataset",
]
