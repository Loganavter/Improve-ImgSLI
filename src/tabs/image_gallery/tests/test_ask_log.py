"""Ask AI disk log: record shape, secrets, bounding, scope filtering.

Falsification (pre-fix): the module does not exist — answers lived only in
``GalleryController._ask_cache`` and vanished with the process, so there was
nothing to read back and no "N previous questions" to show.

Hermetic: ``IMGSLI_PROJECT_CACHE`` points the shared cache root at ``tmp_path``
(the same override ``ai_cache``/``vlm_cache`` honour), so the real user cache is
never touched.
"""

from __future__ import annotations

import json

import pytest

from tabs.image_gallery.services import ask_log


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("IMGSLI_PROJECT_CACHE", str(tmp_path / "cache"))
    return tmp_path


def _answer(**overrides):
    kwargs = dict(
        scope_kind="selection",
        scope_label="Selection",
        paths=["/gallery/a.png"],
        question="What matters here?",
        answer="The first image is sharper.",
        model="openai/gpt-4o",
        base_url="https://api.example.test/v1",
        mode="fidelity",
        profile="sharpness,noise",
        effort="low",
        cache_hit=False,
    )
    kwargs.update(overrides)
    return kwargs


def test_record_shape_is_fixed_and_deterministic():
    rec = ask_log.append_answer(**_answer())
    assert rec is not None
    assert list(rec) == list(ask_log.RECORD_KEYS)
    assert list(rec["backend"]) == ["model", "base_url"]
    assert rec["ts"], "ts must be stamped"
    assert rec["paths"] == ["/gallery/a.png"]
    assert rec["cache_hit"] is False

    stored = ask_log.recent(limit=1)[0]
    assert list(stored) == list(ask_log.RECORD_KEYS)
    assert json.loads(ask_log.log_path().read_text(encoding="utf-8").strip()) == stored


def test_log_lives_under_the_shared_cache_root(tmp_path):
    ask_log.append_answer(**_answer())
    assert ask_log.log_path() == (
        tmp_path / "cache" / ask_log.ASK_LOG_DIRNAME / ask_log.ASK_LOG_FILENAME
    )
    assert ask_log.log_path().is_file()


def test_api_key_is_never_persisted():
    record = ask_log.make_record(**_answer())
    # Simulate a caller smuggling a secret into the backend mapping.
    record["backend"]["api_key"] = "sk-super-secret"
    record["api_key"] = "sk-super-secret"
    assert ask_log.append(record) is True

    text = ask_log.log_path().read_text(encoding="utf-8")
    assert "sk-super-secret" not in text
    assert "api_key" not in text
    assert ask_log.recent(limit=1)[0]["backend"] == {
        "model": "openai/gpt-4o",
        "base_url": "https://api.example.test/v1",
    }


def test_cache_hit_is_recorded_as_a_flag_not_a_second_schema():
    rec = ask_log.append_answer(**_answer(cache_hit=True))
    assert rec["cache_hit"] is True
    assert ask_log.recent(limit=1)[0]["cache_hit"] is True


def test_trim_keeps_the_newest_records():
    for index in range(5):
        ask_log.append_answer(**_answer(question=f"q{index}", answer=f"a{index}"))

    dropped = ask_log.trim(max_records=2)

    assert dropped == 3
    assert [r["question"] for r in ask_log.recent(limit=10)] == ["q4", "q3"]


def test_append_enforces_the_bound(monkeypatch):
    monkeypatch.setattr(ask_log, "ASK_LOG_MAX_RECORDS", 3)
    for index in range(5):
        ask_log.append_answer(**_answer(question=f"q{index}", answer=f"a{index}"))

    records = ask_log.recent(limit=10)
    assert [r["question"] for r in records] == ["q4", "q3", "q2"]


def test_corrupt_line_is_skipped_and_dropped_by_trim():
    ask_log.append_answer(**_answer(question="kept"))
    with ask_log.log_path().open("a", encoding="utf-8") as handle:
        handle.write('{"truncated": \n')

    assert [r["question"] for r in ask_log.recent(limit=10)] == ["kept"]
    assert ask_log.trim(max_records=ask_log.ASK_LOG_MAX_RECORDS) == 1
    assert ask_log.recent(limit=10) and len(ask_log.recent(limit=10)) == 1


def test_recent_filters_by_scope_path_intersection():
    ask_log.append_answer(**_answer(paths=["/g/a.png"], question="qa", answer="A"))
    ask_log.append_answer(**_answer(paths=["/g/b.png"], question="qb", answer="B"))
    ask_log.append_answer(
        **_answer(paths=["/g/a.png", "/g/b.png"], question="qab", answer="AB")
    )

    # Newest first; a series record matches through any member path.
    assert [r["question"] for r in ask_log.recent(scope_paths=["/g/a.png"])] == [
        "qab",
        "qa",
    ]
    assert [r["question"] for r in ask_log.recent(scope_paths=["/g/b.png"])] == [
        "qab",
        "qb",
    ]
    assert ask_log.recent(scope_paths=["/g/missing.png"]) == []
    # None / empty = whole log (no scope filter).
    assert len(ask_log.recent(scope_paths=None, limit=10)) == 3
    assert len(ask_log.recent(scope_paths=(), limit=10)) == 3


def test_count_respects_scope_and_limit_zero():
    ask_log.append_answer(**_answer(paths=["/g/a.png"]))
    ask_log.append_answer(**_answer(paths=["/g/b.png"]))
    assert ask_log.count() == 2
    assert ask_log.count(scope_paths=["/g/a.png"]) == 1
    assert ask_log.recent(limit=0) == []


def test_missing_log_reads_as_empty():
    assert ask_log.recent() == []
    assert ask_log.count() == 0
    assert ask_log.trim() == 0
