"""Light-theme contrast norm for the gallery (white-cards + visible-borders).

Reads LIVE ``src/resources/themes.json`` (light section) and asserts the
WCAG contrast ratios from design.md "Light-theme contrast norm":
``ratio = (L1 + 0.05) / (L2 + 0.05)``. No Qt needed — pure color math, so a
palette edit that breaks readability fails here before any widget test.

Philosophy (mockups v2/v3/v4-light): white cards on a white substrate —
separation is carried by 1px ``gallery.card.border`` (``#e2e4e8``) hairlines,
not by fill contrast. Fill-vs-fill pairs that share ``#ffffff`` therefore
carry a documented mockup-fidelity exception: WCAG non-text 3:1 does not
apply to hairline decoration (the 1px edge is the boundary, not the fill).
See design.md "Light-theme contrast norm".
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
        "gallery.card.border",
        "gallery.card.hover",
        "gallery.grid.background",
        "gallery.stats.background",
        "gallery.stats.text",
        "gallery.header.text",
        "gallery.footer.text",
        "gallery.accent.text",
        "gallery.accent.bar",
        "separator.color",
        "surface.background",
        "Window",
    ):
        assert key in tokens, f"light palette missing {key}"


def test_light_globals_unleaked() -> None:
    """App-global tokens stay at their pre-epic values (2026-09-23 rescope).

    The gallery substrate lives in gallery.grid.background; Window /
    surface.background / separator.color must never be re-tinted for gallery
    (a #cecece Window leaked into every autoFillBackground widget app-wide).
    """
    tokens = _light_tokens()
    assert tokens["Window"].lower() == "#f5f5f5"
    assert tokens["surface.background"].lower() == "#ffffff"
    assert tokens["separator.color"].lower() == "#e5e5e5"


def test_light_card_vs_grid_border_separation() -> None:
    """White cards on a white substrate separate via the border hairline.

    Mockup-fidelity exception (design.md; v2/v3/v4-light): card
    (``#ffffff``) and grid (``#ffffff``) fills are 1:1 by design — the 1px
    ``gallery.card.border`` (``#e2e4e8``) hairline carries the separation, and
    WCAG non-text 3:1 does not apply to hairline decoration. The border token
    must exist and must differ from the card fill (computed here: border vs
    card ≈ 1.27 — visible as an edge, not as a fill step).
    """
    tokens = _light_tokens()
    assert tokens["gallery.card.background"].lower() == "#ffffff"
    assert tokens["gallery.grid.background"].lower() == "#ffffff"
    border = tokens["gallery.card.border"].lower()
    assert border != tokens["gallery.card.background"].lower(), "border must differ from card fill"
    assert _ratio(tokens["gallery.card.border"], tokens["gallery.card.background"]) > 1.0


def test_light_hover_step_vs_card() -> None:
    """Hover reads via fill nudge + border change, not fill contrast.

    Mockup-fidelity exception (design.md; v2-light): hover ``#f5f8fc`` vs
    card ``#ffffff`` computes ≈ 1.06 — effectively 1.0x. The hover state works
    because the card edge switches ``#e2e4e8`` → ``#c9ccd1`` while the fill
    nudges; assert the fill differs from idle and the two border steps exist
    as distinct values.
    """
    tokens = _light_tokens()
    assert tokens["gallery.card.hover"].lower() != tokens["gallery.card.background"].lower()
    assert _ratio(tokens["gallery.card.hover"], tokens["gallery.card.background"]) < 1.3
    assert tokens["gallery.card.border"].lower() == "#e2e4e8"


def test_light_stats_surface_vs_card_border_separation() -> None:
    """Stats strip on white separates via its painted border, not fill contrast.

    Same border exception as cards (design.md; v2-light): the strip fill is
    ``#ffffff`` like the cards, and ``StatsStrip.paintEvent`` strokes the same
    1px ``gallery.card.border`` edge — assert the token exists and differs
    from the strip fill.
    """
    tokens = _light_tokens()
    assert tokens["gallery.stats.background"].lower() == "#ffffff"
    assert tokens["gallery.card.background"].lower() == "#ffffff"
    assert tokens["gallery.card.border"].lower() != tokens["gallery.stats.background"].lower()


def test_light_gallery_texts_vs_backgrounds() -> None:
    """Body text stays readable: header/stats texts vs their backgrounds >= 4.5.

    Mockup texts pass (``#23262b`` ≈ 15.2, ``#6b7078`` ≈ 5.0 vs card).
    """
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.header.text", "gallery.card.background", 4.5)
    _assert_ratio(tokens, "gallery.header.text", "Window", 4.5)
    _assert_ratio(tokens, "gallery.stats.text", "gallery.stats.background", 4.5)
    _assert_ratio(tokens, "gallery.stats.text", "gallery.card.background", 4.5)


def test_light_footer_text_decorative_supplement() -> None:
    """Footer hints stay legible at >= 3.0 (decorative-supplement exception).

    ``#767a80`` on ``#ffffff`` computes ≈ 4.3 — below the 4.5 body-text bar.
    Footers carry keyboard hints and other non-essential supplements (the
    same information is always available in the primary UI), so 3.0 applies
    per design.md; the pair must still clear it with margin.
    """
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.footer.text", "gallery.card.background", 3.0)
    _assert_ratio(tokens, "gallery.footer.text", "Window", 3.0)


def test_light_accent_text_vs_card() -> None:
    """Small accent text (Clean-rejected link, AI pill, Compare, mode chip) >= 4.5.

    Mockup ``#0077cc`` on ``#ffffff`` computes ≈ 4.7 — passes as real text
    contrast (fills stay ``gallery.accent.bar``; this token is text only).
    """
    tokens = _light_tokens()
    _assert_ratio(tokens, "gallery.accent.text", "gallery.card.background", 4.5)
