import logging

from PySide6.QtCore import QObject, QTimer, Signal
from sli_ui_toolkit.workers import GenericWorker

from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from core.state_management.actions import (
    SetChannelViewModeAction,
    SetDiffModeAction,
    SetFullResImageAction,
    SetImagePathAction,
    SetInteractiveModeAction,
    SetPendingUnificationPathsAction,
    SetPreviewImageAction,
    SetUnificationInProgressAction,
)
from tabs.image_compare.events import (
    AnalysisRequestMetricsEvent,
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
    AnalysisToggleDiffModeEvent,
)
from tabs.image_compare.services.analysis.cached_diff import CachedDiffService
from tabs.image_compare.use_cases import list_ops, loading, navigation
from sli_ui_toolkit.i18n import tr

logger = logging.getLogger("ImproveImgSLI")


def _format_worker_error(err) -> str:
    if isinstance(err, tuple) and len(err) >= 2:
        return str(err[1])
    return str(err)


class SessionController(QObject):

    error_occurred = Signal(str)
    image_loaded = Signal()
    update_requested = Signal()

    def __init__(
        self,
        store,
        thread_pool,
        playlist_manager,
        metrics_service=None,
        diff_service: CachedDiffService | None = None,
        presenter=None,
        event_bus=None,
    ):
        super().__init__()
        self.store = store
        self.thread_pool = thread_pool
        self.playlist_manager = playlist_manager
        self.metrics_service = metrics_service
        self.diff_service = diff_service
        self.presenter = presenter
        self.event_bus = event_bus

        self._unification_task_id = 0

    def _update_image_slot(
        self,
        slot_number: int,
        *,
        image=None,
        path=None,
        emit=True,
        is_preview=False,
        is_full_res=False,
    ):
        dispatcher = self.store.get_dispatcher()
        if is_full_res and image is not None:
            dispatcher.dispatch(SetFullResImageAction(slot=slot_number, image=image))
        if is_preview and image is not None:
            dispatcher.dispatch(SetPreviewImageAction(slot=slot_number, image=image))
        if path is not None:
            dispatcher.dispatch(SetImagePathAction(slot=slot_number, path=path))
        if emit:
            self.store.emit_state_change("document")

    def initialize_app_display(self):
        loading.initialize_app_display(self)

    def _load_image_async(self, path, image_number, index_in_list, target_size=None):
        from shared.image_processing.progressive_loader import (
            load_preview_image,
            should_use_progressive_load,
        )
        from shared.image_processing.tiled_pixel_store import TiledPixelStore

        should_crop = getattr(self.store.settings, "auto_crop_black_borders", True)

        try:
            use_progressive = should_use_progressive_load(path)

            if use_progressive:
                preview = load_preview_image(path, should_crop)
                if preview:
                    return preview, path, image_number, index_in_list, True

            store = TiledPixelStore.from_path(path, auto_crop=should_crop)
            return store, path, image_number, index_in_list, False
        except Exception as e:
            if self.event_bus:
                self.event_bus.emit(
                    CoreErrorOccurredEvent(
                        f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n{path}\n\n{e}"
                    )
                )
            else:
                self.error_occurred.emit(
                    f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n{path}\n\n{e}"
                )
            return None, path, image_number, index_in_list, False

    def _cancel_pending_unification(self, new_path1: str, new_path2: str) -> bool:
        if not self.store.viewport.session_data.render_cache.unification_in_progress:
            return False
        pending = (
            self.store.viewport.session_data.render_cache.pending_unification_paths
        )
        if pending and (pending[0] != new_path1 or pending[1] != new_path2):
            dispatcher = self.store.get_dispatcher()
            dispatcher.dispatch(SetUnificationInProgressAction(enabled=False))
            dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None))
            self.store.invalidate_geometry_cache()
            return True
        return False

    def _on_image_loaded(self, result):
        if result is None:
            return

        if isinstance(result, tuple) and len(result) == 5:
            pil_img, path, image_number, index_in_list, is_preview = result
        else:
            pil_img, path, image_number, index_in_list = result
            is_preview = False
        document = self.store.get_session_state_slot("document")
        target_list = (
            document.image_list1 if image_number == 1 else document.image_list2
        )

        if not pil_img:
            if (
                0 <= index_in_list < len(target_list)
                and target_list[index_in_list].path == path
            ):
                target_list.pop(index_in_list)
                current_app_index = (
                    document.current_index1
                    if image_number == 1
                    else document.current_index2
                )
                if index_in_list == current_app_index:
                    self.set_current_image(image_number)
                if self.presenter:
                    self.presenter.ui_batcher.schedule_update("combobox")
            return

        if (
            0 <= index_in_list < len(target_list)
            and target_list[index_in_list].path == path
        ):
            item = target_list[index_in_list]

            if is_preview:
                self._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_preview=True,
                )
                self._load_full_resolution_async(path, image_number, index_in_list)
            else:
                from shared.image_processing.tiled_pixel_store import (
                    TiledPixelStore,
                    close_pixel_store,
                    maybe_wrap_pixel_store,
                )

                outgoing = getattr(document, f"full_res_image{image_number}", None)
                other = 2 if image_number == 1 else 1
                other_full = getattr(document, f"full_res_image{other}", None)
                # Never close a store still installed on the other compare slot
                # (stale path-only selections used to share one store across both).
                if outgoing is not None and outgoing is not other_full:
                    close_pixel_store(outgoing)
                if not isinstance(pil_img, TiledPixelStore):
                    pil_img = maybe_wrap_pixel_store(pil_img)
                self._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_full_res=True,
                )

            item.image = pil_img

            current_app_index = (
                document.current_index1
                if image_number == 1
                else document.current_index2
            )
            if index_in_list == current_app_index:
                if not is_preview:
                    QTimer.singleShot(
                        0,
                        lambda: self.set_current_image(
                            image_number, force_refresh=True
                        ),
                    )
                else:
                    QTimer.singleShot(
                        0,
                        lambda num=image_number: self._trigger_preview_unification(num),
                    )

    def _on_image_loaded_from_worker(self, result):
        self._on_image_loaded(result)

    def _trigger_preview_unification(self, image_number: int):
        loading.trigger_preview_unification(self, image_number)

    def _load_full_resolution_async(self, path, image_number, index_in_list):
        from shared.image_processing.tiled_pixel_store import TiledPixelStore

        should_crop = getattr(self.store.settings, "auto_crop_black_borders", True)

        def load_full_task(path_str, crop_flag, slot_number, item_index):
            return (
                TiledPixelStore.from_path(path_str, auto_crop=crop_flag),
                path_str,
                slot_number,
                item_index,
            )

        worker = GenericWorker(
            load_full_task,
            path,
            should_crop,
            image_number,
            index_in_list,
        )
        worker.signals.result.connect(self._on_full_resolution_loaded_result)
        worker.signals.error.connect(
            lambda err: self._on_full_resolution_error(path, err)
        )
        self.thread_pool.start(worker)

    def _on_full_resolution_loaded_result(self, result) -> None:
        if not isinstance(result, tuple) or len(result) != 4:
            return
        full_img, path, image_number, index_in_list = result
        self._on_full_image_loaded(
            full_img,
            path,
            int(image_number),
            int(index_in_list),
        )

    def _on_full_resolution_error(self, path: str, err) -> None:
        logger.error(f"Failed to load full resolution: {err}")
        message = (
            f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n"
            f"{path}\n\n{_format_worker_error(err)}"
        )
        if self.event_bus:
            self.event_bus.emit(CoreErrorOccurredEvent(message))
        else:
            self.error_occurred.emit(message)

    def _on_full_image_loaded(self, full_img, path, image_number, index_in_list):
        loading.handle_full_image_loaded(
            self, full_img, path, image_number, index_in_list
        )

    def load_images_from_paths(self, file_paths: list[str], image_number: int):
        loading.load_images_from_paths(self, file_paths, image_number)

    def duplicate_image_to_slot(self, source_slot: int, target_slot: int) -> None:
        loading.duplicate_image_to_slot(self, source_slot, target_slot)

    def _invalidate_image_canvas_render_state(self, clear_magnifier: bool = False):
        presenter = getattr(self, "presenter", None)
        if presenter and hasattr(presenter, "invalidate_canvas_render_state"):
            presenter.invalidate_canvas_render_state(clear_magnifier=clear_magnifier)

    def _schedule_image_canvas_update(self):
        presenter = getattr(self, "presenter", None)
        if presenter and hasattr(presenter, "schedule_canvas_update"):
            QTimer.singleShot(0, presenter.schedule_canvas_update)

    def set_current_image(
        self, image_number: int, force_refresh: bool = False, emit_signal: bool = True
    ):
        loading.set_current_image(self, image_number, force_refresh, emit_signal)

    def _unify_images_worker_task(
        self,
        img1,
        img2,
        path1: str | None,
        path2: str | None,
        task_id: int,
        method_name: str = "LANCZOS",
    ):
        """Produces the full-resolution unified pair only. The downscaled
        "display cache" used for the on-screen preview is a separate,
        per-frame concern owned exclusively by ``image_cache.create_preview_cache_async``
        (docs/dev/DISPLAY_IMAGE_PIPELINE.md) -- this used to also compute its
        own downscaled copy here and write it into ``display_cache_image1/2``,
        which raced against that per-frame writer and could leave the stale,
        non-downscaled pair in place (the "shrink" bug)."""
        try:
            from shared.image_processing.pixel_ops.unify import unify_pair
            from shared.image_processing.store_lease import StoreLease

            lease1 = StoreLease.capture(img1)
            lease2 = StoreLease.capture(img2)
            u1, u2 = unify_pair(
                img1,
                img2,
                method_name,
                lease1=lease1,
                lease2=lease2,
            )
            if u1 is None and u2 is None:
                return None

            return u1, u2, path1, path2, task_id
        except Exception as e:
            logger.error(f"Failed to unify images: {e}")
            return None

    def _on_unified_images_ready(self, result):
        loading.on_unified_images_ready(self, result)

    def _trigger_metrics_calculation_if_needed(self):
        self.metrics_service.trigger_metrics_calculation_if_needed()

    def _trigger_full_diff_generation(self):
        if self.diff_service is not None:
            self.diff_service.request_generation(optimize_ssim=False)

    def toggle_diff_mode(self, checked: bool):
        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetInteractiveModeAction(checked), scope="viewport")
        self.store.emit_state_change("viewport")

    def set_diff_mode(self, mode: str):
        if self.store.viewport.view_state.diff_mode == mode:
            return

        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetDiffModeAction(mode), scope="viewport")
        if self.diff_service is not None:
            self.diff_service.invalidate()

        if mode == "off" and self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())

        self._trigger_metrics_calculation_if_needed()
        self.store.invalidate_render_cache()
        self.store.emit_state_change("viewport")

    def set_channel_view_mode(self, mode: str):
        if self.store.viewport.view_state.channel_view_mode == mode:
            return

        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(SetChannelViewModeAction(mode), scope="viewport")
        if (
            self.store.viewport.view_state.diff_mode != "off"
            and self.diff_service is not None
        ):
            self.diff_service.invalidate()

        self.store.invalidate_render_cache()
        self.store.emit_state_change("viewport")
        if self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())

    def on_set_channel_view_mode(self, event: AnalysisSetChannelViewModeEvent):
        self.set_channel_view_mode(event.mode)

    def on_toggle_diff_mode(self, event: AnalysisToggleDiffModeEvent):
        self.toggle_diff_mode(True)

    def on_set_diff_mode(self, event: AnalysisSetDiffModeEvent):
        self.set_diff_mode(event.mode)

    def on_metrics_requested_event(self, event: AnalysisRequestMetricsEvent) -> None:
        payload = event.payload or {}
        calc_psnr = payload.get("psnr", True)
        calc_ssim = payload.get("ssim", True)
        if self.metrics_service is not None:
            self.metrics_service.calculate_metrics_async(calc_psnr, calc_ssim)

    def swap_current_images(self):
        list_ops.swap_current_images(self)

    def swap_entire_lists(self):
        list_ops.swap_entire_lists(self)

    def remove_current_image_from_list(self, image_number: int):
        list_ops.remove_current_image_from_list(self, image_number)

    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int):
        list_ops.remove_specific_image_from_list(self, image_number, index_to_remove)

    def clear_image_list(self, image_number: int):
        list_ops.clear_image_list(self, image_number)

    def reorder_item_in_list(
        self, image_number: int, source_index: int, dest_index: int
    ):
        list_ops.reorder_item_in_list(self, image_number, source_index, dest_index)

    def move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ):
        list_ops.move_item_between_lists(
            self, source_list_num, source_index, dest_list_num, dest_index
        )

    def on_edit_name_changed(self, image_number, new_name):
        list_ops.on_edit_name_changed(self, image_number, new_name)

    def rename_image_at_index(self, image_number: int, index: int, new_name: str):
        list_ops.rename_image_at_index(self, image_number, index, new_name)

    def activate_single_image_mode(self, image_number: int):
        navigation.activate_single_image_mode(self, image_number)

    def deactivate_single_image_mode(self):
        navigation.deactivate_single_image_mode(self)

    def increment_rating(self, image_number: int, index: int):
        list_ops.increment_rating(self, image_number, index)

    def decrement_rating(self, image_number: int, index: int):
        list_ops.decrement_rating(self, image_number, index)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int):
        list_ops.set_rating(self, image_number, index_to_set, new_score)

    def on_combobox_changed(self, image_number: int, index: int, scroll_delta: int = 0):
        navigation.on_combobox_changed(self, image_number, index, scroll_delta)

    def on_interpolation_changed(self, index: int):
        navigation.on_interpolation_changed(self, index)
