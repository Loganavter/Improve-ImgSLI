"""The judge's prose follows the UI language, and ``label`` stays a NAME.

Owner, 2026-10-27 (live screenshot, Russian UI, one reply):

    rows: "Edge sharpness", "Fine detail recovery", "Color saturation",
          "Compression noise", "Tonal contrast", "Композиция — хорошо скомпоновано"

Two defects in one screenshot, both PROMPT-shaped:

- **(a) the language was never stated.** The selector said "in the UI language"
  without ever naming that language, so the model picked one per axis — five
  English names, one Russian. The scorecard prompt had no such clause at all
  (only ``ai_client.request`` appended a directive, and it steered ``reason``
  only). The app already owned the mechanism (`ask_prompt.language_directive` /
  `language_name`, one small language table); neither judge prompt used it.
- **(b) ``label`` absorbed the definition** — the last row reads
  "Композиция — хорошо скомпоновано", i.e. name + what it measures, while the
  definition belongs in the tooltip. The schema asks for ``definition`` right
  next to ``label`` and nothing said where the boundary is.

Falsification (red on ``18dd5af3f``): every test below fails there — no
``language`` parameter existed on either builder, ``build_prompt`` carried no
language sentence at all, and the label rule said only "not the id".

The two invariants that must NOT move with the language: ``name``/``id`` stay
the snake_case key, and scores/`scale`/`direction`/numbers are never localized.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.services import ask_prompt
from tabs.image_gallery.services.ai_client.prompt import build_prompt
from tabs.image_gallery.services.ask_prompt import language_directive
from tabs.image_gallery.use_cases.profile_ai import build_profile_request
from tabs.image_gallery.use_cases.profile_probe import salience_summary


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"), mtime_ns=1, metrics=dict(metrics)
    )


def _selector_text(payload) -> str:
    return payload["messages"][0]["content"][0]["text"]


def _pinned(monkeypatch, code: str) -> None:
    """Pin the UI language the tab reads (the same seam ``test_ask_language`` uses)."""
    monkeypatch.setattr(ask_prompt, "get_current_language", lambda *a, **k: code)


# ---------------------------------------------------------------------------
# (a) both judge prompts carry the language directive
# ---------------------------------------------------------------------------


def test_the_scorecard_prompt_names_the_reply_language():
    text = build_prompt("camera", language="ru")

    assert "Answer in Russian" in text, (
        "the scorecard's reason/labels must be told WHICH language to use — the "
        "prompt used to leave it to the model"
    )
    assert language_directive("ru") in text, (
        "the directive is the tab's existing one, not a second wording"
    )
    assert "Keep numbers/metric names as-is" in text, (
        "ids and numbers ride through the directive untouched"
    )


def test_the_selector_prompt_names_the_reply_language():
    probes = [_item("a.png", sharpness=40.0), _item("b.png", sharpness=80.0)]
    payload = build_profile_request(
        probes,
        model="m",
        salience=salience_summary(probes, probes=probes),
        language="ru",
    )
    text = _selector_text(payload)

    assert "Answer in Russian" in text, (
        "the path that named the owner's axes must state the language — five "
        "English names and one Russian came out of this prompt"
    )
    assert language_directive("ru") in text
    assert "Answer in English" not in text


def test_the_directive_follows_the_current_ui_language(monkeypatch):
    _pinned(monkeypatch, "ru")

    assert "Answer in Russian" in build_prompt("camera")
    probes = [_item("a.png", sharpness=40.0)]
    text = _selector_text(
        build_profile_request(probes, model="m", salience=salience_summary(probes, probes=probes))
    )
    assert "Answer in Russian" in text, "no caller pins a language: the UI one wins"


def test_an_unreadable_ui_language_fails_open_to_english(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no language table")

    monkeypatch.setattr(ask_prompt, "get_current_language", _boom)

    assert "Answer in English" in build_prompt("camera"), (
        "a broken language lookup must not cost the user the answer"
    )
    text = _selector_text(build_profile_request([_item("a.png")], model="m", salience={}))
    assert "Answer in English" in text


# ---------------------------------------------------------------------------
# (b) label is a NAME; the definition belongs to `definition`
# ---------------------------------------------------------------------------


def test_both_prompts_say_the_label_is_a_short_name_without_the_definition():
    scorecard = build_prompt("camera", language="ru")
    selector = _selector_text(
        build_profile_request([_item("a.png")], model="m", salience={}, language="ru")
    )
    for text, name in ((scorecard, "scorecard"), (selector, "selector")):
        assert "`label` is a SHORT name" in text, (
            f"{name}: the label contract must say it is a short standalone name"
        )
        assert "never the definition itself" in text, (
            f"{name}: a label that carries the definition is the reported defect "
            '("Композиция — хорошо скомпоновано")'
        )
        assert "belong in `definition`" in text, (
            f"{name}: the tooltip's field must be named as the definition's home"
        )


def test_the_selector_contract_no_longer_offers_the_definition_as_a_label():
    text = _selector_text(build_profile_request([_item("a.png")], model="m", salience={}))

    assert "NOT the id and NOT the definition" in text, (
        "the schema itself must exclude the definition from the label slot"
    )
    assert "NOT the id>" not in text, "the weaker label wording is superseded"


# ---------------------------------------------------------------------------
# (c) nothing else moves: ids stay keys, numbers stay numbers
# ---------------------------------------------------------------------------


def test_a_pinned_language_never_touches_ids_numbers_or_scale():
    ru_scorecard = build_prompt("camera", language="ru")
    en_scorecard = build_prompt("camera", language="en")

    assert '"sharpness": <0-100' in ru_scorecard, (
        "the axis request keeps its canonical snake_case id + numeric slot"
    )
    assert '"sharpness": <0-100' in en_scorecard, "the id/slot does not depend on the language"
    assert '"composition": <0-100' in ru_scorecard
    assert '"confidence": <0.0-1.0>' in ru_scorecard, (
        "the numeric envelope is untouched by the language"
    )

    # The ONLY difference between the two languages is the language sentence:
    # a localized id, scale or score slot would show up here as extra drift.
    assert ru_scorecard.replace("Russian", "English") == en_scorecard, (
        "pinning the language must change the language word and nothing else"
    )


def test_the_selector_schema_keeps_ids_and_scale_in_the_reply():
    text = _selector_text(
        build_profile_request([_item("a.png")], model="m", salience={}, language="ru")
    )

    assert '"name": "<short id>"' in text, "the key stays snake_case, not prose"
    assert '"scale": "0-100"' in text, "the scale is literal, never localized"
    assert '"direction": "higher-is-better|lower-is-better"' in text
    assert "scores, `scale` and `direction` are never localized" in text
