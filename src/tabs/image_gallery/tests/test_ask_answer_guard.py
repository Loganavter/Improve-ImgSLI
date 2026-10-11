"""P1 — deterministic Ask AI answer guard (pure, no Qt/HTTP).

Content-distinguishable cases: every violation category has a case that the
guard must flag AND a near-miss it must NOT flag (aliases like ``img_1`` must
not read as "numbers"; a numeric question must not trip the number rule).
"""

from __future__ import annotations

from tabs.image_gallery.services.ask_answer_guard import (
    answer_violation,
    build_correction_feedback,
    is_numeric_question,
)


def test_clean_answer_with_aliases_is_not_flagged():
    assert answer_violation(
        "Prefer img_1 — it is the cleanest; img_2 is close but softer.",
        numeric=False,
        labels=("Sharpness",),
    ) is None


def test_percentages_on_non_numeric_question_are_flagged():
    reason = answer_violation(
        "img_1 is 88% vs img_2 at 71%.", numeric=False
    )
    assert reason and "percent" in reason.lower()


def test_bare_number_on_non_numeric_question_is_flagged_but_alias_is_not():
    assert answer_violation("img_1 looks best.", numeric=False) is None  # alias digit is safe
    reason = answer_violation("prefer variant 3.", numeric=False)
    assert reason and "numbers" in reason.lower()


def test_numeric_question_allows_numbers():
    assert answer_violation("img_1 scores 88.", numeric=True) is None
    assert answer_violation("img_1 is 88%.", numeric=True) is None


def test_preamble_and_persona_are_flagged():
    assert answer_violation("Sure, here is the summary.", numeric=False)
    assert answer_violation("As a photographer, I'd keep img_1.", numeric=False)
    assert answer_violation("Конечно, вот ответ.", numeric=False)
    assert answer_violation("Based on the metrics, keep img_1.", numeric=False)


def test_metric_label_recital_is_flagged():
    reason = answer_violation(
        "The Sharpness of img_1 is high.", numeric=False, labels=("Sharpness",)
    )
    assert reason and "Sharpness" in reason


def test_short_common_labels_do_not_trigger_false_positives():
    # "Clean"/"Detail" are legitimate prose words, not metric recitals.
    assert answer_violation(
        "Looks clean and detailed.", numeric=False, labels=("Clean", "Detail")
    ) is None


def test_over_length_is_flagged():
    long = " ".join(["A sentence."] * 6)
    reason = answer_violation(long, numeric=False)
    assert reason and "long" in reason.lower()


def test_empty_answer_is_flagged():
    assert answer_violation("   ", numeric=False)


def test_is_numeric_question_detection():
    assert is_numeric_question("Summary") is False
    assert is_numeric_question("What stands out?") is False
    assert is_numeric_question("give me the sharpness numbers") is True
    assert is_numeric_question("Сколько баллов у img_1?") is True
    assert is_numeric_question("which is 88%?") is True


def test_correction_feedback_names_the_reason():
    fb = build_correction_feedback("quotes percentages")
    assert "quotes percentages" in fb
    assert "JSON envelope" in fb
