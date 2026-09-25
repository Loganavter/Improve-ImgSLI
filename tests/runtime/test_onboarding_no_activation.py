"""Wave W2 (modal-lifetime): onboarding shows without host-window activation.

The onboarding overlay must appear on top of its own startup stack via
``raise_()`` only — no ``activateWindow()`` and no
``ActiveWindowFocusReason`` focus grabs. Host-window activation belongs to
the host shell (dialog_manager); plugin code may only use
``OtherFocusReason`` for targets inside the overlay itself.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QStackedWidget, QWidget

from plugins.onboarding.overlay import OnboardingOverlay
from plugins.onboarding.plugin import OnboardingPlugin

_ONBOARDING_FILES = (
    "src/plugins/onboarding/overlay.py",
    "src/plugins/onboarding/plugin.py",
    "src/plugins/onboarding/pages.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


class _FakeSettingsManager:
    def __init__(self, *, first_run: bool = True) -> None:
        self._first_run = first_run
        self.saved: dict[str, object] = {}
        self.persisted_stores: list = []

    def is_first_run(self) -> bool:
        return self._first_run

    def set_first_run_completed(self) -> None:
        self._first_run = False

    def _save_setting(self, key: str, value: object) -> None:
        self.saved[key] = value

    def schedule_persist(self, store) -> None:
        self.persisted_stores.append(store)


def _make_plugin() -> OnboardingPlugin:
    from core.state_management.dispatcher import Dispatcher
    from core.store import Store

    plugin = OnboardingPlugin()
    store = Store()
    store.set_dispatcher(Dispatcher(store))
    plugin.initialize(
        SimpleNamespace(
            store=store,
            settings_manager=_FakeSettingsManager(first_run=True),
            event_bus=None,
        )
    )
    return plugin


def _make_window(plugin: OnboardingPlugin, stack: QStackedWidget) -> SimpleNamespace:
    return SimpleNamespace(
        _startup_stack=stack,
        _custom_title_bar=None,
        settings_manager=plugin.settings_manager,
        store=plugin.store,
        app_context=SimpleNamespace(event_bus=None),
        image_compare_widget=None,
        onboarding_host=None,
        startup_runtime=SimpleNamespace(hide_cover=lambda: None),
        width=lambda: 960,
        height=lambda: 720,
    )


def test_no_activation_tokens_in_onboarding_files() -> None:
    """Grep-proof: no activateWindow/ActiveWindowFocusReason in the 3 files."""
    root = _repo_root()
    for rel in _ONBOARDING_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        assert "activateWindow" not in text, rel
        assert "ActiveWindowFocusReason" not in text, rel


def test_present_show_path_performs_zero_activate_window(qtbot, monkeypatch) -> None:
    """present() + showEvent() raise the overlay with zero activateWindow."""
    calls: list[QWidget] = []
    real_activate = OnboardingOverlay.activateWindow

    def _spy(self: QWidget) -> None:
        calls.append(self)
        return real_activate(self)

    monkeypatch.setattr(OnboardingOverlay, "activateWindow", _spy)

    plugin = _make_plugin()
    root = QWidget()
    stack = QStackedWidget(root)
    qtbot.addWidget(root)
    root.resize(960, 720)
    stack.resize(960, 684)
    root.show()

    plugin.present(_make_window(plugin, stack), on_completed=None)

    overlay = plugin._overlay
    assert overlay is not None
    # Still on top of its own stack...
    assert stack.currentWidget() is overlay
    assert overlay.isVisible()
    # ...but never escalated to host-window activation (covers both
    # plugin.present() and overlay.showEvent() paths).
    assert calls == []


def test_color_dialog_bring_forward_performs_zero_activate_window(
    qtbot, monkeypatch
) -> None:
    """Existing color dialog is raised, not activated, on repeat clicks."""
    from plugins.onboarding import pages as onboarding_pages

    calls: list[QWidget] = []
    real_activate = QWidget.activateWindow

    def _spy(self: QWidget) -> None:
        calls.append(self)
        return real_activate(self)

    monkeypatch.setattr(QWidget, "activateWindow", _spy)

    dialog = QWidget()
    qtbot.addWidget(dialog)
    dialog.resize(200, 100)
    dialog.show()
    assert dialog.isVisible()

    button = SimpleNamespace(_color_dialog=dialog)
    onboarding_pages._show_color_dialog(None, button, "#ff0000", "en")

    assert dialog.isVisible()
    assert calls == []
