from enum import Enum
from pathlib import Path

from PySide6.QtGui import QIcon

from events.drag_drop_handler import DragAndDropService
import resources.translations  # noqa: F401  — triggers i18n_root configuration
from shared_toolkit.ui.gesture_resolver import RatingGestureTransaction
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.icons import configure_icon_resolver, get_icon_service
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    LabelVariantSpec,
    register_label_variant,
)

register_label_variant(
    LabelVariantSpec("group-title", pixel_size=14, bold=False, color_token="dialog.text", elide=True)
)

class AppIcon(Enum):
    """Host/app-shell icons — tab UI icons live under ``tabs/<name>/icons.py``."""

    SETTINGS = "settings.svg"
    HELP = "help.svg"
    TEXT_MANIPULATOR = "text-manipulator.svg"
    PLAY = "play.svg"
    HIGHLIGHT_DIFFERENCES = "highlight_diff_icon.svg"
    ADD = "add.svg"
    ADD_CIRCLE = "add_circle.svg"
    REMOVE = "remove.svg"
    CLOSE = "close.svg"
    CHECK = "check.svg"
    ENTER = "enter.svg"
    MINIMIZE = "window_minimize.svg"
    MAXIMIZE = "window_maximize.svg"
    RESTORE = "window_restore.svg"
    WINDOW_CLOSE = "window_close.svg"
    SYNC = "sync.svg"
    LINK = "link.svg"
    UNLINK = "unlink.svg"

def get_app_icon(icon: AppIcon | str) -> QIcon:
    if isinstance(icon, Enum):
        enum_module = getattr(type(icon), "__module__", "")
        if enum_module.startswith("tabs.") and enum_module.endswith(".icons"):
            import importlib

            mod = importlib.import_module(enum_module)
            getter = getattr(mod, "get_icon", None)
            if getter is not None:
                return getter(icon)

    project_root = Path(__file__).resolve().parents[1]
    service = get_icon_service("Improve-ImgSLI", project_root=str(project_root))
    if isinstance(icon, AppIcon):
        return service.get_icon(icon.value)
    if isinstance(icon, str):
        return service.get_icon(icon)
    value = getattr(icon, "value", None)
    if isinstance(value, str):
        return service.get_icon(value)
    return QIcon()

configure_icon_resolver(
    get_app_icon,
    named_icons={
        "add": AppIcon.ADD,
        "add_circle": AppIcon.ADD_CIRCLE,
        "remove": AppIcon.REMOVE,
        "check": AppIcon.CHECK,
        "enter": AppIcon.ENTER,
    },
)

configure_toolkit(
    timings=FlyoutTimingConfig(
        transient_auto_hide_delay_ms=300,
        flyout_animation_duration_ms=80,
        text_settings_flyout_animation_duration_ms=80,
    ),
    overlay_resolver=get_overlay_layer,
    rating_gesture_factory=lambda **kwargs: RatingGestureTransaction(**kwargs),
    dragdrop_service_getter=DragAndDropService.get_instance,
)
