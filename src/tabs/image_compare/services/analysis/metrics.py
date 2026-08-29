import logging
from typing import Optional, Tuple

from PIL import Image

from core.state_management.actions import SetPsnrValueAction, SetSsimValueAction
from tabs.image_compare.services.analysis.runtime import AnalysisRuntime
from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class MetricsService:

    def __init__(self, store, runtime: AnalysisRuntime):
        self.store = store
        self.runtime = runtime
        self._active_ssim_toast_id: int | None = None
        # Staleness token: every async calculation bumps this; stale results
        # landing after a pair switch are dropped (same pattern as unify's
        # _unification_task_id and cached-diff request_key).
        self._metrics_request_id: int = 0

    def calculate_metrics_async(self, calc_psnr: bool, calc_ssim: bool):
        img1, img2 = self._get_metric_source_images()
        if not img1 or not img2 or img1.size != img2.size:
            self._close_ssim_metrics_toast()
            self.on_metrics_calculated(None, request_id=None)
            return

        self._show_ssim_metrics_toast_if_needed(calc_ssim)

        from shared.image_processing.store_lease import StoreLease

        self._metrics_request_id += 1
        request_id = self._metrics_request_id

        worker = GenericWorker(
            self.metrics_worker_task,
            img1,
            img2,
            calc_psnr,
            calc_ssim,
            StoreLease.capture(img1),
            StoreLease.capture(img2),
        )
        # Capture request_id so late results for a previous pair are ignored.
        worker.signals.result.connect(lambda r, rid=request_id: self.on_metrics_calculated(r, request_id=rid))
        worker.signals.error.connect(
            lambda _err_tuple, rid=request_id: self._on_metrics_error(rid)
        )
        if self.runtime.thread_pool:
            self.runtime.thread_pool.start(worker)

    def _on_metrics_error(self, request_id: int) -> None:
        if request_id != self._metrics_request_id:
            return
        self._close_ssim_metrics_toast()

    def _dispatch_psnr_value(self, value) -> None:
        dispatcher = getattr(self.store, "get_dispatcher", None)
        dispatcher = dispatcher() if callable(dispatcher) else None
        if dispatcher is not None:
            try:
                dispatcher.dispatch(SetPsnrValueAction(value=value), scope="viewport")
                return
            except Exception:
                logger.error("Failed to dispatch SetPsnrValueAction", exc_info=True)
        try:
            setattr(self.store.viewport.session_data.image_state, "psnr_value", value)
        except Exception:
            pass

    def _dispatch_ssim_value(self, value) -> None:
        dispatcher = getattr(self.store, "get_dispatcher", None)
        dispatcher = dispatcher() if callable(dispatcher) else None
        if dispatcher is not None:
            try:
                dispatcher.dispatch(SetSsimValueAction(value=value), scope="viewport")
                return
            except Exception:
                logger.error("Failed to dispatch SetSsimValueAction", exc_info=True)
        try:
            setattr(self.store.viewport.session_data.image_state, "ssim_value", value)
        except Exception:
            pass

    def _get_metric_source_images(self):
        image_state = self.store.viewport.session_data.image_state
        return image_state.image1, image_state.image2

    def metrics_worker_task(
        self, img1, img2, calc_psnr: bool, calc_ssim: bool, lease1, lease2
    ) -> Optional[Tuple[Optional[float], Optional[float]]]:
        """Worker task to compute metrics."""
        try:
            from shared.analysis import calculate_psnr, calculate_ssim
            from shared.image_processing.pixel_ops.downscale import downscale_pair_to_limit
            from shared.image_processing.store_lease import StoreLease
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            if lease1 is not None and not lease1.valid:
                return None
            if lease2 is not None and not lease2.valid:
                return None
            if isinstance(img1, TiledPixelStore) or isinstance(img2, TiledPixelStore):
                img1, img2 = downscale_pair_to_limit(img1, img2, 4096, allow_materialize=True)
            else:
                img1 = img1.copy() if img1 is not None else None
                img2 = img2.copy() if img2 is not None else None
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
        self, result: Optional[Tuple[Optional[float], Optional[float]]],
        *,
        request_id: int | None = None,
    ):
        # Stale result from a previous pair: ignore (metrics worker has no
        # ordering guarantee; the last finish must not overwrite the current
        # pair's numbers).
        if request_id is not None and request_id != self._metrics_request_id:
            return
        if result:
            psnr_val, ssim_val = result

            if (
                self.store.viewport.session_data.image_state.auto_calculate_psnr
                or self.store.viewport.view_state.diff_mode == "ssim"
            ):
                self._dispatch_psnr_value(psnr_val)
            if (
                self.store.viewport.session_data.image_state.auto_calculate_ssim
                or self.store.viewport.view_state.diff_mode == "ssim"
            ):
                self._dispatch_ssim_value(ssim_val)
        else:
            if not self.store.viewport.session_data.image_state.auto_calculate_psnr:
                self._dispatch_psnr_value(None)
            if not self.store.viewport.session_data.image_state.auto_calculate_ssim:
                self._dispatch_ssim_value(None)

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
            self.on_metrics_calculated(None, request_id=None)

    def _show_ssim_metrics_toast_if_needed(self, calc_ssim: bool) -> None:
        if not calc_ssim:
            return
        if self.store.viewport.view_state.diff_mode == "ssim":
            return

        toast_manager = self.runtime.get_toast_manager()
        if toast_manager is None:
            return

        current_language = getattr(self.store.settings, "current_language", "en")
        message = tr("image_compare.msg.ssim_calculation_in_progress", current_language)
        if message == "image_compare.msg.ssim_calculation_in_progress":
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
            message = tr("image_compare.msg.ssim_calculation_done", current_language)
            if message == "image_compare.msg.ssim_calculation_done":
                message = "SSIM done"
        else:
            message = tr("image_compare.msg.ssim_calculation_failed", current_language)
            if message == "image_compare.msg.ssim_calculation_failed":
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