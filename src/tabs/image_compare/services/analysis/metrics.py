import logging
from typing import Optional, Tuple

from PIL import Image

from tabs.image_compare.services.analysis.runtime import AnalysisRuntime
from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class MetricsService:

    def __init__(self, store, runtime: AnalysisRuntime):
        self.store = store
        self.runtime = runtime
        self._active_ssim_toast_id: int | None = None

    def calculate_metrics_async(self, calc_psnr: bool, calc_ssim: bool):
        img1, img2 = self._get_metric_source_images()
        if not img1 or not img2 or img1.size != img2.size:
            self._close_ssim_metrics_toast()
            self.on_metrics_calculated(None)
            return

        self._show_ssim_metrics_toast_if_needed(calc_ssim)

        worker = GenericWorker(
            self.metrics_worker_task, img1, img2, calc_psnr, calc_ssim
        )
        worker.signals.result.connect(self.on_metrics_calculated)
        worker.signals.error.connect(
            lambda _err_tuple: self._close_ssim_metrics_toast()
        )
        if self.runtime.thread_pool:
            self.runtime.thread_pool.start(worker)

    def _get_metric_source_images(self):
        session_data = self.store.viewport.session_data
        render_cache = session_data.render_cache
        image_state = session_data.image_state

        cache_img1 = (
            render_cache.display_cache_image1
            or render_cache.scaled_image1_for_display
        )
        cache_img2 = (
            render_cache.display_cache_image2
            or render_cache.scaled_image2_for_display
        )
        if (
            cache_img1 is not None
            and cache_img2 is not None
            and getattr(cache_img1, "size", None) == getattr(cache_img2, "size", None)
        ):
            return cache_img1, cache_img2

        return image_state.image1, image_state.image2

    def metrics_worker_task(
        self, img1: Image.Image, img2: Image.Image, calc_psnr: bool, calc_ssim: bool
    ) -> Optional[Tuple[Optional[float], Optional[float]]]:
        """Worker task to compute metrics."""
        try:
            from shared.analysis import calculate_psnr, calculate_ssim
            from shared.image_processing.lazy_pixel_source import to_real_pil_copy

            img1, img2 = to_real_pil_copy(img1), to_real_pil_copy(img2)
            psnr_val, ssim_val = None, None
            if calc_psnr:
                psnr_val = calculate_psnr(img1, img2)
            if calc_ssim:
                ssim_val = calculate_ssim(img1, img2)
            return psnr_val, ssim_val
        except Exception as e:
            logger.error(f"Failed to calculate metrics: {e}")
            return None

    def on_metrics_calculated(
        self, result: Optional[Tuple[Optional[float], Optional[float]]]
    ):
        if result:
            psnr_val, ssim_val = result

            if (
                self.store.viewport.session_data.image_state.auto_calculate_psnr
                or self.store.viewport.view_state.diff_mode == "ssim"
            ):
                self.store.viewport.session_data.image_state.psnr_value = psnr_val
            if (
                self.store.viewport.session_data.image_state.auto_calculate_ssim
                or self.store.viewport.view_state.diff_mode == "ssim"
            ):
                self.store.viewport.session_data.image_state.ssim_value = ssim_val
        else:
            if not self.store.viewport.session_data.image_state.auto_calculate_psnr:
                self.store.viewport.session_data.image_state.psnr_value = None
            if not self.store.viewport.session_data.image_state.auto_calculate_ssim:
                self.store.viewport.session_data.image_state.ssim_value = None

        self._complete_ssim_metrics_toast(success=result is not None)
        self.runtime.ui_updates.emit(("resolution",))

    def trigger_metrics_calculation_if_needed(self):
        calc_psnr = self.store.viewport.session_data.image_state.auto_calculate_psnr
        calc_ssim = self.store.viewport.session_data.image_state.auto_calculate_ssim

        if self.store.viewport.view_state.diff_mode == "ssim":
            calc_ssim = True

        if calc_psnr or calc_ssim:
            self.calculate_metrics_async(calc_psnr=calc_psnr, calc_ssim=calc_ssim)
        else:
            self._close_ssim_metrics_toast()
            self.on_metrics_calculated(None)

    def _show_ssim_metrics_toast_if_needed(self, calc_ssim: bool) -> None:
        if not calc_ssim:
            return
        if self.store.viewport.view_state.diff_mode == "ssim":
            return

        toast_manager = self.runtime.get_toast_manager()
        if toast_manager is None:
            return

        current_language = getattr(self.store.settings, "current_language", "en")
        message = tr("msg.ssim_calculation_in_progress", current_language)
        if message == "msg.ssim_calculation_in_progress":
            message = "SSIM calculation..."

        if self._active_ssim_toast_id is not None:
            try:
                toast_manager.update_toast(
                    self._active_ssim_toast_id,
                    message,
                    success=False,
                    duration=0,
                    progress=0,
                )
                return
            except Exception:
                logger.exception("Failed to refresh SSIM metrics toast")
                self._active_ssim_toast_id = None

        try:
            self._active_ssim_toast_id = toast_manager.show_toast(
                message,
                duration=0,
                progress=0,
            )
        except Exception:
            logger.exception("Failed to show SSIM metrics toast")
            self._active_ssim_toast_id = None

    def _complete_ssim_metrics_toast(self, *, success: bool) -> None:
        toast_manager = self.runtime.get_toast_manager()
        toast_id = self._active_ssim_toast_id
        if toast_manager is None or toast_id is None:
            self._active_ssim_toast_id = None
            return

        current_language = getattr(self.store.settings, "current_language", "en")
        if success:
            message = tr("msg.ssim_calculation_done", current_language)
            if message == "msg.ssim_calculation_done":
                message = "SSIM done"
        else:
            message = tr("msg.ssim_calculation_failed", current_language)
            if message == "msg.ssim_calculation_failed":
                message = "SSIM failed"

        try:
            toast_manager.update_toast(
                toast_id,
                message,
                success=success,
                duration=2000 if success else 5000,
                progress=100 if success else None,
            )
        except Exception:
            logger.exception("Failed to complete SSIM metrics toast")
        finally:
            self._active_ssim_toast_id = None

    def _close_ssim_metrics_toast(self) -> None:
        toast_manager = self.runtime.get_toast_manager()
        toast_id = self._active_ssim_toast_id
        if toast_manager is None or toast_id is None:
            self._active_ssim_toast_id = None
            return
        try:
            toast_manager.close_toast(toast_id)
        except Exception:
            logger.exception("Failed to close SSIM metrics toast")
        finally:
            self._active_ssim_toast_id = None
