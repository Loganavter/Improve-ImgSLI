from enum import Enum
from typing import TYPE_CHECKING

from PyQt6.QtGui import QIcon

if TYPE_CHECKING:
    pass

class _StubAppIcon(Enum):
    pass

def _stub_get_app_icon(icon) -> QIcon:
    return QIcon()

AppIcon: type = _StubAppIcon
get_app_icon = _stub_get_app_icon

try:
    import sys
    from pathlib import Path

    current_file = Path(__file__).resolve()

    src_path = current_file.parent.parent.parent
    icon_manager_path = src_path / "ui" / "icon_manager.py"

    if icon_manager_path.exists():

        src_path_str = str(src_path)
        if src_path_str not in sys.path:
            sys.path.insert(0, src_path_str)

        try:

            import importlib

            ui_icon_manager = importlib.import_module("ui.icon_manager")
            imported_AppIcon = getattr(ui_icon_manager, "AppIcon", None)
            imported_get_app_icon = getattr(ui_icon_manager, "get_app_icon", None)
            if imported_AppIcon is not None:
                AppIcon = imported_AppIcon
            if imported_get_app_icon is not None:
                get_app_icon = imported_get_app_icon
        except (ImportError, AttributeError):

            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "ui.icon_manager", icon_manager_path
                )
                if spec and spec.loader:
                    icon_manager_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(icon_manager_module)
                    imported_AppIcon = getattr(icon_manager_module, "AppIcon", None)
                    imported_get_app_icon = getattr(
                        icon_manager_module, "get_app_icon", None
                    )
                    if imported_AppIcon is not None:
                        AppIcon = imported_AppIcon
                    if imported_get_app_icon is not None:
                        get_app_icon = imported_get_app_icon
            except Exception:
                pass
except Exception:

    pass
