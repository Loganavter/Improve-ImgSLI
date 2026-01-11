import logging
import os

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty, QSize
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel,
    QWidget, QStackedWidget, QSizePolicy
)

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.custom_button import CustomButton
from toolkit.widgets.atomic.toggle_icon_button import ToggleIconButton
from toolkit.widgets.atomic.scrollable_icon_button import ScrollableIconButton
from toolkit.widgets.atomic.toggle_scrollable_icon_button import ToggleScrollableIconButton
from toolkit.widgets.atomic.simple_icon_button import SimpleIconButton
from ui.icon_manager import AppIcon
from utils.resource_loader import resource_path
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class DotIndicator(QWidget):
    def __init__(self, count=3, parent=None):
        super().__init__(parent)
        self._count = count
        self._current = 0
        self._animated_position = 0.0
        self._previous_position = 0.0
        self.setMinimumSize(60, 15)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.theme_manager = ThemeManager.get_instance()

        self._animation = QPropertyAnimation(self, b"animatedPosition")
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad)

    def get_animated_position(self):
        return self._animated_position

    def set_animated_position(self, value):
        self._previous_position = self._animated_position
        self._animated_position = value
        self.update()

    animatedPosition = pyqtProperty(float, get_animated_position, set_animated_position)

    def set_current(self, index):
        old_pos = self._current
        self._current = index

        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
            old_pos = self._animated_position

        self._animation.setStartValue(float(old_pos))
        self._animation.setEndValue(float(index))
        self._animation.start()

    def sizeHint(self):
        if self.parent():
            width = min(200, self.parent().width() // 3)
            height = 20
        else:
            width = 100
            height = 20
        return QSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = self.theme_manager.get_color("accent")
        inactive = self.theme_manager.get_color("dialog.text")
        inactive.setAlpha(60)

        dot_size = max(6, min(10, self.width() // 15))
        spacing = max(10, min(16, self.width() // 10))
        total_width = (self._count * dot_size) + ((self._count - 1) * spacing)
        start_x = (self.width() - total_width) // 2
        y = (self.height() - dot_size) // 2

        animated_x = start_x + self._animated_position * (dot_size + spacing)
        step = dot_size + spacing

        for i in range(self._count):
            x = start_x + i * (dot_size + spacing)
            painter.setBrush(inactive)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(x), int(y), dot_size, dot_size)

        if abs(self._animated_position - self._previous_position) > 0.01 and self._animation.state() == QPropertyAnimation.State.Running:
            animation_progress = self._animation.currentTime() / self._animation.duration() if self._animation.duration() > 0 else 1.0
            direction = -1 if self._animated_position > self._previous_position else 1

            trail_steps = 3
            for i in range(trail_steps):
                trail_offset = (i + 1) * step * 0.17
                trail_x = animated_x + trail_offset * direction

                if trail_x < start_x - step or trail_x > start_x + (self._count - 1) * step + step:
                    continue

                base_alpha = 120 * (1.0 - (i + 1) / (trail_steps + 1))
                fade_alpha = base_alpha * (1.0 - animation_progress)
                alpha = int(fade_alpha)

                if alpha <= 0:
                    continue

                trail_size = max(4, dot_size - i * 1.2)
                trail_color = QColor(accent)
                trail_color.setAlpha(alpha)

                painter.setBrush(trail_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(int(trail_x) - 1, int(y) - 1, int(trail_size) + 2, int(trail_size) + 2)

        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(animated_x) - 1, int(y) - 1, dot_size + 2, dot_size + 2)

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
        self.setMouseTracking(True)

        current_lang = getattr(store.settings, "current_language", "en")
        self.modes = [
            {
                "key": "beginner",
                "name": tr("settings.ui_mode_beginner", current_lang),
                "desc": tr("onboarding.beginner_description", current_lang)
            },
            {
                "key": "advanced",
                "name": tr("settings.ui_mode_advanced", current_lang),
                "desc": tr("onboarding.advanced_description", current_lang)
            },
            {
                "key": "expert",
                "name": tr("settings.ui_mode_expert", current_lang),
                "desc": tr("onboarding.expert_description", current_lang)
            },
        ]

        self._init_ui()
        self._apply_theme()

        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._scale_all)

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
            btn = CustomButton(None, mode["name"])
            btn.RADIUS = 8
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, idx=i: self._on_mode_btn_clicked(idx))
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
        self.bottom_layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        welcome_text = tr("onboarding.welcome", current_lang)
        self.welcome_lbl = QLabel(welcome_text)
        self.welcome_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bottom_layout.addWidget(self.welcome_lbl)

        start_text = tr("onboarding.start_button", current_lang)
        self.btn_start = CustomButton(None, start_text)
        self.btn_start.setProperty("class", "primary")
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
            page = self._create_slide_for_mode(mode)
            self.stack.addWidget(page)

    def _create_slide_for_mode(self, mode_data):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(30)

        lbl_title = QLabel(mode_data["name"])
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        lbl_title.setFont(title_font)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)

        key = mode_data["key"]
        demo_container = QWidget()
        demo_layout = QHBoxLayout(demo_container)
        demo_layout.setSpacing(35)
        demo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        current_lang = getattr(self.store.settings, "current_language", "en")

        if key == "beginner":

            b1 = ToggleIconButton(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT)
            self._style_demo_btn(b1, checked=False)
            b2 = ToggleIconButton(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN)
            self._style_demo_btn(b2)
            b3 = SimpleIconButton(AppIcon.DIVIDER_COLOR)
            self._style_demo_btn(b3)
            accent_color = self.theme_manager.get_color("accent")
            b3.set_color(accent_color)

            def _on_beginner_color_clicked():
                from PyQt6.QtWidgets import QColorDialog
                current_color = b3._current_color if b3._current_color else accent_color
                color_dialog = QColorDialog(current_color, self)
                color_dialog.setWindowTitle(tr("ui.select_color", current_lang))
                self.theme_manager.apply_theme_to_dialog(color_dialog)

                def on_color_selected(color):
                    if color.isValid():
                        b3.set_color(color)

                color_dialog.colorSelected.connect(on_color_selected)
                color_dialog.show()

            b3.clicked.connect(_on_beginner_color_clicked)

            b4 = ScrollableIconButton(AppIcon.DIVIDER_WIDTH, min_value=1, max_value=10)
            self._style_demo_btn(b4)

            labels = [
                tr("onboarding.beginner.button.rotate", current_lang),
                tr("onboarding.beginner.button.view", current_lang),
                tr("onboarding.beginner.button.color", current_lang),
                tr("onboarding.beginner.button.width", current_lang)
            ]

            demo_layout.addLayout(self._wrap_btn(b1, labels[0]))
            demo_layout.addLayout(self._wrap_btn(b2, labels[1]))
            demo_layout.addLayout(self._wrap_btn(b3, labels[2]))
            demo_layout.addLayout(self._wrap_btn(b4, labels[3]))

        elif key == "advanced":

            b_smart = ToggleScrollableIconButton(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT, min_val=0, max_val=20)
            b_smart.setFixedSize(40, 40)
            b_smart.setChecked(False)
            b_smart.set_value(3)

            b_color = SimpleIconButton(AppIcon.DIVIDER_COLOR)
            self._style_demo_btn(b_color)
            accent_color = self.theme_manager.get_color("accent")
            b_color.set_color(accent_color)

            def _on_advanced_color_clicked():
                from PyQt6.QtWidgets import QColorDialog
                current_color = b_color._current_color if b_color._current_color else accent_color
                color_dialog = QColorDialog(current_color, self)
                color_dialog.setWindowTitle(tr("ui.select_color", current_lang))
                self.theme_manager.apply_theme_to_dialog(color_dialog)

                def on_color_selected(color):
                    if color.isValid():
                        b_color.set_color(color)

                color_dialog.colorSelected.connect(on_color_selected)
                color_dialog.show()

            b_color.clicked.connect(_on_advanced_color_clicked)

            txts = [
                tr("onboarding.advanced.button.smart_control", current_lang),
                tr("onboarding.advanced.button.color", current_lang)
            ]

            demo_layout.addLayout(self._wrap_btn(b_smart, txts[0]))
            demo_layout.addLayout(self._wrap_btn(b_color, txts[1]))

        elif key == "expert":

            b_expert = ToggleScrollableIconButton(AppIcon.VERTICAL_SPLIT, AppIcon.HORIZONTAL_SPLIT, min_val=0, max_val=20)
            b_expert.setFixedSize(40, 40)
            b_expert.setChecked(False)
            b_expert.set_value(3)

            accent_color = self.theme_manager.get_color("accent")
            b_expert.set_color(accent_color)

            def _on_expert_right():
                from PyQt6.QtWidgets import QColorDialog

                current_color = b_expert._underline_color if b_expert._underline_color else accent_color
                color_dialog = QColorDialog(current_color, self)
                color_dialog.setWindowTitle(tr("ui.select_color", current_lang))
                self.theme_manager.apply_theme_to_dialog(color_dialog)

                def on_color_selected(color):
                    if color.isValid():
                        b_expert.set_color(color)

                color_dialog.colorSelected.connect(on_color_selected)
                color_dialog.show()

            def _on_expert_middle():
                logger.debug("Onboarding: _on_expert_middle called")
                current_value = b_expert.get_value()

                if current_value == 0:

                    saved_value = b_expert.restore_saved_value()
                    if saved_value is not None and saved_value > 0:
                        logger.debug(f"Onboarding: Restoring saved value {saved_value}")
                        b_expert.set_value(saved_value)
                    else:
                        logger.debug("Onboarding: No saved value, setting to 3")
                        b_expert.set_value(3)
                else:

                    logger.debug(f"Onboarding: Saving current value {current_value} and setting to 0")
                    b_expert.set_saved_value(current_value)
                    b_expert.set_value(0)

            def _on_expert_val_changed(val):

                pass

            b_expert.rightClicked.connect(_on_expert_right)
            logger.debug("Onboarding: Connecting middleClicked signal")
            b_expert.middleClicked.connect(_on_expert_middle)
            logger.debug(f"Onboarding: middleClicked connected, receivers count: {b_expert.receivers(b_expert.middleClicked)}")
            b_expert.valueChanged.connect(_on_expert_val_changed)

            info_txt = tr("onboarding.expert.button.info", current_lang)

            demo_layout.addLayout(self._wrap_btn(b_expert, info_txt))

        layout.addWidget(demo_container)

        lbl_desc_main = QLabel(mode_data.get("desc", ""))
        lbl_desc_main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_col = self.theme_manager.get_color("dialog.text").name()
        lbl_desc_main.setStyleSheet(f"font-size: 16px; color: {text_col}; margin-top: 15px; opacity: 0.9;")
        layout.addWidget(lbl_desc_main)

        return page

    def _style_demo_btn(self, btn, checked=False):
        btn.setFixedSize(40, 40)

        from toolkit.widgets.atomic.toggle_scrollable_icon_button import ToggleScrollableIconButton
        is_toggle_scrollable = isinstance(btn, ToggleScrollableIconButton)

        if is_toggle_scrollable:

            btn.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        else:

            btn.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        btn.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, False)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        if hasattr(btn, 'setChecked'):
            btn.setChecked(checked)
        if hasattr(btn, 'update_styles'):
            btn.update_styles()

        if not is_toggle_scrollable:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        btn.update()

    def _wrap_btn(self, btn, text):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        if text:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text_col = self.theme_manager.get_color("list_item.text.rating").name()
            lbl.setStyleSheet(f"font-size: 13px; color: {text_col}; font-weight: 500;")
            layout.addWidget(lbl)
        return layout

    def _on_mode_btn_clicked(self, index):
        self._update_state(index)

    def _update_state(self, index):
        self._current_index = index
        self.stack.setCurrentIndex(index)
        self.dots.set_current(index)

        accent_color = self.theme_manager.get_color("accent")
        text_color = self.theme_manager.get_color("dialog.text")
        for i, btn in enumerate(self.mode_buttons):
            if i == index:
                btn.set_override_bg_color(accent_color)
                btn.text_label.setStyleSheet("color: #ffffff; background: transparent;")
            else:
                btn.set_override_bg_color(None)
                btn.text_label.setStyleSheet(f"color: {text_color.name()}; background: transparent;")

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

        self.top_layout.setContentsMargins(margin_horizontal, margin_top, margin_horizontal, 0)
        self.top_layout.setSpacing(spacing)

        self.bottom_layout.setSpacing(spacing)
        self.bottom_layout.setContentsMargins(0, 0, 0, bottom_margin)
        self.main_layout.setSpacing(0)

        for layout in [self.top_layout, self.bottom_layout]:
            for i in reversed(range(layout.count())):
                item = layout.itemAt(i)
                if item and item.spacerItem() and not item.spacerItem().sizePolicy().hasHeightForWidth():
                    layout.removeItem(item)

        text_col = self.theme_manager.get_color("WindowText").name()
        accent = self.theme_manager.get_color("accent").name()

        try:
            border_color = self.theme_manager.get_color("dialog.border").name()
        except:
            border_color = "#505050"
        try:
            btn_bg = self.theme_manager.get_color("dialog.input.background").name()
        except:
            btn_bg = "#ffffff"

        hint_font_size = max(12, int(15 * scale))

        self.hint_label.setStyleSheet(
            f"color: {text_col}; font-size: {hint_font_size}px; font-weight: 600; opacity: 0.8;"
        )

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
            if hasattr(btn, 'text_label'):
                btn.text_label.setFont(mode_btn_font)

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
        if hasattr(self.btn_start, 'text_label'):
            self.btn_start.text_label.setFont(custom_font)

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

        self.setStyleSheet(f"""
            OnboardingOverlay {{
                background-color: {bg_window};
            }}
            QLabel {{
                color: {text_col};
                background: transparent;
            }}
        """)

    def _finish(self):
        key = self.modes[self._current_index]["key"]
        if self.settings_manager:
            self.settings_manager._save_setting("ui_mode", key)
            self.settings_manager.set_first_run_completed()
        self.completed.emit(key)
