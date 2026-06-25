from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from resources.translations import tr
from sli_ui_toolkit.widgets import BaseFlyout, Slider, Switch

from ui.widgets.color_swatch import ColorSwatch


class FontSettingsFlyout(BaseFlyout):
    settings_changed = Signal(int, int, QColor, QColor, bool, str, int)
    closed = Signal()
    interaction_started = Signal(str)
    interaction_finished = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.current_language = "en"
        self._active_dialog = False

        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(8)

        self.size_slider = self._slider(50, 400, 100)
        self.weight_slider = self._slider(0, 100, 50)
        self.opacity_slider = self._slider(5, 100, 100)
        self.color_swatch = ColorSwatch(QColor("#ffffff"), parent=self)
        self.bg_color_swatch = ColorSwatch(QColor("#000000"), parent=self)
        self.draw_bg_switch = Switch(parent=self)

        self._size_label = self.add_row(self._tr("label.font_size"), self.size_slider, label_pixel_size=13)
        self._weight_label = self.add_row(self._tr("label.bold"), self.weight_slider, label_pixel_size=13)
        self._opacity_label = self.add_row(self._tr("label.opacity"), self.opacity_slider, label_pixel_size=13)
        self._color_label = self.add_row(self._tr("label.color"), self.color_swatch, label_pixel_size=13)
        self._bg_label = self.add_row(self._tr("label.background"), self.bg_color_swatch, label_pixel_size=13)
        self._draw_bg_label = self.add_row(
            self._tr("label.background"),
            self.draw_bg_switch,
            label_pixel_size=13,
        )
        self._placement_label, self._pos_group, self._pos_radios = self.add_radio_row(
            self._tr("settings.text_position"),
            [
                (self._tr("settings.position_edges"), "edges"),
                (self._tr("settings.position_split_line"), "split_line"),
            ],
            default="edges",
        )
        self._placement_label.setPixelSize(13)

        for slider in (self.size_slider, self.weight_slider, self.opacity_slider):
            slider.valueChanged.connect(self._emit_settings_changed)
        self.color_swatch.colorChanged.connect(lambda *_: self._emit_settings_changed())
        self.bg_color_swatch.colorChanged.connect(lambda *_: self._emit_settings_changed())
        self.draw_bg_switch.checkedChanged.connect(self._emit_settings_changed)
        for radio in self._pos_radios.values():
            radio.toggled.connect(lambda *_: self._emit_settings_changed())

    @staticmethod
    def _slider(minimum: int, maximum: int, value: int) -> Slider:
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setMinimumWidth(160)
        return slider

    def _tr(self, key: str) -> str:
        value = tr(key, self.current_language)
        return value if value != key else key.rsplit(".", 1)[-1].replace("_", " ").title()

    def set_values(
        self,
        size: int,
        weight: int,
        color: QColor,
        bg_color: QColor,
        draw_bg: bool,
        placement: str,
        opacity: int,
        language: str | None = None,
    ) -> None:
        if language:
            self.current_language = language
        blockers = [
            QSignalBlocker(self.size_slider),
            QSignalBlocker(self.weight_slider),
            QSignalBlocker(self.opacity_slider),
            QSignalBlocker(self.color_swatch),
            QSignalBlocker(self.bg_color_swatch),
            QSignalBlocker(self.draw_bg_switch),
        ]
        try:
            self.size_slider.setValue(int(size))
            self.weight_slider.setValue(int(weight))
            self.opacity_slider.setValue(int(opacity))
            self.color_swatch.setColor(color)
            self.bg_color_swatch.setColor(bg_color)
            self.draw_bg_switch.setChecked(bool(draw_bg))
            radio = self._pos_radios.get(placement)
            if radio is not None:
                radio.setChecked(True)
        finally:
            del blockers

    def show_top_left_of(self, anchor_widget: QWidget) -> None:
        self.show_aligned(
            anchor_widget,
            anchor_point="top-left",
            flyout_point="bottom-right",
            offset=10,
            animation="slide",
        )

    def has_active_dialog(self) -> bool:
        return self._active_dialog

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.closed.emit()

    def _placement(self) -> str:
        for value, radio in self._pos_radios.items():
            if radio.isChecked():
                return value
        return "edges"

    def _emit_settings_changed(self, *_) -> None:
        self.settings_changed.emit(
            self.size_slider.value(),
            self.weight_slider.value(),
            self.color_swatch.color(),
            self.bg_color_swatch.color(),
            self.draw_bg_switch.isChecked(),
            self._placement(),
            self.opacity_slider.value(),
        )
