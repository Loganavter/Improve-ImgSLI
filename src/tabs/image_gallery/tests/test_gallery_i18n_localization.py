"""Gallery tab localization: UI keys + session-picker card must resolve per locale.

Falsification (pre-fix): ``session_picker.descriptions.image_gallery`` did not exist
in any locale, so the session-picker create-card rendered an **empty** description;
``session_picker.types.image_gallery`` and ``workspace.session_types.image_gallery``
were also absent, so the picker card / "new tab" menu fell back to the blueprint's
hardcoded ``"Image Gallery"`` in every locale. The toolbar / stats strip / overlays
carried raw English literals ("Open Folder…", "Keep best", "Review rejected files",
…). This test rejects a per-locale value that is empty, is the raw key, or equals
the English string — i.e. a silent English fallback.

Content identity, not counts: the assertion is on the *resolved string per locale*,
mirroring tests/plugins/test_help_hub_i18n.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

NON_EN_LOCALES = ("ru", "zh", "pt_BR")

#: Keys the gallery refactor added/moved — must be real translations, not fallbacks.
_KEYS = (
    "image_gallery.toolbar.open_folder",
    "image_gallery.toolbar.filter_placeholder",
    "image_gallery.grid.resize_tooltip",
    "image_gallery.stats.show_all",
    "image_gallery.stats.clean_rejected",
    "image_gallery.stats.compare_finalists",
    "image_gallery.quick_look.reject",
    "image_gallery.quick_look.report_title",
    "image_gallery.clean_review.title",
    "image_gallery.clean_review.move",
    "types.image_gallery",
    "descriptions.image_gallery",
    "workspace.session_types.image_gallery",
)


def _register_all_i18n_roots() -> None:
    from resources.translations import add_i18n_root

    repo = Path(__file__).resolve().parents[4]
    roots = sorted((repo / "src").rglob("resources/i18n"))
    assert roots, "no i18n roots discovered under src/"
    for root in roots:
        add_i18n_root(root)


@pytest.mark.parametrize("language", NON_EN_LOCALES)
def test_gallery_keys_are_localized(language: str) -> None:
    _register_all_i18n_roots()
    from resources.translations import tr

    problems: list[str] = []
    for key in _KEYS:
        en_value = tr(key, language="en")
        assert en_value and en_value != key, f"{key}: missing from the en reference"
        value = tr(key, language=language)
        if not value or value == key:
            problems.append(f"{key} [{language}]: unresolved -> {value!r}")
        elif value == en_value:
            problems.append(f"{key} [{language}]: English fallback -> {value!r}")
    assert not problems, "\n".join(problems)
