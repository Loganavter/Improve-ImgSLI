"""Color settings: changing a color keeps the laser/guide segment intact even
when guides are hidden — no silent loss of the laser color.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md (guides/laser color state).
"""

from types import SimpleNamespace

from PySide6.QtGui import QColor

from tabs.image_compare.ui import magnifier_color_controls as color_settings_button_module

class _ButtonProbe:
    def __init__(self):
        self.value = None
        self.show_underline = None

    def setUnderlineColor(self, value):
        self.value = value

    def setShowUnderline(self, value):
        self.show_underline = value

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
        "registry",
        lambda: SimpleNamespace(get_feature_command_by_alias=_query),
    )

    button = color_settings_button_module.ColorSettingsButton.__new__(
        color_settings_button_module.ColorSettingsButton
    )
    button.store = SimpleNamespace(
        viewport=SimpleNamespace(view_state=object()),
    )
    probe = _ButtonProbe()
    button.setUnderlineColor = probe.setUnderlineColor
    button.setShowUnderline = probe.setShowUnderline

    color_settings_button_module.ColorSettingsButton._update_underline_colors(button)

    assert isinstance(probe.value, list)
    assert len(probe.value) == 4
    assert probe.value[1] == QColor(40, 50, 60, 230)
    assert probe.show_underline is True


def test_color_button_hides_underline_when_magnifier_disabled(monkeypatch):
    monkeypatch.setattr(
        color_settings_button_module,
        "registry",
        lambda: SimpleNamespace(
            get_feature_command_by_alias=lambda alias: {
                "overlay.enabled": lambda _store: False,
            }.get(alias)
        ),
    )

    button = color_settings_button_module.ColorSettingsButton.__new__(
        color_settings_button_module.ColorSettingsButton
    )
    button.store = SimpleNamespace(viewport=SimpleNamespace(view_state=object()))
    probe = _ButtonProbe()
    button.setUnderlineColor = probe.setUnderlineColor
    button.setShowUnderline = probe.setShowUnderline

    color_settings_button_module.ColorSettingsButton._update_underline_colors(button)

    assert probe.show_underline is False
    assert probe.value is None


def test_color_button_disconnects_store_when_destroyed(qtbot, monkeypatch):
    """Regression: a destroyed ColorSettingsButton must stop reacting to
    store.state_changed.

    PySide6 keeps the Python wrapper alive through the bound-method
    connection, so without the destroyed->disconnect the handler fires after
    the C++ widget (and its flyout buttons) are gone and crashes in
    IconActionFlyout.set_action_state with "Internal C++ object (Button)
    already deleted".
    """
    # Keep the real feature commands out: other tests in the suite register
    # the live "overlay.enabled" command, which would touch the fake store.
    monkeypatch.setattr(
        color_settings_button_module,
        "registry",
        lambda: SimpleNamespace(get_feature_command_by_alias=lambda alias: None),
    )
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QWidget

    class _Store(QObject):
        state_changed = Signal(str)

        def __init__(self):
            super().__init__()
            self.viewport = SimpleNamespace(view_state=object())

    store = _Store()
    calls = []

    parent = QWidget()
    qtbot.addWidget(parent)
    button = color_settings_button_module.ColorSettingsButton(parent=parent, store=store)
    button.refresh_visual_state = lambda: calls.append(1)  # type: ignore[method-assign]

    store.state_changed.emit("viewport")
    assert calls == [1]

    parent.deleteLater()  # destroys button + sibling flyout (shared parent)
    qtbot.wait(20)
    store.state_changed.emit("viewport")
    assert calls == [1], "destroyed button must be disconnected from the store"