"""Onboarding isolation: no legacy concrete-tab getattr in host plugin.

Wave W-B deleted the ``getattr(window, "image_compare_widget", None)`` +
``reapply_button_styles`` branch from ``plugins.onboarding.plugin``. That
attribute is set nowhere in ``src/`` (dead legacy — the only reference was
the deleted read), and per-tab polish after a UI-mode change is owned by
``TabContract.apply_appearance`` via the tab registry, not by the host
reaching into a concrete tab widget.

These tests pin the closure:
- the first-run-without-IC absence path (window carries no concrete tab
  widget at all) applies the mode without crashing;
- the plugin source names no concrete tab (no ``image_compare_widget``
  string, no ``reapply_button_styles`` string, no ``tabs.*`` import).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from plugins.onboarding.plugin import OnboardingPlugin
from plugins.settings.events import SettingsUIModeChangedEvent


class _FakeSettingsManager:
    def __init__(self) -> None:
        self.saved: dict[str, object] = {}
        self.persisted_stores: list = []

    def is_first_run(self) -> bool:
        return True

    def _save_setting(self, key: str, value: object) -> None:
        self.saved[key] = value

    def schedule_persist(self, store) -> None:
        self.persisted_stores.append(store)


class _FakeEventBus:
    def __init__(self) -> None:
        self.events: list[object] = []

    def subscribe(self, event_type, callback) -> None:
        pass

    def emit(self, event: object, *args, **kwargs) -> None:
        del args, kwargs
        self.events.append(event)


def _make_plugin() -> OnboardingPlugin:
    from core.state_management.dispatcher import Dispatcher
    from core.store import Store

    plugin = OnboardingPlugin()
    store = Store()
    store.set_dispatcher(Dispatcher(store))
    plugin.initialize(
        SimpleNamespace(
            store=store,
            settings_manager=_FakeSettingsManager(),
            event_bus=_FakeEventBus(),
        )
    )
    return plugin


def test_apply_ui_mode_without_concrete_tab_widget_does_not_crash() -> None:
    """First-run without any concrete tab widget: no crash, mode applied."""
    plugin = _make_plugin()
    # Deliberately NO image_compare_widget attribute at all — the window
    # must not be probed for concrete tab widgets.
    plugin._window = SimpleNamespace(
        store=plugin.store,
        settings_manager=plugin.settings_manager,
        app_context=SimpleNamespace(event_bus=plugin.event_bus),
    )
    assert not hasattr(plugin._window, "image_compare_widget")

    plugin.apply_ui_mode("advanced")  # must not raise

    assert plugin.store.settings.ui_mode == "advanced"
    assert any(
        isinstance(event, SettingsUIModeChangedEvent)
        for event in plugin.event_bus.events
    )


def test_plugin_source_names_no_concrete_tab() -> None:
    """Source proof: host production never names a concrete tab here.

    The one allowed ``tabs`` touchpoint is the tab-agnostic capability
    probe via ``tabs.registry`` (no concrete tab package, no concrete
    widget attribute, no per-tab method call).
    """
    import re

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "plugins"
        / "onboarding"
        / "plugin.py"
    ).read_text(encoding="utf-8")
    assert "image_compare_widget" not in source
    assert "reapply_button_styles" not in source
    assert "image_compare" not in source
    assert "multi_compare" not in source
    concrete_imports = [
        line
        for line in source.splitlines()
        if re.search(r"(from|import)\s+tabs\.(?!registry\b)", line)
    ]
    assert concrete_imports == []
