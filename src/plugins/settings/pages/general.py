"""General settings page — language + appearance basics."""

from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel

from sli_ui_toolkit.widgets import CheckBox, ComboBox, CustomGroupWidget, RadioButton
from ui.icon_manager import AppIcon

from plugins.settings.registry import SettingsSection


def build(dialog, p):
    dialog.page_general, layout = dialog._create_scrollable_page()

    dialog.lang_group = CustomGroupWidget(dialog.tr("label.language", dialog.current_language))
    lang_layout = QHBoxLayout()
    lang_layout.setContentsMargins(5, 5, 5, 5)
    dialog.radio_en = RadioButton("English")
    dialog.radio_ru = RadioButton("Русский")
    dialog.radio_zh = RadioButton("中文")
    dialog.radio_pt_br = RadioButton("Português")
    dialog._lang_group = QButtonGroup(dialog)
    for rb in (dialog.radio_en, dialog.radio_ru, dialog.radio_zh, dialog.radio_pt_br):
        dialog._lang_group.addButton(rb)
        lang_layout.addWidget(rb)
    dialog.lang_group.add_layout(lang_layout)
    layout.addWidget(dialog.lang_group)
    {"ru": dialog.radio_ru, "zh": dialog.radio_zh, "pt_BR": dialog.radio_pt_br}.get(
        p.current_language, dialog.radio_en
    ).setChecked(True)

    dialog.sys_group = CustomGroupWidget(dialog.tr("settings.appearance", dialog.current_language))
    theme_row = QHBoxLayout()
    theme_row.setContentsMargins(5, 5, 5, 5)
    dialog.theme_label = QLabel(dialog.tr("label.theme", dialog.current_language) + ":")
    dialog.combo_theme = ComboBox()
    dialog.combo_theme.setFixedWidth(140)
    for key in ("auto", "light", "dark"):
        dialog.combo_theme.addItem(dialog.tr(f"settings.{key}", dialog.current_language), key)
    idx = dialog.combo_theme.findData(p.current_theme)
    if idx != -1:
        dialog.combo_theme.setCurrentIndex(idx)
    theme_row.addWidget(dialog.theme_label)
    theme_row.addWidget(dialog.combo_theme)
    theme_row.addStretch()
    dialog.sys_group.add_layout(theme_row)

    dialog.system_notifications_checkbox = CheckBox(
        dialog.tr("settings.system_notifications", dialog.current_language)
    )
    dialog.system_notifications_checkbox.setChecked(p.system_notifications_enabled)
    dialog.sys_group.add_widget(dialog.system_notifications_checkbox)
    dialog.debug_checkbox = CheckBox(
        dialog.tr("settings.enable_debug_logging", dialog.current_language)
    )
    dialog.debug_checkbox.setChecked(p.debug_mode_enabled)
    dialog.sys_group.add_widget(dialog.debug_checkbox)
    dialog.show_workspace_tabs_checkbox = CheckBox(
        dialog.tr("settings.show_workspace_tabs", dialog.current_language)
    )
    dialog.show_workspace_tabs_checkbox.setChecked(
        getattr(p.store.settings, "show_workspace_tabs", True) if p.store else True
    )
    dialog.sys_group.add_widget(dialog.show_workspace_tabs_checkbox)

    dialog.use_custom_decorations_checkbox = CheckBox(
        dialog.tr("settings.use_custom_decorations", dialog.current_language)
    )
    dialog.use_custom_decorations_checkbox.setChecked(
        getattr(p.store.settings, "use_custom_decorations", True) if p.store else True
    )
    dialog.use_custom_decorations_checkbox.setToolTip(
        dialog.tr("settings.use_custom_decorations_tooltip", dialog.current_language)
    )
    dialog.sys_group.add_widget(dialog.use_custom_decorations_checkbox)

    layout.addWidget(dialog.sys_group)
    dialog.pages_stack.addWidget(dialog.page_general)


SECTION = SettingsSection(
    section_id="builtin.general",
    title_key="settings.general",
    icon=AppIcon.SETTINGS,
    build=build,
    owner_tab=None,
    order=10,
)
