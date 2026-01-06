

import logging
from typing import Optional, Tuple

from PIL import Image
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class MetricsService:

    def __init__(self, store, main_controller):
        self.store = store
        self.main_controller = main_controller

    def calculate_metrics_async(self, calc_psnr: bool, calc_ssim: bool):
        img1 = self.store.viewport.image1
        img2 = self.store.viewport.image2
        if not img1 or not img2 or img1.size != img2.size:
            self.on_metrics_calculated(None)
            return

        worker = GenericWorker(self.metrics_worker_task, img1.copy(), img2.copy(), calc_psnr, calc_ssim)
        worker.signals.result.connect(self.on_metrics_calculated)
        if self.main_controller:
            self.main_controller.thread_pool.start(worker)

    def metrics_worker_task(self, img1: Image.Image, img2: Image.Image,
                            calc_psnr: bool, calc_ssim: bool) -> Optional[Tuple[Optional[float], Optional[float]]]:
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

    def on_metrics_calculated(self, result: Optional[Tuple[Optional[float], Optional[float]]]):
        if result:
            psnr_val, ssim_val = result

            if self.store.viewport.auto_calculate_psnr or self.store.viewport.diff_mode == 'ssim':
                self.store.viewport.psnr_value = psnr_val
            if self.store.viewport.auto_calculate_ssim or self.store.viewport.diff_mode == 'ssim':
                self.store.viewport.ssim_value = ssim_val
        else:
            if not self.store.viewport.auto_calculate_psnr:
                self.store.viewport.psnr_value = None
            if not self.store.viewport.auto_calculate_ssim:
                self.store.viewport.ssim_value = None

        if self.main_controller:
            self.main_controller.ui_update_requested.emit(['resolution'])

    def trigger_metrics_calculation_if_needed(self):
        calc_psnr = self.store.viewport.auto_calculate_psnr
        calc_ssim = self.store.viewport.auto_calculate_ssim

        if self.store.viewport.diff_mode == 'ssim':
            calc_ssim = True

        if calc_psnr or calc_ssim:
            self.calculate_metrics_async(calc_psnr=calc_psnr, calc_ssim=calc_ssim)
        else:
            self.on_metrics_calculated(None)

