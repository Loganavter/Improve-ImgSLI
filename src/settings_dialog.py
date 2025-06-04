from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QDialog
from PyQt6.QtCore import QSize, Qt
from qfluentwidgets import RadioButton, SpinBox, PushButton, SubtitleLabel, BodyLabel
try:
    from translations import tr as app_tr
except ImportError:

    def app_tr(text, lang='en', *args, **kwargs):
        try:
            return text.format(*args, **kwargs)
        except (KeyError, IndexError):
            return text

class SettingsDialog(QDialog):

    def __init__(self, current_language, current_max_length, min_limit, max_limit, current_jpeg_quality, parent=None, tr_func=None):
        super().__init__(parent)
        self.tr = tr_func if callable(tr_func) else app_tr
        self.current_language = current_language
        self.setWindowTitle(self.tr('Settings', self.current_language))
        self.setModal(True)
        self.setFixedSize(400, 320)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        title_label = SubtitleLabel(self.tr('Settings', self.current_language))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        lang_title = BodyLabel(self.tr('Language:', self.current_language))
        main_layout.addWidget(lang_title)
        lang_grid_layout = QGridLayout()
        lang_grid_layout.setSpacing(10)
        self.radio_en = RadioButton()
        self.radio_ru = RadioButton()
        self.radio_zh = RadioButton()
        self.radio_pt_br = RadioButton()
        self._setup_language_radio(self.radio_en, 'en')
        self._setup_language_radio(self.radio_ru, 'ru')
        self._setup_language_radio(self.radio_zh, 'zh')
        self._setup_language_radio(self.radio_pt_br, 'pt_BR')
        lang_grid_layout.addWidget(self.radio_en, 0, 0)
        lang_grid_layout.addWidget(self.radio_ru, 0, 1)
        lang_grid_layout.addWidget(self.radio_zh, 1, 0)
        lang_grid_layout.addWidget(self.radio_pt_br, 1, 1)
        main_layout.addLayout(lang_grid_layout)
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
        length_label = BodyLabel(self.tr('Maximum Name Length (UI):', self.current_language))
        self.spin_max_length = SpinBox()
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
        jpeg_quality_label = BodyLabel(self.tr('JPEG Quality:', self.current_language))
        self.spin_jpeg_quality = SpinBox()
        self.spin_jpeg_quality.setRange(1, 100)
        clamped_jpeg_quality = max(1, min(100, current_jpeg_quality))
        self.spin_jpeg_quality.setValue(clamped_jpeg_quality)
        self.spin_jpeg_quality.setToolTip(self.tr('JPEG compression quality (1-100, higher is better).', self.current_language))
        jpeg_quality_layout.addWidget(jpeg_quality_label)
        jpeg_quality_layout.addWidget(self.spin_jpeg_quality)
        main_layout.addLayout(jpeg_quality_layout)
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        self.ok_button = PushButton(self.tr('OK', self.current_language))
        self.cancel_button = PushButton(self.tr('Cancel', self.current_language))
        self.ok_button.setMinimumSize(80, 32)
        self.cancel_button.setMinimumSize(80, 32)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)
        main_layout.addStretch()
        main_layout.addLayout(buttons_layout)

    def _setup_language_radio(self, radio_button: RadioButton, lang_code: str):
        radio_button.setProperty('language_code', lang_code)
        if lang_code == 'en':
            radio_button.setText('English')
        elif lang_code == 'ru':
            radio_button.setText('Русский')
        elif lang_code == 'zh':
            radio_button.setText('中文')
        elif lang_code == 'pt_BR':
            radio_button.setText('Português')
        else:
            radio_button.setText(lang_code)
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
        radio_button.setMinimumSize(QSize(120, 32))

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