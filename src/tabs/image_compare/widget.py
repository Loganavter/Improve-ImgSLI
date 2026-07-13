"""Root widget for the image_compare tab.

The widget is constructed empty by the tab during ``create_page`` (early,
before the host has built the primitive widgets it owns). The host calls
``assemble(ui)`` once those primitives exist; the builder then populates
this widget with the full image-compare layout tree.
"""

from __future__ import annotations

from typing import Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.widgets import ThemedWidget

from sli_ui_toolkit.i18n import tr
from tabs.contract import TabContext
from ui.theming import resolve_theme_color


class ImageCompareWidget(ThemedWidget, QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        context: TabContext | None = None,
    ):
        super().__init__(parent)
        self._context = context
        self._assembled = False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
        super().on_theme_changed()

    def assemble(self, ui) -> None:
        if self._assembled:
            return
        from tabs.image_compare.ui.layout import ImageCompareLayoutBuilder

        ImageCompareLayoutBuilder(self, ui).build_into(self)
        self._assembled = True
        self._wire_transition_mask_release()

    def _wire_transition_mask_release(self) -> None:
        canvas = getattr(self, "image_label", None)
        signal = getattr(canvas, "firstVisualFrameReady", None)
        if signal is None:
            return
        try:
            signal.connect(self._on_first_visual_frame)
        except Exception:
            pass

    def _on_first_visual_frame(self) -> None:
        context = self._context
        services = getattr(context, "services", None) if context else None
        if not services:
            return
        mask = services.get("workspace.transition_mask")
        if mask is None:
            return
        try:
            mask.release()
        except Exception:
            pass

    # --- image_compare's own update/toggle API (moved out of the host shell) ---

    def apply_icon_sizes(self) -> None:
        self.btn_quick_save.setIconSizePx(24)
        self.help_button.setIconSizePx(24)
        self.btn_clear_list1.setIconSizePx(22)
        self.btn_clear_list2.setIconSizePx(22)
        self.btn_divider_color.setIconSizePx(22)
        self.btn_divider_width.setIconSizePx(22)
        self.btn_magnifier_divider_width.setIconSizePx(22)
        self.btn_magnifier_guides_width.setIconSizePx(22)

    def reapply_button_styles(self) -> None:
        import logging
        logger = logging.getLogger("ImproveImgSLI")
        self.apply_icon_sizes()
        for i, btn in enumerate((self.btn_settings, self.btn_quick_save, self.help_button)):
            btn._diag_tag = f"ic_{i}_{type(btn).__name__}"
            logger.warning(
                "DIAG requesting repaint tag=%s visible=%s",
                btn._diag_tag, btn.isVisible(),
            )
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    def toggle_edit_layout_visibility(self, checked: bool):
        self.edit_layout_widget.setVisible(bool(checked))

    def toggle_magnifier_panel_visibility(self, visible: bool):
        self.magnifier_settings_panel.setVisible(visible)
        try:
            self.magnifier_settings_panel.updateGeometry()
            parent = self.magnifier_settings_panel.parentWidget()
            if parent and parent.layout():
                parent.layout().activate()
        except Exception:
            pass
        main_window = getattr(self._context, "main_window", None)
        if main_window is not None and hasattr(main_window, "schedule_update"):
            QTimer.singleShot(0, main_window.schedule_update)

    def is_drag_overlay_visible(self) -> bool:
        return self.image_label.is_drag_overlay_visible()

    def update_drag_overlays(self, horizontal: bool = False, visible: bool = False):
        if not self.image_label.isVisible():
            self.drag_overlay.hide()
            return
        lang = self._context.settings.current_language if self._context else "en"
        text1 = tr("ui.drop_images_1_here", lang)
        text2 = tr("ui.drop_images_2_here", lang)
        self.image_label.set_drag_overlay_state(
            visible=False,
            horizontal=horizontal,
            text1=text1,
            text2=text2,
        )
        self.drag_overlay.set_overlay_state(
            visible=visible,
            target_rect=self.image_label.geometry(),
            horizontal=horizontal,
            text1=text1,
            text2=text2,
        )

    def update_resolution_labels(
        self, res1_text: str, tooltip1: str, res2_text: str, tooltip2: str
    ):
        self.resolution_label1.setText(res1_text)
        self.resolution_label2.setText(res2_text)

    def update_file_names_display(
        self,
        name1_text: str,
        name2_text: str,
        is_horizontal: bool,
        current_language: str,
        show_labels: bool,
    ):
        if not show_labels:
            self._hide_file_name_labels()
            return
        self._show_file_name_labels()
        prefix1, prefix2 = self._get_file_name_prefixes(is_horizontal, current_language)
        max_text_width = self._get_max_file_name_width()
        font_metrics = QFontMetrics(self.file_name_label1.font())
        self.file_name_label1.setText(
            self._elide_file_name_text(
                f"{prefix1}: {name1_text}", font_metrics, max_text_width
            )
        )
        self.file_name_label2.setText(
            self._elide_file_name_text(
                f"{prefix2}: {name2_text}", font_metrics, max_text_width
            )
        )

    def update_name_length_warning(
        self, warning_text: str, tooltip_text: str, visible: bool
    ):
        self.length_warning_label.setText(warning_text)
        self.length_warning_label.setVisible(visible)

    def update_color_button_tooltip(self, color_name: str, current_language: str):
        tooltip = tr("tooltip.magnifier_colors", current_language)
        for attr in (
            "btn_magnifier_color_settings",
            "btn_magnifier_color_settings_beginner",
        ):
            button = getattr(self, attr, None)
            if button is not None:
                button.setToolTip(tooltip)

    def update_combobox_display(
        self,
        image_number: int,
        count: int,
        current_index: int,
        text: str,
        full_path: str,
    ):
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        document = self._context.store.get_session_state_slot("document")
        combobox.updateState(
            count,
            current_index,
            text=text,
            items=[
                item.display_name
                for item in (
                    document.image_list1
                    if image_number == 1
                    else document.image_list2
                )
            ],
        )

    def update_slider_tooltips(
        self,
        speed_value: float,
        magnifier_size: float,
        capture_size: float,
        current_language: str,
    ):
        self.slider_size.setToolTip(
            tr(
                "tooltip.magnifier_size_slider",
                current_language,
                value=int(round(float(magnifier_size) * 100)),
            )
        )
        self.slider_capture.setToolTip(
            tr(
                "tooltip.capture_size_slider",
                current_language,
                value=int(round(float(capture_size) * 100)),
            )
        )
        self.slider_speed.setToolTip(
            tr(
                "tooltip.magnifier_speed_slider",
                current_language,
                value=int(round(float(speed_value) * 100)),
            )
        )

    def update_zoom_indicator(self, zoom: float):
        pan_x = float(getattr(self.image_label, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(self.image_label, "pan_offset_y", 0.0) or 0.0)
        self.zoom_indicator.update_zoom(zoom, pan_x, pan_y)

    def update_rating_display(
        self, image_number: int, score: int | None, current_language: str
    ):
        label = self.label_rating1 if image_number == 1 else self.label_rating2
        if score is not None:
            label.setText(f"<b>{score}</b>")
            label.setVisible(True)
        else:
            label.setText("–")
            label.setVisible(False)

    def install_rating_wheel_handlers(self):
        self.label_rating1.wheelEvent = self._make_rating_wheel_handler(1)
        self.label_rating2.wheelEvent = self._make_rating_wheel_handler(2)

    def _make_rating_wheel_handler(self, image_number: int):
        def _wheel(event):
            delta = event.angleDelta().y()
            if delta == 0:
                return
            session_ctrl = self._get_session_controller()
            if session_ctrl is None:
                return
            current_idx = self._get_current_rating_index(image_number)
            if current_idx < 0:
                return
            if delta > 0:
                session_ctrl.increment_rating(image_number, current_idx)
            else:
                session_ctrl.decrement_rating(image_number, current_idx)
            self._refresh_rating_displays()
            event.accept()

        return _wheel

    def _get_session_controller(self):
        main_window = getattr(self._context, "main_window", None)
        controller = getattr(main_window, "main_controller", None)
        if not controller or not hasattr(controller, "sessions"):
            return None
        return controller.sessions

    def _get_current_rating_index(self, image_number: int) -> int:
        state = self._context.store
        return (
            state.document.current_index1
            if image_number == 1
            else state.document.current_index2
        )

    def _refresh_rating_displays(self):
        main_window = getattr(self._context, "main_window", None)
        presenter = getattr(main_window, "presenter", None)
        if presenter is not None:
            presenter.update_rating_displays()

    def _hide_file_name_labels(self):
        self.file_name_label1.setVisible(False)
        self.file_name_label2.setVisible(False)
        self.file_name_label1.setText("")
        self.file_name_label2.setText("")

    def _show_file_name_labels(self):
        self.file_name_label1.setVisible(True)
        self.file_name_label2.setVisible(True)

    def _get_file_name_prefixes(
        self, is_horizontal: bool, current_language: str
    ) -> Tuple[str, str]:
        if not is_horizontal:
            return (
                tr("common.position.left", current_language),
                tr("common.position.right", current_language),
            )
        return (
            tr("common.position.top", current_language),
            tr("common.position.bottom", current_language),
        )

    def _get_max_file_name_width(self) -> int:
        main_window = getattr(self._context, "main_window", None)
        window_width = main_window.width() if main_window else 800
        return window_width // 2 - 20

    def _elide_file_name_text(
        self, text: str, font_metrics: QFontMetrics, max_text_width: int
    ) -> str:
        if font_metrics.horizontalAdvance(text) > max_text_width:
            return font_metrics.elidedText(
                text, Qt.TextElideMode.ElideRight, max_text_width
            )
        return text
