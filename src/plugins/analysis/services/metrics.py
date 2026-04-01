import logging
from typing import Optional, Tuple

from PIL import Image

from plugins.analysis.services.runtime import AnalysisRuntime
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class MetricsService:

    def __init__(self, store, runtime: AnalysisRuntime):
        self.store = store
        self.runtime = runtime

    def calculate_metrics_async(self, calc_psnr: bool, calc_ssim: bool):
        img1, img2 = self._get_metric_source_images()
        if not img1 or not img2 or img1.size != img2.size:
            self.on_metrics_calculated(None)
            return

        worker = GenericWorker(
            self.metrics_worker_task, img1.copy(), img2.copy(), calc_psnr, calc_ssim
        )
        worker.signals.result.connect(self.on_metrics_calculated)
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
            from plugins.analysis.processing import calculate_psnr, calculate_ssim

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

        self.runtime.ui_updates.emit(("resolution",))

    def trigger_metrics_calculation_if_needed(self):
        calc_psnr = self.store.viewport.session_data.image_state.auto_calculate_psnr
        calc_ssim = self.store.viewport.session_data.image_state.auto_calculate_ssim

        if self.store.viewport.view_state.diff_mode == "ssim":
            calc_ssim = True

        if calc_psnr or calc_ssim:
            self.calculate_metrics_async(calc_psnr=calc_psnr, calc_ssim=calc_ssim)
        else:
            self.on_metrics_calculated(None)
