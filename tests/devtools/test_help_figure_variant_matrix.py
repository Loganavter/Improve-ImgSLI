"""Variant-need declarations: a matrix is justified by what is in the frame.

A locale/theme matrix costs one installed cell per ``(locale, theme)`` pair, so
a blanket matrix over every figure would ship eight copies of a loupe. The
declared rule (owner's correction, 2026-10-21) keys the need to the *frame*:

* ``locale+theme`` — the frame contains UI chrome: labels, buttons, panel
  titles, dialog fields.
* ``theme`` — theme-coloured chrome but no translatable text (a plain button
  row, an overlay).
* ``none`` — canvas/image pixels only (a lens over a photo, no chrome in crop).

Every entry in both manifests must therefore carry ``variant_need``, and the
declared matrix must not contradict it. The shape rules:

* ``none`` ⇒ exactly one declared ``(locale, theme)`` pair (no cell to copy).
* ``theme`` ⇒ every declared locale is ``en`` (a locale copy of a textless frame
  is dead weight).
* ``locale+theme`` ⇒ a declared matrix is the FULL ``4 locales x 2 themes``
  (8 cells). A partial matrix is worse than none: ``resolve_help_asset`` is
  fail-closed, so ``ru``/``zh`` would show the placeholder while ``en`` shows
  an image.

A figure may declare exactly ONE cell while its need is ``theme`` or
``locale+theme``: that is the open debt recorded in the plan (the 14 live
figures are ``en``/``dark`` today) and it stays legal because declaring cells
that are not on disk fails closed. The full shape is enforced the moment a
second cell is declared — that is the ``declaration must land with the capture``
rule, and :func:`test_every_declared_cell_exists_on_disk` is the assertion that
would have caught a declaration-before-install mistake.

RED-BEFORE: the unchanged manifests carry no ``variant_need`` at all, so
:func:`test_every_figure_declares_a_variant_need` fails with "no variant_need";
the parser raises ``AttributeError``/reports no field for the same reason.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools import help_figures, help_live

REPO_ROOT = help_figures.REPO_ROOT
LOCALES = tuple(help_figures.LOCALES)
THEMES = tuple(help_figures.THEMES)
CELLS_LOCALE_THEME = len(LOCALES) * len(THEMES)


def _raw_entries(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["figures"]


def _declared_pairs(figure) -> set[tuple[str, str]]:
    return {(locale, theme) for locale in figure.locales for theme in figure.themes}


def _figures() -> list[tuple[str, object]]:
    """Every figure in both manifests, tagged with the manifest it came from."""
    return [
        ("recipe", figure) for figure in help_figures.load_manifest().figures
    ] + [
        ("live", figure) for figure in help_live.load_recipes()
    ]


def _assets_root(destination: Path) -> Path:
    """``assets`` ancestor of a repo-relative destination (variant roots)."""
    parts = destination.parts
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "assets":
            return Path(*parts[: index + 1])
    return destination.parent


def _cell_path(figure, locale: str, theme: str) -> Path:
    """Where one declared cell has to be on disk.

    The recipe reader owns the install layout (``install_destination``: flat for
    a single cell, ``assets/<locale>/<theme>/<name>`` for a matrix) and the live
    reader installs the same literal destination today. The layout function is
    duck-typed on ``destination``/``locales``/``themes``, so it describes both.
    """
    return REPO_ROOT / help_figures.install_destination(figure, locale, theme)


def test_every_figure_declares_a_variant_need():
    for source, path in (
        ("recipe", help_figures.MANIFEST_PATH),
        ("live", help_live.RECIPE_PATH),
    ):
        for entry in _raw_entries(path):
            assert "variant_need" in entry, f"{source}:{entry.get('id')}: no variant_need declared"
            assert entry["variant_need"] in help_figures.VARIANT_NEEDS, (
                f"{source}:{entry.get('id')}: unknown variant_need {entry['variant_need']!r}"
            )
    # The parser must surface the same value (not a JSON-only field).
    for source, figure in _figures():
        assert figure.variant_need in help_figures.VARIANT_NEEDS, (source, figure.id)


def test_variant_need_does_not_contradict_the_declared_matrix():
    for source, figure in _figures():
        pairs = _declared_pairs(figure)
        label = f"{source}:{figure.id} ({figure.variant_need}, {len(pairs)} cell(s))"
        if figure.variant_need == "none":
            assert len(pairs) == 1, f"{label}: 'none' declares no cell to copy, so exactly one pair"
            continue
        if figure.variant_need == "theme":
            assert set(figure.locales) == {"en"}, (
                f"{label}: 'theme' has no translatable text, so a non-en locale is dead weight"
            )
        if len(pairs) > 1:
            assert figure.variant_need != "none"
            assert set(figure.themes) == set(THEMES), (
                f"{label}: a declared matrix must carry both themes {THEMES}"
            )
            if figure.variant_need == "theme":
                assert set(figure.locales) == {"en"}, (
                    f"{label}: 'theme' matrix is en x {len(THEMES)} themes, not locales"
                )
            else:
                assert len(set(figure.locales)) >= len(LOCALES), (
                    f"{label}: 'locale+theme' matrix is {len(LOCALES)} locales "
                    f"{LOCALES} x {len(THEMES)} themes = {CELLS_LOCALE_THEME} cells; "
                    "a partial matrix fails closed for the missing locales"
                )
                assert len(pairs) == CELLS_LOCALE_THEME, (
                    f"{label}: 'locale+theme' must declare exactly {CELLS_LOCALE_THEME} cells"
                )


def test_every_declared_cell_exists_on_disk():
    """Fail-closed guard: a declared cell that is absent shows a placeholder."""
    for source, figure in _figures():
        pairs = _declared_pairs(figure)
        if len(pairs) <= 1:
            continue
        missing = [
            _cell_path(figure, locale, theme).relative_to(REPO_ROOT).as_posix()
            for locale, theme in sorted(pairs)
            if not _cell_path(figure, locale, theme).is_file()
        ]
        assert not missing, (
            f"{source}:{figure.id}: declared {len(pairs)} cells but "
            f"{len(missing)} are not installed: {missing}"
        )


def test_single_cell_figures_have_no_stray_variant_folder():
    """An undeclared cell is dead weight the storage gate still charges for."""
    for source, figure in _figures():
        pairs = _declared_pairs(figure)
        if len(pairs) != 1 or not figure.destination:
            continue
        destination = Path(figure.destination)
        root = _assets_root(destination)
        stray = [
            (root / locale / theme / destination.name).as_posix()
            for locale in LOCALES
            for theme in THEMES
            if (REPO_ROOT / root / locale / theme / destination.name).is_file()
        ]
        assert not stray, f"{source}:{figure.id}: single cell but stray variants on disk: {stray}"


def test_unknown_variant_need_is_a_manifest_error(tmp_path):
    recipe = json.loads(help_figures.MANIFEST_PATH.read_text(encoding="utf-8"))
    recipe["figures"][0]["variant_need"] = "glossy"
    recipe_path = tmp_path / "help_figures.json"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
    with pytest.raises(help_figures.ManifestError, match=r"unknown variant_need 'glossy'"):
        help_figures.load_manifest(recipe_path)

    live = json.loads(help_live.RECIPE_PATH.read_text(encoding="utf-8"))
    live["figures"][0]["variant_need"] = "glossy"
    live_path = tmp_path / "help_figures_live.json"
    live_path.write_text(json.dumps(live), encoding="utf-8")
    with pytest.raises(help_figures.ManifestError, match=r"unknown variant_need 'glossy'"):
        help_live.load_recipes(live_path)
