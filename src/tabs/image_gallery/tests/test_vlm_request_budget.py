"""VLM image-call budget + reasoning hardening.

Bug (2026-10-15): the tie-break raised ``AiResponseError("empty tie-break
response")`` because ``build_tie_break_request`` sent ``max_tokens=300`` and NO
``reasoning`` parameter — a mandatory-reasoning model (``z-ai/glm-5.3-flash``)
then burned the entire budget in its chain-of-thought and emitted empty
``content`` (probed live: 7/8 empty; with ``reasoning.effort=low`` 0/8).

Falsification story: a request that omits the bounded reasoning effort, or whose
budget does not come from the shared Ask-AI estimator (so it ignores the image
count / headroom), would reintroduce the empty-response class of bug.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from tabs.image_gallery.services import vlm


def _png(path: Path, color=(120, 80, 40)) -> Path:
    Image.new("RGB", (32, 24), color).save(path)
    return path


def test_tie_break_openrouter_gets_bounded_reasoning_and_budget(tmp_path) -> None:
    a = _png(tmp_path / "a.png")
    b = _png(tmp_path / "b.png", (10, 200, 10))
    payload = vlm.build_tie_break_request(a, b, None, model="m", openrouter=True)
    assert payload["reasoning"] == {"effort": "low", "exclude": True}
    assert payload["provider"]["sort"] == "throughput"
    assert payload["max_tokens"] >= 512  # never the old hardcoded 300


def test_tie_break_non_openrouter_has_no_extra_params(tmp_path) -> None:
    a = _png(tmp_path / "a.png")
    b = _png(tmp_path / "b.png")
    payload = vlm.build_tie_break_request(a, b, None, model="m")
    assert "reasoning" not in payload and "provider" not in payload
    assert payload["max_tokens"] >= 512


def test_tie_break_budget_scales_with_image_count(tmp_path) -> None:
    a = _png(tmp_path / "a.png")
    b = _png(tmp_path / "b.png")
    src = _png(tmp_path / "src.png", (200, 200, 200))
    two = vlm.build_tie_break_request(a, b, None, model="m")
    three = vlm.build_tie_break_request(a, b, src, model="m")
    assert three["max_tokens"] > two["max_tokens"]


def test_compare_brief_openrouter_gets_the_same_hardening(tmp_path) -> None:
    a = _png(tmp_path / "a.png")
    b = _png(tmp_path / "b.png")
    payload = vlm.build_compare_brief_request(a, b, model="m", openrouter=True)
    assert payload["reasoning"] == {"effort": "low", "exclude": True}
    assert payload["max_tokens"] >= 512
