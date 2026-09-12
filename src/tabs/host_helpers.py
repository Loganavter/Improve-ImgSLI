"""Platform-facing helpers exposed to tabs.

This module is the official seam through which tab code can access generic
host-side utilities (dialog decoration, app-wide styling hooks, etc.) without
importing platform-private modules (``shared_toolkit``, ``resources.*``,
``ui.*``). The tab-isolation contract test allows tabs to import from
``tabs.*``, so re-exporting these helpers here keeps the dependency direction
correct: tab → tabs.host_helpers → platform.

Only generic, tab-agnostic helpers belong here. Anything specific to a single
tab must live inside that tab's own package.
"""

from __future__ import annotations

from shared_toolkit.ui.decorate_dialog import decorate_dialog, install_dialog_help_menu
from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    HorizontalPaneMinimum,
    apply_dialog_geometry,
    clamp,
    handle_application_font_change,
    tab_widget_intrinsic_width,
    widget_width_hint,
)
from shared_toolkit.ui.message_dialog import MessageKind
from shared_toolkit.ui.mode_picker import ModePicker
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from shared_toolkit.ui.text_input_dialog import AppTextInputDialog
from shared_toolkit.ui.themed_dialog import ThemedDialog


__all__ = [
    "AppTextInputDialog",
    "GeometryApplyPolicy",
    "HorizontalPaneMinimum",
    "MessageKind",
    "ModePicker",
    "ThemedDialog",
    "apply_dialog_geometry",
    "clamp",
    "decorate_dialog",
    "get_overlay_layer",
    "handle_application_font_change",
    "install_dialog_help_menu",
    "tab_widget_intrinsic_width",
    "widget_width_hint",
]
