from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin
from resources.translations import get_current_language
from resources.translations import tr as app_tr

from .dialog import ImagePropertiesDialog
from .service import build_image_properties


@plugin(name="image_properties", version="1.0")
class ImagePropertiesPlugin(Plugin, IControllablePlugin):
    capabilities = ("image_properties",)

    def initialize(self, context: Any) -> None:
        super().initialize(context)

    def get_controller(self) -> "ImagePropertiesPlugin":
        return self

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        target = getattr(self, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Image properties plugin has no command '{command}'")

    def provides_capability(self, capability: str) -> bool:
        return capability == "image_properties"

    def open_dialog(
        self,
        *,
        parent: Any = None,
        path: str | Path | None,
        display_name: str = "",
        image: Any = None,
        app_rows: Iterable[tuple[str, str, Any]] = (),
        language: str | None = None,
        tr_func=None,
    ) -> None:
        open_image_properties_dialog(
            parent=parent,
            path=path,
            display_name=display_name,
            image=image,
            app_rows=app_rows,
            language=language,
            tr_func=tr_func,
        )


def open_image_properties_dialog(
    *,
    parent: Any = None,
    path: str | Path | None,
    display_name: str = "",
    image: Any = None,
    app_rows: Iterable[tuple[str, str, Any]] = (),
    language: str | None = None,
    tr_func=None,
) -> None:
    properties = build_image_properties(
        path=path,
        display_name=display_name,
        image=image,
        app_rows=app_rows,
    )
    dialog = ImagePropertiesDialog(
        properties,
        parent=None,
        current_language=language or get_current_language() or "en",
        tr_func=tr_func if callable(tr_func) else app_tr,
    )
    dialog.exec()
