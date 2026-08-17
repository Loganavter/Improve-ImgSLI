"""First-run onboarding plugin: present / complete / host API / session trigger."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QStackedWidget, QWidget

from core.events import WorkspaceSessionActivatedEvent
from plugins.onboarding import host as onboarding_host
from plugins.onboarding.plugin import (
    _ONBOARDING_CAPABILITY,
    OnboardingPlugin,
)
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
        self._subscribers: dict[type, list] = {}

    def subscribe(self, event_type, callback) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def emit(self, event: object, *args, **kwargs) -> None:
        del args, kwargs
        self.events.append(event)
        for callback in self._subscribers.get(type(event), ()):
            callback(event)


def _make_plugin(*, first_run: bool = True):
    plugin = OnboardingPlugin()
    plugin.initialize(
        SimpleNamespace(
            store=SimpleNamespace(
                settings=SimpleNamespace(
                    current_language="en", ui_mode="beginner"
                )
            ),
            settings_manager=_FakeSettingsManager(first_run=first_run),
            event_bus=_FakeEventBus(),
        )
    )
    return plugin


def _make_window(plugin, stack: QStackedWidget) -> SimpleNamespace:
    return SimpleNamespace(
        _startup_stack=stack,
        _custom_title_bar=None,
        settings_manager=plugin.settings_manager,
        store=plugin.store,
        app_context=SimpleNamespace(event_bus=plugin.event_bus),
        image_compare_widget=None,
        onboarding_host=None,
        startup_runtime=SimpleNamespace(hide_cover=lambda: None),
        width=lambda: 960,
        height=lambda: 720,
    )


def test_should_present_follows_settings_manager() -> None:
    plugin = _make_plugin(first_run=True)
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
    plugin = _make_plugin(first_run=True)
    settings = plugin.settings_manager
    store = plugin.store
    bus = plugin.event_bus

    root = QWidget()
    stack = QStackedWidget(root)
    qtbot.addWidget(root)
    root.resize(960, 720)
    stack.resize(960, 684)

    window = _make_window(plugin, stack)

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


def test_session_activated_triggers_present_for_capability_tabs(
    qtbot, monkeypatch
) -> None:
    root = QWidget()
    stack = QStackedWidget(root)
    qtbot.addWidget(root)
    root.resize(960, 720)
    stack.resize(960, 684)

    plugin = _make_plugin(first_run=True)
    plugin._window = _make_window(plugin, stack)

    # Both image_compare and multi_compare opt in via capability.
    monkeypatch.setattr(plugin, "_tab_requests_onboarding", lambda st: True)
    for session_type in ("image_compare", "multi_compare"):
        plugin.event_bus.emit(
            WorkspaceSessionActivatedEvent(
                session_id="s1", session_type=session_type
            )
        )
        assert plugin.is_active() is True, session_type
        assert stack.currentWidget() is plugin._overlay
        plugin.dismiss()
        assert plugin.is_active() is False


def test_session_activated_ignores_non_capability_tabs(monkeypatch) -> None:
    plugin = _make_plugin(first_run=True)
    plugin._window = SimpleNamespace(_startup_stack=None)
    monkeypatch.setattr(plugin, "_tab_requests_onboarding", lambda st: False)
    for session_type in ("session_picker", "image_gallery", "video_editor"):
        plugin.event_bus.emit(
            WorkspaceSessionActivatedEvent(
                session_id="s1", session_type=session_type
            )
        )
        assert plugin.is_active() is False, session_type


def test_session_activated_once_across_capability_tabs(qtbot, monkeypatch) -> None:
    root = QWidget()
    stack = QStackedWidget(root)
    qtbot.addWidget(root)
    root.resize(960, 720)
    stack.resize(960, 684)

    plugin = _make_plugin(first_run=True)
    plugin._window = _make_window(plugin, stack)
    monkeypatch.setattr(plugin, "_tab_requests_onboarding", lambda st: True)

    # First capability tab opens → onboarding mounts.
    plugin.event_bus.emit(
        WorkspaceSessionActivatedEvent(
            session_id="s1", session_type="image_compare"
        )
    )
    assert plugin.is_active() is True

    # Complete it → first-run flips off.
    plugin._overlay._current_index = 0
    plugin._overlay._finish()
    assert plugin.is_active() is False
    assert plugin.settings_manager.is_first_run() is False

    # Opening another capability tab must NOT re-show (one shot total).
    plugin.event_bus.emit(
        WorkspaceSessionActivatedEvent(
            session_id="s2", session_type="multi_compare"
        )
    )
    assert plugin.is_active() is False


def test_session_activated_uses_default_completion_callback() -> None:
    plugin = _make_plugin(first_run=True)
    calls: list[str] = []
    window = SimpleNamespace(
        _startup_stack=None,
        startup_runtime=SimpleNamespace(
            on_onboarding_completed=lambda mode: calls.append(mode),
            hide_cover=lambda: None,
        ),
    )
    plugin.bind_window_shell(window)
    assert plugin._default_on_completed is not None


def test_tab_capability_probe_against_real_tabs() -> None:
    from tabs.registry import TabRegistry, get_shared_tab_registry

    TabRegistry().discover(tier="deferred")  # multi_compare is deferred
    registry = get_shared_tab_registry()
    # image_compare + multi_compare opt in; others must not.
    for session_type, expected in (
        ("image_compare", True),
        ("multi_compare", True),
        ("session_picker", False),
        ("image_gallery", False),
    ):
        result = registry.create_service_for(
            session_type, _ONBOARDING_CAPABILITY
        )
        assert bool(result) is expected, session_type
