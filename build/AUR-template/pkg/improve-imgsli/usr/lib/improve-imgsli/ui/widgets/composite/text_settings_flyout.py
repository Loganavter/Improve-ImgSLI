from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.constants import AppConstants
from resources import translations as translations_mod
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic import (
    FluentRadioButton,
    FluentSlider,
    FluentSwitch,
)

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)

class FontSettingsFlyout(QWidget):
    settings_changed = pyqtSignal(int, int, QColor, QColor, bool, str, int)
    closed = pyqtSignal()

    def __init__(self, app_ref=None):
        super().__init__(app_ref)
        self.app_ref = app_ref

        self._theme = ThemeManager.get_instance()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.container = QWidget(self)
        self.container.setObjectName("FlyoutWidget")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)

        self._color_dialog = None
        self._bg_color_dialog = None
        shadow.setOffset(1, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container.setGraphicsEffect(shadow)

        self._outer_margin = max(8, 10 + 2)

        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(8)

        size_layout = QHBoxLayout()
        self.size_label = QLabel("Font Size:")
        self.size_slider = FluentSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(50, 200)
        size_layout.addWidget(self.size_label)
        size_layout.addWidget(self.size_slider)

        weight_layout = QHBoxLayout()
        self.weight_label = QLabel("Font Weight:")
        self.weight_slider = FluentSlider(Qt.Orientation.Horizontal)
        self.weight_slider.setRange(0, 100)
        weight_layout.addWidget(self.weight_label)
        weight_layout.addWidget(self.weight_slider)

        opacity_layout = QHBoxLayout()
        self.opacity_label = QLabel("Opacity:")
        self.opacity_slider = FluentSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        opacity_layout.addWidget(self.opacity_label)
        opacity_layout.addWidget(self.opacity_slider)

        color_layout = QHBoxLayout()
        self.color_label = QLabel("Color:")
        self.color_preview = QPushButton()
        self.color_preview.setFixedSize(28, 28)
        color_layout.addWidget(self.color_label)
        color_layout.addStretch()
        color_layout.addWidget(self.color_preview)

        bg_color_layout = QHBoxLayout()
        self.bg_color_label = QLabel("Background:")
        self.bg_color_preview = QPushButton()
        self.bg_color_preview.setFixedSize(28, 28)
        bg_color_layout.addWidget(self.bg_color_label)
        bg_color_layout.addStretch()
        bg_color_layout.addWidget(self.bg_color_preview)

        self.checkbox_text_bg = FluentSwitch()
        self.checkbox_text_bg_label = QLabel("Draw text background")
        text_bg_layout = QHBoxLayout()
        text_bg_layout.addWidget(self.checkbox_text_bg_label)
        text_bg_layout.addStretch()
        text_bg_layout.addWidget(self.checkbox_text_bg)

        self.text_pos_group = QWidget()
        text_pos_layout = QVBoxLayout(self.text_pos_group)
        text_pos_layout.setContentsMargins(0, 0, 0, 0)
        self.pos_group_label = QLabel("Text Position:")
        radio_layout = QHBoxLayout()
        self.radio_pos_edges = FluentRadioButton("At Edges")
        self.radio_pos_split_line = FluentRadioButton("Near Split Line")
        radio_layout.addWidget(self.radio_pos_edges)
        radio_layout.addWidget(self.radio_pos_split_line)
        radio_layout.addStretch()
        self.text_pos_button_group = QButtonGroup(self)
        self.text_pos_button_group.addButton(self.radio_pos_edges, 0)
        self.text_pos_button_group.addButton(self.radio_pos_split_line, 1)
        text_pos_layout.addWidget(self.pos_group_label)
        text_pos_layout.addLayout(radio_layout)

        self.content_layout.addLayout(size_layout)
        self.content_layout.addLayout(weight_layout)
        self.content_layout.addLayout(opacity_layout)
        self.content_layout.addLayout(color_layout)
        self.content_layout.addLayout(bg_color_layout)
        self.content_layout.addLayout(text_bg_layout)
        self.content_layout.addWidget(self.text_pos_group)

        self.size_slider.valueChanged.connect(self._emit_changes)
        self.weight_slider.valueChanged.connect(self._emit_changes)
        self.opacity_slider.valueChanged.connect(self._emit_changes)
        self.color_preview.clicked.connect(self._open_color_dialog)
        self.bg_color_preview.clicked.connect(self._open_bg_color_dialog)
        self.checkbox_text_bg.checkedChanged.connect(self._emit_changes)
        self.radio_pos_edges.toggled.connect(lambda *_: QTimer.singleShot(0, self._emit_changes))
        self.radio_pos_split_line.toggled.connect(lambda *_: QTimer.singleShot(0, self._emit_changes))

        self._theme.theme_changed.connect(self._apply_style)
        self._apply_style()
        self.hide()

    def _apply_style(self):
        bg_color = self._theme.get_color("flyout.background").name(QColor.NameFormat.HexArgb)
        border_color = self._theme.get_color("flyout.border").name(QColor.NameFormat.HexArgb)
        self.container.setStyleSheet(f"""
            QWidget#FlyoutWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_values(self,
     size: int,
     font_weight: int,
     color: QColor,
     bg_color: QColor,
     draw_text_background: bool,
     text_placement_mode: str,
     text_alpha_percent: int,
     current_language: str
    ):
        self.size_slider.blockSignals(True)
        self.weight_slider.blockSignals(True)
        self.opacity_slider.blockSignals(True)
        self.checkbox_text_bg.blockSignals(True)
        self.text_pos_button_group.blockSignals(True)
        self.radio_pos_edges.blockSignals(True)
        self.radio_pos_split_line.blockSignals(True)
        self.size_slider.setValue(size)
        self.weight_slider.setValue(font_weight)
        self.opacity_slider.setValue(max(0, min(100, int(text_alpha_percent))))
        self.color_preview.setStyleSheet(f"background-color: {color.name()}; border-radius: 14px; border: 1px solid grey;")
        self.bg_color_preview.setStyleSheet(f"background-color: {bg_color.name()}; border-radius: 14px; border: 1px solid grey;")
        self.checkbox_text_bg.setChecked(draw_text_background)
        if text_placement_mode == "split_line":
            self.radio_pos_split_line.setChecked(True)
        else:
            self.radio_pos_edges.setChecked(True)
        self._current_language = current_language
        self._update_translations()
        self.size_slider.blockSignals(False)
        self.weight_slider.blockSignals(False)
        self.opacity_slider.blockSignals(False)
        self.checkbox_text_bg.blockSignals(False)
        self.text_pos_button_group.blockSignals(False)
        self.radio_pos_edges.blockSignals(False)
        self.radio_pos_split_line.blockSignals(False)

    def _emit_changes(self):
        size = self.size_slider.value()
        font_weight = self.weight_slider.value()
        color_str = self.color_preview.styleSheet().split("background-color:")[1].split(";")[0].strip()
        color = QColor(color_str)
        bg_color_str = self.bg_color_preview.styleSheet().split("background-color:")[1].split(";")[0].strip()
        bg_color = QColor(bg_color_str)
        draw_text_background = self.checkbox_text_bg.isChecked()
        text_placement_mode = "split_line" if self.radio_pos_split_line.isChecked() else "edges"
        text_alpha_percent = self.opacity_slider.value()
        self.settings_changed.emit(size, font_weight, color, bg_color, draw_text_background, text_placement_mode, text_alpha_percent)

    def _open_color_dialog(self):
        if self._color_dialog and self._color_dialog.isVisible():
            self._color_dialog.raise_()
            self._color_dialog.activateWindow()
            return

        color_str = self.color_preview.styleSheet().split("background-color:")[1].split(";")[0].strip()
        initial_color = QColor(color_str)
        self._color_dialog = QColorDialog(initial_color, self)
        self._color_dialog.setWindowFlags(self._color_dialog.windowFlags() | Qt.WindowType.Window)
        self._color_dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        self._color_dialog.setModal(False)

        ui_manager = self.app_ref.presenter.ui_manager
        ui_manager.set_modal_dialog_active(True)

        def on_color_selected(color):
            if color.isValid():
                self.color_preview.setStyleSheet(f"background-color: {color.name()}; border-radius: 14px; border: 1px solid grey;")
                self._emit_changes()

        def on_finished(result):
            ui_manager.set_modal_dialog_active(False)
            self._color_dialog = None

        self._color_dialog.colorSelected.connect(on_color_selected)
        self._color_dialog.finished.connect(on_finished)
        self._color_dialog.show()

    def _open_bg_color_dialog(self):
        if self._bg_color_dialog and self._bg_color_dialog.isVisible():
            self._bg_color_dialog.raise_()
            self._bg_color_dialog.activateWindow()
            return

        color_str = self.bg_color_preview.styleSheet().split("background-color:")[1].split(";")[0].strip()
        initial_color = QColor(color_str)
        self._bg_color_dialog = QColorDialog(initial_color, self)
        self._bg_color_dialog.setWindowFlags(self._bg_color_dialog.windowFlags() | Qt.WindowType.Window)
        self._bg_color_dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        self._bg_color_dialog.setModal(False)

        ui_manager = self.app_ref.presenter.ui_manager
        ui_manager.set_modal_dialog_active(True)

        def on_color_selected(color):
            if color.isValid():
                self.bg_color_preview.setStyleSheet(f"background-color: {color.name()}; border-radius: 14px; border: 1px solid grey;")
                self._emit_changes()

        def on_finished(result):
            ui_manager.set_modal_dialog_active(False)
            self._bg_color_dialog = None

        self._bg_color_dialog.colorSelected.connect(on_color_selected)
        self._bg_color_dialog.finished.connect(on_finished)
        self._bg_color_dialog.show()

    def _create_debug_marker(self, pos: QPoint, color: str, size: int = 10, text: str = ""):
        marker = QLabel(text, self.parent())
        marker.setFixedSize(size, size)
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setStyleSheet(f"background-color: {color}; border: 1px solid black; color: white; font-weight: bold;")
        marker.move(pos - QPoint(size//2, size//2))
        marker.show()
        marker.raise_()
        QTimer.singleShot(5000, marker.deleteLater)

    def show_top_left_of(self, anchor_widget: QWidget):
        try:
            parent_widget = self.parent()
            if parent_widget is None: return

            anchor_origin_global = anchor_widget.mapToGlobal(anchor_widget.rect().topLeft())

        except Exception:
            return

        content_size = self.container.sizeHint()

        total_width = content_size.width() + self._outer_margin * 2
        total_height = content_size.height() + self._outer_margin * 2

        final_global_x = anchor_origin_global.x() - total_width - 10
        final_global_y = anchor_origin_global.y() - total_height - 10
        final_pos_global = QPoint(final_global_x, final_global_y)

        start_width = max(24, min(total_width, int(total_width * 0.25)))
        start_height = max(24, min(total_height, int(total_height * 0.10)))

        offset_x = 16
        offset_y = 16

        start_global_x = anchor_origin_global.x() - start_width + offset_x
        start_global_y = anchor_origin_global.y() - start_height + offset_y

        start_pos_global = QPoint(start_global_x, start_global_y)

        start_pos_local = parent_widget.mapFromGlobal(start_pos_global)
        final_pos_local = parent_widget.mapFromGlobal(final_pos_global)

        start_rect = QRect(start_pos_local, QSize(start_width, start_height))
        final_rect = QRect(final_pos_local, QSize(total_width, total_height))

        self.setGeometry(start_rect)
        self.show()
        self.raise_()

        anim_geo = QPropertyAnimation(self, b"geometry", self)
        anim_geo.setDuration(AppConstants.TEXT_SETTINGS_FLYOUT_ANIMATION_DURATION_MS)
        anim_geo.setStartValue(start_rect)
        anim_geo.setEndValue(final_rect)
        anim_geo.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim_geo.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _update_translations(self):
        self.size_label.setText(tr("Font Size:", self._current_language))
        self.weight_label.setText(tr("Bold", self._current_language))
        self.opacity_label.setText(tr("Opacity:", self._current_language))
        self.color_label.setText(tr("Color:", self._current_language))
        self.bg_color_label.setText(tr("Background:", self._current_language))
        self.checkbox_text_bg_label.setText(tr("Draw text background", self._current_language))
        self.pos_group_label.setText(tr("Text Position:", self._current_language))
        self.radio_pos_edges.setText(tr("At Edges", self._current_language))
        self.radio_pos_split_line.setText(tr("Near Split Line", self._current_language))

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        content_rect = self.rect().adjusted(
         self._outer_margin,
         self._outer_margin,
         -self._outer_margin,
         -self._outer_margin
        )
        self.container.setGeometry(content_rect)
