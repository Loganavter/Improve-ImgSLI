"""The AI-chain proof tool: its pure parts, without a display or a lease.

The tool itself drives a live app (a lease, an Xvfb, a real gallery run), so the
suite covers what a live run cannot: that the stub's router answers the THREE
question shapes differently, that a log line's wall-clock is parsed (the reset
verdict compares timestamps), and that cache enumeration ignores the store's
``version.json`` (a previous version counted it as an entry and reported a
non-empty cache with the "local metrics persisted" check green while the
directory held nothing — measured 2026-10-28).

Falsification: the module and the tool did not exist before; the router answers
are the ones the app's two parsers accept (a JSON list for the profile, a JSON
object for the scorecard, a ranking for the ranker), so a green run proves the
fixture describes those shapes rather than one fixed string.
"""

from __future__ import annotations

import json

from devtools import live_gallery_ai_chain as chain


def _ask(router, prompt: str) -> dict:
    return json.loads(router({"model": "m", "messages": [{"role": "user", "content": prompt}]}))


def test_router_answers_the_profile_shape():
    reply = _ask(chain._stub_router(), "name FROM 5 TO 8 axes for this series")

    assert isinstance(reply["axes"], list), "the profile selector parses a LIST"
    names = [row for row in reply["axes"] if isinstance(row, str)]
    assert "sharpness" in names
    judged = [row["name"] for row in reply["axes"] if isinstance(row, dict)]
    assert chain.JUDGE_ONLY_AXIS in judged
    for row in reply["axes"]:
        if isinstance(row, dict):
            assert row["scale"] == "0-100" and row["why"], "a row without why is refused"


def test_router_answers_the_scorecard_shape_with_the_distinctive_numbers():
    reply = _ask(chain._stub_router(), "score this frame")

    assert isinstance(reply["axes"], dict), "the scorecard parser parses an OBJECT"
    assert reply["axes"][chain.JUDGE_ONLY_AXIS] == chain.JUDGE_SCORE
    assert reply["axes"][chain.SHARED_AXIS] == chain.JUDGE_SHARED_SCORE


def test_router_answers_the_ranker_with_the_aliases_from_its_own_prompt():
    prompt = 'return object {"ranking": ["img_1", "img_2", "img_3"]} best to worst'

    reply = json.loads(chain._stub_router()({"messages": [{"role": "user", "content": prompt}]}))

    assert reply["ranking"] == ["img_1", "img_2", "img_3"], "aliases must come from the prompt"
    assert 0.0 <= reply["score"] <= 1.0


def test_router_keeps_the_pairwise_answer_separate():
    reply = chain._stub_router()({"messages": [{"role": "user", "content": "WINNER: A|B|TIE"}]})

    assert reply.strip() == "WINNER: A"


def test_the_stub_delay_is_optional_and_does_not_change_the_answer():
    slow = chain._stub_router(0.0)
    assert _ask(slow, "score this frame")["axes"][chain.SHARED_AXIS] == chain.JUDGE_SHARED_SCORE


def test_line_ms_parses_the_log_stamp_and_is_zero_for_a_foreign_line():
    line = "2026-10-28 05:52:13,123 - [INFO] - (prompt.py:29) - [ai] jev rank applied: items=4"

    assert chain._line_ms(line) > 0
    assert chain._line_ms("no stamp here") == 0


def test_cache_entries_skip_the_store_version_file(tmp_path, monkeypatch):
    kind = tmp_path / "BlinkTable" / "BlinkTable" / "gallery_ai_cache"
    kind.mkdir(parents=True)
    (kind / "version.json").write_text('{"version": 3}', encoding="utf-8")
    (kind / "abcd-1234.json").write_text('{"axes": {"sharpness": 37}}', encoding="utf-8")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    entries = chain._read_entries("gallery_ai_cache")

    assert [entry["axes"]["sharpness"] for entry in entries] == [37], (
        "version.json is metadata, not an entry: counting it made an empty cache "
        "look populated"
    )
