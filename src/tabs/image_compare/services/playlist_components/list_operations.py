# Audit-Meta: pattern=thin-owner-target reason="playlist service — list ops with full slot cleanup via document_store_ops + autocrop/pyramid sweep"
from __future__ import annotations

import logging

from core.state_management.actions import (
    SetImageSessionImageAction,
    SetPendingUnificationPathsAction,
    SetUnificationInProgressAction,
)

from tabs.image_compare.services import document_store_ops
from tabs.image_compare.services.playlist_components.common import (
    emit_ui_update,
    find_index_by_path,
    get_current_item_path,
    get_current_index,
    get_target_list,
    set_current_index,
)

_log = logging.getLogger("ImproveImgSLI.playlist.list_ops")


def _close_outgoing_store(document, image_number: int, outgoing_store) -> None:
    if outgoing_store is None:
        return
    other = 2 if image_number == 1 else 1
    other_store = getattr(document, f"full_res_image{other}", None) if document is not None else None
    if outgoing_store is other_store:
        return
    try:
        from shared.image_processing.tiled_pixel_store import close_pixel_store

        close_pixel_store(outgoing_store)
    except Exception:
        pass


def _discard_pending_loads(main_controller, image_number: int, paths: list[str]) -> None:
    ctrl = main_controller
    real = getattr(ctrl, "session_ctrl", None) if ctrl is not None else None
    holder = real if real is not None else ctrl
    # image loads dedup set
    pending = getattr(holder, "_pending_image_loads", None) if holder is not None else None
    if pending is not None:
        import os as _os

        if paths:
            for p in paths:
                if not p:
                    continue
                try:
                    pending.discard((image_number, p))
                except Exception:
                    pass
                try:
                    norm = _os.path.normpath(p)
                    pending.discard((image_number, norm))
                except Exception:
                    pass
        # sweeping: also drop any stale entries for this slot that remain (e.g. clear of whole list)
        try:
            for key in list(pending):
                if isinstance(key, tuple) and len(key) == 2 and key[0] == image_number:
                    pending.discard(key)
        except Exception:
            pass
    # full-res decode counters — reset for the cleared slot so mixed-unify defer does not hang
    try:
        full_pending = getattr(holder, "_pending_full_loads", None) if holder is not None else None
        if isinstance(full_pending, dict) and image_number in full_pending:
            full_pending[image_number] = 0
    except Exception:
        pass


def _invalidate_caches_for_paths(paths: list[str]) -> None:
    if not paths:
        return
    for p in paths:
        if not p:
            continue
        try:
            from shared.image_processing import autocrop_service

            autocrop_service.invalidate(p)
        except Exception:
            pass
        try:
            from shared.image_processing import pixel_cache_registry

            cache = getattr(pixel_cache_registry, "_cache", None)
            if isinstance(cache, dict):
                cache.pop(p, None)
                # also try normalized / str variants
                import os as _os

                try:
                    cache.pop(_os.path.normpath(p), None)
                except Exception:
                    pass
                try:
                    cache.pop(str(p), None)
                except Exception:
                    pass
        except Exception:
            pass
    try:
        from shared.image_processing import pyramid_registry

        pyramid_registry.sweep()
    except Exception:
        pass


def _force_cancel_unification(store, main_controller) -> None:
    ctrl = main_controller
    real = getattr(ctrl, "session_ctrl", None) if ctrl is not None else None
    holder = real if real is not None else ctrl
    if holder is not None and hasattr(holder, "_cancel_pending_unification"):
        try:
            # new signature supports force=True
            holder._cancel_pending_unification("", "", force=True)  # type: ignore[call-arg]
            return
        except TypeError:
            pass
        try:
            holder._cancel_pending_unification("", "")
            return
        except Exception:
            pass
    # fallback: dispatch directly if controller unavailable
    try:
        dispatcher = store.get_dispatcher()
        if dispatcher is not None:
            with store.batch_changes():
                dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
    except Exception:
        pass


class PlaylistListOperations:
    def __init__(
        self,
        store,
        main_controller=None,
        set_current_image_callback=None,
        trigger_metrics_callback=None,
    ):
        self.store = store
        self.main_controller = main_controller
        self._set_current_image = set_current_image_callback
        self._trigger_metrics = trigger_metrics_callback

    def swap_current_images(self) -> None:
        dispatcher = self.store.get_dispatcher()
        assert dispatcher is not None, "swap_current_images requires dispatcher"
        from core.state_management.actions import (
            SetFullResImageAction,
            SetImagePathAction,
            SetImageSessionImageAction,
            SetOriginalImageAction,
            SetPreviewImageAction,
        )

        document = self.store.get_session_state_slot("document")
        idx1 = document.current_index1
        idx2 = document.current_index2
        list1 = document.image_list1
        list2 = document.image_list2
        if not (0 <= idx1 < len(list1) and 0 <= idx2 < len(list2)):
            return

        list1[idx1], list2[idx2] = list2[idx2], list1[idx1]

        # Capture before any dispatch — reducers replace document, so later
        # reads would see already-swapped values.
        prev1 = document.preview_image1
        prev2 = document.preview_image2
        orig1 = document.original_image1
        orig2 = document.original_image2
        full1 = document.full_res_image1
        full2 = document.full_res_image2
        path1 = document.image1_path
        path2 = document.image2_path
        img1 = self.store.viewport.session_data.image_state.image1
        img2 = self.store.viewport.session_data.image_state.image2

        with self.store.batch_changes():
            dispatcher.dispatch(SetPreviewImageAction(1, prev2), scope="document")
            dispatcher.dispatch(SetPreviewImageAction(2, prev1), scope="document")
            dispatcher.dispatch(SetOriginalImageAction(1, orig2), scope="document")
            dispatcher.dispatch(SetOriginalImageAction(2, orig1), scope="document")
            dispatcher.dispatch(SetFullResImageAction(1, full2), scope="document")
            dispatcher.dispatch(SetFullResImageAction(2, full1), scope="document")
            dispatcher.dispatch(SetImagePathAction(1, path2), scope="document")
            dispatcher.dispatch(SetImagePathAction(2, path1), scope="document")
            dispatcher.dispatch(
                SetImageSessionImageAction(slot=1, image=img2), scope="viewport"
            )
            dispatcher.dispatch(
                SetImageSessionImageAction(slot=2, image=img1), scope="viewport"
            )
            self.store.invalidate_geometry_cache()

        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])
        self._emit_metrics_update()

    def swap_entire_lists(self) -> None:
        document_store_ops.swap_all_image_data(self.store)
        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])

    def remove_current_image_from_list(self, image_number: int) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        if not (0 <= current_index < len(target_list)):
            return

        outgoing_item = target_list[current_index]
        outgoing_path = getattr(outgoing_item, "path", None) if outgoing_item else None
        document = self.store.get_session_state_slot("document")
        outgoing_store = getattr(document, f"full_res_image{image_number}", None) if document is not None else None
        # fallback: ImageItem.image may hold the live TiledPixelStore when document slot is already stale
        try:
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            item_img = getattr(outgoing_item, "image", None)
            if isinstance(item_img, TiledPixelStore) and outgoing_store is None:
                outgoing_store = item_img
        except Exception:
            pass

        target_list.pop(current_index)

        new_index = min(current_index, len(target_list) - 1) if target_list else -1
        set_current_index(self.store, image_number, new_index)

        # full cleanup: document slot + image_state + pixel store + pending + caches + pyramid + unification
        outgoing_paths = [outgoing_path] if outgoing_path else []
        try:
            if not target_list:
                document_store_ops.clear_image_slot_data(self.store, image_number)
            # image_state (viewport) — always clear stale image to avoid blank strip sharing old store
            try:
                dispatcher = self.store.get_dispatcher()
                if dispatcher is not None:
                    dispatcher.dispatch(SetImageSessionImageAction(slot=image_number, image=None), scope="viewport")
            except Exception:
                pass
            _close_outgoing_store(document, image_number, outgoing_store)
            _discard_pending_loads(self.main_controller, image_number, outgoing_paths)
            _invalidate_caches_for_paths(outgoing_paths)
            _force_cancel_unification(self.store, self.main_controller)
        except Exception:
            pass

        self.store.invalidate_geometry_cache()
        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])
        self._emit_metrics_update()
        self._set_current_image(image_number)

    def remove_specific_image_from_list(
        self, image_number: int, index_to_remove: int
    ) -> None:
        target_list = get_target_list(self.store, image_number)
        current_index = get_current_index(self.store, image_number)
        if not (0 <= index_to_remove < len(target_list)):
            return

        outgoing_item = target_list[index_to_remove]
        outgoing_path = getattr(outgoing_item, "path", None) if outgoing_item else None
        document = self.store.get_session_state_slot("document")
        # only close document store if the removed index was the current slot
        is_current_removal = index_to_remove == current_index
        outgoing_store = None
        if is_current_removal and document is not None:
            outgoing_store = getattr(document, f"full_res_image{image_number}", None)
            try:
                from shared.image_processing.tiled_pixel_store import TiledPixelStore

                item_img = getattr(outgoing_item, "image", None)
                if isinstance(item_img, TiledPixelStore) and outgoing_store is None:
                    outgoing_store = item_img
            except Exception:
                pass

        target_list.pop(index_to_remove)

        if not target_list:
            new_current_index = -1
        elif index_to_remove < current_index:
            new_current_index = current_index - 1
        elif index_to_remove == current_index:
            new_current_index = min(index_to_remove, len(target_list) - 1)
        else:
            new_current_index = current_index

        set_current_index(self.store, image_number, new_current_index)
        # cleanup for the removed entry (always invalidate its caches; slot clear only if it was current)
        try:
            outgoing_paths = [outgoing_path] if outgoing_path else []
            if outgoing_paths:
                # pixel store for non-current removals: close the item's own store if tiled
                if not is_current_removal:
                    try:
                        from shared.image_processing.tiled_pixel_store import TiledPixelStore, close_pixel_store

                        item_img = getattr(outgoing_item, "image", None)
                        if isinstance(item_img, TiledPixelStore):
                            close_pixel_store(item_img)
                    except Exception:
                        pass
                else:
                    _close_outgoing_store(document, image_number, outgoing_store)
                    # clear slot data if list became empty, otherwise current slot will be reloaded
                    if not target_list:
                        document_store_ops.clear_image_slot_data(self.store, image_number)
                    try:
                        dispatcher = self.store.get_dispatcher()
                        if dispatcher is not None:
                            dispatcher.dispatch(SetImageSessionImageAction(slot=image_number, image=None), scope="viewport")
                    except Exception:
                        pass
                    _force_cancel_unification(self.store, self.main_controller)
                _discard_pending_loads(self.main_controller, image_number, outgoing_paths)
                _invalidate_caches_for_paths(outgoing_paths)
        except Exception:
            pass

        self.store.invalidate_geometry_cache()
        emit_ui_update(self.main_controller, ["combobox"])
        self._set_current_image(image_number)

    def clear_image_list(self, image_number: int) -> None:
        target_list = get_target_list(self.store, image_number)
        outgoing_paths = [getattr(item, "path", None) for item in list(target_list) if getattr(item, "path", None)]
        document = self.store.get_session_state_slot("document")
        outgoing_stores: list = []
        if document is not None:
            slot_store = getattr(document, f"full_res_image{image_number}", None)
            if slot_store is not None:
                outgoing_stores.append(slot_store)
        # collect per-item tiled stores (JXL etc) that are not the slot store
        try:
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            for item in list(target_list):
                img = getattr(item, "image", None)
                if isinstance(img, TiledPixelStore) and img not in outgoing_stores:
                    outgoing_stores.append(img)
        except Exception:
            pass

        self.store.clear_all_caches()
        target_list.clear()
        set_current_index(self.store, image_number, -1)
        document_store_ops.clear_image_slot_data(self.store, image_number)
        try:
            dispatcher = self.store.get_dispatcher()
            if dispatcher is not None:
                dispatcher.dispatch(SetImageSessionImageAction(slot=image_number, image=None), scope="viewport")
        except Exception:
            pass
        for st in outgoing_stores:
            _close_outgoing_store(document, image_number, st)
        # also close any remaining collected stores that were not the slot store (already handled)
        _discard_pending_loads(self.main_controller, image_number, outgoing_paths)
        _invalidate_caches_for_paths(outgoing_paths)
        _force_cancel_unification(self.store, self.main_controller)

        emit_ui_update(self.main_controller, ["combobox", "file_names", "resolution"])
        self.store.state_changed.emit("document")

    def reorder_item_in_list(
        self, image_number: int, source_index: int, dest_index: int
    ) -> None:
        self.reorder_items_in_list(
            list_num=image_number,
            indices=[source_index],
            dest_index=dest_index,
        )

    def reorder_items_in_list(
        self, *, list_num: int, indices, dest_index: int
    ) -> None:
        from sli_ui_toolkit.ui.widgets.helpers.multi_move import (
            normalize_indices,
            reorder_many,
        )

        normalized = normalize_indices(indices)
        if not normalized:
            return
        target_list = get_target_list(self.store, list_num)
        if not target_list:
            return
        current_path = get_current_item_path(self.store, list_num)
        rebuilt = reorder_many(list(target_list), normalized, dest_index)
        target_list[:] = rebuilt
        new_current = find_index_by_path(target_list, current_path)
        if new_current == -1 and target_list:
            new_current = min(get_current_index(self.store, list_num), len(target_list) - 1)
        set_current_index(self.store, list_num, new_current)
        emit_ui_update(self.main_controller, ["combobox"])

    def move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        self.move_items_between_lists(
            source_list_num=source_list_num,
            indices=[source_index],
            dest_list_num=dest_list_num,
            dest_index=dest_index,
        )

    def move_items_between_lists(
        self,
        *,
        source_list_num: int,
        indices,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        from sli_ui_toolkit.ui.widgets.helpers.multi_move import (
            normalize_indices,
        )

        normalized = normalize_indices(indices)
        if not normalized:
            return
        if len(normalized) == 1:
            # Keep the original single-item path (duplicate-path handling).
            self._move_one_between_lists(
                source_list_num, normalized[0], dest_list_num, dest_index
            )
            return

        source_list = get_target_list(self.store, source_list_num)
        dest_list = get_target_list(self.store, dest_list_num)
        extracted = [source_list[i] for i in normalized if i < len(source_list)]
        if not extracted:
            return

        path1_before = get_current_item_path(self.store, 1)
        path2_before = get_current_item_path(self.store, 2)

        for i in reversed(normalized):
            if i < len(source_list):
                source_list.pop(i)

        insert_at = max(0, min(int(dest_index), len(dest_list)))
        for item in extracted:
            path = item.path if item else None
            existing = find_index_by_path(dest_list, path)
            if existing != -1:
                dest_list.pop(existing)
                if existing < insert_at:
                    insert_at -= 1
        insert_at = max(0, min(insert_at, len(dest_list)))
        for offset, item in enumerate(extracted):
            dest_list.insert(insert_at + offset, item)

        # Resolve currents by path; for the source list, pretend the first
        # removed index was the "source_index" hint used by the single helper.
        hint = normalized[0]
        idx1 = self._resolve_current_index_after_cross_move(
            1, path1_before, source_list_num, hint
        )
        idx2 = self._resolve_current_index_after_cross_move(
            2, path2_before, source_list_num, hint
        )
        set_current_index(self.store, 1, idx1)
        set_current_index(self.store, 2, idx2)

        emit_ui_update(self.main_controller, ["combobox"])
        self._set_current_image(1, emit_signal=False)
        self._set_current_image(2, emit_signal=False)
        self.store.state_changed.emit("document")

    def _move_one_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        source_list = get_target_list(self.store, source_list_num)
        dest_list = get_target_list(self.store, dest_list_num)
        if not (0 <= source_index < len(source_list)):
            return

        path1_before = get_current_item_path(self.store, 1)
        path2_before = get_current_item_path(self.store, 2)

        item_to_move = source_list.pop(source_index)
        source_path = item_to_move.path if item_to_move else None

        existing_dest_idx = find_index_by_path(dest_list, source_path)
        if existing_dest_idx != -1:
            dest_list.pop(existing_dest_idx)
            if existing_dest_idx < dest_index:
                dest_index -= 1

        dest_index = max(0, min(dest_index, len(dest_list)))
        dest_list.insert(dest_index, item_to_move)

        idx1 = self._resolve_current_index_after_cross_move(
            1, path1_before, source_list_num, source_index
        )
        idx2 = self._resolve_current_index_after_cross_move(
            2, path2_before, source_list_num, source_index
        )
        set_current_index(self.store, 1, idx1)
        set_current_index(self.store, 2, idx2)

        list1 = get_target_list(self.store, 1)
        list2 = get_target_list(self.store, 2)
        _log.debug(
            "move_item_between_lists: src=%d→dest=%d path=%s "
            "resolved idx1=%d(len=%d) idx2=%d(len=%d) "
            "path1_before=%s path2_before=%s",
            source_list_num, dest_list_num, source_path,
            idx1, len(list1), idx2, len(list2),
            path1_before, path2_before,
        )

        emit_ui_update(self.main_controller, ["combobox"])
        self._set_current_image(1, emit_signal=False)
        self._set_current_image(2, emit_signal=False)
        self.store.state_changed.emit("document")

    def _resolve_current_index_after_cross_move(
        self, image_number: int, previous_path, source_list_num: int, source_index: int
    ) -> int:
        target_list = get_target_list(self.store, image_number)
        resolved_index = find_index_by_path(target_list, previous_path)
        if resolved_index != -1:
            return resolved_index
        if not target_list:
            return -1
        if source_list_num == image_number and source_index == get_current_index(self.store, image_number):
            return min(source_index, len(target_list) - 1)
        return 0

    def _emit_metrics_update(self) -> None:
        if self._trigger_metrics is not None:
            self._trigger_metrics()
