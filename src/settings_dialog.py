import base64
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton, QLabel, QSpinBox, QDialogButtonBox, QSizePolicy
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import QSize, Qt
try:
    from translations import tr as app_tr
except ImportError:

    def app_tr(text, lang='en', *args, **kwargs):
        try:
            return text.format(*args, **kwargs)
        except (KeyError, IndexError):
            return text
try:
    from icons import FLAG_ICONS
except ImportError:
    FLAG_ICONS = {}

class SettingsDialog(QDialog):

    def __init__(self, current_language, current_max_length, min_limit, max_limit, current_jpeg_quality, parent=None, tr_func=None):
        super().__init__(parent)
        self.tr = tr_func if callable(tr_func) else app_tr
        self.current_language = current_language
        self.setWindowTitle(self.tr('Settings', self.current_language))
        self.setMinimumWidth(350)
        main_layout = QVBoxLayout(self)
        lang_group_box = QGroupBox(self.tr('Language:', self.current_language))
        lang_layout = QHBoxLayout()
        self.radio_en = QRadioButton('English')
        self.radio_ru = QRadioButton('Русский')
        self.radio_zh = QRadioButton('中文')
        self.radio_pt_br = QRadioButton('Português (BR)')
        self._setup_language_radio(self.radio_en, 'en', FLAG_ICONS.get('en'))
        self._setup_language_radio(self.radio_ru, 'ru', FLAG_ICONS.get('ru'))
        self._setup_language_radio(self.radio_zh, 'zh', FLAG_ICONS.get('zh'))
        self._setup_language_radio(self.radio_pt_br, 'pt_BR', FLAG_ICONS.get('pt_BR'))
        lang_layout.addWidget(self.radio_en)
        lang_layout.addWidget(self.radio_ru)
        lang_layout.addWidget(self.radio_zh)
        lang_layout.addWidget(self.radio_pt_br)
        lang_layout.addStretch()
        lang_group_box.setLayout(lang_layout)
        main_layout.addWidget(lang_group_box)
        if current_language == 'en':
            self.radio_en.setChecked(True)
        elif current_language == 'ru':
            self.radio_ru.setChecked(True)
        elif current_language == 'zh':
            self.radio_zh.setChecked(True)
        elif current_language == 'pt_BR':
            self.radio_pt_br.setChecked(True)
        else:
            self.radio_en.setChecked(True)
        length_layout = QHBoxLayout()
        length_label = QLabel(self.tr('Maximum Name Length (UI):', self.current_language))
        self.spin_max_length = QSpinBox()
        self.spin_max_length.setRange(min_limit, max_limit)
        clamped_current_max_length = max(min_limit, min(max_limit, current_max_length))
        self.spin_max_length.setValue(clamped_current_max_length)
        tooltip_template = self.tr('Limits the displayed name length in the UI ({min}-{max}).', self.current_language)
        tooltip_text = tooltip_template.format(min=min_limit, max=max_limit)
        self.spin_max_length.setToolTip(tooltip_text)
        length_layout.addWidget(length_label)
        length_layout.addWidget(self.spin_max_length)
        main_layout.addLayout(length_layout)
        jpeg_quality_layout = QHBoxLayout()
        jpeg_quality_label = QLabel(self.tr('JPEG Quality:', self.current_language))
        self.spin_jpeg_quality = QSpinBox()
        self.spin_jpeg_quality.setRange(1, 100)
        clamped_jpeg_quality = max(1, min(100, current_jpeg_quality))
        self.spin_jpeg_quality.setValue(clamped_jpeg_quality)
        self.spin_jpeg_quality.setToolTip(self.tr('JPEG compression quality (1-100, higher is better).', self.current_language))
        jpeg_quality_layout.addWidget(jpeg_quality_label)
        jpeg_quality_layout.addWidget(self.spin_jpeg_quality)
        main_layout.addLayout(jpeg_quality_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setText(self.tr('OK', self.current_language))
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText(self.tr('Cancel', self.current_language))
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

    def _setup_language_radio(self, radio_button, lang_code, base64_icon):
        radio_button.setProperty('language_code', lang_code)
        radio_button.setText('')
        icon = QIcon()
        if base64_icon:
            try:
                pixmap = QPixmap()
                loaded = pixmap.loadFromData(base64.b64decode(base64_icon))
                if loaded and (not pixmap.isNull()):
                    icon = QIcon(pixmap)
                else:
                    print(f"Warning: Failed to load pixmap from base64 for language '{lang_code}' in SettingsDialog.")
            except Exception as e:
                print(f"Error creating flag icon for language '{lang_code}' in SettingsDialog: {e}")
        else:
            print(f"Warning: No base64 icon data provided for language '{lang_code}' in SettingsDialog.")
        radio_button.setIcon(icon)
        radio_button.setIconSize(QSize(24, 16))
        radio_button.setStyleSheet('\n            QRadioButton {\n                spacing: 5px;\n                border: 1px solid transparent;\n                padding: 2px;\n                background-color: transparent;\n                border-radius: 3px;\n            }\n            QRadioButton::indicator { width: 0px; height: 0px; }\n            QRadioButton:checked { border: 1px solid palette(highlight); }\n            QRadioButton:hover { background-color: palette(alternate-base); }\n        ')
        lang_name = lang_code
        tooltip_key = f'Switch language to {lang_code}'
        if lang_code == 'en':
            tooltip_key = 'Switch language to English'
        elif lang_code == 'ru':
            tooltip_key = 'Switch language to Русский'
        elif lang_code == 'zh':
            tooltip_key = 'Switch language to 中文'
        elif lang_code == 'pt_BR':
            tooltip_key = 'Switch language to Brazilian Portuguese'
        radio_button.setToolTip(self.tr(tooltip_key, self.current_language))
        radio_button.setMinimumSize(QSize(30, 22))
        radio_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def get_settings(self):
        selected_language = 'en'
        if self.radio_en.isChecked():
            selected_language = 'en'
        elif self.radio_ru.isChecked():
            selected_language = 'ru'
        elif self.radio_zh.isChecked():
            selected_language = 'zh'
        elif self.radio_pt_br.isChecked():
            selected_language = 'pt_BR'
        max_length = self.spin_max_length.value()
        jpeg_quality = self.spin_jpeg_quality.value()
        return (selected_language, max_length, jpeg_quality)
