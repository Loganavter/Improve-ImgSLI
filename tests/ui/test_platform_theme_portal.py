"""The file chooser must come from the XDG desktop portal when it is available.

Owner decision 2026-10-28: "вернуть нативный через портал" — the modern GNOME
chooser. The portal's chooser is a separate application whose window the portal
parents itself, so the native look and the stacking fix coexist; Qt's in-process
GTK dialog could map under the main window
(docs/dev/platform/investigations/help-dialog-opens-below-main-window.md).

Red-before: ``core.platform_theme.resolve_platform_theme`` did not exist on the previous
tree (nothing seeded ``QT_QPA_PLATFORMTHEME``), so these cases could not pass.
"""

from __future__ import annotations

from pathlib import Path

from core.platform_theme import resolve_platform_theme


def _plugin_dir(tmp_path: Path, *, with_portal: bool) -> str:
    themes = tmp_path / "platformthemes"
    themes.mkdir()
    if with_portal:
        (themes / "libqxdgdesktopportal.so").write_bytes(b"")
    (themes / "libqgtk3.so").write_bytes(b"")
    return str(tmp_path)


def test_portal_theme_is_chosen_when_unset_and_available(tmp_path):
    assert (
        resolve_platform_theme({}, plugin_dir=_plugin_dir(tmp_path, with_portal=True))
        == "xdgdesktopportal"
    )


def test_an_explicit_user_theme_wins(tmp_path):
    plugin_dir = _plugin_dir(tmp_path, with_portal=True)
    assert (
        resolve_platform_theme(
            {"QT_QPA_PLATFORMTHEME": "qt6ct"}, plugin_dir=plugin_dir
        )
        is None
    )


def test_no_portal_plugin_leaves_qt_default(tmp_path):
    assert (
        resolve_platform_theme({}, plugin_dir=_plugin_dir(tmp_path, with_portal=False))
        is None
    )


def test_missing_plugin_dir_is_not_an_error(tmp_path):
    assert resolve_platform_theme({}, plugin_dir=str(tmp_path / "absent")) is None
