from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402



























from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from resources.translations import tr
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import BaseFlyout, Switch

from ui.widgets.color import ColorSwatch
from ui.widgets.slider_hint import ValueSlider


class FontSettingsFlyout(BaseFlyout):
    settings_changed = Signal(int, int, QColor, QColor, bool, str, int)
    closed = Signal()
    interaction_started = Signal(str)
    interaction_finished = Signal(str)

    # Identity for host ``GroupShowPolicy``.
    flyout_group = "font_settings"

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.current_language = "en"
        self._active_dialog = False

        self.content_layout.setContentsMargins(scaled_px(10), scaled_px(10), scaled_px(10), scaled_px(10))
        self.content_layout.setSpacing(scaled_px(8))

        self.size_slider = self._slider(50, 400, 100)
        self.weight_slider = self._slider(0, 100, 50)
        self.opacity_slider = self._slider(5, 100, 100)
        self.color_swatch = ColorSwatch(QColor("#ffffff"), parent=self)
        self.bg_color_swatch = ColorSwatch(QColor("#000000"), parent=self)
        self.draw_bg_switch = Switch(parent=self)

        self._size_label = self.add_row("", self.size_slider, label_pixel_size=13)
        self._weight_label = self.add_row("", self.weight_slider, label_pixel_size=13)
        self._opacity_label = self.add_row("", self.opacity_slider, label_pixel_size=13)
        self._color_label = self.add_row("", self.color_swatch, label_pixel_size=13)
        self._bg_label = self.add_row("", self.bg_color_swatch, label_pixel_size=13)
        self._draw_bg_label = self.add_row("", self.draw_bg_switch, label_pixel_size=13)
        self._placement_label, self._pos_group, self._pos_radios = self.add_radio_row(
            "",
            [
                ("", "edges"),
                ("", "split_line"),
            ],
            default="edges",
        )
        self._placement_label.setPixelSize(13)
        self._tag_find_action_chrome()
        self._retranslate()

        for slider in (self.size_slider, self.weight_slider, self.opacity_slider):
            slider.valueChanged.connect(self._emit_settings_changed)
        self.color_swatch.colorChanged.connect(lambda *_: self._emit_settings_changed())
        self.bg_color_swatch.colorChanged.connect(lambda *_: self._emit_settings_changed())
        self.draw_bg_switch.checkedChanged.connect(self._emit_settings_changed)
        for radio in self._pos_radios.values():
            radio.toggled.connect(lambda *_: self._emit_settings_changed())

    def _tag_find_action_chrome(self) -> None:
        from ui.widgets.font_settings_search import tag_font_settings_flyout

        tag_font_settings_flyout(self, include_placement=True)

    @staticmethod
    def _slider(minimum: int, maximum: int, value: int) -> ValueSlider:
        slider = ValueSlider(
            Qt.Orientation.Horizontal,
            # Raw value (font size / weight / opacity), not percent-of-span.
            hint_formatter=lambda s: str(s.value()),
        )
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setMinimumWidth(scaled_px(160))
        return slider

    def _tr(self, key: str) -> str:
        value = tr(key, self.current_language)
        return value if value != key else key.rsplit(".", 1)[-1].replace("_", " ").title()

    def _retranslate(self) -> None:
        self._size_label.setText(self._tr("label.font_size"))
        self._weight_label.setText(self._tr("label.bold"))
        self._opacity_label.setText(self._tr("label.opacity"))
        self._color_label.setText(self._tr("label.color"))
        self._bg_label.setText(self._tr("label.background"))
        self._draw_bg_label.setText(self._tr("label.draw_text_background"))
        self._placement_label.setText(self._tr("label.text_position"))
        edges = self._pos_radios.get("edges")
        if edges is not None:
            edges.setText(self._tr("label.position_edges"))
        split = self._pos_radios.get("split_line")
        if split is not None:
            split.setText(self._tr("label.position_split_line"))

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
            self._retranslate()
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
            animation="slide-fade",
            # "diagonal" (not "auto"): "auto" splits one fixed distance
            # across the anchor->flyout unit vector, so with a narrow icon
            # button as the anchor and this much wider panel, the vertical
            # component of that vector dominates and the horizontal slide
            # shrinks to a few barely-visible pixels -- looks like it's
            # sliding straight up out of the button's top-center, not left.
            # "diagonal" gives each axis the full distance independently.
            animation_axis="diagonal",
        )

    def has_active_dialog(self) -> bool:
        return self._active_dialog

    def restore_focus_on_hide(self) -> bool:
        # Same as context menus: activateWindow/setFocus on hide re-enters
        # focusChanged and can jerk the canvas / desync toggle state.
        return False

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


FontSettingsFlyout.inspect_spec = InspectSpec(
    family="FontSettingsFlyout",
    state=(
        SpecField("font_size", lambda w: w.size_slider.value()),
        SpecField("font_weight", lambda w: w.weight_slider.value()),
        SpecField("opacity", lambda w: w.opacity_slider.value()),
        SpecField("draw_background", lambda w: w.draw_bg_switch.isChecked()),
        SpecField("placement", "_placement", private=True),
        SpecField("foreground", lambda w: w.color_swatch.color()),
        SpecField("background", lambda w: w.bg_color_swatch.color()),
    ),
    docs="docs/dev/APP_WIDGETS.md",
)


FontSettingsFlyout.inspect_spec = InspectSpec(
    family="FontSettingsFlyout",
    state=(
        SpecField("font_size", lambda w: w.size_slider.value()),
        SpecField("font_weight", lambda w: w.weight_slider.value()),
        SpecField("opacity", lambda w: w.opacity_slider.value()),
        SpecField("draw_background", lambda w: w.draw_bg_switch.isChecked()),
        SpecField("placement", "_placement", private=True),
        SpecField("foreground", lambda w: w.color_swatch.color()),
        SpecField("background", lambda w: w.bg_color_swatch.color()),
    ),
    docs="docs/dev/widgets/font_settings_flyout.md",
)