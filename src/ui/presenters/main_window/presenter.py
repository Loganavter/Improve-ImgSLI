import logging

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QWidget

from core.main_controller import MainController
from core.store import Store
from ui.main_window.ui import Ui_ImageComparisonApp
from ui.presenters.main_window.actions import (
    hide_orientation_popup,
)
from ui.presenters.main_window.connections import (
    connect_event_handler_signals as connect_event_handler_signals_impl,
)
from ui.presenters.main_window.connections import (
    connect_signals as connect_signals_impl,
)
from ui.presenters.main_window.connections import (
    repopulate_flyouts,
)
from ui.presenters.main_window.features import MainWindowFeatureSet
from ui.presenters.main_window.state import (
    apply_initial_settings_to_ui,
    on_language_changed,
)
from ui.presenters.main_window.workspace import (
    configure_workspace_actions,
    initialize_workspace_state,
    sync_session_mode,
    sync_workspace_tabs,
)
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
    ):
        super().__init__(main_window_app)
        self.main_window_app = main_window_app
        self.ui = ui
        self.store = store
        self.main_controller = main_controller
        self.session_manager = (
            main_controller.session_manager if main_controller else None
        )
        self.event_bus = main_controller.event_bus if main_controller else None

        self.features = features
        self.ui_manager = features.ui_manager
        self.ui_batcher = UIUpdateBatcher(self)

        from ui.widgets.font_settings_flyout import FontSettingsFlyout

        self.font_settings_flyout = FontSettingsFlyout(main_window_app)
        self.font_settings_flyout.hide()
        self.ui_manager.transient.font_settings_flyout = self.font_settings_flyout

        self._orientation_popup = None
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(self._hide_orientation_popup)

        initialize_workspace_state(self)
        self._bind_workspace_tabs_translation()

        self._connect_signals()

        try:
            if self.main_controller is not None:
                self.main_controller.layout.setup_ui_reference(
                    self.ui, self.main_window_app
                )

            self._apply_initial_settings_to_ui()
            self._configure_workspace_actions()
            self.sync_workspace_tabs()
            self.sync_session_mode()
<<<<<<< Updated upstream
=======
            self.update_slider_tooltips()
            self.ui.reapply_button_styles()
>>>>>>> Stashed changes
            self.repopulate_flyouts()
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
        # Reached from generic window-resize/settle handling
        # (`ui/main_window/window.py::schedule_update`), which fires
        # regardless of which tab is active. This isn't just a startup-
        # materialization race: session_picker has no canvas at all, so
        # while it's the active tab this can never resolve — not only
        # "not yet", but "not applicable".
        schedule_update = getattr(self.features.image_canvas, "schedule_update", None)
        if schedule_update is not None:
            schedule_update()

    def invalidate_canvas_render_state(self, clear_overlay_state: bool = False):
        # May be called from session lifecycle while session_picker is
        # active — no canvas exists yet/lazily unresolved then. Same
        # tolerance as schedule_canvas_update (see above).
        method = getattr(
            self.features.image_canvas, "invalidate_render_state", None
        )
        if method is not None:
            method(clear_overlay_state=clear_overlay_state)

    def shutdown(self):
        method = getattr(self.features.export, "shutdown", None)
        if method is not None:
            try:
                method()
            except AttributeError:
                # LazyTabService raises AttributeError when the tab was
                # never activated (export_presenter not yet materialized)
                # — matches lifecycle.py's "Ошибка при отмене экспортов"
                # degrade path, not a real error at shutdown.
                logger.debug(
                    "shutdown: export_presenter not available yet (lazy, tab never shown)"
                )

    def _connect_signals(self):
        return connect_signals_impl(self)

    def _connect_button_action(self, button, action_id, fallback):
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

    def update_resolution_labels(self):
        self.ui_batcher.schedule_update("resolution")

    def _do_update_resolution_labels(self):
        chrome = self._chrome_sync()
        if chrome is not None:
            chrome.do_update_resolution_labels(self)

    def update_file_names_display(self):
        self.ui_batcher.schedule_update("file_names")

    def _do_update_file_names_display(self):
        chrome = self._chrome_sync()
        if chrome is not None:
            chrome.do_update_file_names_display(self)

    def _do_sync_zoom_indicator(self):
        chrome = self._chrome_sync()
        if chrome is not None:
            chrome.do_sync_zoom_indicator(self)

    def check_name_lengths(self):
        self.features.toolbar.check_name_lengths()

    def update_combobox_displays(self):
        self.ui_batcher.schedule_update("combobox")

    def _do_update_combobox_displays(self):
        chrome = self._chrome_sync()
        if chrome is not None:
            chrome.do_update_combobox_displays(self)

    def update_rating_displays(self):
        self.ui_batcher.schedule_update("ratings")

    def _do_update_rating_displays(self):
        chrome = self._chrome_sync()
        if chrome is not None:
            chrome.do_update_rating_displays(self)

    def _chrome_sync(self):
        toolbar = getattr(self.features, "toolbar", None)
        if toolbar is None:
            return None
        return getattr(toolbar, "chrome_sync", None)

    def on_language_changed(self):
        return on_language_changed(self)

    def _bind_workspace_tabs_translation(self):
        from sli_ui_toolkit.i18n import translatable_callback

        translatable_callback(
            self.ui.workspace_tabs,
            lambda _lang: self.sync_workspace_tabs(),
        )

    def _hide_orientation_popup(self):
        return hide_orientation_popup(self)

    def get_current_label_dimensions(self) -> tuple[int, int]:
        method = getattr(
            self.features.image_canvas, "get_current_label_dimensions", None
        )
        if method is not None:
            try:
                return method()
            except AttributeError:
                pass
        return (0, 0)

    def update_minimum_window_size(self):
        method = getattr(
            self.features.image_canvas, "update_minimum_window_size", None
        )
        if method is not None:
            try:
                method()
            except AttributeError:
                pass

    def _update_interpolation_combo_box_ui(self):
        self.features.settings.update_interpolation_combo_box_ui()