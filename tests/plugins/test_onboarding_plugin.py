"""First-run onboarding plugin: present / complete / host API."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QStackedWidget, QWidget

from plugins.onboarding import host as onboarding_host
from plugins.onboarding.plugin import OnboardingPlugin
from plugins.settings.events import SettingsUIModeChangedEvent


class _FakeSettingsManager:
    def __init__(self, *, first_run: bool = True) -> None:
        self._first_run = first_run
        self.saved: dict[str, object] = {}

    def is_first_run(self) -> bool:
        return self._first_run

    def set_first_run_completed(self) -> None:
        self._first_run = False

    def _save_setting(self, key: str, value: object) -> None:
        self.saved[key] = value


class _FakeEventBus:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object, *args, **kwargs) -> None:
        del args, kwargs
        self.events.append(event)


def test_should_present_follows_settings_manager() -> None:
    plugin = OnboardingPlugin()
    plugin.settings_manager = _FakeSettingsManager(first_run=True)
    assert plugin.should_present() is True
    plugin.settings_manager = _FakeSettingsManager(first_run=False)
    assert plugin.should_present() is False


def test_host_should_present_falls_back_to_window_settings() -> None:
    window = SimpleNamespace(
        onboarding_host=None,
        app_context=None,
        settings_manager=_FakeSettingsManager(first_run=True),
    )
    assert onboarding_host.should_present(window) is True
    window.settings_manager = _FakeSettingsManager(first_run=False)
    assert onboarding_host.should_present(window) is False


def test_present_mounts_and_completed_dismisses(qtbot) -> None:
    emitted: list[str] = []
    bus = _FakeEventBus()
    settings = _FakeSettingsManager(first_run=True)
    store = SimpleNamespace(settings=SimpleNamespace(current_language="en", ui_mode="beginner"))

    root = QWidget()
    stack = QStackedWidget(root)
    qtbot.addWidget(root)
    root.resize(960, 720)
    stack.resize(960, 684)

    window = SimpleNamespace(
        _startup_stack=stack,
        _custom_title_bar=None,
        settings_manager=settings,
        store=store,
        app_context=SimpleNamespace(event_bus=bus),
        image_compare_widget=None,
        onboarding_host=None,
        startup_runtime=SimpleNamespace(hide_cover=lambda: None),
        width=lambda: 960,
        height=lambda: 720,
    )

    plugin = OnboardingPlugin()
    plugin.initialize(
        SimpleNamespace(store=store, settings_manager=settings, event_bus=bus)
    )
    def _on_done(mode: str) -> None:
        emitted.append(mode)
        plugin.apply_ui_mode(mode)

    plugin.present(window, on_completed=_on_done)

    assert plugin.is_active()
    assert window.onboarding_host is plugin
    assert onboarding_host.is_active(window)
    assert stack.indexOf(plugin._overlay) >= 0
    assert stack.currentWidget() is plugin._overlay

    plugin._overlay._current_index = 1  # advanced
    plugin._overlay._finish()

    assert emitted == ["advanced"]
    assert plugin.is_active() is False
    assert onboarding_host.is_active(window) is False
    assert settings.saved.get("ui_mode") == "advanced"
    assert settings.is_first_run() is False
    assert store.settings.ui_mode == "advanced"
    assert any(isinstance(e, SettingsUIModeChangedEvent) for e in bus.events)
