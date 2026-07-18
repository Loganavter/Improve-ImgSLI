"""UI inspector snapshot reads widget identity, properties, palette and theme
token matches without booting the application.

Dogma source: docs/dev/UI_INSPECTOR.md.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from sli_ui_toolkit.widgets import Button, Label

from devtools.ui_inspector.widget_snapshot import inspect_widget

_APP = None


class _ThemeManagerProbe:
    def __init__(self):
        self._dark_palette = {
            "dialog.text": QColor("#dfdfdf"),
            "accent": QColor("#0096ff"),
        }
        self._light_palette = {}

    def is_dark(self):
        return True


class _ButtonThemeManagerProbe:
    def __init__(self):
        self._dark_palette = {}
        self._light_palette = {
            "button.toggle.background.normal": "#f0f0f0",
            "button.toggle.background.hover": "#e6e6e6",
            "button.toggle.background.pressed": "#dcdcdc",
            "button.toggle.background.checked": "#c0c0c0",
            "button.toggle.background.checked.hover": "#b0b0b0",
        }
        self._qss_paths = (str(Path.cwd() / "src/resources/styles/app.qss"),)

    def is_dark(self):
        return False


def _app():
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def test_widget_snapshot_collects_identity_properties_and_theme_matches():
    """Uses the toolkit's own Label(QLabel) — see API_CATALOG.md's "Label"
    entry — rather than a raw QLabel: a raw QLabel is a native Qt class with
    no discoverable Python source file, so source_file would always be
    empty for it (see widget_snapshot.py's _is_binary_or_thirdparty)."""
    _app()
    widget = Label("Rating")
    widget.setObjectName("ratingLabel")
    widget.setProperty("class", "rating-label")
    widget.setStyleSheet("font-weight: bold;")

    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#dfdfdf"))
    widget.setPalette(palette)

    snapshot = inspect_widget(widget, _ThemeManagerProbe())

    assert snapshot.class_name == "Label"
    assert snapshot.object_name == "ratingLabel"
    assert snapshot.selector == "Label#ratingLabel"
    assert snapshot.dynamic_properties["class"] == "rating-label"
    assert snapshot.inline_stylesheet == "font-weight: bold;"
    assert snapshot.path[-1] == "Label#ratingLabel"
    assert snapshot.source_file

    window_text = next(color for color in snapshot.palette if color.name == "WindowText")
    assert window_text.value == "#ffdfdfdf"
    assert window_text.theme_keys == ("dialog.text",)


def test_widget_snapshot_reports_toolkit_button_state_theme_sources():
    _app()
    button = Button(variant="default")

    snapshot = inspect_widget(button, _ButtonThemeManagerProbe())

    keys = [source.key for source in snapshot.widget_theme_sources]
    assert keys == [
        "button.toggle.background.normal",
        "button.toggle.background.hover",
        "button.toggle.background.pressed",
        "button.toggle.background.checked",
        "button.toggle.background.checked.hover",
    ]
    assert Path(snapshot.widget_theme_sources[1].path).as_posix().endswith(
        "src/resources/themes.json"
    )
    assert snapshot.widget_theme_sources[1].line == 81
