"""Color settings: changing a color keeps the laser/guide segment intact even
when guides are hidden — no silent loss of the laser color.

Dogma source: docs/dev/CANVAS_FEATURES.md (guides/laser color state).
"""

from types import SimpleNamespace

from PyQt6.QtGui import QColor

from ui.widgets import magnifier_color_controls as color_settings_button_module

class _ButtonProbe:
    def __init__(self):
        self.value = None

    def set_color(self, value):
        self.value = value

def test_color_button_keeps_laser_segment_when_guides_hidden(monkeypatch):
    overlay_enabled = lambda _store: True
    overlay_active_state = lambda _store: {
        "capture_color": SimpleNamespace(r=10, g=20, b=30, a=255),
        "guides_color": SimpleNamespace(r=40, g=50, b=60, a=255),
        "border_color": SimpleNamespace(r=70, g=80, b=90, a=255),
        "divider_color": SimpleNamespace(r=100, g=110, b=120, a=255),
        "divider_visible": True,
        "divider_thickness": 2,
        "show_laser": True,
    }
    overlay_active_combined = lambda _store: True
    capture_widget_state = lambda _view_state: SimpleNamespace(
        color=SimpleNamespace(r=1, g=2, b=3, a=255)
    )
    guides_widget_state = lambda _view_state: SimpleNamespace(
        enabled=False,
        color=SimpleNamespace(r=4, g=5, b=6, a=255),
    )

    def _query(alias):
        mapping = {
            "overlay.enabled": overlay_enabled,
            "overlay.active_state": overlay_active_state,
            "overlay.active_combined": overlay_active_combined,
            "capture.widget_state": capture_widget_state,
            "guides.widget_state": guides_widget_state,
        }
        return mapping.get(alias)

    monkeypatch.setattr(
        color_settings_button_module,
        "get_canvas_feature_command_by_alias",
        _query,
    )

    button = color_settings_button_module.ColorSettingsButton.__new__(
        color_settings_button_module.ColorSettingsButton
    )
    button.store = SimpleNamespace(
        viewport=SimpleNamespace(view_state=object()),
    )
    button.button = _ButtonProbe()

    color_settings_button_module.ColorSettingsButton._update_underline_colors(button)

    assert isinstance(button.button.value, list)
    assert len(button.button.value) == 4
    assert button.button.value[1] == QColor(40, 50, 60, 230)
