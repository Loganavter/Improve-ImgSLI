"""General settings page — language + appearance basics."""

from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel

from sli_ui_toolkit.widgets import CheckBox, ComboBox, RadioButton
from ui.icon_manager import AppIcon

from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group

LANGUAGE = group(
    "label.language",
    "settings.language_en",
    "settings.language_ru",
    "settings.language_zh",
    "settings.language_pt_br",
)
APPEARANCE = group(
    "settings.appearance",
    "label.theme",
    "settings.auto",
    "settings.light",
    "settings.dark",
    "settings.system_notifications",
    "settings.enable_debug_logging",
)
SEARCH = SearchIndex.of(LANGUAGE, APPEARANCE)


def build(dialog, p):
    dialog.page_general, layout = dialog._create_scrollable_page()

    dialog.lang_group = LANGUAGE.widget(dialog)
    lang_layout = QHBoxLayout()
    lang_layout.setContentsMargins(5, 5, 5, 5)
    dialog.radio_en = RadioButton(LANGUAGE.text(dialog, "settings.language_en"))
    dialog.radio_ru = RadioButton(LANGUAGE.text(dialog, "settings.language_ru"))
    dialog.radio_zh = RadioButton(LANGUAGE.text(dialog, "settings.language_zh"))
    dialog.radio_pt_br = RadioButton(LANGUAGE.text(dialog, "settings.language_pt_br"))
    LANGUAGE.tag_member(dialog.radio_en, "settings.language_en")
    LANGUAGE.tag_member(dialog.radio_ru, "settings.language_ru")
    LANGUAGE.tag_member(dialog.radio_zh, "settings.language_zh")
    LANGUAGE.tag_member(dialog.radio_pt_br, "settings.language_pt_br")
    dialog._lang_group = QButtonGroup(dialog)
    for rb in (dialog.radio_en, dialog.radio_ru, dialog.radio_zh, dialog.radio_pt_br):
        dialog._lang_group.addButton(rb)
        lang_layout.addWidget(rb)
    dialog.lang_group.add_layout(lang_layout)
    layout.addWidget(dialog.lang_group)
    {"ru": dialog.radio_ru, "zh": dialog.radio_zh, "pt_BR": dialog.radio_pt_br}.get(
        p.current_language, dialog.radio_en
    ).setChecked(True)

    dialog.sys_group = APPEARANCE.widget(dialog)
    theme_row = QHBoxLayout()
    theme_row.setContentsMargins(5, 5, 5, 5)
    dialog.theme_label = QLabel(APPEARANCE.text(dialog, "label.theme") + ":")
    dialog.combo_theme = ComboBox()
    APPEARANCE.tag_combo(dialog.combo_theme, "label.theme")
    dialog.combo_theme.setFixedWidth(140)
    for key in ("auto", "light", "dark"):
        dialog.combo_theme.addItem(
            APPEARANCE.text(dialog, f"settings.{key}"), key
        )
        APPEARANCE.note_combo_option(dialog.combo_theme, f"settings.{key}")
    idx = dialog.combo_theme.findData(p.current_theme)
    if idx != -1:
        dialog.combo_theme.setCurrentIndex(idx)
    theme_row.addWidget(dialog.theme_label)
    theme_row.addWidget(dialog.combo_theme)
    theme_row.addStretch()
    dialog.sys_group.add_layout(theme_row)

    dialog.system_notifications_checkbox = CheckBox(
        APPEARANCE.text(dialog, "settings.system_notifications")
    )
    dialog.system_notifications_checkbox.setChecked(p.system_notifications_enabled)
    APPEARANCE.tag_member(
        dialog.system_notifications_checkbox, "settings.system_notifications"
    )
    dialog.sys_group.add_widget(dialog.system_notifications_checkbox)
    dialog.debug_checkbox = CheckBox(
        APPEARANCE.text(dialog, "settings.enable_debug_logging")
    )
    dialog.debug_checkbox.setChecked(p.debug_mode_enabled)
    APPEARANCE.tag_member(dialog.debug_checkbox, "settings.enable_debug_logging")
    dialog.sys_group.add_widget(dialog.debug_checkbox)

    layout.addWidget(dialog.sys_group)
    dialog.pages_stack.addWidget(dialog.page_general)


SECTION = SettingsSection(
    section_id="builtin.general",
    title_key="settings.general",
    icon=AppIcon.SETTINGS,
    build=build,
    owner_tab=None,
    order=10,
    action_description_key="action.settings.general_desc",
    search=SEARCH,
)
