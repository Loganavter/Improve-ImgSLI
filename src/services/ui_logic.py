import importlib
import os
from qfluentwidgets import PushButton, CheckBox, Slider, BodyLabel, LineEdit, ComboBox, TransparentPushButton, FluentIcon, CaptionLabel
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize, QTimer
translations_mod = importlib.import_module('translations')
tr = getattr(translations_mod, 'tr', lambda text, lang='en', *args, **kwargs: text)
try:
    clickable_label_mod = importlib.import_module('clickable_label')
    ClickableLabel = getattr(clickable_label_mod, 'ClickableLabel', QLabel)
except ImportError:
    print("Warning: 'clickable_label.py' not found. Falling back to QLabel for image display.")
    ClickableLabel = QLabel
from services.state_manager import AppConstants
from PIL import Image

class UILogic:

    def __init__(self, app_instance, app_state):
        self.app = app_instance
        self.app_state = app_state
        self.app.resolution_label1 = CaptionLabel('--x--')
        self.app.resolution_label2 = CaptionLabel('--x--')
        self.app.magnifier_settings_panel = QWidget(self.app)
        self.app.image_label = ClickableLabel(self.app)
        self.app.length_warning_label = BodyLabel(self.app)
        self.app.btn_image1 = PushButton()
        self.app.btn_image2 = PushButton()
        self.app.btn_swap = TransparentPushButton()
        self.app.btn_clear_list1 = TransparentPushButton()
        self.app.btn_clear_list2 = TransparentPushButton()
        self.app.help_button = TransparentPushButton()
        self.app.btn_settings = TransparentPushButton()
        self.app.btn_color_picker = PushButton()
        self.app.btn_save = PushButton()
        self.app.combo_image1 = ComboBox()
        self.app.combo_image2 = ComboBox()
        self.app.combo_interpolation = ComboBox()
        self.app.checkbox_horizontal = CheckBox()
        self.app.checkbox_magnifier = CheckBox()
        self.app.freeze_button = CheckBox()
        self.app.checkbox_file_names = CheckBox()
        self.app.slider_size = Slider(Qt.Orientation.Horizontal)
        self.app.slider_capture = Slider(Qt.Orientation.Horizontal)
        self.app.slider_speed = Slider(Qt.Orientation.Horizontal)
        self.app.font_size_slider = Slider(Qt.Orientation.Horizontal)
        self.app.edit_name1 = LineEdit()
        self.app.edit_name2 = LineEdit()
        self.app.label_magnifier_size = BodyLabel()
        self.app.label_capture_size = BodyLabel()
        self.app.label_movement_speed = BodyLabel()
        self.app.label_interpolation = BodyLabel()
        self.app.file_name_label1 = CaptionLabel('--')
        self.app.file_name_label2 = CaptionLabel('--')
        self.app.label_edit_name1 = BodyLabel()
        self.app.label_edit_name2 = BodyLabel()
        self.app.label_edit_font_size = BodyLabel()
        self.app.drag_overlay1 = QLabel(self.app.image_label)
        self.app.drag_overlay2 = QLabel(self.app.image_label)

    def update_combobox_tooltip_on_selection(self, combobox, index):
        if index >= 0 and index < combobox.count():
            item_data = combobox.itemData(index)
            if isinstance(item_data, dict) and 'full_name' in item_data:
                combobox.setToolTip(item_data['full_name'])
            else:
                combobox.setToolTip('')
        else:
            combobox.setToolTip('')

    def build_all(self):
        self.app.setWindowTitle(tr('Improve ImgSLI', self.app_state.current_language))
        self.app.setAcceptDrops(True)
        self._configure_image_label()
        self._init_drag_overlays()
        self._init_warning_label()
        self._configure_resolution_labels()
        main_layout = QVBoxLayout(self.app)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        selection_layout = QVBoxLayout()
        selection_layout.setSpacing(3)
        selection_layout.addLayout(self._create_button_layout())
        selection_layout.addLayout(self._create_combobox_layout())
        main_layout.addLayout(selection_layout)
        main_layout.addLayout(self._create_checkbox_layout())
        self._create_slider_layout()
        main_layout.addWidget(self.app.magnifier_settings_panel)
        main_layout.addWidget(self.app.image_label)
        resolutions_and_filenames_group_layout = QVBoxLayout()
        resolutions_and_filenames_group_layout.setSpacing(0)
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(self.app.resolution_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        resolution_layout.addStretch()
        resolution_layout.addWidget(self.app.resolution_label2, alignment=Qt.AlignmentFlag.AlignRight)
        resolution_layout.setContentsMargins(5, 0, 5, 0)
        resolutions_and_filenames_group_layout.addLayout(resolution_layout)
        filenames_layout = self._create_file_names_layout()
        filenames_layout.setContentsMargins(5, 0, 5, 0)
        resolutions_and_filenames_group_layout.addLayout(filenames_layout)
        main_layout.addLayout(resolutions_and_filenames_group_layout)
        main_layout.addWidget(self.app.length_warning_label)
        self.app.edit_layout_widget = QWidget()
        self.app.edit_layout = self._create_edit_layout()
        self.app.edit_layout_widget.setLayout(self.app.edit_layout)
        main_layout.addWidget(self.app.edit_layout_widget)
        main_layout.addWidget(self._create_save_buttons_widget())
        self.app.setLayout(main_layout)

    def _create_button_layout(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self.app.btn_image1.setIcon(FluentIcon.PHOTO.icon())
        self.app.btn_image1.setMinimumWidth(120)
        self.app.btn_image2.setIcon(FluentIcon.PHOTO.icon())
        self.app.btn_image2.setMinimumWidth(120)
        self.app.btn_swap.setIcon(FluentIcon.SYNC.icon())
        self.app.btn_swap.setIconSize(QSize(24, 24))
        self.app.btn_swap.setFixedSize(36, 36)
        self.app.btn_swap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app.btn_swap.setStyleSheet('\n            TransparentPushButton {\n                padding: 6px;\n                qproperty-iconSize: 24px;\n            }\n        ')
        icon_size = QSize(22, 22)
        clear_button_size = QSize(36, 36)
        self.app.btn_clear_list1.setIcon(FluentIcon.DELETE.icon())
        self.app.btn_clear_list1.setIconSize(icon_size)
        self.app.btn_clear_list1.setFixedSize(clear_button_size)
        self.app.btn_clear_list1.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app.btn_clear_list1.setStyleSheet('\n            TransparentPushButton {\n                padding: 7px;\n                qproperty-iconSize: 22px;\n            }\n        ')
        self.app.btn_clear_list2.setIcon(FluentIcon.DELETE.icon())
        self.app.btn_clear_list2.setIconSize(icon_size)
        self.app.btn_clear_list2.setFixedSize(clear_button_size)
        self.app.btn_clear_list2.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app.btn_clear_list2.setStyleSheet('\n            TransparentPushButton {\n                padding: 7px;\n                qproperty-iconSize: 22px;\n            }\n        ')
        self.app.btn_image1.setText(tr('Add Image(s) 1', self.app_state.current_language))
        self.app.btn_image2.setText(tr('Add Image(s) 2', self.app_state.current_language))
        layout.addWidget(self.app.btn_image1)
        layout.addWidget(self.app.btn_clear_list1)
        layout.addWidget(self.app.btn_swap)
        layout.addWidget(self.app.btn_image2)
        layout.addWidget(self.app.btn_clear_list2)
        return layout

    def _create_combobox_layout(self):
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self.app.combo_image1.setToolTip(tr('Select image for left/top side', self.app_state.current_language))
        self.app.combo_image2.setToolTip(tr('Select image for right/bottom side', self.app_state.current_language))
        self.app.combo_image1.setMinimumHeight(28)
        self.app.combo_image2.setMinimumHeight(28)
        layout.addWidget(self.app.combo_image1)
        layout.addWidget(self.app.combo_image2)
        return layout

    def _create_checkbox_layout(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        checkbox_sub_layout = QHBoxLayout()
        checkbox_sub_layout.setSpacing(15)
        self.app.checkbox_horizontal.setText(tr('Horizontal Split', self.app_state.current_language))
        self.app.checkbox_magnifier.setText(tr('Use Magnifier', self.app_state.current_language))
        self.app.freeze_button.setText(tr('Freeze Magnifier', self.app_state.current_language))
        self.app.checkbox_file_names.setText(tr('Include file names in saved image', self.app_state.current_language))
        self.app.checkbox_horizontal.setMinimumWidth(130)
        self.app.checkbox_magnifier.setMinimumWidth(130)
        self.app.freeze_button.setMinimumWidth(130)
        self.app.checkbox_file_names.setMinimumWidth(250)
        checkbox_sub_layout.addWidget(self.app.checkbox_horizontal)
        checkbox_sub_layout.addWidget(self.app.checkbox_magnifier)
        checkbox_sub_layout.addWidget(self.app.freeze_button)
        checkbox_sub_layout.addWidget(self.app.checkbox_file_names)
        checkbox_sub_layout.addStretch(1)
        layout.addLayout(checkbox_sub_layout, 1)
        buttons_sub_layout = QHBoxLayout()
        buttons_sub_layout.setSpacing(8)
        self.app.btn_settings.setIcon(FluentIcon.SETTING.icon())
        self.app.btn_settings.setIconSize(QSize(24, 24))
        self.app.btn_settings.setFixedSize(36, 36)
        self.app.btn_settings.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app.btn_settings.setStyleSheet('\n            TransparentPushButton {\n                padding: 6px;\n                qproperty-iconSize: 24px;\n            }\n        ')
        self.app.help_button.setIcon(FluentIcon.HELP.icon())
        self.app.help_button.setIconSize(QSize(24, 24))
        self.app.help_button.setFixedSize(36, 36)
        self.app.help_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app.help_button.setStyleSheet('\n            TransparentPushButton {\n                padding: 6px;\n                qproperty-iconSize: 24px;\n            }\n        ')
        if not self.app.settings_dialog_available:
            self.app.btn_settings.setEnabled(False)
            self.app.btn_settings.setToolTip(self.app.tr('Settings dialog module not found.', self.app_state.current_language))
        buttons_sub_layout.addWidget(self.app.btn_settings)
        buttons_sub_layout.addWidget(self.app.help_button)
        layout.addLayout(buttons_sub_layout)
        return layout

    def _create_slider_layout(self):
        panel_layout = QVBoxLayout(self.app.magnifier_settings_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(5)
        sliders_main_layout = QHBoxLayout()
        sliders_main_layout.setSpacing(10)
        self.app.label_magnifier_size.setText(tr('Magnifier Size (%):', self.app_state.current_language))
        self.app.slider_size.setMinimum(5)
        self.app.slider_size.setMaximum(100)
        self.app.slider_size.setMinimumWidth(80)
        sliders_main_layout.addWidget(self.app.label_magnifier_size)
        sliders_main_layout.addWidget(self.app.slider_size, 1)
        sliders_main_layout.addSpacing(15)
        self.app.label_capture_size.setText(tr('Capture Size (%):', self.app_state.current_language))
        self.app.slider_capture.setMinimum(1)
        self.app.slider_capture.setMaximum(50)
        self.app.slider_capture.setMinimumWidth(80)
        sliders_main_layout.addWidget(self.app.label_capture_size)
        sliders_main_layout.addWidget(self.app.slider_capture, 1)
        sliders_main_layout.addSpacing(15)
        self.app.label_movement_speed.setText(tr('Move Speed:', self.app_state.current_language))
        self.app.slider_speed.setMinimum(1)
        self.app.slider_speed.setMaximum(50)
        self.app.slider_speed.setMinimumWidth(80)
        sliders_main_layout.addWidget(self.app.label_movement_speed)
        sliders_main_layout.addWidget(self.app.slider_speed, 1)
        panel_layout.addLayout(sliders_main_layout)
        interpolation_layout = QHBoxLayout()
        interpolation_layout.setSpacing(5)
        self.app.label_interpolation.setText(tr('Magnifier Interpolation:', self.app_state.current_language))
        self.app.combo_interpolation.blockSignals(True)
        self.app.combo_interpolation.clear()
        for i, (key_str, display_text_key) in enumerate(AppConstants.INTERPOLATION_METHODS_MAP.items()):
            if not hasattr(Image.Resampling, key_str):
                print(f"WARNING: PIL.Image.Resampling does not have method '{key_str}'. Skipping adding to ComboBox.")
                continue
            translated_display_text = tr(display_text_key, self.app_state.current_language)
            self.app.combo_interpolation.addItem(translated_display_text, userData=i)
            print(f"DEBUG: Added item '{translated_display_text}' with userData={i} for internal key '{key_str}'.")
        self.app.combo_interpolation.blockSignals(False)
        interpolation_layout.addWidget(self.app.label_interpolation)
        interpolation_layout.addWidget(self.app.combo_interpolation)
        interpolation_layout.addStretch()
        panel_layout.addLayout(interpolation_layout)
        return self.app.magnifier_settings_panel

    def _configure_image_label(self):
        self.app.image_label.setMinimumSize(200, 150)
        self.app.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.app.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app.image_label.setMouseTracking(True)
        self.app.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.app.image_label.setAutoFillBackground(True)

    def _create_file_names_layout(self):
        layout = QHBoxLayout()
        self.app.file_name_label1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.app.file_name_label2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.app.file_name_label1.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.app.file_name_label2.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.app.file_name_label1.setMinimumHeight(22)
        self.app.file_name_label2.setMinimumHeight(22)
        self.app.file_name_label1.setStyleSheet('color: #A0A0A0;')
        self.app.file_name_label2.setStyleSheet('color: #A0A0A0;')
        layout.addWidget(self.app.file_name_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(self.app.file_name_label2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setContentsMargins(5, 2, 5, 2)
        return layout

    def _create_edit_layout(self):
        edit_outer_layout = QHBoxLayout()
        edit_outer_layout.setSpacing(8)
        self.app.label_edit_name1.setText(tr('Name 1:', self.app_state.current_language))
        self.app.edit_name1.setPlaceholderText(tr('Edit Current Image 1 Name', self.app_state.current_language))
        self.app.edit_name1.setMinimumHeight(28)
        self.app.label_edit_name2.setText(tr('Name 2:', self.app_state.current_language))
        self.app.edit_name2.setPlaceholderText(tr('Edit Current Image 2 Name', self.app_state.current_language))
        self.app.edit_name2.setMinimumHeight(28)
        self.app.label_edit_font_size.setText(tr('Font Size (%):', self.app_state.current_language))
        self.app.font_size_slider.setMinimum(50)
        self.app.font_size_slider.setMaximum(200)
        self.app.font_size_slider.setValue(100)
        self.app.font_size_slider.setMinimumWidth(100)
        self.app.btn_color_picker.setIcon(FluentIcon.PALETTE.icon())
        self.app.btn_color_picker.setIconSize(QSize(24, 24))
        self.app.btn_color_picker.setFixedSize(36, 36)
        self.app.btn_color_picker.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app.btn_color_picker.setStyleSheet('\n            PushButton {\n                padding: 6px;\n                qproperty-iconSize: 24px;\n            }\n        ')
        edit_outer_layout.addWidget(self.app.label_edit_name1)
        edit_outer_layout.addWidget(self.app.edit_name1, 1)
        edit_outer_layout.addSpacing(5)
        edit_outer_layout.addWidget(self.app.label_edit_name2)
        edit_outer_layout.addWidget(self.app.edit_name2, 1)
        edit_outer_layout.addSpacing(10)
        edit_outer_layout.addWidget(self.app.label_edit_font_size)
        edit_outer_layout.addWidget(self.app.font_size_slider, 1)
        edit_outer_layout.addSpacing(5)
        edit_outer_layout.addWidget(self.app.btn_color_picker)
        self.toggle_edit_layout_visibility(False)
        return edit_outer_layout

    def _create_save_buttons_widget(self):
        save_layout = QHBoxLayout()
        save_layout.setSpacing(8)
        self.app.btn_save.setIcon(FluentIcon.SAVE.icon())
        self.app.btn_save.setText(tr('Save Result', self.app_state.current_language))
        self.app.btn_save.setMinimumHeight(32)
        self.app.btn_save.setMinimumWidth(120)
        save_layout.addWidget(self.app.btn_save)
        save_widget = QWidget()
        save_widget.setLayout(save_layout)
        return save_widget

    def _init_drag_overlays(self):
        style = 'background-color: rgba(0, 100, 200, 0.6); color: white; font-size: 20px; border-radius: 10px; padding: 15px; border: 1px solid rgba(255, 255, 255, 0.7);'
        self.app.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app.drag_overlay1.setStyleSheet(style)
        self.app.drag_overlay1.setWordWrap(True)
        self.app.drag_overlay1.hide()
        self.app.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app.drag_overlay2.setStyleSheet(style)
        self.app.drag_overlay2.setWordWrap(True)
        self.app.drag_overlay2.hide()

    def _update_drag_overlays(self, horizontal: bool=False):
        if not hasattr(self.app, 'drag_overlay1') or not hasattr(self.app, 'image_label') or (not self.app.image_label.isVisible()):
            return
        try:
            label_geom = self.app.image_label.geometry()
            margin = 10
            if not horizontal:
                half_width = label_geom.width() // 2
                overlay_w = max(1, half_width - margin - margin // 2)
                overlay_h = max(1, label_geom.height() - 2 * margin)
                self.app.drag_overlay1.setGeometry(margin, margin, overlay_w, overlay_h)
                self.app.drag_overlay2.setGeometry(half_width + margin // 2, margin, overlay_w, overlay_h)
            else:
                half_height = label_geom.height() // 2
                overlay_w = max(1, label_geom.width() - 2 * margin)
                overlay_h = max(1, half_height - margin - margin // 2)
                self.app.drag_overlay1.setGeometry(margin, margin, overlay_w, overlay_h)
                self.app.drag_overlay2.setGeometry(margin, half_height + margin // 2, overlay_w, overlay_h)
        except Exception as e:
            print(f'[DEBUG] Error updating drag overlays geometry in UILogic: {e}')

    def _init_warning_label(self):
        self.app.length_warning_label.setStyleSheet('color: #FF4500; font-weight: bold;')
        self.app.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app.length_warning_label.setVisible(False)

    def _configure_resolution_labels(self):
        pass

    def toggle_edit_layout_visibility(self, checked: bool):
        if not hasattr(self.app, 'edit_layout_widget'):
            return
        is_visible = bool(checked)
        self.app.edit_layout_widget.setVisible(is_visible)

    def _update_magnifier_controls_visibility(self, visible: bool):
        if hasattr(self.app, 'magnifier_settings_panel'):
            self.app.magnifier_settings_panel.setVisible(visible)
            print(f'DEBUG: Magnifier panel visibility set to {visible}')
        else:
            print('CRITICAL WARNING: magnifier_settings_panel not found during visibility update!')
            if hasattr(self.app, 'slider_size'):
                self.app.slider_size.setVisible(visible)
        if hasattr(self.app, 'freeze_button'):
            self.app.freeze_button.setEnabled(visible)

    def update_file_names(self):
        name1_from_edit = self.app.edit_name1.text().strip() if hasattr(self.app, 'edit_name1') else ''
        name2_from_edit = self.app.edit_name2.text().strip() if hasattr(self.app, 'edit_name2') else ''
        display_name1_for_label = name1_from_edit
        display_name2_for_label = name2_from_edit
        if not self.app_state.original_image1:
            display_name1_for_label = tr('Image 1', self.app_state.current_language)
        if not self.app_state.original_image2:
            display_name2_for_label = tr('Image 2', self.app_state.current_language)
        max_len_ui = self.app_state.max_name_length
        if hasattr(self.app, 'file_name_label1') and hasattr(self.app, 'file_name_label2'):
            should_be_visible = self.app_state.original_image1 is not None and self.app_state.original_image2 is not None and (self.app_state.showing_single_image_mode == 0)
            self.app.file_name_label1.setVisible(should_be_visible)
            self.app.file_name_label2.setVisible(should_be_visible)
            if should_be_visible:
                prefix1 = tr('Left', self.app_state.current_language) if not self.app_state.is_horizontal else tr('Top', self.app_state.current_language)
                prefix2 = tr('Right', self.app_state.current_language) if not self.app_state.is_horizontal else tr('Bottom', self.app_state.current_language)
                self.app.file_name_label1.setText(f'{prefix1}: {display_name1_for_label}')
                self.app.file_name_label2.setText(f'{prefix2}: {display_name2_for_label}')
                self.app.file_name_label1.setToolTip(display_name1_for_label if display_name1_for_label else tr('No name entered', self.app_state.current_language))
                self.app.file_name_label2.setToolTip(display_name2_for_label if display_name2_for_label else tr('No name entered', self.app_state.current_language))
            else:
                self.app.file_name_label1.setText('')
                self.app.file_name_label2.setText('')
                self.app.file_name_label1.setToolTip('')
                self.app.file_name_label2.setToolTip('')
        self.check_name_lengths(name1_from_edit, name2_from_edit)

    def check_name_lengths(self, name1=None, name2=None):
        if not hasattr(self.app, 'length_warning_label'):
            return
        if name1 is None:
            name1 = self.app.edit_name1.text() if hasattr(self.app, 'edit_name1') else ''
        if name2 is None:
            name2 = self.app.edit_name2.text() if hasattr(self.app, 'edit_name2') else ''
        len1, len2, limit = (len(name1 or ''), len(name2 or ''), self.app_state.max_name_length)
        if (len1 > limit or len2 > limit) and self.app_state.include_file_names_in_saved:
            longest = max(len1, len2)
            warning_text = tr('Name length limit ({limit}) exceeded!', self.app_state.current_language).format(limit=limit)
            tooltip_text = tr('One or both names exceed the current limit of {limit} characters (longest is {length}).\nChange the limit in the Settings dialog.', self.app_state.current_language).format(length=longest, limit=limit)
            self.app.length_warning_label.setText(warning_text)
            self.app.length_warning_label.setToolTip(tooltip_text)
            if not self.app.length_warning_label.isVisible():
                self.app.length_warning_label.setVisible(True)
        elif self.app.length_warning_label.isVisible():
            self.app.length_warning_label.setVisible(False)
            self.app.length_warning_label.setToolTip('')

    def update_translations(self):
        lang = self.app_state.current_language
        self.app.setWindowTitle(tr('Improve ImgSLI', lang))
        if hasattr(self.app, 'combo_interpolation'):
            self.app.combo_interpolation.blockSignals(True)
            current_selected_user_data = self.app.combo_interpolation.itemData(self.app.combo_interpolation.currentIndex())
            self.app.combo_interpolation.clear()
            method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
            for i, (key_str, display_text_key) in enumerate(AppConstants.INTERPOLATION_METHODS_MAP.items()):
                if not hasattr(Image.Resampling, key_str):
                    continue
                translated_display_text = tr(display_text_key, self.app_state.current_language)
                self.app.combo_interpolation.addItem(translated_display_text, userData=i)
            index_to_restore = -1
            if isinstance(current_selected_user_data, int):
                for i in range(self.app.combo_interpolation.count()):
                    if self.app.combo_interpolation.itemData(i) == current_selected_user_data:
                        index_to_restore = i
                        break
            if index_to_restore != -1:
                self.app.combo_interpolation.setCurrentIndex(index_to_restore)
            elif self.app.combo_interpolation.count() > 0:
                self.app.combo_interpolation.setCurrentIndex(0)
            self.app.combo_interpolation.blockSignals(False)
        if hasattr(self.app, 'btn_image1'):
            self.app.btn_image1.setText(tr('Add Image(s) 1', lang))
            self.app.btn_image1.setToolTip(tr('Add images to the left/top panel', lang))
        if hasattr(self.app, 'btn_image2'):
            self.app.btn_image2.setText(tr('Add Image(s) 2', lang))
            self.app.btn_image2.setToolTip(tr('Add images to the right/bottom panel', lang))
        if hasattr(self.app, 'btn_swap'):
            self.app.btn_swap.setToolTip(tr('Use the ⇄ button to swap the entire left and right image lists.', lang))
        if hasattr(self.app, 'btn_clear_list1'):
            self.app.btn_clear_list1.setToolTip(tr('Clear Left Image List', lang))
        if hasattr(self.app, 'btn_clear_list2'):
            self.app.btn_clear_list2.setToolTip(tr('Clear Right Image List', lang))
        if hasattr(self.app, 'btn_save'):
            self.app.btn_save.setText(tr('Save Result', lang))
            self.app.btn_save.setToolTip(tr('Save Result outputs the current comparison view as an image file.', lang))
        if hasattr(self.app, 'help_button'):
            self.app.help_button.setToolTip(tr('Show Help', lang))
        if hasattr(self.app, 'btn_settings'):
            self.app.btn_settings.setToolTip(tr('Settings dialog module not found.', lang) if not self.app.settings_dialog_available else tr('Open Application Settings', lang))
        if hasattr(self.app, 'checkbox_horizontal'):
            self.app.checkbox_horizontal.setText(tr('Horizontal Split', lang))
        if hasattr(self.app, 'checkbox_magnifier'):
            self.app.checkbox_magnifier.setText(tr('Use Magnifier', lang))
        if hasattr(self.app, 'freeze_button'):
            self.app.freeze_button.setText(tr('Freeze Magnifier', lang))
        if hasattr(self.app, 'checkbox_file_names'):
            self.app.checkbox_file_names.setText(tr('Include file names in saved image', lang))
        if hasattr(self.app, 'label_magnifier_size'):
            self.app.label_magnifier_size.setText(tr('Magnifier Size (%):', lang))
        if hasattr(self.app, 'label_capture_size'):
            self.app.label_capture_size.setText(tr('Capture Size (%):', lang))
        if hasattr(self.app, 'label_movement_speed'):
            self.app.label_movement_speed.setText(tr('Move Speed:', lang))
        if hasattr(self.app, 'label_edit_name1'):
            self.app.label_edit_name1.setText(tr('Name 1:', lang))
        if hasattr(self.app, 'edit_name1'):
            self.app.edit_name1.setPlaceholderText(tr('Edit Current Image 1 Name', lang))
        if hasattr(self.app, 'label_edit_name2'):
            self.app.label_edit_name2.setText(tr('Name 2:', lang))
        if hasattr(self.app, 'edit_name2'):
            self.app.edit_name2.setPlaceholderText(tr('Edit Current Image 2 Name', lang))
        if hasattr(self.app, 'label_edit_font_size'):
            self.app.label_edit_font_size.setText(tr('Font Size (%):', lang))
        if hasattr(self.app, 'combo_image1'):
            self.app.combo_image1.setToolTip(tr('Select image for left/top side', lang))
        if hasattr(self.app, 'combo_image2'):
            self.app.combo_image2.setToolTip(tr('Select image for right/bottom side', lang))
        if hasattr(self.app, 'slider_speed'):
            self.app.slider_speed.setToolTip(f"{self.app_state.movement_speed_per_sec:.1f} {tr('rel. units/sec', lang)}")
        if hasattr(self.app, 'slider_size'):
            self.app.slider_size.setToolTip(f'{int(self.app_state.magnifier_size_relative * 100):.0f}%')
        if hasattr(self.app, 'slider_capture'):
            self.app.slider_capture.setToolTip(f'{int(self.app_state.capture_size_relative * 100):.0f}%')
        if hasattr(self.app, 'label_interpolation'):
            self.app.label_interpolation.setText(tr('Magnifier Interpolation:', lang))
        if hasattr(self.app, 'btn_color_picker'):
            self.app._update_color_button_tooltip()
        if hasattr(self.app, 'drag_overlay1') and self.app.drag_overlay1.isVisible():
            self.app.drag_overlay1.setText(tr('Drop Image(s) 1 Here', lang))
        if hasattr(self.app, 'drag_overlay2') and self.app.drag_overlay2.isVisible():
            self.app.drag_overlay2.setText(tr('Drop Image(s) 2 Here', lang))
        if hasattr(self.app, 'length_warning_label') and self.app.length_warning_label.isVisible():
            self.check_name_lengths()
        self.update_file_names()
        if hasattr(self.app, '_reapply_button_styles'):
            QTimer.singleShot(0, self.app._reapply_button_styles)