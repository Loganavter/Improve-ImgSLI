import logging

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QWidget

from core.main_controller import MainController
from core.plugin_system.ui_integration import PluginUIRegistry
from core.store import Store
from plugins.export.presenter import ExportPresenter
from plugins.settings.presenter import SettingsPresenter
from plugins.video_editor.model import VideoSessionModel
from ui.main_window_ui import Ui_ImageComparisonApp
from ui.managers.ui_manager import UIManager
from ui.presenters.image_canvas_presenter import ImageCanvasPresenter
from ui.presenters.main_window.connections import (
    connect_event_handler_signals as connect_event_handler_signals_impl,
    connect_signals as connect_signals_impl,
    handle_global_mouse_press,
    on_font_flyout_closed,
    on_interpolation_combo_clicked,
    repopulate_flyouts,
)
from ui.presenters.main_window.helpers import (
    hide_orientation_popup,
    on_color_option_clicked,
    on_error_occurred,
    on_magnifier_element_hover_ended,
    on_magnifier_element_hovered,
    on_magnifier_guides_thickness_changed,
    on_magnifier_guides_toggled,
    on_ui_update_requested,
    on_update_requested,
    open_image_dialog,
    start_interactive_movement as start_interactive_movement_impl,
    stop_interactive_movement as stop_interactive_movement_impl,
    update_image_name,
)
from ui.presenters.main_window.state import (
    apply_initial_settings_to_ui,
    do_update_combobox_displays,
    do_update_file_names_display,
    do_update_rating_displays,
    do_update_resolution_labels,
    do_update_slider_tooltips,
    get_current_display_name,
    get_current_score,
    get_image_dimensions,
    on_language_changed,
    on_store_state_changed,
)
from ui.presenters.toolbar_presenter import ToolbarPresenter
from ui.presenters.ui_update_batcher import UIUpdateBatcher

logger = logging.getLogger("ImproveImgSLI")

class MainWindowPresenter(QObject):
    def __init__(
        self,
        main_window_app: QWidget,
        ui: Ui_ImageComparisonApp,
        store: Store,
        main_controller: MainController,
        plugin_ui_registry: PluginUIRegistry | None = None,
    ):
        super().__init__(main_window_app)
        self.main_window_app = main_window_app
        self.ui = ui
        self.store = store
        self.main_controller = main_controller
        self.session_manager = (
            main_controller.session_manager if main_controller else None
        )
        self.plugin_ui_registry = plugin_ui_registry
        self.event_bus = main_controller.event_bus if main_controller else None

        self.ui_manager = UIManager(
            store,
            main_controller,
            ui,
            main_window_app,
            plugin_ui_registry=plugin_ui_registry,
        )
        self.ui_batcher = UIUpdateBatcher(self)
        self.image_canvas_presenter = ImageCanvasPresenter(
            store, main_controller, ui, main_window_app
        )
        self.toolbar_presenter = ToolbarPresenter(
            store, main_controller, ui, main_window_app, ui_manager=self.ui_manager
        )
        self.export_presenter = ExportPresenter(
            store,
            main_controller,
            self.ui_manager,
            main_window_app,
            main_window_app.font_path_absolute,
        )
        self.settings_presenter = SettingsPresenter(
            store, main_controller, self.ui_manager, main_window_app
        )

        from shared_toolkit.ui.widgets.composite.text_settings_flyout import (
            FontSettingsFlyout,
        )

        self.font_settings_flyout = FontSettingsFlyout(main_window_app)
        self.font_settings_flyout.hide()
        self.ui_manager.font_settings_flyout = self.font_settings_flyout

        self._orientation_popup = None
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(self._hide_orientation_popup)

        self._file_dialog = None
        self._first_dialog_load_pending = True
        self._video_session_model: VideoSessionModel | None = None

        self._connect_signals()

        try:
            self._apply_initial_settings_to_ui()
            self.ui.update_translations(self.store.settings.current_language)
            self._configure_workspace_actions()
            self.sync_workspace_tabs()
            self.sync_session_mode()
            self.update_slider_tooltips()
            self.ui.reapply_button_styles()
            self.repopulate_flyouts()

            if (
                self.main_controller is not None
                and self.main_controller.plugin_coordinator is not None
            ):
                layout_plugin = self.main_controller.plugin_coordinator.get_plugin(
                    "layout"
                )
                if layout_plugin is not None:
                    layout_plugin.setup_ui_reference(self.ui, self.main_window_app)
        except Exception:
            logger.exception(
                "MainWindowPresenter.__init__: error during initialization"
            )

    def _connect_signals(self):
        return connect_signals_impl(self)

    def _connect_button_action(self, button, action_id, fallback):
        handler = None
        if self.plugin_ui_registry:
            handler = self.plugin_ui_registry.get_action(action_id)
        if handler:
            button.clicked.connect(handler)
        else:
            button.clicked.connect(fallback)

    def connect_event_handler_signals(self, event_handler):
        return connect_event_handler_signals_impl(self, event_handler)

    def _on_interpolation_combo_clicked(self):
        return on_interpolation_combo_clicked(self)

    def repopulate_flyouts(self):
        return repopulate_flyouts(self)

    def _handle_global_mouse_press(self, event):
        return handle_global_mouse_press(self, event)

    def _on_font_flyout_closed(self):
        return on_font_flyout_closed(self)

    def _apply_initial_settings_to_ui(self):
        return apply_initial_settings_to_ui(self)

    def _on_store_state_changed(self, domain: str):
        return on_store_state_changed(self, domain)

    def _configure_workspace_actions(self):
        actions = []
        if self.main_controller:
            for blueprint in self.main_controller.list_session_blueprints():
                label = blueprint.resolved_title() or blueprint.session_type
                actions.append((label, blueprint.session_type))
        self.ui.btn_new_session.set_actions(actions)

    def sync_workspace_tabs(self):
        if not self.session_manager:
            return
        active = self.session_manager.get_active_session()
        self.ui.sync_workspace_tabs(
            self.session_manager.list_sessions(),
            active.id if active else None,
        )
        self.sync_session_mode()

    def sync_session_mode(self):
        if not self.session_manager:
            return
        active = self.session_manager.get_active_session()
        session_type = active.session_type if active else "image_compare"
        session_title = active.title if active else None
        self.ui.sync_session_mode(session_type, session_title)
        self.sync_video_session_view()

    def sync_video_session_view(self):
        if not self.session_manager:
            return
        active = self.session_manager.get_active_session()
        if active is None or active.session_type != "video_compare":
            self._video_session_model = None
            self.ui.video_session_widget.clear()
            return

        if (
            self._video_session_model is None
            or self._video_session_model.session_id != active.id
        ):
            self._video_session_model = VideoSessionModel(
                store=self.store,
                session_manager=self.session_manager,
                main_controller=self.main_controller,
                session_id=active.id,
            )

        self.ui.video_session_widget.set_snapshot(
            self._video_session_model.get_snapshot()
        )

    def _on_workspace_tab_changed(self, index: int):
        if index < 0:
            return
        session_id = self.ui.workspace_tabs.tabData(index)
        if session_id and self.main_controller:
            self.main_controller.switch_workspace_session(session_id)

    def _on_workspace_session_triggered(self, action):
        session_type = action.data()
        if not session_type or not self.main_controller:
            return
        self.main_controller.create_workspace_session(session_type, activate=True)

    def _on_video_session_advance_requested(self):
        if self._video_session_model is None:
            return
        self._video_session_model.advance_timeline()

    def _on_video_session_attach_resource_requested(self):
        if self._video_session_model is None:
            return
        self._video_session_model.attach_decoder()

    def _on_video_session_create_image_compare_requested(self):
        if self._video_session_model is None:
            return
        self._video_session_model.open_image_compare()

    def _open_image_dialog(self, image_number: int):
        return open_image_dialog(self, image_number)

    def update_resolution_labels(self):
        self.ui_batcher.schedule_update("resolution")

    def _do_update_resolution_labels(self):
        return do_update_resolution_labels(self)

    def update_file_names_display(self):
        self.ui_batcher.schedule_update("file_names")

    def _do_update_file_names_display(self):
        return do_update_file_names_display(self)

    def check_name_lengths(self):
        self.toolbar_presenter.check_name_lengths()

    def update_combobox_displays(self):
        self.ui_batcher.schedule_update("combobox")

    def _do_update_combobox_displays(self):
        return do_update_combobox_displays(self)

    def update_slider_tooltips(self):
        self.ui_batcher.schedule_update("slider_tooltips")

    def _do_update_slider_tooltips(self):
        return do_update_slider_tooltips(self)

    def update_rating_displays(self):
        self.ui_batcher.schedule_update("ratings")

    def _do_update_rating_displays(self):
        return do_update_rating_displays(self)

    def on_language_changed(self):
        return on_language_changed(self)

    def _hide_orientation_popup(self):
        return hide_orientation_popup(self)

    def get_current_label_dimensions(self) -> tuple[int, int]:
        return self.image_canvas_presenter.get_current_label_dimensions()

    def update_minimum_window_size(self):
        self.image_canvas_presenter.update_minimum_window_size()

    def _finish_resize_delay(self):
        self.image_canvas_presenter._finish_resize_delay()

    def update_magnifier_orientation_button_state(self):
        self.toolbar_presenter.update_magnifier_orientation_button_state()

    def _update_interpolation_combo_box_ui(self):
        self.settings_presenter.update_interpolation_combo_box_ui()

    def _get_current_display_name(self, image_number: int) -> str:
        return get_current_display_name(self, image_number)

    def _get_current_score(self, image_number: int) -> int | None:
        return get_current_score(self, image_number)

    def _get_image_dimensions(self, image_number: int) -> tuple[int, int] | None:
        return get_image_dimensions(self, image_number)

    def _on_error_occurred(self, error_message: str):
        return on_error_occurred(self, error_message)

    def _on_update_requested(self):
        return on_update_requested(self)

    def _on_ui_update_requested(self, components: list):
        return on_ui_update_requested(self, components)

    def update_image_name(self, image_number: int, name: str):
        return update_image_name(self, image_number, name)

    def start_interactive_movement(self):
        return start_interactive_movement_impl(self)

    def stop_interactive_movement(self):
        return stop_interactive_movement_impl(self)

    def _on_magnifier_guides_toggled(self, checked: bool):
        return on_magnifier_guides_toggled(self, checked)

    def _on_magnifier_guides_thickness_changed(self, thickness: int):
        return on_magnifier_guides_thickness_changed(self, thickness)

    def _on_magnifier_element_hovered(self, element_name: str):
        return on_magnifier_element_hovered(self, element_name)

    def _on_magnifier_element_hover_ended(self):
        return on_magnifier_element_hover_ended(self)

    def _on_color_option_clicked(self, option: str):
        return on_color_option_clicked(self, option)
