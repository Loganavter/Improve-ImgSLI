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

        if self._check_cancellation():
            return

        try:
            image1_scaled = self.render_params["image1_scaled_for_display"]
            image2_scaled = self.render_params["image2_scaled_for_display"]

            width, height = image1_scaled.size if image1_scaled else (0, 0)

            if self._check_cancellation():
                return

            render_params_dict = self.render_params.get("render_params_dict")
            store_snapshot = self.render_params.get("store_snapshot")

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

            is_interactive = False
            if render_params_dict:
                is_interactive = render_params_dict.get('is_interactive_mode', False)
            elif store_snapshot:
                is_interactive = getattr(store_snapshot.viewport, 'is_interactive_mode', False)

            if ctx:
                ctx.return_layers = is_interactive

            font_path = self.render_params.get("font_path_absolute")
            pipeline = RenderingPipeline(font_path)

            final_canvas, padding_left, padding_top, magnifier_bbox_on_canvas, combined_center, magnifier_pil = pipeline.render_frame(ctx)

            if final_canvas is None:
                return

            result_payload = {
                "final_canvas": final_canvas,
                "magnifier_pil": magnifier_pil,
                "magnifier_pos_rel": combined_center,
                "padding_left": padding_left,
                "padding_top": padding_top,
                "magnifier_bbox": magnifier_bbox_on_canvas,
                "combined_center": combined_center,
                "is_interactive": is_interactive
            }

            self.finished.emit(result_payload, self.render_params, task_id)

        except Exception as e:
            logger.error(f"Rendering worker error: {e}", exc_info=True)
