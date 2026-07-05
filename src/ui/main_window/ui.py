import logging
from typing import Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QStackedWidget,
    QWidget,
)

from resources.translations import tr
from ui.icon_manager import AppIcon
from ui.main_window.layouts import LayoutComposer
from ui.widgets.workspace_tab_strip import WorkspaceTabStrip

logger = logging.getLogger("ImproveImgSLI")

_SESSION_TYPE_KEYS = {
    "multi_compare": "workspace.session_types.multi_compare",
    "session_picker": "workspace.session_types.session_picker",
}


class Ui_ImageComparisonApp:
    """Owns widget construction and exposes the update API used by the presenter.

    Layout assembly is delegated to LayoutComposer (ui/main_window/layouts.py).
    """

    def setupUi(self, main_window: QWidget):
        self.main_window = main_window
        from resources.translations import emit_language_changed

        emit_language_changed(self._current_language())
        self._create_static_widgets(main_window)
        self._layout = LayoutComposer(self)
        self._layout.build(main_window)
        self._init_drag_overlays()
        from ui.main_window.translations import install_translations

        install_translations(self)

    def _create_static_widgets(self, main_window: QWidget):
        self.workspace_tabs = WorkspaceTabStrip(
            add_icon=AppIcon.ADD,
            close_icon=AppIcon.CLOSE,
            parent=main_window,
        )
        self.btn_new_session = self.workspace_tabs.add_button
        self.workspace_stack = QStackedWidget(main_window)
        self._tab_registry = None
        self.legacy_tab_widgets = {}

    def _init_drag_overlays(self):
        self.image_label.set_drag_overlay_state(False)
        if hasattr(self, "drag_overlay"):
            self.drag_overlay.hide()

    def _current_language(self) -> str:
        try:
            return self.main_window.store.settings.current_language
        except AttributeError:
            return "en"

    def sync_workspace_tabs(self, sessions, active_session_id):
        tabs = self.workspace_tabs
        language = self._current_language()
        tabs.blockSignals(True)
        try:
            sessions = list(sessions)
            target_count = len(sessions)

            while tabs.count() > target_count:
                tabs.removeTab(tabs.count() - 1)

            active_index = -1
            for index, session in enumerate(sessions):
                tab_text = self._localized_session_title(session, language)
                session_type_label = self._localized_session_type_label(
                    session.session_type,
                    language,
                )
                tooltip = f"{tab_text} [{session_type_label}]"
                if index < tabs.count():
                    if tabs.tabText(index) != tab_text:
                        tabs.setTabText(index, tab_text)
                    if tabs.tabData(index) != session.id:
                        tabs.setTabData(index, session.id)
                    tabs.setTabToolTip(index, tooltip)
                else:
                    tabs.addTab(tab_text)
                    tabs.setTabData(index, session.id)
                    tabs.setTabToolTip(index, tooltip)
                if session.id == active_session_id:
                    active_index = index

            if active_index >= 0 and tabs.currentIndex() != active_index:
                tabs.setCurrentIndex(active_index)
            tabs.refresh_close_buttons()
        finally:
            tabs.blockSignals(False)

    def _localized_session_title(self, session, language: str) -> str:
        title = getattr(session, "title", "") or ""
        session_type = getattr(session, "session_type", "")
        default_prefix = session_type.replace("_", " ").title()
        if title != default_prefix and not title.startswith(f"{default_prefix} "):
            return title
        suffix = title.removeprefix(default_prefix)
        if suffix and not suffix.strip().isdigit():
            return title
        return f"{self._localized_session_type_label(session_type, language)}{suffix}"

    def _localized_session_type_label(self, session_type: str, language: str) -> str:
        tab_registry = getattr(self, "_tab_registry", None)
        if tab_registry is not None:
            tab = tab_registry.get_tab(session_type)
            if tab is not None:
                localized = tab.localized_display_name(language)
                if localized and localized != session_type:
                    return localized
        key = _SESSION_TYPE_KEYS.get(session_type)
        if key is None:
            return session_type
        translated = tr(key, language)
        return session_type if translated == key else translated

    def sync_session_mode(self, session_type: str, session_title: str | None = None):
        tab_page = (
            self._tab_registry.get_page(session_type) if self._tab_registry else None
        )
        if tab_page is not None:
            self.workspace_stack.setCurrentWidget(tab_page)
            if self._tab_registry:
                self._tab_registry.activate(session_type)

        handled = (
            self._tab_registry.apply_host_session_mode(
                session_type,
                self,
                session_title=session_title,
            )
            if self._tab_registry
            else False
        )
        if not handled:
            self.edit_layout_widget.setVisible(False)

    def reapply_button_styles(self):
        self._layout.apply_icon_sizes()
        for btn in [self.btn_settings, self.btn_quick_save, self.help_button]:
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
        try:
            if hasattr(self.main_window, "schedule_update"):
                QTimer.singleShot(0, self.main_window.schedule_update)
        except Exception:
            pass

    def is_drag_overlay_visible(self) -> bool:
        return self.image_label.is_drag_overlay_visible()

    def get_current_label_dimensions(self) -> Tuple[int, int]:
        return (
            self.image_label.contentsRect().width(),
            self.image_label.contentsRect().height(),
        )

    def update_drag_overlays(self, horizontal: bool = False, visible: bool = False):
        if not self.image_label.isVisible():
            if hasattr(self, "drag_overlay"):
                self.drag_overlay.hide()
            return
        lang = self.main_window.store.settings.current_language
        text1 = tr("ui.drop_images_1_here", lang)
        text2 = tr("ui.drop_images_2_here", lang)
        self.image_label.set_drag_overlay_state(
            visible=False,
            horizontal=horizontal,
            text1=text1,
            text2=text2,
        )
        if hasattr(self, "drag_overlay"):
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
        combobox.updateState(
            count,
            current_index,
            text=text,
            items=[
                item.display_name
                for item in (
                    self.main_window.store.document.image_list1
                    if image_number == 1
                    else self.main_window.store.document.image_list2
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
        controller = getattr(self.main_window, "main_controller", None)
        if not controller or not hasattr(controller, "sessions"):
            return None
        return controller.sessions

    def _get_current_rating_index(self, image_number: int) -> int:
        state = self.main_window.store
        return (
            state.document.current_index1
            if image_number == 1
            else state.document.current_index2
        )

    def _refresh_rating_displays(self):
        if hasattr(self.main_window, "presenter"):
            self.main_window.presenter.update_rating_displays()

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
        window_width = (
            self.main_window.width()
            if hasattr(self, "main_window") and self.main_window
            else 800
        )
        return window_width // 2 - 20

    def _elide_file_name_text(
        self, text: str, font_metrics: QFontMetrics, max_text_width: int
    ) -> str:
        if font_metrics.horizontalAdvance(text) > max_text_width:
            return font_metrics.elidedText(
                text, Qt.TextElideMode.ElideRight, max_text_width
            )
        return text
