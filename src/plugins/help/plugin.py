from __future__ import annotations

import logging
from typing import Any

from plugins.settings.events import SettingsChangeLanguageEvent
from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin
from plugins.help.dialog import HelpDialog

logger = logging.getLogger("ImproveImgSLI")

@plugin(name="help", version="1.0", startup_tier="deferred")
class HelpPlugin(Plugin, IControllablePlugin):
    def __init__(self):
        super().__init__()
        self._dialog: HelpDialog | None = None
        self.store: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)
        if self.event_bus is not None:
            self.event_bus.subscribe(
                SettingsChangeLanguageEvent, self._on_language_changed
            )
        self._install_plugin_contributions(context)

    def _install_plugin_contributions(self, context: Any) -> None:
        """Collect typed plugin help fragments from the plugin registry.

        Duck-typed probe (no ``plugins/<name>`` imports): prefers
        ``context.plugin_coordinator.lifecycle.all_plugins()`` (matches the
        ``ExportPlugin`` ``context.plugin_coordinator`` convention), falls
        back to ``context.plugin_registry.all_plugins()``. Missing registry
        or collection failure is best-effort — help still serves the host
        tree. Re-runnable after deferred-tier discovery.
        """
        from plugins.help.tree import contribute_all_help_plugins

        try:
            plugins: Any = ()
            coordinator = getattr(context, "plugin_coordinator", None)
            lifecycle = getattr(coordinator, "lifecycle", None)
            if lifecycle is not None and hasattr(lifecycle, "all_plugins"):
                plugins = lifecycle.all_plugins()
            else:
                registry = getattr(context, "plugin_registry", None)
                if registry is not None and hasattr(registry, "all_plugins"):
                    plugins = registry.all_plugins()
            contribute_all_help_plugins(plugins)
        except Exception:
            logger.exception("HelpPlugin plugin-contribution collection failed")

    def get_controller(self) -> "HelpPlugin":
        return self

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        target = getattr(self, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Help plugin has no command '{command}'")
    def show_dialog(
        self,
        *,
        parent: Any = None,
        language: str = "en",
        page: str | None = None,
        anchor: str | None = None,
        video_url: str | None = None,
        learn_more_url: str | None = None,
    ) -> None:
        # Transient-parent Help to the calling window (Export dialog pattern:
        # parent=self.host.parent_widget in dialog_manager). An attached
        # dialog of the focused window activates freely under xdg-activation,
        # while a parentless top-level reached a turn later is denied and the
        # compositor parks the host as demanding-attention.
        host = parent
        if host is None:
            try:
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                host = app.activeWindow() if app is not None else None
            except RuntimeError:
                host = None
        if self._dialog is None:
            self._dialog = HelpDialog(
                current_language=language,
                app_name="Improve-ImgSLI",
                parent=host,
            )
            self._dialog.destroyed.connect(self._on_dialog_destroyed)

        if self._dialog.current_language != language:
            self._dialog.update_language(language)

        # Wayland activation for this independent modeless top-level is
        # handled by ThemedDialog (suppress the stale show-time request +
        # retry until the compositor grants focus) — see the module docstring
        # in shared_toolkit/ui/themed_dialog.py.
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        if page:
            self._dialog.navigate_to(
                page, anchor, video_url=video_url, learn_more_url=learn_more_url
            )

    def _on_dialog_destroyed(self) -> None:
        self._dialog = None

    def _on_language_changed(self, event: SettingsChangeLanguageEvent) -> None:
        if self._dialog is not None:
            self._dialog.update_language(event.lang_code)