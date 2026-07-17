from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSeparator,
)

from plugins.image_properties.plugin import open_image_properties_dialog
from shared_toolkit.ui.text_input_dialog import AppTextInputDialog
from sli_ui_toolkit.i18n import get_current_language, tr
from tabs.image_compare.services import document_store_ops
from ui.context_menu.models import ContextMenuRequest
from tabs.image_compare.icons import Icon


class ImageCompareContextMenuProvider:
    def __init__(self, canvas, store, *, flyout=None, ui_manager=None):
        self.canvas = canvas
        self.store = store
        self.flyout = flyout
        self._ui_manager_ref = ui_manager
        self._session_ctrl = None

    def attach_session_controller(self, session_ctrl) -> None:
        self._session_ctrl = session_ctrl

    def attach_flyout(self, flyout) -> None:
        self.flyout = flyout

    def attach_ui_manager(self, ui_manager) -> None:
        self._ui_manager_ref = ui_manager

    def entries_for(self, request: ContextMenuRequest) -> tuple[ContextMenuEntry, ...]:
        if request.session_type != "image_compare":
            return ()
        if request.target.kind == "image_compare_list_item":
            return self._list_item_entries(request)
        if request.target.kind != "image_compare_slot":
            return ()
        if request.source_widget is not self.canvas:
            return ()
        slot = self._slot_number(request)
        if slot is None or not self._path_for(slot):
            return ()
        return self._slot_entries(slot)

    def execute(
        self, action_id: str, request: ContextMenuRequest, data: object
    ) -> bool:
        if not action_id.startswith("image_compare."):
            return False
        if request.target.kind == "image_compare_list_item":
            return self._execute_list_item(action_id, request, data)
        slot = self._slot_number(request, data)
        if slot is None:
            return True
        if action_id == "image_compare.copy_path":
            QApplication.clipboard().setText(self._path_for(slot) or "")
            return True
        if action_id == "image_compare.duplicate_image":
            self._begin_duplicate(slot)
            return True
        if action_id == "image_compare.show_properties":
            self._show_properties(slot)
            return True
        if action_id == "image_compare.remove_image":
            self._remove_image(slot)
            return True
        return False

    def _slot_entries(self, slot: int) -> tuple[ContextMenuEntry, ...]:
        return (
            ContextMenuAction(
                "image_compare.copy_path",
                self._tr("action.context_copy_path", "Copy path"),
                icon=Icon.COPY,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.duplicate_image",
                self._tr("action.context_duplicate", "Duplicate"),
                icon=Icon.ADD,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.show_properties",
                self._tr("action.context_properties", "Properties"),
                icon=Icon.PHOTO,
                data=slot,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.remove_image",
                self._tr("action.context_remove", "Remove"),
                icon=Icon.DELETE,
                danger=True,
                data=slot,
            ),
        )

    def _list_item_entries(
        self, request: ContextMenuRequest
    ) -> tuple[ContextMenuEntry, ...]:
        if self.flyout is not None and request.source_widget is not self.flyout:
            return ()
        list_num, index = self._list_item_ref(request)
        if list_num is None or index is None:
            return ()
        if not self._list_item_path(list_num, index):
            return ()
        ref = (list_num, index)
        return (
            ContextMenuAction(
                "image_compare.rename_list_item",
                self._tr("action.context_rename", "Rename"),
                icon=Icon.TEXT_MANIPULATOR,
                data=ref,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.copy_path",
                self._tr("action.context_copy_path", "Copy path"),
                icon=Icon.COPY,
                data=ref,
            ),
            ContextMenuAction(
                "image_compare.show_properties",
                self._tr("action.context_properties", "Properties"),
                icon=Icon.PHOTO,
                data=ref,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.remove_list_item",
                self._tr("action.context_remove", "Remove"),
                icon=Icon.DELETE,
                danger=True,
                data=ref,
            ),
        )

    def _execute_list_item(
        self, action_id: str, request: ContextMenuRequest, data: object
    ) -> bool:
        list_num, index = self._list_item_ref(request, data)
        if list_num is None or index is None:
            return True
        if action_id == "image_compare.rename_list_item":
            self._rename_list_item(list_num, index)
            return True
        if action_id == "image_compare.copy_path":
            QApplication.clipboard().setText(
                self._list_item_path(list_num, index) or ""
            )
            return True
        if action_id == "image_compare.show_properties":
            self._show_list_item_properties(list_num, index)
            return True
        if action_id == "image_compare.remove_list_item":
            self._remove_list_item(list_num, index)
            return True
        return False

    def _rename_list_item(self, list_num: int, index: int) -> None:
        current = self._list_item_display_name(list_num, index)
        parent = None
        if self.flyout is not None:
            parent = self.flyout.window()
        if parent is None and self.canvas is not None:
            parent = self.canvas.window()
        text, ok = self._run_modal_text_prompt(
            parent,
            self._tr("action.context_rename", "Rename"),
            self._tr("action.context_name", "Name"),
            current,
        )
        if not ok:
            return
        name = text.strip()
        if not name or name == current:
            return
        ctrl = self._session_ctrl
        if ctrl is not None and hasattr(ctrl, "rename_image_at_index"):
            ctrl.rename_image_at_index(list_num, index, name)

    def _ui_manager(self):
        if self._ui_manager_ref is not None:
            return self._ui_manager_ref
        ctrl = self._session_ctrl
        presenter = getattr(ctrl, "presenter", None) if ctrl is not None else None
        return getattr(presenter, "ui_manager", None)

    def _run_modal_text_prompt(
        self,
        parent,
        title: str,
        prompt: str,
        text: str,
    ) -> tuple[str, bool]:
        """Run ``AppTextInputDialog`` without dismissing the list flyout.

        Focus leaving the flyout for the modal normally triggers
        ``hide_transient_same_window_ui``; ``set_modal_dialog_active`` blocks
        that path (and outside-click close) for the duration of ``exec``.
        """
        ui_manager = self._ui_manager()
        if ui_manager is not None and hasattr(ui_manager, "set_modal_dialog_active"):
            ui_manager.set_modal_dialog_active(True)
        try:
            return AppTextInputDialog.get_text(
                parent,
                title,
                prompt,
                text,
                ok_text=self._tr("common.ok", "OK"),
                cancel_text=self._tr("common.cancel", "Cancel"),
            )
        finally:
            if ui_manager is not None and hasattr(ui_manager, "set_modal_dialog_active"):
                ui_manager.set_modal_dialog_active(False)

    def _remove_image(self, slot: int) -> None:
        ctrl = self._session_ctrl
        if ctrl is not None and hasattr(ctrl, "remove_current_image_from_list"):
            ctrl.remove_current_image_from_list(slot)
            return
        document_store_ops.clear_image_slot_data(self.store, slot)
        self.store.emit_state_change("document")
        if self.canvas is not None:
            self.canvas.update()

    def _remove_list_item(self, list_num: int, index: int) -> None:
        ctrl = self._session_ctrl
        if ctrl is not None and hasattr(ctrl, "remove_specific_image_from_list"):
            ctrl.remove_specific_image_from_list(list_num, index)

    def _slot_number(
        self, request: ContextMenuRequest, value: object = None
    ) -> int | None:
        raw = value if value is not None else request.target.id
        try:
            slot = int(raw)
        except (TypeError, ValueError):
            return None
        return slot if slot in (1, 2) else None

    def _list_item_ref(
        self, request: ContextMenuRequest, value: object = None
    ) -> tuple[int | None, int | None]:
        raw = value if value is not None else request.target.id
        if isinstance(raw, (tuple, list)) and len(raw) == 2:
            try:
                list_num, index = int(raw[0]), int(raw[1])
            except (TypeError, ValueError):
                return None, None
            if list_num in (1, 2) and index >= 0:
                return list_num, index
            return None, None
        payload = request.target.payload or {}
        try:
            list_num = int(payload.get("list_num"))
            index = int(payload.get("index"))
        except (TypeError, ValueError):
            return None, None
        if list_num in (1, 2) and index >= 0:
            return list_num, index
        return None, None

    def _path_for(self, slot: int) -> str:
        document = self.store.get_session_state_slot("document")
        return getattr(document, f"image{slot}_path", None) or ""

    def _list_item_path(self, list_num: int, index: int) -> str:
        item = self._list_item(list_num, index)
        if item is None:
            return ""
        return getattr(item, "path", None) or ""

    def _list_item(self, list_num: int, index: int):
        document = self.store.get_session_state_slot("document")
        items = document.image_list1 if list_num == 1 else document.image_list2
        if 0 <= index < len(items):
            return items[index]
        return None

    def _display_name_for(self, slot: int) -> str:
        document = self.store.get_session_state_slot("document")
        try:
            return document.get_current_display_name(slot)
        except Exception:
            path = self._path_for(slot)
            return Path(path).name if path else ""

    def _list_item_display_name(self, list_num: int, index: int) -> str:
        item = self._list_item(list_num, index)
        if item is None:
            return ""
        name = getattr(item, "display_name", None) or ""
        if name:
            return name
        path = getattr(item, "path", None) or ""
        return Path(path).name if path else ""

    def _show_properties(self, slot: int) -> None:
        path = self._path_for(slot)
        name = self._display_name_for(slot)
        image = getattr(
            self.store.get_session_state_slot("document"), f"original_image{slot}", None
        )
        rating = self._rating_for(slot)
        self._open_properties(path, name, image, slot, rating)

    def _show_list_item_properties(self, list_num: int, index: int) -> None:
        item = self._list_item(list_num, index)
        if item is None:
            return
        path = self._list_item_path(list_num, index)
        name = self._list_item_display_name(list_num, index)
        rating = getattr(item, "rating", None)
        # List rows may not have a loaded PIL image; dialog still shows path/meta.
        self._open_properties(path, name, None, list_num, rating)

    def _open_properties(
        self,
        path: str,
        name: str,
        image,
        side_slot: int,
        rating: int | None,
    ) -> None:
        lang = get_current_language() or "en"
        side_key = (
            "image_properties.side_left"
            if side_slot == 1
            else "image_properties.side_right"
        )
        side_fallback = "Left" if side_slot == 1 else "Right"
        side_text = tr(side_key, lang)
        if side_text == side_key:
            side_text = side_fallback
        ui_manager = self._ui_manager()
        if ui_manager is not None and hasattr(ui_manager, "set_modal_dialog_active"):
            ui_manager.set_modal_dialog_active(True)
        try:
            open_image_properties_dialog(
                path=path,
                display_name=name,
                image=image,
                app_rows=(
                    ("image_properties.side", "Side", side_text),
                    ("image_properties.rating", "Rating", rating),
                ),
                language=lang,
                tr_func=tr,
            )
        finally:
            if ui_manager is not None and hasattr(ui_manager, "set_modal_dialog_active"):
                ui_manager.set_modal_dialog_active(False)

    def _begin_duplicate(self, source_slot: int) -> None:
        document = self.store.get_session_state_slot("document")
        image = getattr(document, f"original_image{source_slot}", None)
        path = self._path_for(source_slot)
        name = self._display_name_for(source_slot)
        if image is None and not path:
            return
        canvas = self.canvas
        if canvas is None:
            return
        view_state = self.store.viewport.view_state
        is_horizontal = bool(getattr(view_state, "is_horizontal", False))
        lang = get_current_language() or "en"

        def _resolve(key: str, fallback: str) -> str:
            text = tr(key, lang)
            return fallback if text == key else text

        def _cleanup() -> None:
            for sig, slot_fn in (
                (canvas.pasteOverlayDirectionSelected, on_dir),
                (canvas.pasteOverlayCancelled, on_cancel),
            ):
                try:
                    sig.disconnect(slot_fn)
                except Exception:
                    pass

        def on_dir(direction: str) -> None:
            _cleanup()
            target = 1 if direction in ("up", "left") else 2
            ctrl = self._session_ctrl
            if ctrl is not None and path and hasattr(ctrl, "load_images_from_paths"):
                ctrl.load_images_from_paths([path], target)
                return
            document_store_ops.set_current_image_data(
                self.store, target, image, path, name
            )
            try:
                self.store.emit_state_change("document")
            except Exception:
                pass
            canvas.update()

        def on_cancel() -> None:
            _cleanup()

        canvas.pasteOverlayDirectionSelected.connect(on_dir)
        canvas.pasteOverlayCancelled.connect(on_cancel)

        left_label = _resolve("image_properties.side_left", "Left")
        right_label = _resolve("image_properties.side_right", "Right")
        if is_horizontal:
            texts = {"up": left_label, "down": right_label, "left": "", "right": ""}
        else:
            texts = {"left": left_label, "right": right_label, "up": "", "down": ""}
        canvas.set_paste_overlay_state(True, is_horizontal=is_horizontal, texts=texts)

    def _rating_for(self, slot: int) -> int | None:
        document = self.store.get_session_state_slot("document")
        index = document.current_index1 if slot == 1 else document.current_index2
        items = document.image_list1 if slot == 1 else document.image_list2
        if 0 <= index < len(items):
            return getattr(items[index], "rating", None)
        return None

    def _tr(self, key: str, default: str) -> str:
        text = tr(key, get_current_language() or "en")
        return default if text == key else text
