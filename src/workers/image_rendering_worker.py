import logging
from PyQt6.QtCore import QRunnable, pyqtSlot
from shared.image_processing.pipeline import RenderingPipeline, create_render_context_from_store, create_render_context_from_params

logger = logging.getLogger("ImproveImgSLI")

class ImageRenderingWorker(QRunnable):
    def __init__(self, render_params, current_task_id_provider=None):
        super().__init__()
        self.render_params = render_params
        self.finished = self.render_params["finished_signal"]
        self.error = self.render_params["error_signal"]
        self.current_task_id_provider = current_task_id_provider
        self.setAutoDelete(True)

    def _check_cancellation(self) -> bool:
        if not self.current_task_id_provider:
            return False

        task_id = self.render_params.get("task_id", 0)
        latest_id = self.current_task_id_provider()
        return task_id < latest_id

    @pyqtSlot()
    def run(self):
        task_id = self.render_params.get("task_id", 0)
        label_dims = self.render_params.get("label_dims", (0, 0))
        use_magnifier = self.render_params.get("render_params_dict", {}).get("use_magnifier", False)

        if self._check_cancellation():
            return

        try:
            image1_scaled = self.render_params["image1_scaled_for_display"]
            image2_scaled = self.render_params["image2_scaled_for_display"]

            width, height = image1_scaled.size if image1_scaled else (0, 0)

            if self._check_cancellation():
                return

            render_params_dict = self.render_params.get("render_params_dict")
            if render_params_dict:
                try:
                    ctx = create_render_context_from_params(
                        render_params_dict=render_params_dict,
                        width=width,
                        height=height,
                        magnifier_drawing_coords=self.render_params.get("magnifier_coords"),
                        image1_scaled=image1_scaled,
                        image2_scaled=image2_scaled,
                        original_image1=self.render_params.get("original_image1_pil"),
                        original_image2=self.render_params.get("original_image2_pil"),
                        file_name1=self.render_params.get("file_name1_text", ""),
                        file_name2=self.render_params.get("file_name2_text", ""),
                        session_caches=self.render_params.get("session_caches")
                    )
                except Exception as e:
                    logger.error(f"Error creating render context from params: {e}", exc_info=True)
                    return
            else:

                store_snapshot = self.render_params.get("store_snapshot")
                if store_snapshot:
                    ctx = create_render_context_from_store(
                        store=store_snapshot,
                        width=width,
                        height=height,
                        magnifier_drawing_coords=self.render_params.get("magnifier_coords"),
                        image1_scaled=image1_scaled,
                        image2_scaled=image2_scaled
                    )
                    ctx.file_name1 = self.render_params.get("file_name1_text", "")
                    ctx.file_name2 = self.render_params.get("file_name2_text", "")
                else:
                    logger.error("Neither render_params_dict nor store_snapshot provided")
                    return

            if self._check_cancellation():
                return

            ctx.is_export = self.render_params.get("is_export", False)

            font_path = self.render_params.get("font_path_absolute")
            pipeline = RenderingPipeline(font_path)

            result_dict = pipeline.render_frame(ctx)

            if not result_dict:
                return

            if result_dict.get("is_interactive", False):

                result_payload = {
                    "is_interactive": True,
                    "base_image": result_dict.get("base_image"),
                    "overlay_image": result_dict.get("overlay_image"),
                    "overlay_pos": result_dict.get("overlay_pos"),
                    "ui_data": result_dict.get("ui_data"),
                    "padding_left": 0,
                    "padding_top": 0
                }
            else:

                result_payload = {
                    "is_interactive": False,
                    "final_canvas": result_dict.get("final_canvas"),
                    "padding_left": result_dict.get("padding_left", 0),
                    "padding_top": result_dict.get("padding_top", 0),
                    "magnifier_bbox": result_dict.get("magnifier_bbox"),
                    "combined_center": result_dict.get("combined_center")
                }

            self.finished.emit(result_payload, self.render_params, task_id)

        except Exception as e:
            logger.error(f"Rendering worker error: {e}", exc_info=True)

