"""Locale/theme asset variants: the resolution chain and its fail-closed rule.

Shipped help bodies reference ONE literal asset path per figure; every locale
reads the same bytes, so a Russian page shows an English screenshot. The
resolver therefore derives variants from the same literal path:

    assets/<locale>/<theme>/<name>  ->  assets/<locale>/<name>
    ->  assets/<theme>/<name>  ->  assets/<name>  ->  None

The base path is today's behaviour and must keep working (a single-variant
recipe ships flat). A variant the manifest *declares* but that is absent is a
content bug: returning the base image there would silently show the wrong
language/theme, so the resolver returns ``None`` (the dialog's existing
placeholder path) instead.
"""

from __future__ import annotations

import json
from pathlib import Path

from plugins.help.tree import resolve_help_asset


def _body_and_assets(tmp_path: Path) -> tuple[Path, Path]:
    """A minimal help package: ``<tmp>/help/en/page.md`` + ``<tmp>/help/assets``."""
    help_root = tmp_path / "resources" / "help"
    body = help_root / "en" / "page.md"
    body.parent.mkdir(parents=True)
    body.write_text("## Page\n", encoding="utf-8")
    assets = help_root / "assets"
    assets.mkdir()
    return body, assets


def _write(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode("utf-8"))
    return path


def test_locale_variant_wins_over_the_base_image(tmp_path):
    """RED-BEFORE: the resolver ignored ``locale`` and returned the base file."""
    body, assets = _body_and_assets(tmp_path)
    base = _write(assets / "shot.png", "base")
    variant = _write(assets / "ru" / "shot.png", "ru")

    resolved = resolve_help_asset(
        "../assets/shot.png", body, locale="ru", theme="dark"
    )

    assert resolved == variant
    assert resolved != base


def test_theme_only_variant_is_used_when_no_locale_variant_exists(tmp_path):
    body, assets = _body_and_assets(tmp_path)
    _write(assets / "shot.png", "base")
    variant = _write(assets / "dark" / "shot.png", "dark")

    resolved = resolve_help_asset("../assets/shot.png", body, locale="en", theme="dark")

    assert resolved == variant


def test_both_variant_wins_over_narrower_ones(tmp_path):
    body, assets = _body_and_assets(tmp_path)
    _write(assets / "shot.png", "base")
    _write(assets / "ru" / "shot.png", "locale")
    _write(assets / "dark" / "shot.png", "theme")
    both = _write(assets / "ru" / "dark" / "shot.png", "both")

    resolved = resolve_help_asset("../assets/shot.png", body, locale="ru", theme="dark")

    assert resolved == both


def test_base_image_still_resolves_without_variants(tmp_path):
    """The 25 shipped figures are single-variant: today's flat path unchanged."""
    body, assets = _body_and_assets(tmp_path)
    base = _write(assets / "shot.png", "base")

    assert resolve_help_asset("../assets/shot.png", body, locale="ru", theme="dark") == base
    # No locale/theme arguments at all: legacy callers keep the old lookup.
    assert resolve_help_asset("../assets/shot.png", body) == base


def test_declared_variant_that_is_missing_fails_closed(tmp_path):
    """A declared ru/dark file that is absent must not fall back to base."""
    body, assets = _body_and_assets(tmp_path)
    _write(assets / "shot.png", "base")

    resolved = resolve_help_asset(
        "../assets/shot.png",
        body,
        locale="ru",
        theme="dark",
        declared_variants=[("ru", "dark")],
    )

    assert resolved is None


def test_undeclared_missing_variant_may_fall_back_to_base(tmp_path):
    body, assets = _body_and_assets(tmp_path)
    base = _write(assets / "shot.png", "base")

    resolved = resolve_help_asset(
        "../assets/shot.png",
        body,
        locale="zh",
        theme="light",
        declared_variants=[("ru", "dark")],
    )

    assert resolved == base


def test_undeclared_locale_falls_back_for_a_declared_theme(tmp_path):
    """A matrix declares (locale, theme) pairs, never a theme-only folder.

    zh ships no figure variants; a zh reader on the dark theme must keep the
    base image (today's behaviour) instead of failing closed because ``dark`` is
    declared for other locales.
    """
    body, assets = _body_and_assets(tmp_path)
    base = _write(assets / "shot.png", "base")

    resolved = resolve_help_asset(
        "../assets/shot.png",
        body,
        locale="zh",
        theme="dark",
        declared_variants=[("ru", "dark"), ("en", "dark")],
    )

    assert resolved == base


def test_nested_asset_variants_live_under_the_assets_root(tmp_path):
    """``assets/ui/toolbar.jpg`` variants are ``assets/<locale>/<theme>/toolbar.jpg``."""
    body, assets = _body_and_assets(tmp_path)
    _write(assets / "ui" / "toolbar.jpg", "base")
    variant = _write(assets / "ru" / "dark" / "toolbar.jpg", "both")

    resolved = resolve_help_asset(
        "../assets/ui/toolbar.jpg", body, locale="ru", theme="dark"
    )

    assert resolved == variant


def test_no_variant_and_no_base_returns_none(tmp_path):
    body, _assets = _body_and_assets(tmp_path)

    assert resolve_help_asset("../assets/shot.png", body, locale="ru", theme="dark") is None
    assert resolve_help_asset("../assets/shot.png", None, locale="ru", theme="dark") is None


def test_manifest_declares_the_variant_matrix(tmp_path, monkeypatch):
    """``help_figures.json`` is the manifest of record for variants."""
    from plugins.help import tree as help_tree

    manifest = tmp_path / "help_figures.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [
                    {
                        "destination": "src/resources/help/assets/platform/shot.png",
                        "locales": ["en", "ru"],
                        "themes": ["dark", "light"],
                    },
                    {
                        "destination": "src/resources/help/assets/platform/single.png",
                        "locales": ["en"],
                        "themes": ["dark"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(help_tree, "_VARIANT_MANIFEST", manifest)
    help_tree.clear_help_variant_cache()
    try:
        declared = help_tree._declared_variants_for(
            Path("/repo/src/resources/help/assets/platform/shot.png")
        )
        assert declared == frozenset(
            {("en", "dark"), ("en", "light"), ("ru", "dark"), ("ru", "light")}
        )
        # A single-variant recipe keeps the flat base path (no variant churn).
        assert not help_tree._declared_variants_for(
            Path("/repo/src/resources/help/assets/platform/single.png")
        )
    finally:
        help_tree.clear_help_variant_cache()


def test_help_dialog_passes_locale_and_theme_to_the_resolver(qtbot, monkeypatch):
    """The ONE call site reads the dialog's language and the toolkit theme."""
    from plugins.help import dialog as help_dialog
    from plugins.help.plugin import HelpPlugin

    seen: dict = {}

    def _fake_resolver(rel_path, body_file=None, **kwargs):
        seen.update({"rel_path": rel_path, "body_file": body_file, **kwargs})
        return None

    monkeypatch.setattr(help_dialog, "resolve_help_asset", _fake_resolver)
    monkeypatch.setattr(help_dialog, "_current_theme_name", lambda: "dark")

    plugin = HelpPlugin()
    plugin.show_dialog(parent=None, language="ru", page="platform.hotkeys")
    dialog = plugin._dialog
    qtbot.addWidget(dialog)

    assert dialog._resolve_asset("../../assets/platform/settings_keyboard.png") is None
    assert seen["locale"] == "ru"
    assert seen["theme"] == "dark"
    assert seen["body_file"] == dialog._current_body_file



def test_live_manifest_declarations_reach_the_resolver():
    """The live capture set is a declaration of record too.

    RED-BEFORE: only ``help_figures.json`` was read, so every live figure's
    declared matrix was invisible to the resolver and a missing cell fell back
    to the base image — a Russian light-theme help page rendered the English
    dark dialog with no signal (measured live, 2026-10-22).
    """
    from plugins.help import tree as help_tree

    base = Path("/repo/src/plugins/export/resources/help/assets/export_dialog.jpg")
    declared = help_tree._declared_variants_for(base)
    assert declared == frozenset(
        (locale, theme)
        for locale in ("en", "pt_BR", "ru", "zh")
        for theme in ("dark", "light")
    )


def test_a_missing_declared_live_cell_fails_closed(tmp_path, monkeypatch):
    """A live cell the manifest declares but the tree lacks is a content bug."""
    from plugins.help import tree as help_tree

    help_root = tmp_path / "resources" / "help"
    body = help_root / "ru" / "page.md"
    body.parent.mkdir(parents=True)
    body.write_text("## Page\n", encoding="utf-8")
    base = help_root / "assets" / "export_dialog.jpg"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"base")

    help_tree.clear_help_variant_cache()
    try:
        assert (
            help_tree.resolve_help_asset(
                "../assets/export_dialog.jpg", body, locale="ru", theme="light"
            )
            is None
        ), "a declared live cell that is absent must not fall back to the base image"
    finally:
        help_tree.clear_help_variant_cache()


def test_the_two_manifests_merge_into_one_stronger_claim(tmp_path, monkeypatch):
    """One destination, two manifests: the union wins, not the load order."""
    from plugins.help import tree as help_tree

    recipe = tmp_path / "help_figures.json"
    recipe.write_text(
        json.dumps(
            {
                "figures": [
                    {
                        "destination": "src/resources/help/assets/platform/shot.png",
                        "locales": ["en"],
                        "themes": ["dark"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    live = tmp_path / "help_figures_live.json"
    live.write_text(
        json.dumps(
            {
                "figures": [
                    {
                        "destination": "src/resources/help/assets/platform/shot.png",
                        "locales": ["en", "ru"],
                        "themes": ["dark", "light"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(help_tree, "_VARIANT_MANIFEST", recipe)
    monkeypatch.setattr(help_tree, "_LIVE_VARIANT_MANIFEST", live)
    help_tree.clear_help_variant_cache()
    try:
        declared = help_tree._declared_variants_for(
            Path("/repo/src/resources/help/assets/platform/shot.png")
        )
        assert declared == frozenset(
            {("en", "dark"), ("en", "light"), ("ru", "dark"), ("ru", "light")}
        )
    finally:
        help_tree.clear_help_variant_cache()
