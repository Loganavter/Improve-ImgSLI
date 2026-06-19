"""UI inspector panel stays compact; full details are reserved for copy actions.

Dogma source: docs/dev/UI_INSPECTOR.md.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect

from devtools.ui_inspector.panel import (
    _format_compact_snapshot,
    _format_compact_snapshot_html,
    _format_full_snapshot,
)
from devtools.ui_inspector.qss_index import QssRule
from devtools.ui_inspector.widget_snapshot import (
    ColorValue,
    ThemeColorSource,
    WidgetSnapshot,
)


def test_compact_panel_format_limits_palette_and_qss_noise():
    snapshot = WidgetSnapshot(
        class_name="Button",
        object_name="recordButton",
        path=("Main", "Toolbar", "Button#recordButton"),
        geometry=QRect(10, 20, 40, 32),
        visible=True,
        enabled=True,
        has_focus=False,
        under_mouse=True,
        source_file="/repo/ui/toolbar.py",
        source_line=12,
        dynamic_properties={
            "variant": "default",
            "iconSizePx": "22",
            "_systemSelectWidget": "true",
        },
        palette=(
            ColorValue(
                "Window",
                "#ffffffff",
                ("Window", "Base", "ToolTipBase", "button.dialog.default.background"),
                (
                    ThemeColorSource(
                        "/repo/src/resources/themes.json",
                        3,
                        "light",
                        "Window",
                        "#ffffff",
                    ),
                    ThemeColorSource(
                        "/repo/src/resources/themes.json",
                        5,
                        "light",
                        "Base",
                        "#ffffff",
                    ),
                ),
            ),
            ColorValue("Base", "#ffffffff", ("Window", "Base")),
            ColorValue(
                "Text",
                "#ff1f1f1f",
                ("WindowText", "Text", "dialog.text"),
                (
                    ThemeColorSource(
                        "/repo/src/resources/themes.json",
                        20,
                        "light",
                        "dialog.text",
                        "#1f1f1f",
                    ),
                ),
            ),
            ColorValue("ToolTipText", "#ff1f1f1f", ("WindowText", "Text")),
            ColorValue("Highlight", "#ff0078d4", ("Highlight", "accent")),
        ),
    )
    snapshot.theme_token_sources["dialog.text"] = ThemeColorSource(
        "/repo/src/resources/themes.json",
        20,
        "light",
        "dialog.text",
        "#1f1f1f",
    )
    snapshot.theme_token_sources["button.default.background"] = ThemeColorSource(
        "/repo/src/resources/themes.json",
        16,
        "light",
        "button.default.background",
        "#260078d7",
    )
    snapshot.theme_token_sources["button.default.background.hover"] = ThemeColorSource(
        "/repo/src/resources/themes.json",
        17,
        "light",
        "button.default.background.hover",
        "#360078d7",
    )
    rules = tuple(
        QssRule(
            source=f"/tmp/styles_{idx}.qss",
            selector=f"QWidget#recordButton[state=\"{idx}\"]",
            body="background-color: @button.default.background;\ncolor: @dialog.text;",
        )
        for idx in range(10)
    ) + (
        QssRule(
            source="/tmp/button.qss",
            selector='QWidget#recordButton[state="hover"]',
            body="background-color: @button.default.background.hover;",
        ),
    )

    compact = _format_compact_snapshot(snapshot, rules)
    compact_html = _format_compact_snapshot_html(snapshot, rules)
    full = _format_full_snapshot(snapshot, rules)

    assert "iconSizePx" not in compact
    assert "source: /repo/ui/toolbar.py:12" in compact
    assert "objectName: recordButton" in compact
    assert "Theme colors" in compact
    assert "  Button:" in compact
    assert "source: /repo/src/resources/themes.json (16-17, 20)" in compact
    assert '"button.default.background.hover": "#360078d7" ■' in compact
    assert '"dialog.text": "#1f1f1f" ■' in compact
    assert "Hover" in compact
    assert 'QWidget#recordButton[state="hover"]' in compact
    assert "color:#360078d7" in compact_html
    assert "button.dialog.default.background" not in compact
    assert "+5 more in Copy details" in compact
    assert len(compact.splitlines()) < len(full.splitlines())


def test_compact_panel_uses_widget_theme_sources_without_palette_noise():
    snapshot = WidgetSnapshot(
        class_name="ColorSettingsButton",
        object_name="",
        path=("Main", "ColorSettingsButton"),
        geometry=QRect(0, 0, 36, 36),
        visible=True,
        enabled=True,
        has_focus=False,
        under_mouse=True,
        dynamic_properties={"variant": "default"},
        palette=(
            ColorValue(
                "Window",
                "#ffffffff",
                ("Window",),
                (
                    ThemeColorSource(
                        "/repo/src/resources/themes.json",
                        3,
                        "light",
                        "Window",
                        "#ffffff",
                    ),
                ),
            ),
        ),
        widget_theme_sources=(
            ThemeColorSource(
                "/repo/src/resources/themes.json",
                79,
                "light",
                "button.toggle.background.normal",
                "#f0f0f0",
            ),
            ThemeColorSource(
                "/repo/src/resources/themes.json",
                80,
                "light",
                "button.toggle.background.hover",
                "#e6e6e6",
            ),
            ThemeColorSource(
                "/repo/src/resources/themes.json",
                81,
                "light",
                "button.toggle.background.pressed",
                "#dcdcdc",
            ),
        ),
    )

    compact = _format_compact_snapshot(snapshot, ())
    compact_html = _format_compact_snapshot_html(snapshot, ())

    assert "source: /repo/src/resources/themes.json (79-81)" in compact
    assert '"button.toggle.background.hover": "#e6e6e6" ■' in compact
    assert '"Window": "#ffffff" ■' not in compact
    assert "QSS candidates\n  none" in compact
    assert "color:#e6e6e6" in compact_html
