from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QSizePolicy

from plugins.settings.layout_geometry import apply_settings_dialog_geometry
from shared_toolkit.ui.layout_sizing import defer_dialog_geometry
from sli_ui_toolkit.widgets import (
    ScrollableDialogPage,
    SidebarDialogShell,
)
from ui.icon_manager import AppIcon
from ui.theming import polish_themed_dialog
from ui.widgets.form_controls import DialogActionBar

def setup_dialog_shell(dialog):
    dialog.main_layout.setContentsMargins(0, 0, 0, 0)
    dialog.main_layout.setSpacing(0)

    dialog.shell = SidebarDialogShell()
    dialog.main_layout.addWidget(dialog.shell)

    dialog.sidebar = dialog.shell.sidebar
    dialog.sidebar.setObjectName("SettingsSidebar")
    dialog.sidebar.currentRowChanged.connect(dialog._on_category_changed)

    dialog.content_area = dialog.shell.content_area
    dialog.content_area.setObjectName("SettingsContentArea")
    dialog.content_layout = dialog.shell.content_layout
    dialog.pages_stack = dialog.shell.pages_stack

    dialog.action_bar = DialogActionBar(
        dialog.tr("common.ok", dialog.current_language),
        dialog.tr("common.cancel", dialog.current_language),
    )
    dialog.ok_button = dialog.action_bar.primary_button
    dialog.cancel_button = dialog.action_bar.secondary_button
    dialog.ok_button.clicked.connect(dialog.confirm_settings)
    dialog.cancel_button.clicked.connect(dialog.reject)
    dialog.content_layout.addWidget(dialog.action_bar)

def setup_sidebar_items(dialog):
    sections = getattr(dialog, "_active_sections", None)
    if sections:
        dialog._sidebar_items_data = [
            (dialog.tr(s.title_key, dialog.current_language), s.icon)
            for s in sections
        ]
    else:
        dialog._sidebar_items_data = [
            (dialog.tr("settings.appearance", dialog.current_language), AppIcon.SETTINGS),
            (dialog.tr("label.view", dialog.current_language), AppIcon.TEXT_MANIPULATOR),
            (dialog.tr("settings.optimization", dialog.current_language), AppIcon.PLAY),
            (
                dialog.tr("label.details", dialog.current_language),
                AppIcon.HIGHLIGHT_DIFFERENCES,
            ),
        ]
    dialog.sidebar.set_items(dialog._sidebar_items_data)

def create_scrollable_page():
    page = ScrollableDialogPage()
    page.content_widget.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
    )
    return page, page.content_layout

def page_scroll_area(page):
    if page is None:
        return None
    return page.findChild(QScrollArea)

def apply_styles(dialog):
    polish_themed_dialog(dialog.theme_manager, dialog)
    dialog._update_sidebar_icons()

def defer_geometry(dialog):
    defer_dialog_geometry(dialog, dialog._calculate_and_apply_geometry)

def calculate_and_apply_geometry(dialog):
    apply_settings_dialog_geometry(dialog)
