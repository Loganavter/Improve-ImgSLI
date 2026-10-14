"""AI prose follows the CURRENT UI language (Ask AI + VLM notes).

Falsification (pre-fix): the Ask AI system prompt (``ask_prompt``) was a fixed
English constant with no language directive, so answers always came back in
English regardless of the UI language. There was no ``language_directive`` /
``with_language`` helper (ImportError) and ``ask_router.answer`` did not append
one; ``vlm``/``ai_client`` prompts had no directive either.

These tests are pure (no GUI, no network): the transport is a fake, the current
language is injected by monkeypatching ``ask_prompt.get_current_language``.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from tabs.image_gallery.services import ask_prompt, ask_router
from tabs.image_gallery.services.ask_prompt import (
    ASK_OUTPUT_CONTRACT,
    ASK_SYSTEM_PROMPT,
    language_directive,
    language_name,
    with_language,
)

_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _set_language(monkeypatch, code: str) -> None:
    """Pin the current UI language the tab reads (no global mutation)."""
    monkeypatch.setattr(ask_prompt, "get_current_language", lambda *a, **k: code)


# -- unit: code → name + directive ------------------------------------------


@pytest.mark.parametrize(
    "code,name",
    [
        ("en", "English"),
        ("ru", "Russian"),
        ("zh", "Chinese"),
        ("pt_BR", "Brazilian Portuguese"),
    ],
)
def test_language_name_maps_shipped_locales(code, name):
    assert language_name(code) == name


def test_language_directive_names_the_language():
    assert language_directive("ru") == "Answer in Russian. Keep numbers/metric names as-is."
    assert language_directive("en") == "Answer in English. Keep numbers/metric names as-is."


def test_with_language_appends_directive_and_keeps_envelope():
    ru = with_language(ASK_SYSTEM_PROMPT, language="ru")
    assert "Answer in Russian" in ru
    assert ru.startswith(ASK_SYSTEM_PROMPT)
    # JSON envelope / guard contract is untouched.
    assert ASK_OUTPUT_CONTRACT in ru
    assert '{"answer"' in ru


def test_with_language_defaults_to_current_language(monkeypatch):
    _set_language(monkeypatch, "ru")
    assert "Answer in Russian" in with_language(ASK_SYSTEM_PROMPT)
    assert "Answer in English" not in with_language(ASK_SYSTEM_PROMPT)


def test_default_prompt_is_not_hardcoded_english(monkeypatch):
    # The base prompt itself is English prose, but the *directive* must follow
    # the current language rather than assuming English.
    _set_language(monkeypatch, "ru")
    text = with_language(ASK_SYSTEM_PROMPT)
    assert "Answer in Russian" in text
    assert "Answer in English" not in text


# -- end-to-end: ask_router.answer sends the directive ----------------------


def _capture_answer(monkeypatch, *, language: str):
    _set_language(monkeypatch, language)
    seen: list[dict] = []

    def fake_transport(base_url, api_key, payload):
        seen.append(payload)
        return {"choices": [{"message": {"content": '{"answer": "Prefer img_1.", "confidence": "high"}'}}]}

    ctx = {"count": 1, "metric_labels": {}, "items": []}
    result = ask_router.answer(
        "Summary",
        ctx,
        backend=ask_router.BACKEND_TEXT,
        base_url="http://x",
        api_key="k",
        model="m",
        transport=fake_transport,
    )
    return result, seen


def test_answer_system_prompt_carries_current_language(monkeypatch):
    result, seen = _capture_answer(monkeypatch, language="ru")
    assert result.error is None and result.text == "Prefer img_1."
    system_text = seen[0]["messages"][0]["content"][0]["text"]
    assert seen[0]["messages"][0]["role"] == "system"
    assert "Answer in Russian" in system_text
    assert "Answer in English" not in system_text


def test_answer_system_prompt_english_when_english(monkeypatch):
    _, seen = _capture_answer(monkeypatch, language="en")
    system_text = seen[0]["messages"][0]["content"][0]["text"]
    assert "Answer in English" in system_text


def test_answer_preserves_region_system_prompt_base(monkeypatch):
    """A caller-supplied (region) prompt keeps its base + gains the directive."""
    _set_language(monkeypatch, "ru")
    from tabs.image_gallery.services.ask_prompt import ASK_REGION_SYSTEM_PROMPT

    seen: list[dict] = []

    def fake_transport(base_url, api_key, payload):
        seen.append(payload)
        return {"choices": [{"message": {"content": '{"answer": "ok", "confidence": "high"}'}}]}

    ask_router.answer(
        "What is wrong?",
        {"count": 1, "metric_labels": {}, "items": []},
        backend=ask_router.BACKEND_VLM,
        base_url="http://x",
        api_key="k",
        model="m",
        system_prompt=ASK_REGION_SYSTEM_PROMPT,
        transport=fake_transport,
    )
    system_text = seen[0]["messages"][0]["content"][0]["text"]
    assert system_text.startswith(ASK_REGION_SYSTEM_PROMPT)
    assert "Answer in Russian" in system_text


# -- other AI prose paths: VLM tie-break / compare brief / per-image notes ---


def test_tie_break_prompt_is_localized(monkeypatch):
    _set_language(monkeypatch, "ru")
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda p: ("png", "AAAA"))
    payload = vlm.build_tie_break_request(
        Path("a.png"), Path("b.png"), None, model="m"
    )
    text = payload["messages"][0]["content"][0]["text"]
    assert "Answer in Russian" in text
    assert "WINNER:" in text  # strict response format intact


def test_compare_brief_prompt_is_localized(monkeypatch):
    _set_language(monkeypatch, "ru")
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda p: ("png", "AAAA"))
    payload = vlm.build_compare_brief_request(Path("a.png"), Path("b.png"), model="m")
    text = payload["messages"][0]["content"][0]["text"]
    assert "Answer in Russian" in text
    assert "SUMMARY:" in text  # strict response format intact


def test_per_image_analysis_prompt_is_localized(monkeypatch, tmp_path):
    _set_language(monkeypatch, "ru")
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "a.png"
    img.write_bytes(_PNG_1x1)
    payload = build_request(img, model="m")
    text = payload["messages"][0]["content"][0]["text"]
    assert "Answer in Russian" in text
