"""Dark-theme contrast + token-coverage norm for the gallery.

Companion to ``test_light_contrast.py``. Reads the LIVE
``src/resources/themes.json`` (dark + light sections) and asserts, with pure
color math (no Qt), that:

- the severity trio (``gallery.status.ok`` / ``warn`` / ``danger``) is legible
  on the gallery card + grid substrates. Red-before/green-after: the old dark
  danger ``#D93025`` measured ≈2.46:1 on ``gallery.card.background``
  (``#383838``) — below the WCAG non-text 3:1 floor and unreadable as the
  "unreadable — excluded from triage" error text; it is now ``#ff7b72``.
- the rank-badge ink (``button.primary.text``) clears 4.5:1 on the rank pill
  fill (``button.toggle.background.checked``) in BOTH themes.
- every gallery token the UI references now EXISTS in both palettes
  (the ``gallery.nav.*`` / ``gallery.pill.background`` /
  ``gallery.card.unreadable.plate`` / ``gallery.status.neutral`` set used to
  be fallback-only hardcoded hexes).
- the overlay surface (``gallery.panel.background``) is the flat plate AND
  scroll-host tone (light ``#ffffff`` / dark ``#303030``, mockup svg:31),
  never the raw Qt ``Window`` role (dark ``#1e1e1e`` hole) nor the grid-card
  ``#383838`` — the plate resolves the same token as the panels, so no recess
  seam shows on the card; and the rank-pill hover fill
  (``gallery.pill.background.hover``) keeps the fixed black ink >= 4.5:1
  (the surface hover token ``#4a4a4a`` measured 2.44:1).
- the prev/next nav circles (``gallery.nav.*``) are theme-aware: dark disc
  ``#2b2b2b`` + light chevron ``#dfdfdf``, so they never stay white in dark.
- the light palette is untouched by the dark fix (danger stays ``#c0392b``).
"""

from __future__ import annotations

import json

# Tokens the gallery UI resolves; every one must exist in BOTH palettes so a
# theme flip never silently falls back to a hardcoded hex (THEMING.md: same
# key set in light + dark).
GALLERY_REFERENCED_TOKENS = (
    "gallery.accent.bar",
    "gallery.accent.text",
    "gallery.card.background",
    "gallery.card.border",
    "gallery.card.hover",
    "gallery.card.unreadable.plate",
    "gallery.footer.text",
    "gallery.grid.background",
    "gallery.header.text",
    "gallery.nav.border",
    "gallery.nav.fill",
    "gallery.nav.glyph",
    "gallery.panel.background",
    "gallery.pill.background",
    "gallery.pill.background.hover",
    "gallery.pill.text",
    "gallery.stats.background",
    "gallery.stats.text",
    "gallery.status.danger",
    "gallery.status.neutral",
    "gallery.status.ok",
    "gallery.status.warn",
    "quick_look.bar.background",
    "flyout.border",
    "input.border.thin",
    "button.toggle.background.checked",
    "button.primary.text",
    "surface.button",
)


def _themes() -> dict:
    from utils.resource_loader import resource_path

    with open(resource_path("resources/themes.json"), encoding="utf-8") as f:
        return json.load(f)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 8:  # ARGB (e.g. #1EFFFFFF)
        h = h[2:]
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def test_gallery_referenced_tokens_present_in_both_palettes() -> None:
    """No gallery token is fallback-only — every referenced key exists twice."""
    data = _themes()
    light, dark = data["light"], data["dark"]
    missing_light = [t for t in GALLERY_REFERENCED_TOKENS if t not in light]
    missing_dark = [t for t in GALLERY_REFERENCED_TOKENS if t not in dark]
    assert not missing_light, f"light palette missing {missing_light}"
    assert not missing_dark, f"dark palette missing {missing_dark}"


def test_dark_status_trio_legible_on_card_and_grid() -> None:
    """Severity dots/marks on the dark card + grid clear the WCAG 3:1 floor.

    Red-before: ``gallery.status.danger`` dark ``#D93025`` = 2.46 on the card
    (2.97 on the grid). Green-after: the lighter red clears 4.5:1 on both.
    """
    dark = _themes()["dark"]
    card = dark["gallery.card.background"]
    grid = dark["gallery.grid.background"]
    for token in ("gallery.status.ok", "gallery.status.warn", "gallery.status.danger"):
        on_card = _ratio(dark[token], card)
        on_grid = _ratio(dark[token], grid)
        assert on_card >= 3.0, f"{token} {dark[token]} on card {card}: {on_card:.2f} < 3.0"
        assert on_grid >= 3.0, f"{token} {dark[token]} on grid {grid}: {on_grid:.2f} < 3.0"


def test_dark_danger_readable_as_error_text() -> None:
    """The danger red is also the "unreadable" error row text → 4.5:1 body bar."""
    dark = _themes()["dark"]
    got = _ratio(dark["gallery.status.danger"], dark["gallery.card.background"])
    assert got >= 4.5, f"dark danger {dark['gallery.status.danger']}: {got:.2f} < 4.5"
    # Never regress to the old low-contrast red.
    assert _ratio("#D93025", dark["gallery.card.background"]) < 3.0


def test_dark_neutral_text_legible_on_card() -> None:
    """Muted metric text (``gallery.status.neutral``) clears 4.5:1 on the card."""
    dark = _themes()["dark"]
    got = _ratio(dark["gallery.status.neutral"], dark["gallery.card.background"])
    assert got >= 4.5, f"neutral {dark['gallery.status.neutral']}: {got:.2f} < 4.5"


def test_rank_badge_ink_legible_on_pill_in_both_themes() -> None:
    """Badge ink (``button.primary.text``) >= 4.5:1 on the rank pill fill."""
    data = _themes()
    for theme in ("light", "dark"):
        ink = data[theme]["button.primary.text"]
        pill = data[theme]["button.toggle.background.checked"]
        got = _ratio(ink, pill)
        assert got >= 4.5, f"{theme}: ink {ink} on pill {pill}: {got:.2f} < 4.5"
    # The dark ink must not be the old hardcoded black.
    assert data["dark"]["button.primary.text"].lower() == "#ffffff"


def test_light_palette_unchanged_by_dark_fix() -> None:
    """The dark fix must not move any light gallery value."""
    light = _themes()["light"]
    assert light["gallery.status.danger"].lower() == "#c0392b"
    assert light["gallery.stats.background"].lower() == "#ffffff"
    assert light["gallery.card.background"].lower() == "#ffffff"
    assert light["gallery.grid.background"].lower() == "#ffffff"


def test_overlay_surface_is_one_flat_tone_not_a_recess() -> None:
    """The overlay plate + scroll hosts resolve ONE flat surface token.

    Red-before: the Quick Look / clean-review plate resolved
    ``gallery.card.background`` (dark ``#383838``) while the sidebar /
    filmstrip hosts resolved ``gallery.panel.background`` (dark ``#303030``) —
    two greys on the same card. Green-after: both read
    ``gallery.panel.background`` = the mockup's flat overlay surface (light
    ``#ffffff`` / dark ``#303030``, svg:31 / svg:42), so the seam is gone and
    no scroll host falls through to the raw Qt ``Window`` hole (dark
    ``#1e1e1e``).
    """
    light, dark = _themes()["light"], _themes()["dark"]
    assert light["gallery.panel.background"].lower() == "#ffffff"
    assert dark["gallery.panel.background"].lower() == "#303030"
    # The overlay surface is deliberately distinct from the grid-card tone
    # (dark #383838): the plate must not fall back to ``gallery.card.background``.
    assert dark["gallery.panel.background"].lower() != dark["gallery.card.background"].lower()
    # Never the raw Qt Window role (dark #1e1e1e near-black hole).
    assert dark["gallery.panel.background"].lower() != "#1e1e1e"
    assert _ratio("#1e1e1e", dark["gallery.panel.background"]) > 1.2


def test_dark_nav_controls_follow_the_theme() -> None:
    """Prev/next circles are theme-aware, not the light mockup frozen into dark.

    Red-before: ``gallery.nav.*`` carried the LIGHT mockup values in BOTH
    palettes (disc ``#f1f2f4``, chevron ``#23262b``), so dark rendered a
    near-white disc with a dark chevron on the dark card. Green-after: dark
    disc ``#2b2b2b`` + light chevron ``#dfdfdf`` + translucent white ring
    (dark mockup prev/next); light keeps the light mockup pair.
    """
    dark = _themes()["dark"]
    assert dark["gallery.nav.fill"].lower() == "#2b2b2b"
    assert dark["gallery.nav.glyph"].lower() == "#dfdfdf"
    assert dark["gallery.nav.border"].lower() == "#40ffffff"
    # The chevron must read on the disc.
    assert _ratio(dark["gallery.nav.glyph"], dark["gallery.nav.fill"]) >= 4.5
    # The light mockup pair is unchanged.
    light = _themes()["light"]
    assert light["gallery.nav.fill"].lower() == "#f1f2f4"
    assert light["gallery.nav.glyph"].lower() == "#23262b"


def test_pill_hover_ink_legible_in_both_themes() -> None:
    """The rank-pill ink (fixed black) clears 4.5:1 on the hovered pill fill.

    Red-before: the white pill (``gallery.pill.background``) left its hover to
    the surface token — dark ``#4a4a4a`` (opaque) replaced the white base under
    the fixed black ink at 2.44:1, so #N vanished on hover. Green-after:
    ``gallery.pill.background.hover`` stays light, so the ink clears 4.5:1.
    """
    data = _themes()
    ink = "#000000"
    for theme in ("light", "dark"):
        hover = data[theme]["gallery.pill.background.hover"]
        got = _ratio(ink, hover)
        assert got >= 4.5, f"{theme}: ink on pill hover {hover}: {got:.2f} < 4.5"
    # Never regress to the surface hover wash that hid the digits.
    assert _ratio(ink, "#4a4a4a") < 3.0


def test_dark_modal_veil_softer_than_light(monkeypatch) -> None:
    """The modal veil is a dim amount, not a colour: light keeps the mockup
    0.45, dark softens so the surroundings do not read as a near-black
    "different world" next to the #383838 card (background *coherence*, not
    extra contrast)."""
    from tabs.image_gallery.ui.quick_look import labels_theme

    assert labels_theme.DIM_VEIL_ALPHA == round(0.45 * 255) == 115
    assert labels_theme._DIM_VEIL_ALPHA_DARK < labels_theme.DIM_VEIL_ALPHA
    monkeypatch.setattr(labels_theme, "_is_dark_theme", lambda: True)
    assert labels_theme._dim_veil_alpha() == labels_theme._DIM_VEIL_ALPHA_DARK
    monkeypatch.setattr(labels_theme, "_is_dark_theme", lambda: False)
    assert labels_theme._dim_veil_alpha() == labels_theme.DIM_VEIL_ALPHA
