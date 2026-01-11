import logging
import time
import PIL.Image
from PyQt6.QtCore import QObject, QTimer, QSize, QRect, Qt, QPoint, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter
from PyQt6.QtWidgets import QSizePolicy

from core.store import Store
from events.image_label_event_handler import ImageLabelEventHandler
from events.window_event_handler import WindowEventHandler
from workers.image_rendering_worker import ImageRenderingWorker
from shared_toolkit.workers import GenericWorker
from utils.resource_loader import get_scaled_pixmap_dimensions, get_magnifier_drawing_coords
from toolkit.managers.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")

class ImageCanvasPresenter(QObject):

    _worker_finished_signal = pyqtSignal(dict, dict, int)
    _worker_error_signal = pyqtSignal(str)

    def __init__(
        self,
        store: Store,
        main_controller,
        ui,
        main_window_app,
        parent=None
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.main_window_app = main_window_app

        self.image_label_handler = ImageLabelEventHandler(
            store, main_controller, self
        )
        self.window_handler = WindowEventHandler(
            store, main_controller, ui, main_window_app
        )

        self.current_displayed_pixmap: QPixmap | None = None
        self.current_rendering_task_id = 0
        self.current_scaling_task_id = 0
        self._last_displayed_task_id = 0

        self._cached_base_pixmap: QPixmap | None = None
        self._cached_split_pos: float = -1.0
        self._cached_render_params: tuple | None = None

        self._pending_interactive_mode: bool | None = None

        self._update_scheduler_timer = QTimer(self)
        self._update_scheduler_timer.setSingleShot(True)

        target_fps = getattr(self.store.settings, 'video_recording_fps', 60)
        target_fps = max(10, min(144, target_fps))
        interval = int(1000 / target_fps)
        self._update_scheduler_timer.setInterval(interval)
        self._update_scheduler_timer.timeout.connect(self.update_comparison_if_needed)

        self._worker_finished_signal.connect(self._on_worker_finished)
        self._worker_error_signal.connect(self._on_worker_error)

    def connect_event_handler_signals(self, event_handler):
        event_handler.mouse_press_event_on_image_label_signal.connect(
            self.image_label_handler.handle_mouse_press
        )
        event_handler.mouse_move_event_on_image_label_signal.connect(
            self.image_label_handler.handle_mouse_move
        )
        event_handler.mouse_release_event_on_image_label_signal.connect(
            self.image_label_handler.handle_mouse_release
        )
        event_handler.keyboard_press_event_signal.connect(
            self.image_label_handler.handle_key_press
        )
        event_handler.keyboard_release_event_signal.connect(
            self.image_label_handler.handle_key_release
        )
        event_handler.mouse_wheel_event_on_image_label_signal.connect(
            self.image_label_handler.handle_wheel_scroll
        )
        event_handler.drag_enter_event_signal.connect(
            self.window_handler.handle_drag_enter
        )
        event_handler.drag_move_event_signal.connect(
            self.window_handler.handle_drag_move
        )
        event_handler.drag_leave_event_signal.connect(
            self.window_handler.handle_drag_leave
        )
        event_handler.drop_event_signal.connect(
            self.window_handler.handle_drop
        )
        event_handler.resize_event_signal.connect(
            self.window_handler.handle_resize
        )
        event_handler.close_event_signal.connect(
            self.window_handler.handle_close
        )

    def get_current_label_dimensions(self) -> tuple[int, int]:
        if hasattr(self.ui, "image_label"):
            size = self.ui.image_label.size()
            return (size.width(), size.height())
        return (0, 0)

    def update_minimum_window_size(self):
        layout = self.main_window_app.layout()
        if not layout or not hasattr(self.ui, "image_label"):
            return

        original_policy = self.ui.image_label.sizePolicy()
        temp_policy = QSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred
        )
        temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
        temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
        temp_policy.setVerticalPolicy(
            QSizePolicy.Policy.Preferred
            if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored
            else QSizePolicy.Policy.Ignored
        )
        temp_policy.setHorizontalPolicy(
            QSizePolicy.Policy.Preferred
            if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored
            else QSizePolicy.Policy.Ignored
        )

        try:
            self.ui.image_label.setSizePolicy(temp_policy)
            self.ui.image_label.updateGeometry()
            if layout:
                layout.invalidate()
                layout.activate()

            layout_hint_size = layout.sizeHint() if layout else QSize(250, 300)
            base_min_w, base_min_h = (250, 300)
            new_min_w = max(base_min_w, layout_hint_size.width())
            new_min_h = max(base_min_h, layout_hint_size.height())
            padding = 10
            new_min_w += padding
            new_min_h += padding
            current_min = self.main_window_app.minimumSize()
            if current_min.width() != new_min_w or current_min.height() != new_min_h:
                self.main_window_app.setMinimumSize(new_min_w, new_min_h)
        finally:
            if (hasattr(self.ui, "image_label") and
                    self.ui.image_label.sizePolicy() != original_policy):
                self.ui.image_label.setSizePolicy(original_policy)
                self.ui.image_label.updateGeometry()
                if layout:
                    layout.invalidate()
                    layout.activate()

    def schedule_update(self):
        if hasattr(self.main_window_app, '_closing') and self.main_window_app._closing:
            return

        is_interactive = self.store.viewport.is_interactive_mode

        if is_interactive:
            self._pending_interactive_mode = True

        if is_interactive:
            self._update_scheduler_timer.stop()
            result = self.update_comparison_if_needed()
            if result:
                self._pending_interactive_mode = None
        else:
            if not self._update_scheduler_timer.isActive():
                self._update_scheduler_timer.start()

    def update_comparison_if_needed(self) -> bool:
        if not getattr(self.main_window_app, '_is_ui_stable', False) or self.store.viewport.resize_in_progress:
            return False

        if not self.main_window_app.isVisible() or self.main_window_app.isMinimized():
            return False

        label_width, label_height = self.get_current_label_dimensions()

        if label_width <= 2 or label_height <= 2:
            return False

        if getattr(self.store.viewport, 'unification_in_progress', False):
            if self.store.viewport.image1 is None:
                return False

        source1 = self.store.document.full_res_image1 or self.store.document.preview_image1 or self.store.document.original_image1
        source2 = self.store.document.full_res_image2 or self.store.document.preview_image2 or self.store.document.original_image2

        if self.store.viewport.showing_single_image_mode != 0:
            image_to_show = source1 if self.store.viewport.showing_single_image_mode == 1 else source2
            self._display_single_image_on_label(image_to_show)
            return False

        if self.store.viewport.image1 is None or self.store.viewport.image2 is None or not source1 or not source2:
            self.ui.image_label.clear()
            self.current_displayed_pixmap = None
            return False

        last_source1_id = getattr(self.store.viewport, '_last_source1_id', 0)
        last_source2_id = getattr(self.store.viewport, '_last_source2_id', 0)

        if (not self.store.viewport.image1 or not self.store.viewport.image2 or
            last_source1_id != id(source1) or last_source2_id != id(source2)):

            cache_key = (self.store.document.image1_path, self.store.document.image2_path)
            cache = self.store.viewport.session_data.unified_image_cache
            if cache_key in cache:

                cache.move_to_end(cache_key)
                unified1, unified2 = cache[cache_key]
                self.store.viewport.image1, self.store.viewport.image2 = unified1, unified2
                setattr(self.store.viewport, '_last_source1_id', id(source1))
                setattr(self.store.viewport, '_last_source2_id', id(source2))

                if not self.store.viewport.display_cache_image1 or not self.store.viewport.display_cache_image2:
                    self._create_preview_cache_async(unified1, unified2)

                self.store.viewport.scaled_image1_for_display = None
                self.store.viewport.scaled_image2_for_display = None
                self.store.viewport.cached_scaled_image_dims = None

                if hasattr(self, '_last_render_params_dict'):
                    delattr(self, '_last_render_params_dict')
                if hasattr(self.store.viewport, '_last_render_params'):
                    delattr(self.store.viewport, '_last_render_params')
            else:
                return False

        if self.store.viewport.display_cache_image1 and self.store.viewport.display_cache_image2:
            src_resize1, src_resize2 = self.store.viewport.display_cache_image1, self.store.viewport.display_cache_image2
        else:
            src_resize1, src_resize2 = self.store.viewport.image1, self.store.viewport.image2

        scaled_w, scaled_h = get_scaled_pixmap_dimensions(src_resize1, src_resize2, label_width, label_height)
        if scaled_w <= 0 or scaled_h <= 0:
            return False

        is_interactive = self.store.viewport.is_interactive_mode or (self._pending_interactive_mode is True)

        cache_is_valid = False
        if self.store.viewport.scaled_image1_for_display and self.store.viewport.cached_scaled_image_dims:
            cached_w, cached_h = self.store.viewport.cached_scaled_image_dims
            if is_interactive:

                w_diff_ratio = abs(cached_w - scaled_w) / max(scaled_w, 1)
                h_diff_ratio = abs(cached_h - scaled_h) / max(scaled_h, 1)
                if w_diff_ratio < 0.1 and h_diff_ratio < 0.1:
                    cache_is_valid = True
            else:

                if abs(cached_w - scaled_w) < 2 and abs(cached_h - scaled_h) < 2:
                    cache_is_valid = True

        if not self.store.viewport.scaled_image1_for_display:
            cache_is_valid = False

        if not cache_is_valid:

            try:
                from PIL import Image
                img1_scaled = src_resize1.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS) if src_resize1 else None
                img2_scaled = src_resize2.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS) if src_resize2 else None

                self.store.viewport.scaled_image1_for_display = img1_scaled
                self.store.viewport.scaled_image2_for_display = img2_scaled
                self.store.viewport.cached_scaled_image_dims = (scaled_w, scaled_h)

                pixmap_w, pixmap_h = scaled_w, scaled_h
            except Exception as e:
                logger.error(f"Error scaling images: {e}", exc_info=True)
                self._start_scaling_worker(src_resize1, src_resize2, scaled_w, scaled_h)
                return False
        else:
            pixmap_w, pixmap_h = self.store.viewport.cached_scaled_image_dims
        self.store.viewport.pixmap_width, self.store.viewport.pixmap_height = pixmap_w, pixmap_h
        img_x, img_y = (label_width - pixmap_w) // 2, (label_height - pixmap_h) // 2
        self.store.viewport.image_display_rect_on_label = QRect(img_x, img_y, pixmap_w, pixmap_h)

        current_params = self._get_render_params_signature(source1, source2)
        last_params = getattr(self.store.viewport, '_last_render_params', None)

        is_interactive_mode_at_task_creation = (
            self._pending_interactive_mode
            if self._pending_interactive_mode is not None
            else self.store.viewport.is_interactive_mode
        )

        render_params_dict = self.store.viewport.get_render_params()
        render_params_dict['is_interactive_mode'] = is_interactive_mode_at_task_creation

        if last_params != current_params:
            setattr(self.store.viewport, '_last_render_params', current_params)

        magnifier_coords = get_magnifier_drawing_coords(
            store=self.store,
            drawing_width=pixmap_w,
            drawing_height=pixmap_h,
            container_width=label_width,
            container_height=label_height,
        ) if self.store.viewport.use_magnifier else None

        self.current_rendering_task_id += 1

        image1_for_render = self.store.viewport.scaled_image1_for_display
        image2_for_render = self.store.viewport.scaled_image2_for_display

        if is_interactive_mode_at_task_creation:
            if not image1_for_render:
                image1_for_render = src_resize1
            if not image2_for_render:
                image2_for_render = src_resize2

        render_params = {
            "render_params_dict": render_params_dict,
            "image1_scaled_for_display": image1_for_render,
            "image2_scaled_for_display": image2_for_render,
            "original_image1_pil": source1,
            "original_image2_pil": source2,
            "magnifier_coords": magnifier_coords,
            "font_path_absolute": FontManager.get_instance().get_font_path_for_image_text(self.store),
            "file_name1_text": self.store.document.get_current_display_name(1),
            "file_name2_text": self.store.document.get_current_display_name(2),
            "finished_signal": self._worker_finished_signal,
            "error_signal": self._worker_error_signal,
            "task_id": self.current_rendering_task_id,
            "label_dims": (label_width, label_height),

            "session_caches": {
                "magnifier": self.store.viewport.session_data.magnifier_cache,
                "background": self.store.viewport.session_data.caches
            }
        }

        worker = ImageRenderingWorker(render_params, lambda: self.current_rendering_task_id)

        priority = 1 if not is_interactive_mode_at_task_creation else 0

        if self.main_window_app.thread_pool.activeThreadCount() == self.main_window_app.thread_pool.maxThreadCount():
            self.main_window_app.thread_pool.clear()

        self.main_window_app.thread_pool.start(worker, priority=priority)

        self._pending_interactive_mode = None

        return True

    def _get_render_params_signature(self, s1, s2):
        vp = self.store.viewport
        doc = self.store.document
        return (

            vp.capture_position_relative,
            vp.split_position_visual,
            vp.use_magnifier,

            vp.show_magnifier_guides,
            vp.magnifier_guides_thickness,

            vp.capture_size_relative,
            vp.magnifier_size_relative,

            vp.is_magnifier_combined,
            vp.magnifier_internal_split,
            vp.magnifier_is_horizontal,
            vp.diff_mode,
            vp.channel_view_mode,
            vp.is_horizontal,
            vp.magnifier_visible_left, vp.magnifier_visible_center, vp.magnifier_visible_right,

            vp.divider_line_thickness, vp.divider_line_color.rgba(), vp.divider_line_visible,
            vp.magnifier_divider_thickness, vp.magnifier_divider_color.rgba(), vp.magnifier_divider_visible,
            vp.magnifier_border_color.rgba(),
            vp.magnifier_laser_color.rgba(),
            vp.capture_ring_color.rgba(),
            vp.magnifier_offset_relative_visual,
            vp.magnifier_spacing_relative_visual,

            vp.include_file_names_in_saved,
            vp.font_size_percent,
            vp.font_weight,
            vp.text_alpha_percent,
            vp.file_name_color.rgba(),
            vp.file_name_bg_color.rgba(),
            vp.draw_text_background,
            vp.text_placement_mode,
            vp.max_name_length,

            vp.render_config.magnifier_movement_interpolation_method,
            vp.render_config.laser_smoothing_interpolation_method,
            vp.optimize_magnifier_movement,
            vp.optimize_laser_smoothing,

            doc.get_current_display_name(1),
            doc.get_current_display_name(2),

            id(s1), id(s2)
        )

    def _start_scaling_worker(self, src1, src2, w, h):
        try:
            self.current_scaling_task_id += 1
            scaling_task_id = self.current_scaling_task_id

            def scale_task(img1, img2, width, height, tid):
                i1 = img1.resize((width, height), PIL.Image.Resampling.BILINEAR)
                i2 = img2.resize((width, height), PIL.Image.Resampling.BILINEAR)
                return i1, i2, width, height, tid

            worker = GenericWorker(scale_task, src1.copy(), src2.copy(), w, h, scaling_task_id)
            worker.signals.result.connect(self._on_display_scaling_ready)

            priority = 0 if (self.store.viewport.is_interactive_mode) else 1
            self.main_window_app.thread_pool.start(worker, priority=priority)
        except Exception as e:
            logger.error(f"Scaling start failed: {e}")

    @pyqtSlot(object)
    def _on_display_scaling_ready(self, result):
        if not result: return
        img1_s, img2_s, w, h, task_id = result
        if int(task_id) != int(self.current_scaling_task_id): return

        self.store.viewport.scaled_image1_for_display = img1_s
        self.store.viewport.scaled_image2_for_display = img2_s
        self.store.viewport.cached_scaled_image_dims = (w, h)
        self.schedule_update()

    def _should_use_dirty_rects_optimization(self, render_params_dict: dict, label_dims: tuple = None) -> bool:
        if not self.store.viewport.is_interactive_mode:
            return False

        if render_params_dict.get('use_magnifier', False):

            return False

        if not self._cached_base_pixmap or self._cached_base_pixmap.isNull():
            return False

        if label_dims is None:
            label_dims = self.get_current_label_dimensions()

        current_params = (
            render_params_dict.get('diff_mode', 'off'),
            render_params_dict.get('channel_view_mode', 'RGB'),
            render_params_dict.get('is_horizontal', False),
            render_params_dict.get('include_file_names_in_saved', False),
            label_dims
        )

        if self._cached_render_params and self._cached_render_params[:4] != current_params[:4]:

            return False

        return True

    def _render_divider_line_only(self, base_pixmap: QPixmap, render_params_dict: dict,
                                   target_rect: QRect, old_split_pos: float) -> QPixmap:
        """
        Перерисовывает только линию разделения на существующем pixmap (dirty rects оптимизация).

        Это намного быстрее чем полный рендер через PIL pipeline.
        """
        result_pixmap = base_pixmap.copy()

        if not render_params_dict.get('divider_line_visible', True):
            return result_pixmap

        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        is_horizontal = render_params_dict.get('is_horizontal', False)
        split_pos = render_params_dict.get('split_pos', 0.5)
        thickness = render_params_dict.get('divider_line_thickness', 3)
        color = render_params_dict.get('divider_line_color', (255, 255, 255, 255))

        from PyQt6.QtGui import QColor
        if isinstance(color, tuple) and len(color) >= 3:
            qcolor = QColor(color[0], color[1], color[2], color[3] if len(color) > 3 else 255)
        else:
            qcolor = QColor(255, 255, 255, 255)

        img_w = target_rect.width()
        img_h = target_rect.height()

        if not is_horizontal:
            old_x = int(target_rect.x() + img_w * old_split_pos)
            new_x = int(target_rect.x() + img_w * split_pos)

            update_x = min(old_x, new_x) - thickness - 2
            update_width = abs(new_x - old_x) + thickness * 2 + 4
            update_rect = QRect(
                max(0, update_x),
                target_rect.y(),
                min(update_width, base_pixmap.width() - max(0, update_x)),
                img_h
            )

            source_rect = QRect(
                max(0, update_x),
                target_rect.y(),
                update_rect.width(),
                img_h
            )
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawPixmap(update_rect, base_pixmap, source_rect)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor)
            line_x = max(0, min(new_x - thickness // 2, base_pixmap.width() - 1))
            line_width = min(thickness, base_pixmap.width() - line_x)
            painter.drawRect(
                line_x,
                target_rect.y(),
                line_width,
                img_h
            )
        else:
            old_y = int(target_rect.y() + img_h * old_split_pos)
            new_y = int(target_rect.y() + img_h * split_pos)

            update_y = min(old_y, new_y) - thickness - 2
            update_height = abs(new_y - old_y) + thickness * 2 + 4
            update_rect = QRect(
                target_rect.x(),
                max(0, update_y),
                img_w,
                min(update_height, base_pixmap.height() - max(0, update_y))
            )

            source_rect = QRect(
                target_rect.x(),
                max(0, update_y),
                img_w,
                update_rect.height()
            )
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawPixmap(update_rect, base_pixmap, source_rect)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor)
            line_y = max(0, min(new_y - thickness // 2, base_pixmap.height() - 1))
            line_height = min(thickness, base_pixmap.height() - line_y)
            painter.drawRect(
                target_rect.x(),
                line_y,
                img_w,
                line_height
            )

        painter.end()
        return result_pixmap

    @pyqtSlot(dict, dict, int)
    def _on_worker_finished(self, result_payload: dict, params: dict, finished_task_id: int):
        if finished_task_id < self._last_displayed_task_id:
            return
        self._last_displayed_task_id = finished_task_id

        if self.store.viewport.showing_single_image_mode != 0: return

        final_canvas_pil = result_payload.get("final_canvas")
        if not final_canvas_pil: return

        padding_left = result_payload.get("padding_left", 0)
        padding_top = result_payload.get("padding_top", 0)
        magnifier_bbox = result_payload.get("magnifier_bbox")

        combined_center = result_payload.get("combined_center")

        if magnifier_bbox and isinstance(magnifier_bbox, QRect):
            target_rect = self.store.viewport.image_display_rect_on_label

            if combined_center and isinstance(combined_center, QPoint):

                self.store.viewport.magnifier_screen_center = combined_center + target_rect.topLeft()

                self.store.viewport.magnifier_screen_size = magnifier_bbox.width()

            else:

                draw_x = target_rect.x() - padding_left
                draw_y = target_rect.y() - padding_top
                self.store.viewport.magnifier_screen_center = magnifier_bbox.translated(draw_x, draw_y).center()
                self.store.viewport.magnifier_screen_size = max(magnifier_bbox.width(), magnifier_bbox.height())

        try:

            from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

            canvas_pixmap = pil_to_qpixmap_optimized(final_canvas_pil, copy=False)

            if canvas_pixmap.isNull():
                return

            label_width, label_height = params.get("label_dims", self.get_current_label_dimensions())

            if label_width <= 0 or label_height <= 0:
                return

            final_pixmap = QPixmap(label_width, label_height)
            final_pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(final_pixmap)
            target_rect = self.store.viewport.image_display_rect_on_label
            painter.drawPixmap(target_rect.x() - padding_left, target_rect.y() - padding_top, canvas_pixmap)
            painter.end()

            render_params_dict = params.get("render_params_dict", {})
            self._cached_split_pos = render_params_dict.get('split_pos', 0.5)

            if (self.store.viewport.is_interactive_mode and
                not render_params_dict.get('use_magnifier', False) and
                render_params_dict.get('diff_mode', 'off') == 'off'):
                self._cached_base_pixmap = final_pixmap.copy()
                current_params = (
                    render_params_dict.get('diff_mode', 'off'),
                    render_params_dict.get('channel_view_mode', 'RGB'),
                    render_params_dict.get('is_horizontal', False),
                    render_params_dict.get('include_file_names_in_saved', False),
                    (label_width, label_height)
                )
                self._cached_render_params = current_params

            self.ui.image_label.setPixmap(final_pixmap)
            self.current_displayed_pixmap = final_pixmap
        except Exception as e:
            logger.error(f"Error displaying task: {e}")

    @pyqtSlot(str)
    def _on_worker_error(self, msg: str):
        logger.error(f"Render worker error: {msg}")

    def _display_single_image_on_label(self, pil_image: PIL.Image.Image | None):
        if not hasattr(self.ui, "image_label") or self.ui.image_label is None:
            return
        if not pil_image:
            self.ui.image_label.clear()
            self.current_displayed_pixmap = None
            return

        try:
            w, h = self.get_current_label_dimensions()

            rgba = pil_image.convert("RGBA")
            data = rgba.tobytes("raw", "RGBA")
            qimg = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
            pix = QPixmap.fromImage(qimg).scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            self.ui.image_label.setPixmap(pix)
            self.current_displayed_pixmap = pix
        except Exception as e:
            logger.error(f"ImageCanvasPresenter._display_single_image_on_label: failed to display image: {e}")

    def _create_preview_cache_async(self, img1, img2):
        def cache_task(i1, i2, limit):
            w, h = i1.size
            if limit > 0 and max(w, h) > limit:
                ratio = min(limit/w, limit/h)
                nw, nh = int(w*ratio), int(h*ratio)
                return i1.resize((nw, nh), PIL.Image.Resampling.LANCZOS), i2.resize((nw, nh), PIL.Image.Resampling.LANCZOS)
            return i1, i2

        worker = GenericWorker(cache_task, img1.copy(), img2.copy(), self.store.viewport.display_resolution_limit)
        worker.signals.result.connect(self._on_preview_cache_ready)
        self.main_window_app.thread_pool.start(worker, priority=1)

    @pyqtSlot(object)
    def _on_preview_cache_ready(self, result):
        if result:
            c1, c2 = result
            self.store.viewport.display_cache_image1 = c1
            self.store.viewport.display_cache_image2 = c2
            self.schedule_update()

    def _finish_resize_delay(self):
        if self.store.viewport.resize_in_progress:
            self.store.viewport.resize_in_progress = False
            self.schedule_update()

    def start_interactive_movement(self):
        self.store.viewport.is_interactive_mode = True
        self.schedule_update()

    def stop_interactive_movement(self):
        self.store.viewport.is_interactive_mode = False

        self.store.invalidate_render_cache()

        if hasattr(self, '_last_store_snapshot'):
            delattr(self, '_last_store_snapshot')
        if hasattr(self, '_last_render_params_dict'):
            delattr(self, '_last_render_params_dict')

        self._cached_base_pixmap = None
        self._cached_split_pos = -1.0
        self._cached_render_params = None

        self.schedule_update()
