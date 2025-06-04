from PyQt6.QtCore import QRunnable, pyqtSlot
import traceback
import time
from processing_services.image_drawing import generate_comparison_image_pil, create_base_split_image_pil

class ImageRenderingWorker(QRunnable):

    def __init__(self, render_params):
        super().__init__()
        self.render_params = render_params
        self.finished = self.render_params['finished_signal']
        self.error = self.render_params['error_signal']
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        _DEBUG_TIMER_START_WORKER_RUN = time.perf_counter()
        print(f"--- ImageRenderingWorker.run START (Task ID: {self.render_params.get('task_id', 'N/A')}) ---")
        try:
            app_state_copy = self.render_params['app_state_copy']
            image1_pil_copy = self.render_params['image1_pil_copy']
            image2_pil_copy = self.render_params['image2_pil_copy']
            original_image1_pil = self.render_params['original_image1_pil_copy']
            original_image2_pil = self.render_params['original_image2_pil_copy']
            current_label_dims = self.render_params['current_label_dims']
            magnifier_coords = self.render_params['magnifier_coords']
            font_path_absolute = self.render_params['font_path_absolute']
            current_name1_text = self.render_params['file_name1_text']
            current_name2_text = self.render_params['file_name2_text']
            task_id = self.render_params['task_id']
            task_was_interactive_at_creation = app_state_copy.is_interactive_mode
            print(f'WORKER (Task {task_id}): Received split_position={app_state_copy.split_position:.4f}, split_position_visual={app_state_copy.split_position_visual:.4f}, is_interactive_mode={app_state_copy.is_interactive_mode}')
            processed_for_drawing_img1 = image1_pil_copy
            processed_for_drawing_img2 = image2_pil_copy
            base_image_pil = None
            current_split_params_key = (app_state_copy.split_position_visual, app_state_copy.is_horizontal, id(processed_for_drawing_img1), id(processed_for_drawing_img2), (processed_for_drawing_img1.width, processed_for_drawing_img1.height), task_was_interactive_at_creation)
            if not app_state_copy._cached_split_base_image or app_state_copy._last_split_cached_params != current_split_params_key:
                print(f'WORKER (Task {task_id}): Base split image cache MISS or parameters changed. Re-creating base image.')
                create_base_start = time.perf_counter()
                base_image_pil_new = create_base_split_image_pil(processed_for_drawing_img1, processed_for_drawing_img2, app_state_copy.split_position_visual, app_state_copy.is_horizontal)
                print(f'_DEBUG_TIMER_ (Worker Task {task_id}): create_base_split_image_pil took {(time.perf_counter() - create_base_start) * 1000:.2f} ms')
                if base_image_pil_new:
                    app_state_copy._cached_split_base_image = base_image_pil_new
                    app_state_copy._last_split_cached_params = current_split_params_key
                    base_image_pil = base_image_pil_new
                else:
                    self.error.emit(f'Task {task_id}: Failed to create base split image (worker).')
                    return
            else:
                print(f'WORKER (Task {task_id}): Base split image cache HIT. Using cached image.')
                base_image_pil = app_state_copy._cached_split_base_image
            if base_image_pil is None:
                self.error.emit(f'Task {task_id}: Base image is None after cache logic (worker).')
                return
            render_overlays_start = time.perf_counter()
            result_pil_image = generate_comparison_image_pil(app_state=app_state_copy, base_image=base_image_pil, image1_processed=processed_for_drawing_img1, image2_processed=processed_for_drawing_img2, split_position_visual=app_state_copy.split_position_visual, is_horizontal=app_state_copy.is_horizontal, use_magnifier=app_state_copy.use_magnifier, show_capture_area_on_main_image=app_state_copy.show_capture_area_on_main_image, capture_position_relative=app_state_copy.capture_position_relative, original_image1=original_image1_pil, original_image2=original_image2_pil, magnifier_drawing_coords=magnifier_coords, include_file_names=app_state_copy.include_file_names_in_saved, font_path_absolute=font_path_absolute, font_size_percent=app_state_copy.font_size_percent, max_name_length=app_state_copy.max_name_length, file_name1_text=current_name1_text, file_name2_text=current_name2_text, file_name_color_rgb=app_state_copy.file_name_color.getRgb(), interpolation_method=app_state_copy.interpolation_method)
            print(f'_DEBUG_TIMER_ (Worker Task {task_id}): generate_comparison_image_pil (overlays) took {(time.perf_counter() - render_overlays_start) * 1000:.2f} ms')
            if result_pil_image:
                self.finished.emit(result_pil_image, current_label_dims, (processed_for_drawing_img1.size, processed_for_drawing_img2.size), current_name1_text, current_name2_text, task_id, task_was_interactive_at_creation)
            else:
                self.error.emit(f'Task {task_id}: Failed to generate comparison image (worker).')
        except Exception as e:
            current_task_id_for_error = self.render_params.get('task_id', 'N/A_IN_EXCEPT')
            print(f'ERROR in ImageRenderingWorker (Task {current_task_id_for_error}): {e}')
            traceback.print_exc()
            self.error.emit(f'Rendering error (Task {current_task_id_for_error}): {e}')
        total_worker_time = (time.perf_counter() - _DEBUG_TIMER_START_WORKER_RUN) * 1000
        print(f"--- ImageRenderingWorker.run END (Task ID: {self.render_params.get('task_id', 'N/A')}) Total time: {total_worker_time:.2f} ms ---")