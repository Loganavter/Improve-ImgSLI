import logging
import time
import traceback

from PyQt6.QtCore import QRunnable, pyqtSlot

from image_processing.composer import ImageComposer

logger = logging.getLogger("ImproveImgSLI")

class ImageRenderingWorker(QRunnable):
    def __init__(self, render_params):
        super().__init__()
        self.render_params = render_params
        self.finished = self.render_params["finished_signal"]
        self.error = self.render_params["error_signal"]
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        task_id = self.render_params.get("task_id", "N/A")
        worker_start_time = time.perf_counter()

        try:
            font_path = self.render_params.get("font_path_absolute")
            composer = ImageComposer(font_path)

            final_canvas, padding_left, padding_top, magnifier_bbox_on_canvas, combined_center = composer.generate_comparison_image(
                self.render_params["app_state_copy"],
                self.render_params["image1_scaled_for_display"],
                self.render_params["image2_scaled_for_display"],
                self.render_params.get("original_image1_pil"),
                self.render_params.get("original_image2_pil"),
                self.render_params.get("magnifier_coords"),
                self.render_params.get("font_path_absolute"),
                self.render_params.get("file_name1_text"),
                self.render_params.get("file_name2_text"),
            )

            worker_duration_ms = (time.perf_counter() - worker_start_time) * 1000

            if final_canvas is None:
                self.error.emit(f"Task {task_id}: Failed to generate final canvas.")
                return

            result_payload = {
                "final_canvas": final_canvas,
                "padding_left": padding_left,
                "padding_top": padding_top,
                "magnifier_bbox": magnifier_bbox_on_canvas,
                "combined_center": combined_center,
            }

            self.finished.emit(result_payload, self.render_params, task_id)

        except Exception as e:
            current_task_id_for_error = self.render_params.get(
                "task_id", "N/A_IN_EXCEPT"
            )
            traceback.print_exc()
            self.error.emit(f"Rendering error (Task {current_task_id_for_error}): {e}")
