from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin, IUIPlugin
from plugins.help.dialog import HelpDialog

@plugin(name="help", version="1.0")
class HelpPlugin(Plugin, IUIPlugin, IControllablePlugin):
    capabilities = ("help_dialog",)

    def __init__(self):
        super().__init__()
        self._dialog: HelpDialog | None = None
        self.store: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)

    def get_qss_paths(self) -> tuple[str, ...]:
        return (self.plugin_resource_path("resources", "help.qss"),)

    def get_controller(self) -> "HelpPlugin":
        return self

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        target = getattr(self, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Help plugin has no command '{command}'")

    def provides_capability(self, capability: str) -> bool:
        return capability == "help_dialog"

    def show_dialog(self, *, parent: Any = None, language: str = "en") -> None:
        if self._dialog is None:
            self._dialog = HelpDialog(
                current_language=language,
                app_name="Improve-ImgSLI",
                parent=parent,
            )
            self._dialog.destroyed.connect(self._on_dialog_destroyed)

        if self._dialog.current_language != language:
            self._dialog.update_language(language)

        if parent is not None and self._dialog.parent() is None:
            self._dialog.setParent(parent)

        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _on_dialog_destroyed(self) -> None:
        self._dialog = None
