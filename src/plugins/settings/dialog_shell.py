from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QScrollArea, QSizePolicy

from shared_toolkit.ui.widgets.composite import (
    DialogActionBar,
    ScrollableDialogPage,
    SidebarDialogShell,
)
from ui.icon_manager import AppIcon

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
    dialog.ok_button.clicked.connect(dialog.accept)
    dialog.cancel_button.clicked.connect(dialog.reject)
    dialog.content_layout.addWidget(dialog.action_bar)

def setup_sidebar_items(dialog):
    dialog._sidebar_items_data = [
        (dialog.tr("settings.appearance", dialog.current_language), AppIcon.SETTINGS),
        (dialog.tr("label.view", dialog.current_language), AppIcon.TEXT_MANIPULATOR),
        (dialog.tr("settings.optimization", dialog.current_language), AppIcon.PLAY),
        (
            dialog.tr("label.details", dialog.current_language),
            AppIcon.HIGHLIGHT_DIFFERENCES,
        ),
    ]
    dialog.sidebar.set_nav_items(dialog._sidebar_items_data)

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
    dialog.theme_manager.apply_theme_to_dialog(dialog)
    dialog._update_sidebar_icons()

def defer_geometry(dialog):
    QTimer.singleShot(0, dialog._calculate_and_apply_geometry)

def calculate_and_apply_geometry(dialog):
    dialog.ensurePolished()
    sidebar_width = dialog.sidebar.width()
    content_margins = dialog.content_layout.contentsMargins()
    total_width_margins = content_margins.left() + content_margins.right() + 40

    max_group_width = 0
    max_content_height = 0
    for i in range(dialog.pages_stack.count()):
        page_wrapper = dialog.pages_stack.widget(i)
        scroll_area = page_wrapper.findChild(QScrollArea)
        if scroll_area:
            content_widget = scroll_area.widget()
            content_widget.ensurePolished()
            content_widget.adjustSize()

            groups = content_widget.findChildren(dialog._custom_group_widget_cls)
            if groups:
                for group in groups:
                    max_group_width = max(max_group_width, group.sizeHint().width())
            else:
                max_group_width = max(max_group_width, content_widget.sizeHint().width())
            max_content_height = max(max_content_height, content_widget.sizeHint().height())

    required_width = sidebar_width + max_group_width + total_width_margins
    final_width = max(800, min(required_width, 1200))
    bottom_controls_height = 80
    sidebar_req_height = dialog.sidebar.count() * 45 + 40
    required_height = max(sidebar_req_height, max_content_height + bottom_controls_height)
    screen_h = QApplication.primaryScreen().availableGeometry().height()
    final_height = min(required_height, screen_h - 100) + 5

    dialog.resize(final_width, final_height)
    dialog.setMinimumSize(final_width, final_height)
    if dialog.parent():
        geo = dialog.geometry()
        geo.moveCenter(dialog.parent().geometry().center())
        dialog.move(geo.topLeft())
