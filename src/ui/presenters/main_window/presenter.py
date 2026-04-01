import logging

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QWidget

from core.main_controller import MainController
from core.plugin_system.ui_integration import PluginUIRegistry
from core.store import Store
from ui.main_window_ui import Ui_ImageComparisonApp
from ui.presenters.main_window.connections import (
    connect_event_handler_signals as connect_event_handler_signals_impl,
    connect_signals as connect_signals_impl,
    handle_global_mouse_press,
    on_font_flyout_closed,
    on_interpolation_combo_clicked,
    repopulate_flyouts,
)
from ui.presenters.main_window.actions import (
    hide_orientation_popup,
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
)
from ui.presenters.main_window.workspace import (
    configure_workspace_actions,
    initialize_workspace_state,
    sync_session_mode,
    sync_video_session_view,
    sync_workspace_tabs,
)
from ui.presenters.main_window.features import MainWindowFeatureSet
from ui.presenters.ui_update_batcher import UIUpdateBatcher

logger = logging.getLogger("ImproveImgSLI")

class MainWindowPresenter(QObject):
    def __init__(
        self,
        main_window_app: QWidget,
        ui: Ui_ImageComparisonApp,
        store: Store,
        main_controller: MainController,
        features: MainWindowFeatureSet,
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

        self.features = features
        self.ui_manager = features.ui_manager
        self.ui_batcher = UIUpdateBatcher(self)

        from shared_toolkit.ui.widgets.composite.text_settings_flyout import (
            FontSettingsFlyout,
        )

        self.font_settings_flyout = FontSettingsFlyout(main_window_app)
        self.font_settings_flyout.hide()
        self.ui_manager.transient.font_settings_flyout = self.font_settings_flyout

        self._orientation_popup = None
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(self._hide_orientation_popup)

        initialize_workspace_state(self)

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
            ):
                self.main_controller.layout.setup_ui_reference(
                    self.ui, self.main_window_app
                )
        except Exception:
            logger.exception(
                "MainWindowPresenter.__init__: error during initialization"
            )

    def get_feature(self, feature_name: str):
        mapping = {
            "image_canvas": self.features.image_canvas,
            "toolbar": self.features.toolbar,
            "export": self.features.export,
            "settings": self.features.settings,
        }
        return mapping.get(feature_name)

    def schedule_canvas_update(self):
        self.features.image_canvas.schedule_update()

    def invalidate_canvas_render_state(self, clear_magnifier: bool = False):
        self.features.image_canvas.invalidate_render_state(
            clear_magnifier=clear_magnifier
        )

    def finish_resize_delay(self):
        self.features.image_canvas.lifecycle.finish_resize_delay()

    def shutdown(self):
        self.features.export.shutdown()

    def set_magnifier_orientation_checked(self, is_checked: bool) -> None:
        self.ui.btn_magnifier_orientation.setChecked(is_checked, emit_signal=False)

    def toggle_magnifier_panel_visibility(self, is_visible: bool) -> None:
        self.ui.toggle_magnifier_panel_visibility(is_visible)

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

    def repopulate_flyouts(self):
        return repopulate_flyouts(self)

    def _apply_initial_settings_to_ui(self):
        return apply_initial_settings_to_ui(self)

    def _configure_workspace_actions(self):
        return configure_workspace_actions(self)

    def sync_workspace_tabs(self):
        return sync_workspace_tabs(self)

    def sync_session_mode(self):
        return sync_session_mode(self)

    def sync_video_session_view(self):
        return sync_video_session_view(self)

    def update_resolution_labels(self):
        self.ui_batcher.schedule_update("resolution")

    def _do_update_resolution_labels(self):
        return do_update_resolution_labels(self)

    def update_file_names_display(self):
        self.ui_batcher.schedule_update("file_names")

    def _do_update_file_names_display(self):
        return do_update_file_names_display(self)

    def check_name_lengths(self):
        self.features.toolbar.check_name_lengths()

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
        return self.features.image_canvas.get_current_label_dimensions()

    def update_minimum_window_size(self):
        self.features.image_canvas.update_minimum_window_size()

    def update_magnifier_orientation_button_state(self):
        self.features.toolbar.update_magnifier_orientation_button_state()

    def _update_interpolation_combo_box_ui(self):
        self.features.settings.update_interpolation_combo_box_ui()

    def _get_current_display_name(self, image_number: int) -> str:
        return get_current_display_name(self, image_number)

    def _get_current_score(self, image_number: int) -> int | None:
        return get_current_score(self, image_number)

    def _get_image_dimensions(self, image_number: int) -> tuple[int, int] | None:
        return get_image_dimensions(self, image_number)
