"""Interface settings page — UI mode, font, max name length."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.widgets import ComboBox, CustomGroupWidget, RadioButton, SpinBox
from ui.icon_manager import AppIcon

from plugins.settings.registry import SettingsSection


def build(dialog, p):
    dialog.page_interface, layout = dialog._create_scrollable_page()
    dialog.ui_mode_group = CustomGroupWidget(dialog.tr("settings.ui_mode", dialog.current_language))
    row = QHBoxLayout()
    row.setContentsMargins(5, 5, 5, 5)
    dialog.radio_ui_mode_beginner = RadioButton(
        dialog.tr("settings.ui_mode_beginner", dialog.current_language)
    )
    dialog.radio_ui_mode_advanced = RadioButton(
        dialog.tr("settings.ui_mode_advanced", dialog.current_language)
    )
    dialog.radio_ui_mode_expert = RadioButton(
        dialog.tr("settings.ui_mode_expert", dialog.current_language)
    )
    dialog._ui_mode_group = QButtonGroup(dialog)
    for rb in (dialog.radio_ui_mode_beginner, dialog.radio_ui_mode_advanced, dialog.radio_ui_mode_expert):
        dialog._ui_mode_group.addButton(rb)
        row.addWidget(rb)
    dialog.ui_mode_group.add_layout(row)
    layout.addWidget(dialog.ui_mode_group)
    {"expert": dialog.radio_ui_mode_expert, "advanced": dialog.radio_ui_mode_advanced}.get(
        p.current_ui_mode, dialog.radio_ui_mode_beginner
    ).setChecked(True)

    dialog.font_group = CustomGroupWidget(dialog.tr("settings.ui_font", dialog.current_language))
    font_radio_layout = QVBoxLayout()
    font_radio_layout.setContentsMargins(5, 5, 5, 5)
    dialog.radio_font_builtin = RadioButton(dialog.tr("settings.builtin_font", dialog.current_language))
    dialog.radio_font_system_default = RadioButton(
        dialog.tr("settings.system_default", dialog.current_language)
    )
    dialog.radio_font_system_custom = RadioButton(dialog.tr("settings.custom", dialog.current_language))
    for rb in (dialog.radio_font_builtin, dialog.radio_font_system_default, dialog.radio_font_system_custom):
        font_radio_layout.addWidget(rb)
    dialog.font_group.add_layout(font_radio_layout)

    dialog.combo_font_family = ComboBox()
    dialog.combo_font_family.setFixedWidth(320)
    dialog.combo_font_family.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    from PySide6.QtGui import QFontDatabase

    for fam in QFontDatabase.families():
        dialog.combo_font_family.addItem(fam, fam)
    font_combo_container = QWidget()
    fc_layout = QHBoxLayout(font_combo_container)
    fc_layout.setContentsMargins(5, 0, 5, 5)
    fc_layout.addWidget(dialog.combo_font_family)
    fc_layout.addStretch()
    dialog.font_group.add_widget(font_combo_container)
    layout.addWidget(dialog.font_group)

    mode = p.current_ui_font_mode or "builtin"
    {
        "system_default": dialog.radio_font_system_default,
        "system": dialog.radio_font_system_default,
        "system_custom": dialog.radio_font_system_custom,
    }.get(mode, dialog.radio_font_builtin).setChecked(True)
    idx_fam = dialog.combo_font_family.findData(p.current_ui_font_family or "")
    if idx_fam != -1:
        dialog.combo_font_family.setCurrentIndex(idx_fam)

    def sync_font_ui():
        is_custom = dialog.radio_font_system_custom.isChecked()
        scroll_area = dialog._page_scroll_area(dialog.page_interface)
        if scroll_area is not None:
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font_combo_container.setVisible(is_custom)
        font_combo_container.adjustSize()
        dialog.font_group.adjustSize()
        dialog._calculate_and_apply_geometry()
        if scroll_area is not None:
            QTimer.singleShot(
                0,
                lambda: scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded),
            )

    for rb in (dialog.radio_font_system_custom, dialog.radio_font_builtin, dialog.radio_font_system_default):
        rb.toggled.connect(sync_font_ui)
    sync_font_ui()

    dialog.other_ui_group = CustomGroupWidget(
        dialog.tr("settings.maximum_name_length_ui", dialog.current_language)
    )
    len_layout = QHBoxLayout()
    len_layout.setContentsMargins(12, 5, 12, 5)
    value = max(p.min_limit, min(p.max_limit, p.current_max_length))
    dialog.spin_max_length = SpinBox(default_value=value)
    dialog.spin_max_length.setRange(p.min_limit, p.max_limit)
    dialog.spin_max_length.setValue(value)
    dialog.spin_max_length.setFixedWidth(100)
    dialog.spin_max_length.setAlignment(Qt.AlignmentFlag.AlignCenter)
    len_layout.addWidget(dialog.spin_max_length)
    len_layout.addStretch()
    dialog.other_ui_group.add_layout(len_layout)
    layout.addWidget(dialog.other_ui_group)
    dialog.pages_stack.addWidget(dialog.page_interface)


SECTION = SettingsSection(
    section_id="builtin.interface",
    title_key="settings.appearance",
    icon=AppIcon.TEXT_MANIPULATOR,
    build=build,
    owner_tab=None,
    order=20,
)
