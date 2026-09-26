"""General settings page — language + appearance basics."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import CheckBox, ComboBox, RadioButton, RadioButtonGroup
from plugins.settings.typography import apply_settings_body, settings_group
from ui.icon_manager import AppIcon

from plugins.settings.nav_rows import page_nav_builder, register_page_navigation
from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group

LANGUAGE = group(
    "label.language",
    "settings.language_en",
    "settings.language_ru",
    "settings.language_zh",
    "settings.language_pt_br",
    # Rows show native names (English/Русский/中文/Português) regardless of
    # UI language, so Find Action can't rely on i18n-key expansion here —
    # give each row its translated name in every supported UI language too
    # (e.g. ru query "английский" must still hit the English row).
    aliases={
        "settings.language_en": (
            "английский", "English", "英语", "inglês",
        ),
        "settings.language_ru": (
            "русский", "Russian", "俄语", "russo",
        ),
        "settings.language_zh": (
            "китайский", "Chinese", "中文", "chinês",
        ),
        "settings.language_pt_br": (
            "португальский", "Portuguese", "葡萄牙语", "português",
        ),
    },
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
    builder = page_nav_builder(dialog, tag="settings-general")

    dialog.lang_group = settings_group(dialog, LANGUAGE)
    lang_layout = QHBoxLayout()
    # Flush sides: the group contributes no horizontal insets, so the row
    # adds none either — radios align to the group edge.
    lang_layout.setContentsMargins(0, scaled_px(5), 0, scaled_px(5))
    dialog.radio_en = RadioButton(LANGUAGE.text(dialog, "settings.language_en"))
    dialog.radio_ru = RadioButton(LANGUAGE.text(dialog, "settings.language_ru"))
    dialog.radio_zh = RadioButton(LANGUAGE.text(dialog, "settings.language_zh"))
    dialog.radio_pt_br = RadioButton(LANGUAGE.text(dialog, "settings.language_pt_br"))
    for _rb in (dialog.radio_en, dialog.radio_ru, dialog.radio_zh, dialog.radio_pt_br):
        apply_settings_body(_rb)
    LANGUAGE.tag_member(dialog.radio_en, "settings.language_en")
    LANGUAGE.tag_member(dialog.radio_ru, "settings.language_ru")
    LANGUAGE.tag_member(dialog.radio_zh, "settings.language_zh")
    LANGUAGE.tag_member(dialog.radio_pt_br, "settings.language_pt_br")
    dialog._lang_group = RadioButtonGroup()
    for rb in (dialog.radio_en, dialog.radio_ru, dialog.radio_zh, dialog.radio_pt_br):
        dialog._lang_group.addButton(rb)
        lang_layout.addWidget(rb)
    lang_row = builder.row(lang_layout)
    dialog.lang_group.add_widget(lang_row)
    layout.addWidget(dialog.lang_group)
    {"ru": dialog.radio_ru, "zh": dialog.radio_zh, "pt_BR": dialog.radio_pt_br}.get(
        p.current_language, dialog.radio_en
    ).setChecked(True)

    dialog.sys_group = settings_group(dialog, APPEARANCE)
    theme_row = QHBoxLayout()
    theme_row.setContentsMargins(0, scaled_px(5), 0, scaled_px(5))
    dialog.combo_theme = ComboBox()
    apply_settings_body(dialog.combo_theme)
    APPEARANCE.tag_combo(dialog.combo_theme, "label.theme")
    dialog.combo_theme.setFixedWidth(scaled_px(140))
    for key in ("auto", "light", "dark"):
        dialog.combo_theme.addItem(
            APPEARANCE.text(dialog, f"settings.{key}"), key
        )
        APPEARANCE.note_combo_option(dialog.combo_theme, f"settings.{key}")
    idx = dialog.combo_theme.findData(p.current_theme)
    if idx != -1:
        dialog.combo_theme.setCurrentIndex(idx)
    theme_row.addWidget(dialog.combo_theme)
    theme_row.addStretch()
    theme_row_widget = builder.row(theme_row)
    dialog.sys_group.add_widget(theme_row_widget)

    dialog.system_notifications_checkbox = CheckBox(
        APPEARANCE.text(dialog, "settings.system_notifications")
    )
    apply_settings_body(dialog.system_notifications_checkbox)
    dialog.system_notifications_checkbox.setChecked(p.system_notifications_enabled)
    APPEARANCE.tag_member(
        dialog.system_notifications_checkbox, "settings.system_notifications"
    )
    notifications_row = builder.row(dialog.system_notifications_checkbox)
    dialog.sys_group.add_widget(notifications_row)
    dialog.debug_checkbox = CheckBox(
        APPEARANCE.text(dialog, "settings.enable_debug_logging")
    )
    apply_settings_body(dialog.debug_checkbox)
    dialog.debug_checkbox.setChecked(p.debug_mode_enabled)
    APPEARANCE.tag_member(dialog.debug_checkbox, "settings.enable_debug_logging")
    debug_row = builder.row(dialog.debug_checkbox)
    dialog.sys_group.add_widget(debug_row)

    layout.addWidget(dialog.sys_group)
    register_page_navigation(dialog, dialog.page_general, builder)
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