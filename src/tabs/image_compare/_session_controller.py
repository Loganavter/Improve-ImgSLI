# Audit-Meta: pattern=thin-owner reason="reference thin owner per CODE_PATTERNS — delegates to use_cases/loading,list_ops,navigation"
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
    AnalysisSetChannelViewModeEvent,
    AnalysisSetDiffModeEvent,
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
        # B2/B3 shared coordinators (state-owning collaborators, CODE_PATTERNS.md)
        from tabs._shared.loading_toast import LoadingToastCoordinator
        from tabs._shared.pyramid import PyramidBuildCoordinator

        def _ic_get_toast_manager():
            # mirrors tabs.image_compare.use_cases.loading_toast.get_toast_manager
            try:
                return getattr(
                    getattr(self.presenter, "main_window_app", None), "toast_manager", None
                )
            except Exception:
                return None

        def _ic_translate(key: str, default: str | None = None):
            from sli_ui_toolkit.i18n import get_current_language, tr as _tr

            try:
                return _tr(key, get_current_language())
            except Exception:
                return default if default is not None else key

        self._loading_toast_coordinator = LoadingToastCoordinator(
            get_toast_manager=_ic_get_toast_manager,
            translate=_ic_translate,
        )
        # Keep legacy dict attributes as live views onto the coordinator's state
        # so external fakes/tests that poke controller._loading_toasts keep working.
        self._loading_toasts: dict[int, int] = self._loading_toast_coordinator._loading_toasts  # type: ignore[attr-defined]
        # Pyramid coordinator owns builds + uid->slot routing; toast via the same coordinator.
        self._pyramid_coordinator = PyramidBuildCoordinator(
            get_thread_pool=lambda: self.thread_pool,
            toast_coordinator=self._loading_toast_coordinator,
            request_view_update=self._schedule_image_canvas_update,
            invalidate_render=lambda complete: self._invalidate_image_canvas_render_state() if complete else None,
        )
        self._pyramid_builds: set[int] = self._pyramid_coordinator._pyramid_builds
        self._loading_toast_uid_slot: dict[int, int] = self._pyramid_coordinator._pyramid_toast_slot
        # Slots with a full-resolution decode in flight; unify against a
        # preview side is deferred while the real pixels are on the way.
        self._pending_full_loads: dict[int, int] = {1: 0, 2: 0}
        # Undo/redo of browsing (SET_CURRENT_INDEX) restores the index but
        # the slot's pixels can point at a closed store — re-sync on the
        # "document" scope. Deferred to the next loop turn: the emit fires
        # inside Dispatcher.undo() while its lock is held, and the re-sync
        # dispatches (non-reentrant lock).
        self.store.on_change(self._on_store_scoped_change)

    def _on_store_scoped_change(self, scope: str) -> None:
        if scope != "document":
            return
        QTimer.singleShot(0, self._resync_current_image_slots_if_needed)

    def _resync_current_image_slots_if_needed(self) -> None:
        from tabs.image_compare.use_cases.loading import resync_current_image_slots

        resync_current_image_slots(self)

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

            from shared.image_processing.pixel_cache_loader import load_pixel_store

            store = load_pixel_store(path, auto_crop=should_crop)
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

            # A superseded worker (the user already switched this slot to a
            # different index while this decode was in flight) must only
            # cache the decoded pixels on the list item -- never overwrite
            # the live document slot. Multiple decodes for the same slot can
            # be in flight at once under rapid switching, and Qt gives no
            # ordering guarantee for their completion, so an unconditional
            # overwrite lets a stale result win and corrupts
            # document.full_res_imageN/pathN (rapid Space+click bug).
            current_app_index = (
                document.current_index1
                if image_number == 1
                else document.current_index2
            )
            is_current = index_in_list == current_app_index

            if is_current:
                self._show_loading_toast(image_number)

            if is_preview:
                if is_current:
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

                if not isinstance(pil_img, TiledPixelStore):
                    pil_img = maybe_wrap_pixel_store(pil_img)
                if is_current:
                    outgoing = getattr(document, f"full_res_image{image_number}", None)
                    other = 2 if image_number == 1 else 1
                    other_full = getattr(document, f"full_res_image{other}", None)
                    # Never close a store still installed on the other compare slot
                    # (stale path-only selections used to share one store across both).
                    if outgoing is not None and outgoing is not other_full:
                        close_pixel_store(outgoing)
                    self._update_image_slot(
                        image_number,
                        image=pil_img,
                        path=path,
                        is_full_res=True,
                    )
                    self._mark_full_res_ready(image_number)

            item.image = pil_img

            if is_current:
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
            from shared.image_processing.pixel_cache_loader import load_pixel_store

            store = load_pixel_store(path_str, auto_crop=crop_flag)
            return (
                store,
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
        self._pending_full_loads[image_number] += 1
        worker.signals.result.connect(self._on_full_resolution_loaded_result)
        worker.signals.error.connect(
            lambda err: self._on_full_resolution_error(path, err)
        )
        worker.signals.finished.connect(
            lambda num=image_number: self._on_full_load_finished(num)
        )
        self.thread_pool.start(worker)

    def _on_full_load_finished(self, image_number: int) -> None:
        self._pending_full_loads[image_number] = max(
            0, self._pending_full_loads[image_number] - 1
        )
        if self._pending_full_loads[image_number]:
            return
        # If the decode failed, a unify deferred on this slot (see
        # _defer_mixed_unify) would otherwise never run; fall back to
        # unifying with whatever this slot still has.
        document = self.store.get_session_state_slot("document")
        if getattr(document, f"full_res_image{image_number}") is None:
            self._trigger_preview_unification(image_number)

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
        logger.error(f"Failed to load full resolution: {err}", exc_info=True)
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

    def _invalidate_image_canvas_render_state(self, clear_overlay_state: bool = False):
        presenter = getattr(self, "presenter", None)
        if presenter and hasattr(presenter, "invalidate_canvas_render_state"):
            presenter.invalidate_canvas_render_state(clear_overlay_state=clear_overlay_state)

    def _schedule_image_canvas_update(self):
        presenter = getattr(self, "presenter", None)
        if presenter and hasattr(presenter, "schedule_canvas_update"):
            QTimer.singleShot(0, presenter.schedule_canvas_update)

    def set_current_image(
        self, image_number: int, force_refresh: bool = False, emit_signal: bool = True
    ):
        loading.set_current_image(self, image_number, force_refresh, emit_signal)

    def _unify_images_worker_task(
        self, img1, img2, path1, path2, task_id, method_name
    ):
        from shared.image_processing.pixel_ops.unify import unify_pair
        from shared.image_processing.store_lease import StoreLease

        try:
            if task_id != self._unification_task_id:
                return None

            lease1 = StoreLease.capture(img1)
            lease2 = StoreLease.capture(img2)
            import time

            t0 = time.perf_counter()
            logger.info(
                "[Unify] task %d started (%sx%s + %sx%s)",
                task_id,
                getattr(img1, "width", "?"),
                getattr(img1, "height", "?"),
                getattr(img2, "width", "?"),
                getattr(img2, "height", "?"),
            )
            u1, u2 = unify_pair(
                img1,
                img2,
                method_name,
                lease1=lease1,
                lease2=lease2,
                should_abort=lambda: task_id != self._unification_task_id,
            )
            if u1 is None and u2 is None:
                logger.info(
                    "[Unify] task %d aborted/empty after %.2fs",
                    task_id,
                    time.perf_counter() - t0,
                )
                return None
            logger.info(
                "[Unify] task %d finished in %.2fs", task_id, time.perf_counter() - t0
            )

            return u1, u2, path1, path2, task_id
        except Exception as e:
            logger.error(f"Failed to unify images: {e}", exc_info=True)
            return None

    def _on_unified_images_ready(self, result):
        loading.on_unified_images_ready(self, result)

    def _start_pyramid_builds(self, *stores):
        loading.start_pyramid_builds(self, *stores)

    def _pyramid_build_task(
        self, pyramid, task_id, uid, total_levels, progress_callback=None
    ):
        return loading.pyramid_build_task(
            self, pyramid, task_id, uid, total_levels, progress_callback
        )

    def _on_pyramid_level_ready(self, payload):
        loading.on_pyramid_level_ready(self, payload)

    def _get_toast_manager(self):
        # Prefer coordinator; fallback to legacy use_case for fakes without it.
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            return coord.get_toast_manager()
        return loading.get_toast_manager(self)

    # Single source for progress checkpoints: re-export from shared
    # (legacy alias kept for tests that read controller._DECODE_DONE_PROGRESS).
    @property
    def _DECODE_DONE_PROGRESS(self) -> int:  # type: ignore[override]
        from tabs._shared.loading_toast import DECODE_DONE_PROGRESS as _V

        return _V

    @property
    def _PYRAMID_START_PROGRESS(self) -> int:  # type: ignore[override]
        from tabs._shared.loading_toast import PYRAMID_START_PROGRESS as _V

        return _V

    def _show_loading_toast(self, image_number: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.show(image_number)
            return
        loading.show_loading_toast(self, image_number)

    def _set_loading_toast_progress(self, image_number: int, percent: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.set_progress(image_number, percent)
            return
        loading.set_loading_toast_progress(self, image_number, percent)

    def _mark_full_res_ready(self, image_number: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.mark_full_res_ready(image_number)
            return
        loading.mark_full_res_ready(self, image_number)

    def _bump_loading_toast_pyramid_started(self, image_number: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.bump_pyramid_started(image_number)
            return
        loading.bump_loading_toast_pyramid_started(self, image_number)

    def _finish_loading_toast(self, image_number: int) -> None:
        coord = getattr(self, "_loading_toast_coordinator", None)
        if coord is not None:
            coord.finish(image_number)
            return
        loading.finish_loading_toast(self, image_number)

    def _trigger_metrics_calculation_if_needed(self):
        try:
            presenter = getattr(self, "presenter", None)
            widget = getattr(presenter, "widget", None) if presenter is not None else None
            if widget is not None:
                is_hidden = False
                try:
                    if hasattr(widget, "is_current_stack_page"):
                        is_hidden = not widget.is_current_stack_page()
                    else:
                        window = widget.window()
                        ui = getattr(window, "ui", None) if window is not None else None
                        if ui is None:
                            pp = getattr(window, "presenter", None) if window is not None else None
                            ui = getattr(pp, "ui", None) if pp is not None else None
                        stack = getattr(ui, "workspace_stack", None) if ui is not None else None
                        if stack is not None:
                            cur = stack.currentWidget()
                            is_hidden = cur is not widget and not (cur is not None and hasattr(cur, "isAncestorOf") and cur.isAncestorOf(widget))
                        else:
                            is_hidden = not bool(widget.isVisible())
                except Exception:
                    try:
                        is_hidden = not bool(widget.isVisible())
                    except Exception:
                        is_hidden = False
                if is_hidden:
                    widget._metrics_stale = True  # type: ignore[attr-defined]
                    try:
                        from core.tracing.tracer import Tracer
                        if Tracer.enabled():
                            Tracer.instance().record("metrics.deferred", "metrics deferred - background tab", {})
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        self.metrics_service.trigger_metrics_calculation_if_needed()

    def _trigger_full_diff_generation(self):
        try:
            presenter = getattr(self, "presenter", None)
            widget = getattr(presenter, "widget", None) if presenter is not None else None
            if widget is not None:
                is_hidden = False
                try:
                    if hasattr(widget, "is_current_stack_page"):
                        is_hidden = not widget.is_current_stack_page()
                    else:
                        is_hidden = not bool(widget.isVisible())
                except Exception:
                    is_hidden = False
                if is_hidden:
                    widget._metrics_stale = True  # type: ignore[attr-defined]
                    try:
                        from core.tracing.tracer import Tracer
                        if Tracer.enabled():
                            Tracer.instance().record("metrics.deferred", "diff generation deferred - background tab", {})
                    except Exception:
                        pass
                    return
        except Exception:
            pass
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

    def on_set_diff_mode(self, event: AnalysisSetDiffModeEvent):
        self.set_diff_mode(event.mode)

    def on_metrics_requested_event(self, event: Any) -> None:
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

    def reorder_items_in_list(self, *, list_num: int, indices, dest_index: int):
        list_ops.reorder_items_in_list(
            self, list_num=list_num, indices=indices, dest_index=dest_index
        )

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

    def move_items_between_lists(
        self,
        *,
        source_list_num: int,
        indices,
        dest_list_num: int,
        dest_index: int,
    ):
        list_ops.move_items_between_lists(
            self,
            source_list_num=source_list_num,
            indices=indices,
            dest_list_num=dest_list_num,
            dest_index=dest_index,
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
