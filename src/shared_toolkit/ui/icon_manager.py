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

def _load_project_icon_manager():
    try:
        import importlib

        return importlib.import_module("ui.icon_manager")
    except Exception:
        pass

    try:
        import importlib.util
        import sys
        from pathlib import Path

        current_file = Path(__file__).resolve()
        src_path = current_file.parent.parent.parent
        icon_manager_path = src_path / "ui" / "icon_manager.py"
        if not icon_manager_path.exists():
            return None

        src_path_str = str(src_path)
        if src_path_str not in sys.path:
            sys.path.insert(0, src_path_str)

        spec = importlib.util.spec_from_file_location("ui.icon_manager", icon_manager_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception:
        return None

    return None

icon_manager_module = _load_project_icon_manager()
if icon_manager_module is not None:
    imported_app_icon = getattr(icon_manager_module, "AppIcon", None)
    imported_get_app_icon = getattr(icon_manager_module, "get_app_icon", None)
    if imported_app_icon is not None:
        AppIcon = imported_app_icon
    if imported_get_app_icon is not None:
        get_app_icon = imported_get_app_icon
