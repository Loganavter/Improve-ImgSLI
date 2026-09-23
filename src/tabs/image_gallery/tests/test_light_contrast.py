"""Light-theme contrast norm for the gallery (W4).

Reads LIVE ``src/resources/themes.json`` (light section) and asserts the
WCAG contrast ratios from design.md "Light-theme contrast norm":
``ratio = (L1 + 0.05) / (L2 + 0.05)``. No Qt needed — pure color math, so a
palette edit that breaks readability fails here before any widget test.
"""

from __future__ import annotations

import json


def _light_tokens() -> dict[str, str]:
    from utils.resource_loader import resource_path

    with open(resource_path("resources/themes.json"), encoding="utf-8") as f:
        return json.load(f)["light"]


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def _assert_ratio(tokens: dict[str, str], fg: str, bg: str, minimum: float) -> None:
    got = _ratio(tokens[fg], tokens[bg])
    assert got >= minimum, f"{fg} vs {bg}: {got:.3f} < {minimum}"


def test_light_gallery_tokens_present() -> None:
    """Every token the norm covers exists in the light palette."""
    tokens = _light_tokens()
    for key in (
        "gallery.card.background",
        "gallery.card.hover",
        "gallery.stats.background",
        "gallery.stats.text",
        "gallery.header.text",
        "gallery.footer.text",
        "separator.color",
        "surface.background",
        "Window",
    ):
        assert key in tokens, f"light palette missing {key}"


def test_light_card_vs_substrate() -> None:
    """White cards separate from the gray substrate: card vs Window and card vs surface.background >= 1.5."""
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.card.background", "Window", 1.5)
    _assert_ratio(tokens, "gallery.card.background", "surface.background", 1.5)


def test_light_hover_step_vs_card() -> None:
    """Hover stays a visible step away from idle: hover vs card >= 1.3."""
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.card.hover", "gallery.card.background", 1.3)


def test_light_separator_vs_surfaces() -> None:
    """Separators read on every surface: separator vs card/Window/surface.background >= 3.0."""
    tokens = _light_tokens()
    _assert_ratio(tokens, "separator.color", "gallery.card.background", 3.0)
    _assert_ratio(tokens, "separator.color", "Window", 3.0)
    _assert_ratio(tokens, "separator.color", "surface.background", 3.0)


def test_light_stats_surface_vs_card() -> None:
    """Stats bar surface separates from cards: stats.bg vs card >= 3.0."""
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.stats.background", "gallery.card.background", 3.0)


def test_light_gallery_texts_vs_backgrounds() -> None:
    """Body text stays readable: header/footer/stats texts vs their backgrounds >= 4.5."""
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.header.text", "gallery.card.background", 4.5)
    _assert_ratio(tokens, "gallery.header.text", "Window", 4.5)
    _assert_ratio(tokens, "gallery.footer.text", "gallery.card.background", 4.5)
    _assert_ratio(tokens, "gallery.footer.text", "Window", 4.5)
    _assert_ratio(tokens, "gallery.stats.text", "gallery.stats.background", 4.5)
