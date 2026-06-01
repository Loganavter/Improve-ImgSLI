from __future__ import annotations

from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPalette
from PyQt6.QtGui import QResizeEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from resources.translations import tr
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button
from ui.onboarding.indicator import DotIndicator
from ui.onboarding.pages import build_modes, create_slide_for_mode


class OnboardingOverlay(QWidget):
    completed = pyqtSignal(str)

    def __init__(self, settings_manager, store, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.store = store
        self.theme_manager = ThemeManager.get_instance()
        self._current_index = 0

        self._base_window_width = 1920
        self._base_window_height = 1080

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.modes = build_modes(store)

        self._init_ui()
        self._apply_theme()

        QTimer.singleShot(0, self._scale_all)

    def showEvent(self, event: QEvent):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        QTimer.singleShot(0, self._scale_all)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._scale_all()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        event.accept()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.top_container = QWidget()
        self.top_layout = QVBoxLayout(self.top_container)

        self.stack = QStackedWidget()
        self._init_slides()

        slide_wrapper = QWidget()
        slide_layout = QVBoxLayout(slide_wrapper)
        slide_layout.setContentsMargins(0, 0, 0, 0)
        slide_layout.addWidget(self.stack)
        slide_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.top_layout.addWidget(slide_wrapper, 1)

        current_lang = getattr(self.store.settings, "current_language", "en")

        hint_text_main = tr("onboarding.mode_hint", current_lang)
        hint_text_controls = tr("onboarding.magnifier_controls_hint", current_lang)
        full_hint_text = f"{hint_text_main}\n{hint_text_controls}"

        self.hint_label = QLabel(full_hint_text)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_layout.addWidget(self.hint_label)

        self.mode_buttons_layout = QHBoxLayout()
        self.mode_buttons_layout.addStretch()

        self.mode_buttons = []
        for i, mode in enumerate(self.modes):
            btn = Button(text=mode["name"], variant="surface", corner_radius=8)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, idx=i: self._on_mode_btn_clicked(idx)
            )
            self.mode_buttons.append(btn)
            self.mode_buttons_layout.addWidget(btn)

        self.mode_buttons_layout.addStretch()
        self.top_layout.addLayout(self.mode_buttons_layout)

        self.dots = DotIndicator(count=len(self.modes))
        dots_layout = QHBoxLayout()
        dots_layout.addStretch()
        dots_layout.addWidget(self.dots)
        dots_layout.addStretch()
        self.top_layout.addLayout(dots_layout)

        self.main_layout.addWidget(self.top_container, 75)

        self.bottom_container = QWidget()
        self.bottom_layout = QVBoxLayout(self.bottom_container)
        self.bottom_layout.setAlignment(
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
        )

        welcome_text = tr("onboarding.welcome", current_lang)
        self.welcome_lbl = QLabel(welcome_text)
        self.welcome_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bottom_layout.addWidget(self.welcome_lbl)

        start_text = tr("onboarding.start_button", current_lang)
        self.btn_start = Button(text=start_text, variant="primary")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self._finish)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addStretch()
        self.bottom_layout.addLayout(btn_layout)

        self.main_layout.addWidget(self.bottom_container, 25)

        self._update_state(0)

    def _init_slides(self):
        self._slide_widgets = []
        for mode in self.modes:
            page = create_slide_for_mode(self, mode)
            self.stack.addWidget(page)

    def _on_mode_btn_clicked(self, index):
        self._update_state(index)

    def _update_state(self, index):
        self._current_index = index
        self.stack.setCurrentIndex(index)
        self.dots.set_current(index)

        accent_color = self.theme_manager.get_color("accent")
        text_color = self.theme_manager.get_color("dialog.text")
        highlighted_text = self.theme_manager.get_color("HighlightedText")

        for i, btn in enumerate(self.mode_buttons):
            if i == index:
                btn.set_override_bg_color(accent_color)
                btn.setProperty("textColor", highlighted_text)
                btn.update()
            else:
                btn.set_override_bg_color(None)
                btn.setProperty("textColor", text_color)
                btn.update()

    def _get_scale_factor(self):
        width_scale = self.width() / self._base_window_width
        height_scale = self.height() / self._base_window_height
        scale = min(width_scale, height_scale)
        if scale < 0.7:
            scale = 0.7 + (scale - 0.5) * 0.2
        elif scale > 1.0:
            scale = 1.0 + (scale - 1.0) * 0.5
        return max(0.7, min(1.5, scale))

    def _scale_all(self):
        scale = self._get_scale_factor()

        if scale > 1.0:
            margin_horizontal = max(2, int(10 / scale))
            margin_top = max(5, int(15 / scale))
            bottom_margin = max(2, int(5 / scale))
        else:
            margin_horizontal = max(5, int(10 * scale))
            margin_top = max(10, int(15 * scale))
            bottom_margin = max(2, int(5 * scale))

        spacing = max(1, int(2 * scale)) if scale <= 1.0 else max(1, int(2 / scale))

        self.top_layout.setContentsMargins(
            margin_horizontal, margin_top, margin_horizontal, 0
        )
        self.top_layout.setSpacing(spacing)

        self.bottom_layout.setSpacing(spacing)
        self.bottom_layout.setContentsMargins(0, 0, 0, bottom_margin)
        self.main_layout.setSpacing(0)

        for layout in [self.top_layout, self.bottom_layout]:
            for i in reversed(range(layout.count())):
                item = layout.itemAt(i)
                if (
                    item
                    and item.spacerItem()
                    and not item.spacerItem().sizePolicy().hasHeightForWidth()
                ):
                    layout.removeItem(item)

        text_col = self.theme_manager.get_color("WindowText").name()

        hint_font_size = max(12, int(15 * scale))

        hint_font = self.hint_label.font()
        hint_font.setPixelSize(hint_font_size)
        hint_font.setWeight(600)
        self.hint_label.setFont(hint_font)
        hint_palette = self.hint_label.palette()
        hint_palette.setColor(self.hint_label.foregroundRole(), QColor(text_col))
        self.hint_label.setPalette(hint_palette)

        btn_width = max(150, int(200 * scale))
        btn_height = max(42, int(52 * scale))
        btn_spacing = int(20 * scale)

        self.mode_buttons_layout.setSpacing(btn_spacing)

        mode_btn_font_size = max(13, int(16 * scale))
        mode_btn_font = QFont()
        mode_btn_font.setPixelSize(mode_btn_font_size)
        mode_btn_font.setBold(True)

        for btn in self.mode_buttons:
            btn.setFixedSize(btn_width, btn_height)
            if not hasattr(btn, "text_label"):
                btn.setFont(mode_btn_font)

        welcome_font_size = max(22, int(28 * scale))
        w_font = QFont()
        w_font.setPointSize(welcome_font_size)
        w_font.setBold(True)
        self.welcome_lbl.setFont(w_font)

        start_btn_width = max(200, int(260 * scale))
        start_btn_height = max(48, int(56 * scale))

        start_font_size = max(14, int(17 * scale))
        custom_font = QFont()
        custom_font.setPixelSize(start_font_size)
        custom_font.setBold(True)

        if not hasattr(self.btn_start, "text_label"):
            self.btn_start.setFont(custom_font)

        self.btn_start.setFixedSize(start_btn_width, start_btn_height)

        dots_height = max(20, int(26 * scale))
        self.dots.setFixedHeight(dots_height)

        hint_index = self.top_layout.indexOf(self.hint_label)
        if hint_index >= 0:
            s = int(4 / scale) if scale > 1.0 else int(4 * scale)
            self.top_layout.insertSpacing(hint_index + 1, max(2, s))

        buttons_index = self.top_layout.indexOf(self.mode_buttons_layout)
        if buttons_index >= 0:
            s = int(3 / scale) if scale > 1.0 else int(3 * scale)
            self.top_layout.insertSpacing(buttons_index + 2, max(2, s))

        welcome_index = self.bottom_layout.indexOf(self.welcome_lbl)
        if welcome_index >= 0:
            s = int(4 / scale) if scale > 1.0 else int(4 * scale)
            self.bottom_layout.insertSpacing(welcome_index + 1, max(2, s))

    def _apply_theme(self):
        bg_window = self.theme_manager.get_color("Window").name()
        text_col = self.theme_manager.get_color("WindowText").name()
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(bg_window))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(text_col))
        self.setPalette(palette)

    def _finish(self):
        key = self.modes[self._current_index]["key"]
        if self.settings_manager:
            self.settings_manager._save_setting("ui_mode", key)
            self.settings_manager.set_first_run_completed()
        self.completed.emit(key)
