import asyncio
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
import time

import PIL.Image
from PyQt6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QAction,
    QDesktopServices,
    QIcon,
    QImage,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import QApplication, QLineEdit, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from shared_toolkit.core import setup_logging
from shared_toolkit.ui.managers.font_manager import FontManager
from core.app_state import AppState
from core.constants import AppConstants
from core.geometry import GeometryManager
from core.main_controller import MainController
from core.settings import SettingsManager
from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from events.app_event_handler import EventHandler
from image_processing.resize import resize_images_processor
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from ui.main_window_ui import Ui_ImageComparisonApp
from ui.presenters.main_window_presenter import MainWindowPresenter
from ui.widgets.composite.toast import ToastManager
from utils.resource_loader import (
    get_magnifier_drawing_coords,
    get_scaled_pixmap_dimensions,
    resource_path,
)
from workers.image_rendering_worker import ImageRenderingWorker
from shared_toolkit.workers import GenericWorker

try:
    from desktop_notifier import Attachment, DesktopNotifier, Icon, Urgency
except Exception:
    DesktopNotifier = None
    Icon = None
    Attachment = None
    Urgency = None

try:
    from ui.dialogs.settings_dialog import SettingsDialog
    _SETTINGS_DIALOG_AVAILABLE = True
except ImportError:
    logging.getLogger("ImproveImgSLI").warning("settings_dialog.py not found.")
    _SETTINGS_DIALOG_AVAILABLE = False

from resources import translations as translations_mod

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)

PIL.Image.MAX_IMAGE_PIXELS = None
logger = logging.getLogger("ImproveImgSLI")

class MainWindow(QWidget):
    _worker_finished_signal = pyqtSignal(dict, dict, int)
    _worker_error_signal = pyqtSignal(str)

    def __init__(self, parent=None, debug_mode: bool = False):
        super().__init__(parent)
        self.setObjectName("ImageComparisonApp")

        self._is_ui_stable = False

        self._previous_window_state = self.windowState()

        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))

        self.app_state = AppState()
        self.theme_manager = ThemeManager.get_instance()

        self.theme_manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
        qss_path = resource_path("resources/styles/base.qss")
        self.theme_manager.register_qss_path(qss_path)

        app = QApplication.instance()
        if app:
            self.theme_manager.apply_theme_to_app(app)
            self.theme_manager.theme_changed.connect(self._on_theme_changed)

        self.settings_manager = SettingsManager("improve-imgsli", "improve-imgsli")
        self.geometry_manager = GeometryManager(self, self.settings_manager.settings)

        from events.drag_drop_handler import DragAndDropService
        if DragAndDropService._instance is None:
            DragAndDropService._instance = DragAndDropService(self, self)

        self.settings_manager.load_all_settings(self.app_state)
        if debug_mode:
            self.app_state.debug_mode_enabled = True

        import os
        if os.getenv("IMPROVE_DEBUG", "0") == "1":
            self.app_state.debug_mode_enabled = True

        setup_logging("Improve-ImgSLI", self.app_state.debug_mode_enabled, "IMPROVE_DEBUG")

        try:
            from shared_toolkit.ui.managers.font_manager import FontManager
            FontManager.get_instance().apply_from_state(self.app_state)
        except Exception as e:
            logger.error(f"Failed to apply font from state: {e}", exc_info=True)

        self.ui = Ui_ImageComparisonApp()
        self.ui.setupUi(self)
        try:
            self.ui.install_rating_wheel_handlers()
        except Exception:
            pass

        try:
            from shared_toolkit.ui.managers.font_manager import FontManager
            FontManager.get_instance().set_font(
                FontManager.get_instance().get_current_mode(),
                FontManager.get_instance().get_current_family()
            )
        except Exception as e:
            logger.error(f"Failed to reapply font after UI creation: {e}", exc_info=True)

        self.tray_icon = None
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():

                icon_path = resource_path("resources/icons/icon.png")
                icon = QIcon(icon_path)

                if icon.isNull():
                    logger.warning(f"Could not load tray icon from {icon_path}")
                    icon = QIcon.fromTheme("application", QIcon())

                self.tray_icon = QSystemTrayIcon(icon, self)
                self.tray_icon.setToolTip("Improve-ImgSLI")

                tray_menu = QMenu(self)
                self._action_toggle = QAction("Показать/Скрыть окно", self)
                self._action_open_file = QAction("Открыть последний файл", self)
                self._action_open_folder = QAction("Открыть папку сохранения", self)
                self._action_quit = QAction("Выход", self)
                self._action_open_file.triggered.connect(self._open_last_saved_file)
                self._action_open_folder.triggered.connect(self._open_last_saved_folder)
                self._action_toggle.triggered.connect(self._toggle_main_window_visibility)
                self._action_quit.triggered.connect(QApplication.instance().quit)

                try:
                    has_saved = hasattr(self, "_last_saved_path") and os.path.isfile(getattr(self, "_last_saved_path"))
                except Exception:
                    has_saved = False
                self._action_open_file.setVisible(bool(has_saved))
                tray_menu.addAction(self._action_toggle)
                tray_menu.addSeparator()
                tray_menu.addAction(self._action_open_file)
                tray_menu.addAction(self._action_open_folder)
                tray_menu.addSeparator()
                tray_menu.addAction(self._action_quit)
                self.tray_icon.setContextMenu(tray_menu)

                self.tray_icon.activated.connect(self._on_tray_activated)
                self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)

                if not self.tray_icon.icon().isNull():
                    self.tray_icon.show()
        except Exception:
            self.tray_icon = None

        self.notifier = None
        self._notifier_loop: asyncio.AbstractEventLoop | None = None
        self._notifier_thread: threading.Thread | None = None
        try:
            if DesktopNotifier is not None and Icon is not None:
                app_icon_path = resource_path("resources/icons/icon.png")

                try:
                    abs_icon_path = Path(app_icon_path).resolve()

                    if not abs_icon_path.exists():
                        logger.warning(f"Notification icon not found: {abs_icon_path}")
                        icon_obj = None
                    else:
                        icon_obj = Icon(path=str(abs_icon_path))
                        logger.debug(f"DesktopNotifier initialized with icon: {abs_icon_path}")
                except Exception as e:
                    logger.warning(f"Could not create Icon object: {e}")
                    icon_obj = None

                self.notifier = DesktopNotifier(app_name="Improve-ImgSLI", app_icon=icon_obj)
                self._start_notifier_loop()
        except Exception as e:
            logger.error(f"Failed to initialize DesktopNotifier: {e}")

        self.main_controller = MainController(self.app_state, self, self.settings_manager)

        self.event_handler = EventHandler(self, self.app_state, None)

        self.presenter = MainWindowPresenter(
            self,
            self.ui,
            self.app_state,
            self.main_controller
        )
        self.event_handler.presenter = self.presenter
        self.main_controller.set_presenter(self.presenter)

        self.presenter.connect_event_handler_signals(self.event_handler)

        self.toast_manager = ToastManager(self, self.ui.image_label)
        self.save_task_counter = 0

        try:
            from shared_toolkit.ui.managers.font_manager import FontManager
            self.font_path_absolute = str(FontManager.get_instance()._built_in_font_path) if FontManager.get_instance().is_builtin_available() else None
        except Exception as e:
            logger.error(f"Failed to get font path: {e}", exc_info=True)
            self.font_path_absolute = None

        self.setAcceptDrops(True)

        self._update_scheduler_timer = QTimer(self)
        self._update_scheduler_timer.setSingleShot(True)
        self._update_scheduler_timer.setInterval(10)
        self._update_scheduler_timer.timeout.connect(self.update_comparison_if_needed)

        self._debounced_resize_timer = QTimer(self)
        self._debounced_resize_timer.setSingleShot(True)
        self._debounced_resize_timer.setInterval(150)
        self._debounced_resize_timer.timeout.connect(self._handle_debounced_resize)

        self.current_displayed_pixmap: QPixmap | None = None
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)
        self._worker_finished_signal.connect(self._on_worker_finished)
        self._worker_error_signal.connect(self._on_worker_error)
        self.render_start_times = {}
        self.current_rendering_task_id = 0
        self.current_scaling_task_id = 0
        self._reflagged_flyout = None

        self.installEventFilter(self.event_handler)
        self.ui.image_label.installEventFilter(self.event_handler)
        QApplication.instance().installEventFilter(self.event_handler)

        QTimer.singleShot(0, self.initialize_application)

    def initialize_application(self):
        self.geometry_manager.load_and_apply()

        theme_from_env = os.getenv("APP_THEME", "auto").lower()
        final_theme_setting = theme_from_env
        if final_theme_setting == "auto":
            final_theme_setting = self.app_state.theme

        self.apply_application_theme(final_theme_setting)

        try:
            from shared_toolkit.ui.managers.font_manager import FontManager
            FontManager.get_instance().apply_from_state(self.app_state)
        except Exception as e:
            logger.error(f"Failed to apply font from state: {e}", exc_info=True)

        self._update_image_label_background()

        self.main_controller.initialize_app_display()
        self.ui.reapply_button_styles()

    def apply_application_theme(self, theme_name: str):
        app = QApplication.instance()
        self.theme_manager.set_theme(theme_name, app)

        if self.app_state.theme != theme_name:
            self.app_state.theme = theme_name

        self.ui.reapply_button_styles()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            is_maximizing = self.windowState() & Qt.WindowState.WindowMaximized
            was_maximized = event.oldState() & Qt.WindowState.WindowMaximized

            if is_maximizing != was_maximized:
                if self.current_displayed_pixmap:
                    self.ui.image_label.clear()
                    self.current_displayed_pixmap = None
                QTimer.singleShot(0, self.schedule_update)

    def _handle_debounced_resize(self):
        if self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = False
            self.schedule_update()
        if not self.isMaximized() and not self.isFullScreen() and hasattr(self, 'geometry_manager'):
            try:
                self.geometry_manager.update_normal_geometry_if_needed()
            except Exception:
                pass

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.presenter.ui_manager.unified_flyout.hide()

        if not self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = True

        self.ui.update_drag_overlays(
            self.app_state.is_horizontal,
            self.ui.drag_overlay1.isVisible()
        )

        self._debounced_resize_timer.start()

    def closeEvent(self, event: QEvent):
        self.geometry_manager.update_normal_geometry_if_needed()
        self.geometry_manager.save_on_close()
        self.settings_manager.save_all_settings(self.app_state)

        try:
            if hasattr(self, 'event_handler'):
                try:
                    if QApplication.instance():
                        QApplication.instance().removeEventFilter(self.event_handler)
                except Exception:
                    pass
                try:
                    if hasattr(self.ui, 'image_label'):
                        self.ui.image_label.removeEventFilter(self.event_handler)
                except Exception:
                    pass
                try:
                    if hasattr(self.event_handler, 'movement_timer') and self.event_handler.movement_timer.isActive():
                        self.event_handler.movement_timer.stop()
                except Exception:
                    pass
                try:
                    if hasattr(self.event_handler, 'resize_timer') and self.event_handler.resize_timer.isActive():
                        self.event_handler.resize_timer.stop()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                try:
                    self.tray_icon.hide()
                except Exception:
                    pass
                try:
                    self.tray_icon.setContextMenu(None)
                except Exception:
                    pass
                try:
                    self.tray_icon.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            loop = getattr(self, "_notifier_loop", None)
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
        except Exception:
            pass
        try:
            th = getattr(self, "_notifier_thread", None)
            if th is not None and th.is_alive():
                th.join(timeout=1.0)
        except Exception:
            pass

        try:
            if hasattr(self, 'thread_pool') and self.thread_pool:
                self.thread_pool.waitForDone()
        except Exception:
            pass

        super().closeEvent(event)

    def moveEvent(self, event: QEvent):
        super().moveEvent(event)
        self.presenter.ui_manager.unified_flyout.hide()
        if not self.isMaximized() and not self.isFullScreen() and hasattr(self, 'geometry_manager'):
            try:
                self.geometry_manager.update_normal_geometry_if_needed()
            except Exception:
                pass

    def showEvent(self, event: QEvent):
        super().showEvent(event)

        if not getattr(self, '_is_ui_stable', False):
             QTimer.singleShot(50, self._set_ui_stable)

    def _set_ui_stable(self):
        self._is_ui_stable = True
        self.schedule_update()

    def hideEvent(self, event: QEvent):
        super().hideEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        self.clear_input_focus()
        super().mousePressEvent(event)

    def clear_input_focus(self):
        focused_widget = self.focusWidget()
        if not focused_widget:
            return

        is_edit_name1 = focused_widget == self.ui.edit_name1
        is_edit_name2 = focused_widget == self.ui.edit_name2

        if is_edit_name1 or is_edit_name2:
            focused_widget.clearFocus()

    def schedule_update(self):
        if not self._update_scheduler_timer.isActive():
            self._update_scheduler_timer.start()

    def _update_image_label_background(self):
        if not hasattr(self.ui, "image_label"):
            return
        bg_color = self.theme_manager.get_color("label.image.background")
        palette = self.ui.image_label.palette()
        palette.setColor(self.ui.image_label.backgroundRole(), bg_color)
        self.ui.image_label.setPalette(palette)

    def update_comparison_if_needed(self) -> bool:
        if not getattr(self, '_is_ui_stable', False):
            return False

        if self.app_state.resize_in_progress:
            return False
        if self.app_state.showing_single_image_mode != 0:
            image_to_show = (
                self.app_state.original_image1
                if self.app_state.showing_single_image_mode == 1
                else self.app_state.original_image2
            )
            self._display_single_image_on_label(image_to_show)
            return False

        if not self.app_state.original_image1 or not self.app_state.original_image2:
            if self.current_displayed_pixmap is not None:
                self.ui.image_label.clear()
                self.current_displayed_pixmap = None
            self.app_state.pixmap_width, self.app_state.pixmap_height = (0, 0)
            return False

        label_width, label_height = self.presenter.get_current_label_dimensions()
        if label_width <= 1 or label_height <= 1:
            return False

        source1 = self.app_state.full_res_image1 or self.app_state.original_image1
        source2 = self.app_state.full_res_image2 or self.app_state.original_image2

        if not source1 or not source2:
            if self.current_displayed_pixmap is not None:
                self.ui.image_label.clear()
                self.current_displayed_pixmap = None
            return False

        last_source1_id = getattr(self.app_state, '_last_source1_id', 0)
        last_source2_id = getattr(self.app_state, '_last_source2_id', 0)

        if (not self.app_state.image1 or not self.app_state.image2 or
            last_source1_id != id(source1) or last_source2_id != id(source2)):

            try:

                cache_key = (self.app_state.image1_path, self.app_state.image2_path)

                if cache_key in self.app_state._unified_image_cache:
                    unified1, unified2 = self.app_state._unified_image_cache[cache_key]
                    self.app_state.image1, self.app_state.image2 = unified1, unified2
                    setattr(self.app_state, '_last_source1_id', id(source1))
                    setattr(self.app_state, '_last_source2_id', id(source2))

                    if not self.app_state._display_cache_image1 or not self.app_state._display_cache_image2:
                        self._create_preview_cache_async(unified1, unified2)

                    self.app_state._scaled_image1_for_display = None
                    self.app_state._scaled_image2_for_display = None
                    self.app_state._cached_scaled_image_dims = None
                else:

                    if getattr(self.app_state, '_unification_in_progress', False):

                        if self.app_state.image1 and self.app_state.image2:

                            pass
                        else:

                            return False
                    else:

                        if not self.app_state.image1 or not self.app_state.image2:
                            return False

                        setattr(self.app_state, '_last_source1_id', id(source1))
                        setattr(self.app_state, '_last_source2_id', id(source2))
            except Exception:
                return False

        if self.app_state._display_cache_image1 and self.app_state._display_cache_image2:
            source_for_widget_resize1, source_for_widget_resize2 = (
                self.app_state._display_cache_image1, self.app_state._display_cache_image2,
            )
        else:
            source_for_widget_resize1, source_for_widget_resize2 = (
                self.app_state.image1, self.app_state.image2,
            )
        scaled_w, scaled_h = get_scaled_pixmap_dimensions(source_for_widget_resize1, source_for_widget_resize2, label_width, label_height)
        if scaled_w <= 0 or scaled_h <= 0:
            return False

        cache_is_valid = False
        if self.app_state.scaled_image1_for_display and self.app_state._cached_scaled_image_dims:
            cached_w, cached_h = self.app_state._cached_scaled_image_dims
            if abs(cached_w - scaled_w) < 2 and abs(cached_h - scaled_h) < 2:
                cache_is_valid = True

        if not cache_is_valid:

            unification_in_progress = getattr(self.app_state, '_unification_in_progress', False)
            is_very_small = (scaled_w * scaled_h < 1000000)

            if is_very_small and not unification_in_progress:

                try:
                    self.app_state.scaled_image1_for_display = source_for_widget_resize1.resize((scaled_w, scaled_h), PIL.Image.Resampling.BILINEAR)
                    self.app_state.scaled_image2_for_display = source_for_widget_resize2.resize((scaled_w, scaled_h), PIL.Image.Resampling.BILINEAR)
                    self.app_state._cached_scaled_image_dims = (scaled_w, scaled_h)
                except Exception:
                    return False
            else:

                try:

                    self.current_scaling_task_id += 1
                    scaling_task_id = self.current_scaling_task_id

                    worker = GenericWorker(
                        self._scale_images_for_display_worker_task,
                        source_for_widget_resize1.copy(),
                        source_for_widget_resize2.copy(),
                        scaled_w,
                        scaled_h,
                        scaling_task_id,
                    )
                    worker.signals.result.connect(self._on_display_scaling_ready)

                    priority = 0 if (self.app_state.is_interactive_mode or unification_in_progress) else 1
                    self.thread_pool.start(worker, priority=priority)
                    return False
                except Exception:
                    return False

        pixmap_w, pixmap_h = self.app_state._cached_scaled_image_dims
        self.app_state.pixmap_width, self.app_state.pixmap_height = pixmap_w, pixmap_h
        img_x, img_y = (label_width - pixmap_w) // 2, (label_height - pixmap_h) // 2
        self.app_state.image_display_rect_on_label = QRect(img_x, img_y, pixmap_w, pixmap_h)

        app_state_copy = self.app_state.copy_for_worker()

        magnifier_coords = get_magnifier_drawing_coords(
            app_state=self.app_state,
            drawing_width=pixmap_w,
            drawing_height=pixmap_h,
            container_width=label_width,
            container_height=label_height,
        ) if self.app_state.use_magnifier else None

        current_name1_text, current_name2_text = self.app_state.get_current_display_name(1), self.app_state.get_current_display_name(2)

        self.current_rendering_task_id += 1

        render_params = {
            "app_state_copy": app_state_copy,
            "image1_scaled_for_display": self.app_state.scaled_image1_for_display,
            "image2_scaled_for_display": self.app_state.scaled_image2_for_display,

            "original_image1_pil": (self.app_state.full_res_image1 or self.app_state.original_image1),
            "original_image2_pil": (self.app_state.full_res_image2 or self.app_state.original_image2),
            "magnifier_coords": magnifier_coords,
            "font_path_absolute": str(FontManager.get_instance()._built_in_font_path) if FontManager.get_instance().is_builtin_available() else None,
            "file_name1_text": current_name1_text,
            "file_name2_text": current_name2_text,
            "finished_signal": self._worker_finished_signal,
            "error_signal": self._worker_error_signal,
            "task_id": self.current_rendering_task_id,
            "label_dims": (label_width, label_height),
        }

        self.render_start_times[self.current_rendering_task_id] = time.perf_counter()
        worker = ImageRenderingWorker(render_params)
        priority = 1 if not self.app_state.is_interactive_mode else 0
        self.thread_pool.start(worker, priority=priority)
        return True

    @pyqtSlot(dict, dict, int)
    def _on_worker_finished(self, result_payload: dict, params: dict, finished_task_id: int):
        start_time = self.render_start_times.pop(finished_task_id, None)
        task_was_interactive = params["app_state_copy"].is_interactive_mode
        is_stale = (
            (self.app_state.is_interactive_mode and not task_was_interactive) or
            (not self.app_state.is_interactive_mode and task_was_interactive) or
            (not self.app_state.is_interactive_mode and finished_task_id < self.current_rendering_task_id)
        )
        if is_stale:
            return

        if self.app_state.showing_single_image_mode != 0:
            return

        final_canvas_pil = result_payload.get("final_canvas")
        padding_left, padding_top = result_payload.get("padding_left", 0), result_payload.get("padding_top", 0)

        magnifier_bbox = result_payload.get("magnifier_bbox")
        if magnifier_bbox and isinstance(magnifier_bbox, QRect):
            target_image_rect_in_label = self.app_state.image_display_rect_on_label
            draw_x = target_image_rect_in_label.x() - padding_left
            draw_y = target_image_rect_in_label.y() - padding_top

            final_bbox_on_label = magnifier_bbox.translated(draw_x, draw_y)

            combined_center = result_payload.get("combined_center")

            if combined_center and isinstance(combined_center, QPoint):
                self.app_state.is_magnifier_combined = True

                self.app_state.magnifier_screen_center = combined_center + QPoint(draw_x, draw_y)

                self.app_state.magnifier_screen_size = min(final_bbox_on_label.width(), final_bbox_on_label.height())
            else:

                self.app_state.magnifier_screen_center = final_bbox_on_label.center()
                self.app_state.magnifier_screen_size = max(final_bbox_on_label.width(), final_bbox_on_label.height())
                app_state_copy = params["app_state_copy"]
                should_combine = app_state_copy.magnifier_spacing_relative_visual < AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
                self.app_state.is_magnifier_combined = should_combine

        else:
            self.app_state.magnifier_screen_center = QPoint()
            self.app_state.magnifier_screen_size = 0
            self.app_state.is_magnifier_combined = False

        if not final_canvas_pil:
            return

        try:
            data = final_canvas_pil.tobytes("raw", "RGBA")
            bytes_per_line = final_canvas_pil.width * 4
            qimage = QImage(data, final_canvas_pil.width, final_canvas_pil.height, bytes_per_line, QImage.Format.Format_RGBA8888)
            qimage = qimage.copy()
            if qimage.isNull():
                raise ValueError("QImage null after conversion from PIL.")

            canvas_pixmap = QPixmap.fromImage(qimage)
            if canvas_pixmap.isNull():
                raise ValueError("QPixmap for canvas is null.")

            label_width, label_height = params.get("label_dims", (self.ui.image_label.width(), self.ui.image_label.height()))
            final_pixmap_for_label = QPixmap(label_width, label_height)
            final_pixmap_for_label.fill(Qt.GlobalColor.transparent)
            painter = QPainter(final_pixmap_for_label)
            target_image_rect_in_label = self.app_state.image_display_rect_on_label
            draw_x, draw_y = target_image_rect_in_label.x() - padding_left, target_image_rect_in_label.y() - padding_top
            painter.drawPixmap(QPoint(draw_x, draw_y), canvas_pixmap)
            painter.end()

            self.ui.image_label.setPixmap(final_pixmap_for_label)
            self.current_displayed_pixmap = final_pixmap_for_label.copy()
            self.app_state.pixmap_width, self.app_state.pixmap_height = target_image_rect_in_label.width(), target_image_rect_in_label.height()
        except Exception as e:
            logger.error(f"Error converting/displaying image: {e}", exc_info=True)

    @pyqtSlot(str)
    def _on_worker_error(self, error_message: str):

        try:
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_toast(
                    error_message or tr("Произошла ошибка", self.app_state.current_language),
                    duration=5000,
                    success=False
                )
                return
        except Exception:
            pass

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(tr("Error", self.app_state.current_language))
        msg_box.setText(error_message or tr("Произошла ошибка", self.app_state.current_language))
        self.theme_manager.apply_theme_to_dialog(msg_box)
        msg_box.exec()

    def _scale_images_for_display_worker_task(self, img1: PIL.Image.Image, img2: PIL.Image.Image, w: int, h: int, task_id: int):
        try:
            img1_s = img1.resize((w, h), PIL.Image.Resampling.BILINEAR)
            img2_s = img2.resize((w, h), PIL.Image.Resampling.BILINEAR)
            return img1_s, img2_s, w, h, task_id
        except Exception as e:
            logger.error(f"Scaling worker failed: {e}", exc_info=True)
            return None

    @pyqtSlot(object)
    def _on_display_scaling_ready(self, result):
        try:
            if not result:
                return
            if isinstance(result, tuple) and len(result) == 5:
                img1_s, img2_s, w, h, task_id = result

                if int(task_id) != int(self.current_scaling_task_id):
                    return

                if img1_s and img2_s and w > 0 and h > 0:

                    label_w, label_h = self.presenter.get_current_label_dimensions()
                    src1 = self.app_state._display_cache_image1
                    src2 = self.app_state._display_cache_image2
                    if not src1 or not src2 or label_w <= 1 or label_h <= 1:
                        return
                    desired_w, desired_h = get_scaled_pixmap_dimensions(src1, src2, label_w, label_h)
                    if abs(desired_w - w) > 1 or abs(desired_h - h) > 1:
                        return

                    self.app_state.scaled_image1_for_display = img1_s
                    self.app_state.scaled_image2_for_display = img2_s
                    self.app_state._cached_scaled_image_dims = (w, h)
                    self.schedule_update()
        except Exception as e:
            logger.error(f"Error handling display scaling result: {e}", exc_info=True)

    def _display_single_image_on_label(self, pil_image_to_display: PIL.Image.Image | None):
        if not hasattr(self.ui, "image_label"):
            return
        try:
            if pil_image_to_display is None or pil_image_to_display.width <= 0 or pil_image_to_display.height <= 0:
                if self.ui.image_label.pixmap() is not None: self.ui.image_label.clear()
                self.current_displayed_pixmap = None
                return

            label_width, label_height = self.presenter.get_current_label_dimensions()
            rgba_image = pil_image_to_display.convert("RGBA")
            data = rgba_image.tobytes("raw", "RGBA")
            bytes_per_line = rgba_image.width * 4
            qimage = QImage(data, rgba_image.width, rgba_image.height, bytes_per_line, QImage.Format.Format_RGBA8888)
            qimage = qimage.copy()
            original_pixmap = QPixmap.fromImage(qimage)
            scaled_pixmap = original_pixmap.scaled(label_width, label_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            self.ui.image_label.setPixmap(scaled_pixmap)
            self.current_displayed_pixmap = scaled_pixmap.copy()
        except Exception:
            if self.ui.image_label.pixmap() is not None: self.ui.image_label.clear()
            self.current_displayed_pixmap = None

    def _on_drag_finished(self, source_data: dict, dest_data: dict | None):
        pass

    def update_tray_actions_visibility(self):
        try:
            if hasattr(self, "_action_open_file"):
                path = getattr(self, "_last_saved_path", None)
                self._action_open_file.setVisible(bool(path and os.path.isfile(path)))
        except Exception:
            pass

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_and_raise()

    def _show_and_raise(self):
        try:
            if not self.isVisible():
                self.show()

            self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def _toggle_main_window_visibility(self):
        try:
            if self.isVisible() and not self.isMinimized():
                self.showMinimized()
            else:
                self._show_and_raise()
        except Exception:
            pass

    def _open_last_saved_file(self):
        path = getattr(self, "_last_saved_path", None)
        if path and os.path.isfile(path):
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except Exception:
                pass

    def _open_last_saved_folder(self):
        path = getattr(self, "_last_saved_path", None)
        folder = None
        if path:
            folder = os.path.dirname(path)
        if not folder or not os.path.isdir(folder):

            folder = self.app_state.export_default_dir or self._get_os_default_downloads()
        if folder and os.path.isdir(folder):
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            except Exception:
                pass

    def _on_tray_message_clicked(self):

        self._open_last_saved_folder()

    def _get_os_default_downloads(self) -> str:
        home = os.path.expanduser("~")
        candidates = []
        try:
            user_dirs = os.path.join(home, ".config", "user-dirs.dirs")
            if os.path.exists(user_dirs):
                with open(user_dirs, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("XDG_DOWNLOAD_DIR"):
                            parts = line.split("=")
                            if len(parts) == 2:
                                path_val = parts[1].strip().strip('"')
                                path_val = path_val.replace("$HOME", home)
                                candidates.append(path_val)
                            break
        except Exception:
            pass
        candidates += [
            os.path.join(home, "Downloads"),
            os.path.join(home, "Загрузки"),
            home,
        ]
        for p in candidates:
            try:
                if os.path.isdir(p):
                    return p
            except Exception:
                continue
        return home

    def notify_system(self, title: str, message: str, image_path: str | None = None, timeout_ms: int = 4000):
        if not getattr(self.app_state, "system_notifications_enabled", True):
            return
        try:
            if self.notifier is not None and self._notifier_loop is not None:
                icon_obj = None
                attach_obj = None
                if image_path and isinstance(image_path, str):
                    path_obj = None
                    try:

                        path_abs = Path(image_path).resolve()
                        if path_abs.is_file():
                            path_obj = path_abs
                    except Exception as e:
                        logger.warning(f"Could not resolve absolute path for notification: {e}")

                    if path_obj:
                        if Icon is not None:
                            icon_obj = Icon(path=str(path_obj))
                        if Attachment is not None:
                            attach_obj = Attachment(path=str(path_obj))

                timeout_seconds = max(0, int(round((timeout_ms or 0) / 1000)))
                coro = self.notifier.send(
                    title=title,
                    message=message,
                    icon=icon_obj,
                    attachment=attach_obj,
                    urgency=Urgency.Normal if Urgency is not None else None,
                    timeout=timeout_seconds,
                )
                try:
                    asyncio.run_coroutine_threadsafe(coro, self._notifier_loop)
                    logger.debug(f"DesktopNotifier notification sent: {title}")
                    return
                except Exception as e:
                    logger.error(f"DesktopNotifier scheduling error: {e}")
        except Exception as e:
            logger.error(f"DesktopNotifier send error: {e}")

        try:
            if self.tray_icon and self.tray_icon.isVisible():

                if QSystemTrayIcon.supportsMessages():
                    self.tray_icon.showMessage(
                        title,
                        message,
                        QSystemTrayIcon.MessageIcon.Information,
                        max(0, int(timeout_ms))
                    )
                    logger.debug(f"TrayIcon notification sent: {title}")
                    return
                else:
                    logger.warning("QSystemTrayIcon does not support messages on this platform")
        except Exception as e:
            logger.error(f"Tray notification error (fallback): {e}")

        if sys.platform != 'win32':
            try:
                notify_send = None
                for cand in ("notify-send", "/usr/bin/notify-send", "/bin/notify-send"):
                    if os.path.isfile(cand) and os.access(cand, os.X_OK):
                        notify_send = cand
                        break
                if notify_send:
                    cmd = [notify_send, "-a", "Improve-ImgSLI"]
                    if isinstance(timeout_ms, int) and timeout_ms > 0:
                        cmd += ["-t", str(timeout_ms)]
                    if image_path and isinstance(image_path, str) and os.path.isfile(image_path):
                        cmd += ["-i", os.path.abspath(image_path)]
                    else:
                        try:
                            cmd += ["-i", resource_path("resources/icons/icon.png")]
                        except Exception:
                            pass
                    cmd += [title or "", message or ""]
                    subprocess.Popen(cmd)
                    logger.debug(f"notify-send notification sent: {title}")
            except Exception as e:
                logger.error(f"notify-send fallback error: {e}")

    def _start_notifier_loop(self):
        try:
            if self._notifier_loop is not None:
                return
            loop = asyncio.new_event_loop()
            def _runner():
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_forever()
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass
            th = threading.Thread(target=_runner, name="NotifierAsyncLoop", daemon=True)
            th.start()
            self._notifier_loop = loop
            self._notifier_thread = th
        except Exception as e:
            logger.error(f"Failed to start notifier loop: {e}")

    @pyqtSlot(object)
    def _on_image_loaded_from_worker(self, result):
        try:

            self.main_controller._on_image_loaded(result)
        except Exception as e:
            logger.error(f"Error handling loaded image in UI thread: {e}", exc_info=True)

    def _on_theme_changed(self):
        self._update_image_label_background()

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _create_preview_cache_async(self, img1: PIL.Image.Image, img2: PIL.Image.Image):
        try:
            worker = GenericWorker(
                self._create_preview_cache_worker_task,
                img1.copy(),
                img2.copy(),
                self.app_state.display_resolution_limit,
            )
            worker.signals.result.connect(self._on_preview_cache_ready)
            self.thread_pool.start(worker, priority=1)
        except Exception as e:
            logger.error(f"Error creating preview cache async: {e}")

    def _create_preview_cache_worker_task(self, img1: PIL.Image.Image, img2: PIL.Image.Image, limit: int):
        try:
            w, h = img1.size
            if limit > 0 and max(w, h) > limit:
                if w > h:
                    new_w, new_h = limit, int(h * limit / w)
                else:
                    new_h, new_w = limit, int(w * limit / h)
                cached_img1 = img1.resize((new_w, new_h), PIL.Image.Resampling.LANCZOS)
                cached_img2 = img2.resize((new_w, new_h), PIL.Image.Resampling.LANCZOS)
            else:
                cached_img1, cached_img2 = img1, img2
            return cached_img1, cached_img2
        except Exception as e:
            logger.error(f"Error creating preview cache: {e}")
            return None

    def _on_preview_cache_ready(self, result):
        if not result:
            return
        try:
            cached_img1, cached_img2 = result
            if cached_img1 and cached_img2:
                self.app_state._display_cache_image1 = cached_img1
                self.app_state._display_cache_image2 = cached_img2

                current_cache_params = (
                    id(self.app_state.image1),
                    id(self.app_state.image2),
                    self.app_state.display_resolution_limit,
                )
                self.app_state._last_display_cache_params = current_cache_params
                self.schedule_update()
        except Exception as e:
            logger.error(f"Error handling preview cache: {e}")
