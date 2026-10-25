from __future__ import annotations

import logging
from dataclasses import replace as _dc_replace

from PySide6.QtCore import QTimer

from tabs.image_compare.services.playlist_components.common import (
    emit_ui_update,
    get_current_index,
    get_presenter,
    get_target_list,
)
from core.log_names import APP_LOGGER_NAME

_log = logging.getLogger(f"{APP_LOGGER_NAME}.playlist.metadata")

_UNSET: object = object()


class PlaylistMetadataController:
    def __init__(self, store, main_controller=None):
        self.store = store
        self.main_controller = main_controller

    def increment_rating(self, image_number: int, index: int) -> None:
        self._change_rating(image_number, index, 1)

    def decrement_rating(self, image_number: int, index: int) -> None:
        self._change_rating(image_number, index, -1)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int) -> None:
        applied = self._dispatch_item_update(
            image_number, index_to_set, rating=new_score
        )
        if applied and index_to_set == get_current_index(self.store, image_number):
            emit_ui_update(self.main_controller, ["ratings"])

    def on_edit_name_changed(self, image_number, new_name) -> None:
        current_index = get_current_index(self.store, image_number)
        try:
            target_list = get_target_list(self.store, image_number)
        except Exception:
            return
        if not (0 <= current_index < len(target_list)):
            return
        raw_name = str(new_name)
        new_name = raw_name.strip()
        if new_name == target_list[current_index].display_name:
            return
        applied = self._dispatch_item_update(
            image_number, current_index, display_name=new_name
        )
        if applied:
            emit_ui_update(self.main_controller, ["combobox", "file_names"])

    def rename_image_at_index(
        self, image_number: int, index: int, new_name: str
    ) -> None:
        try:
            target_list = get_target_list(self.store, image_number)
        except Exception:
            return
        if not (0 <= index < len(target_list)):
            return
        name = str(new_name).strip()
        if name == target_list[index].display_name:
            return
        applied = self._dispatch_item_update(
            image_number, index, display_name=name
        )
        if not applied:
            return
        emit_ui_update(self.main_controller, ["combobox", "file_names"])
        current_index = get_current_index(self.store, image_number)
        if index == current_index:
            emit_ui_update(self.main_controller, ["file_names"])
        QTimer.singleShot(
            0,
            lambda: self._refresh_visible_flyout_labels(image_number),
        )

    def _dispatch_item_update(
        self,
        image_number: int,
        index: int,
        *,
        rating: object = _UNSET,
        display_name: object = _UNSET,
    ) -> bool:
        """Replace one ``ImageItem`` via ``SetImageListAction`` dispatch.

        STORE.md invariant 1 — never mutate items in place on the dispatch
        path; ``DocumentReducer`` replaces list + item (same action family
        as the crop-override path, which uses its own action type).
        Changed-guard: identical values → no dispatch, ``False``.
        Fail-open: no dispatcher (legacy/fake stores) or dispatch error →
        legacy in-place mutation + raw ``state_changed`` emit, ``True``.
        Out-of-range → ``False``.
        """
        try:
            target_list = get_target_list(self.store, image_number)
        except Exception:
            return False
        if not (0 <= index < len(target_list)):
            return False
        item = target_list[index]
        changes: dict = {}
        if rating is not _UNSET and rating != item.rating:
            changes["rating"] = rating
        if display_name is not _UNSET and display_name != item.display_name:
            changes["display_name"] = display_name
        if not changes:
            return False
        try:
            dispatcher = self.store.get_dispatcher()
        except Exception:
            dispatcher = None
        if dispatcher is None:
            self._apply_in_place(item, changes)
            return True
        try:
            from core.state_management.document_actions import SetImageListAction

            new_list = list(target_list)
            new_list[index] = _dc_replace(item, **changes)
            dispatcher.dispatch(
                SetImageListAction(slot=image_number, items=new_list),
                scope="document",
            )
        except Exception:
            _log.warning(
                "rating/rename dispatch failed; falling back to in-place",
                exc_info=True,
            )
            self._apply_in_place(item, changes)
            return True
        try:
            document = self.store.get_session_state_slot("document")
            remember = getattr(document, "remember_current_display_name", None)
            if callable(remember):
                remember(image_number)
        except Exception:
            pass
        return True

    def _apply_in_place(self, item, changes: dict) -> None:
        """Legacy fail-open path: mutate + raw emit (pre-dispatch behavior)."""
        for key, value in changes.items():
            try:
                setattr(item, key, value)
            except Exception:
                pass
        try:
            self.store.state_changed.emit("document")
        except Exception:
            pass

    def _refresh_visible_flyout_labels(self, image_number: int) -> None:
        presenter = get_presenter(self.main_controller)
        if presenter is None:
            return
        ui_manager = getattr(presenter, "ui_manager", None)
        flyout = getattr(ui_manager, "unified_flyout", None) if ui_manager else None
        if flyout is None or not flyout.isVisible():
            return
        if hasattr(flyout, "sync_from_store"):
            flyout.sync_from_store()

    def _change_rating(self, image_number: int, index_to_change: int, delta: int) -> None:
        try:
            target_list = get_target_list(self.store, image_number)
        except Exception:
            return
        if not (0 <= index_to_change < len(target_list)):
            return
        try:
            new_score = target_list[index_to_change].rating + delta
        except Exception:
            return
        applied = self._dispatch_item_update(
            image_number, index_to_change, rating=new_score
        )
        if not applied:
            return

        if index_to_change == get_current_index(self.store, image_number):
            emit_ui_update(self.main_controller, ["ratings"])

        QTimer.singleShot(
            0,
            lambda: self._update_visible_flyout_rating(image_number, index_to_change),
        )

    def _update_visible_flyout_rating(self, image_number: int, index_to_change: int) -> None:
        presenter = get_presenter(self.main_controller)
        if presenter is None:
            return
        ui_manager = getattr(presenter, "ui_manager", None)
        if ui_manager and hasattr(ui_manager, "unified_flyout"):
            flyout = ui_manager.unified_flyout
            if flyout and flyout.isVisible():
                flyout.update_rating_for_item(image_number, index_to_change)
