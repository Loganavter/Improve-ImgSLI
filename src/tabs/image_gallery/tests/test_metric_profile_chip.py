"""P4 — the active-metric-profile chip (offscreen) and its i18n keys.

Falsification story (what each test would catch):

- a chip that renders nothing (the production caller of ``format_profile`` is
  missing), or that shows a fabricated profile when none was published;
- a chip label that ignores the pinned domain / the auto state (the user could
  not tell whether the profile is manual or mode-derived);
- a menu that announces the wrong token (index off-by-one between "auto" and
  the named domains would silently pin the wrong axis set);
- English leaking into the non-en locales for the new keys (the chip and its
  menu are user-facing — plan P4 requires all four locales).

Runs offscreen (real widgets, no window manager); the live-appearance proof is
the supervisor's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tabs.image_gallery.services.metric_profile import (
    DOMAINS,
    format_profile,
    profile_for_domain,
)
from tabs.image_gallery.ui.stats_strip import StatsStrip

_PROFILE_KEYS = (
    "image_gallery.profile.chip",
    "image_gallery.profile.auto",
    "image_gallery.profile.axes",
    "image_gallery.profile.domain.auto",
    "image_gallery.profile.domain.document",
    "image_gallery.profile.domain.photo",
    "image_gallery.profile.domain.synthetic",
    "image_gallery.profile.domain.mixed",
)


@pytest.fixture
def strip(qtbot):
    widget = StatsStrip()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_chip_renders_the_active_domain_and_the_format_profile_tooltip(strip) -> None:
    profile = profile_for_domain("photo", mode="camera")

    strip.set_metric_profile(profile, domain="photo", auto=False)

    text = strip.profile_chip_text
    assert "Photo" in text
    assert "auto" not in text
    # The axis count lives in the tooltip now: a chip is not a paragraph, and
    # the long "· N axes" tail used to squeeze the button below its text width
    # (the painter then clipped its right half — live 2026-10-20).
    assert "axes" not in text.lower()
    assert strip.profile_chip.minimumWidth() > 0
    assert strip.profile_chip.minimumWidth() <= strip.profile_chip.sizeHint().width()
    # First production caller: the exact diagnostic line is the tooltip.
    assert strip.profile_chip.toolTip() == format_profile(profile)
    assert strip.profile_chip.isVisible()
    assert strip.profile_domain == "photo"


def test_chip_says_auto_and_hides_without_a_profile(strip) -> None:
    profile = profile_for_domain("document", mode="fidelity")

    strip.set_metric_profile(profile, domain="document", auto=True)
    assert "Document" in strip.profile_chip_text
    assert "auto" in strip.profile_chip_text
    assert strip.profile_domain == ""

    strip.set_metric_profile(None)
    assert strip.profile_chip_text == ""
    assert not strip.profile_chip.isVisible()


def test_chip_menu_announces_the_picked_domain_and_auto(strip) -> None:
    picked: list[str] = []
    strip.profileDomainSelected.connect(picked.append)

    strip.set_metric_profile(profile_for_domain("photo"), domain="photo", auto=False)
    assert strip._profile_menu_index() == 1 + DOMAINS.index("photo")

    strip._on_profile_domain_chosen(1 + DOMAINS.index("synthetic"))
    strip._on_profile_domain_chosen(0)

    assert picked == ["synthetic", "auto"]
    # Menu labels: auto first, then the named domains (localized via _t).
    assert strip._profile_menu_labels()[0] == "Auto (from mode)"
    assert strip._profile_menu_labels()[1] == "Document"


def test_chip_labels_follow_the_injected_translator(qtbot) -> None:
    def translate(key: str, default: str) -> str:
        return {
            "image_gallery.profile.chip": "Профиль: {profile}",
            "image_gallery.profile.domain.photo": "Фото",
            "image_gallery.profile.auto": "авто",
            "image_gallery.profile.axes": "осей: {n}",
        }.get(key, default)

    widget = StatsStrip(translate=translate)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_metric_profile(profile_for_domain("photo"), domain="photo", auto=True)

    text = widget.profile_chip_text
    assert "Профиль:" in text and "Фото" in text and "авто" in text
    # Keys the stub translator does not know fail open to their English default.
    assert widget._profile_menu_labels()[1] == "Document"


def test_profile_keys_are_localized_in_every_locale() -> None:
    from resources.translations import add_i18n_root, tr

    repo = Path(__file__).resolve().parents[4]
    roots = sorted((repo / "src").rglob("resources/i18n"))
    assert roots, "no i18n roots discovered under src/"
    for root in roots:
        add_i18n_root(root)

    problems: list[str] = []
    for language in ("ru", "zh", "pt_BR"):
        for key in _PROFILE_KEYS:
            en_value = tr(key, language="en")
            if not en_value or en_value == key:
                problems.append(f"{key}: missing from the en reference")
                continue
            value = tr(key, language=language)
            if not value or value == key:
                problems.append(f"{key} [{language}]: unresolved -> {value!r}")
            elif value == en_value:
                problems.append(f"{key} [{language}]: English fallback")
    assert not problems, "\n".join(problems)
