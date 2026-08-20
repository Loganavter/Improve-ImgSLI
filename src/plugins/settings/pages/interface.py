"""Interface settings page — UI mode, font, max name length."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from sli_ui_toolkit.widgets import ComboBox, RadioButton, RadioButtonGroup, SpinBox
from sli_ui_toolkit.managers import scaled_px
from ui.icon_manager import AppIcon
from ui.widgets.slider_hint import ValueSlider, ValueSliderRow

from plugins.settings.nav_rows import page_nav_builder, register_page_navigation
from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group

UI_MODE = group(
    "settings.ui_mode",
    "settings.ui_mode_beginner",
    "settings.ui_mode_advanced",
    "settings.ui_mode_expert",
)
UI_FONT = group(
    "settings.ui_font",
    "settings.builtin_font",
    "settings.system_default",
    "settings.custom",
)
UI_SCALE = group("settings.ui_scale")
MAX_NAME = group("settings.maximum_name_length_ui")
SEARCH = SearchIndex.of(UI_MODE, UI_FONT, UI_SCALE, MAX_NAME)


def build(dialog, p):
    dialog.page_interface, layout = dialog._create_scrollable_page()
    builder = page_nav_builder(dialog, tag="settings-interface")
    dialog.ui_mode_group = UI_MODE.widget(dialog)
    row = QHBoxLayout()
    row.setContentsMargins(scaled_px(5), scaled_px(5), scaled_px(5), scaled_px(5))
    dialog.radio_ui_mode_beginner = RadioButton(
        UI_MODE.text(dialog, "settings.ui_mode_beginner")
    )
    dialog.radio_ui_mode_advanced = RadioButton(
        UI_MODE.text(dialog, "settings.ui_mode_advanced")
    )
    dialog.radio_ui_mode_expert = RadioButton(
        UI_MODE.text(dialog, "settings.ui_mode_expert")
    )
    UI_MODE.tag_member(dialog.radio_ui_mode_beginner, "settings.ui_mode_beginner")
    UI_MODE.tag_member(dialog.radio_ui_mode_advanced, "settings.ui_mode_advanced")
    UI_MODE.tag_member(dialog.radio_ui_mode_expert, "settings.ui_mode_expert")
    dialog._ui_mode_group = RadioButtonGroup()
    for rb in (dialog.radio_ui_mode_beginner, dialog.radio_ui_mode_advanced, dialog.radio_ui_mode_expert):
        dialog._ui_mode_group.addButton(rb)
        row.addWidget(rb)
    ui_mode_row = builder.row(row)
    dialog.ui_mode_group.add_widget(ui_mode_row)
    layout.addWidget(dialog.ui_mode_group)
    {"expert": dialog.radio_ui_mode_expert, "advanced": dialog.radio_ui_mode_advanced}.get(
        p.current_ui_mode, dialog.radio_ui_mode_beginner
    ).setChecked(True)

    dialog.font_group = UI_FONT.widget(dialog)
    dialog.radio_font_builtin = RadioButton(
        UI_FONT.text(dialog, "settings.builtin_font")
    )
    dialog.radio_font_system_default = RadioButton(
        UI_FONT.text(dialog, "settings.system_default")
    )
    dialog.radio_font_system_custom = RadioButton(
        UI_FONT.text(dialog, "settings.custom")
    )
    UI_FONT.tag_member(dialog.radio_font_builtin, "settings.builtin_font")
    UI_FONT.tag_member(dialog.radio_font_system_default, "settings.system_default")
    UI_FONT.tag_member(dialog.radio_font_system_custom, "settings.custom")
    font_radios = (
        dialog.radio_font_builtin,
        dialog.radio_font_system_default,
        dialog.radio_font_system_custom,
    )
    # Previously exclusive "for free" via QRadioButton's autoExclusive
    # (Qt radios sharing one parent widget are mutually exclusive with no
    # QButtonGroup at all) -- Button-based RadioButton has no such native
    # behavior, so this group is now required explicitly.
    dialog._font_group_buttons = RadioButtonGroup()
    for rb in font_radios:
        dialog._font_group_buttons.addButton(rb)
    # Stacked vertically (unlike ui_mode_row's side-by-side radios above), so
    # each radio is its own nav row -- one shared row would let Left/Right
    # jump between them purely by x-coordinate, which is meaningless here.
    # One row widget per radio (not one shared font_radio_layout) so
    # builder.row()'s reparenting can't fight a layout membership -- margins
    # match the QVBoxLayout this replaces (scaled_px(5) each side).
    # Vertical margins stay 0 -- CustomGroupWidget's own 8px inter-row
    # spacing is what used to separate these 3 radios inside the single
    # font_radio_layout, so duplicating a 5px top+bottom margin on every
    # row here would nearly double the gap between them.
    for rb in font_radios:
        row_widget = builder.row(rb)
        row_widget.layout().setContentsMargins(scaled_px(5), 0, scaled_px(5), 0)
        dialog.font_group.add_widget(row_widget)

    dialog.combo_font_family = ComboBox()
    UI_FONT.tag_combo(dialog.combo_font_family, "settings.custom")
    dialog.combo_font_family.setFixedWidth(scaled_px(320))
    dialog.combo_font_family.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    from PySide6.QtGui import QFontDatabase

    for fam in QFontDatabase.families():
        dialog.combo_font_family.addItem(fam, fam)
    font_combo_container = QWidget()
    fc_layout = QHBoxLayout(font_combo_container)
    fc_layout.setContentsMargins(scaled_px(5), 0, scaled_px(5), scaled_px(5))
    fc_layout.addWidget(dialog.combo_font_family)
    fc_layout.addStretch()
    dialog.font_group.add_widget(font_combo_container)
    # Already a real QWidget with its own layout -- builder.row() only
    # matters for wrapping a bare control/layout, so this goes straight
    # through extend() instead (still keeps it in the accumulated row
    # order, unlike the old hand-assembled list this used to require).
    builder.extend([font_combo_container])
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

    dialog.other_ui_group = MAX_NAME.widget(dialog)
    len_layout = QHBoxLayout()
    len_layout.setContentsMargins(scaled_px(12), scaled_px(5), scaled_px(12), scaled_px(5))
    value = max(p.min_limit, min(p.max_limit, p.current_max_length))
    dialog.spin_max_length = SpinBox(default_value=value)
    MAX_NAME.tag_member(dialog.spin_max_length, "settings.maximum_name_length_ui")
    dialog.spin_max_length.setRange(p.min_limit, p.max_limit)
    dialog.spin_max_length.setValue(value)
    dialog.spin_max_length.setFixedWidth(scaled_px(100))
    dialog.spin_max_length.setAlignment(Qt.AlignmentFlag.AlignCenter)
    len_layout.addWidget(dialog.spin_max_length)
    len_layout.addStretch()
    len_row = builder.row(len_layout)
    dialog.other_ui_group.add_widget(len_row)
    layout.addWidget(dialog.other_ui_group)

    dialog.ui_scale_group = UI_SCALE.widget(dialog)
    scale_layout = QHBoxLayout()
    scale_layout.setContentsMargins(scaled_px(12), scaled_px(5), scaled_px(12), scaled_px(5))
    # Free (continuous) slider: value = factor * 100 (range 50..250 →
    # 0.50..2.50, matching UiScale's clamp; any step of 0.01 is available).
    dialog.slider_ui_scale = ValueSlider(
        # Show the actual factor ("1.25"), not the raw 50..250 step index.
        hint_formatter=lambda s: f"{s.value() / 100:.2f}",
    )
    UI_SCALE.tag_member(dialog.slider_ui_scale, "settings.ui_scale")
    dialog.slider_ui_scale.setToolTip(UI_SCALE.text(dialog, "settings.ui_scale_tooltip"))
    dialog.slider_ui_scale.setRange(50, 250)
    dialog.slider_ui_scale.setValue(int(round(float(p.current_ui_scale_factor) * 100)))
    dialog.slider_ui_scale.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    # Persistent value readout on the right of the track; ValueSliderRow
    # disables the hover hint flyout in favor of this always-visible label
    # (fixed-width pad keeps the slider's geometry stable as text changes).
    dialog.slider_ui_scale_row = ValueSliderRow(dialog.slider_ui_scale)
    scale_layout.addWidget(dialog.slider_ui_scale_row, 1)
    scale_row = as_nav_row(scale_layout)
    dialog.ui_scale_group.add_widget(scale_row)
    layout.addWidget(dialog.ui_scale_group)

    register_page_nav_rows(
        dialog,
        dialog.page_interface,
        [ui_mode_row, *font_radio_rows, font_combo_container, len_row, scale_row],
        tag="settings-interface",
    )
    dialog.pages_stack.addWidget(dialog.page_interface)


SECTION = SettingsSection(
    section_id="builtin.interface",
    title_key="settings.appearance",
    icon=AppIcon.TEXT_MANIPULATOR,
    build=build,
    owner_tab=None,
    order=20,
    action_description_key="action.settings.appearance_desc",
    search=SEARCH,
)