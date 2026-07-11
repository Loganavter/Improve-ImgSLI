from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSeparator,
)

from plugins.image_properties.plugin import open_image_properties_dialog
from sli_ui_toolkit.i18n import get_current_language, tr
from tabs.image_compare.services import document_store_ops
from ui.context_menu.models import ContextMenuRequest
from ui.icon_manager import AppIcon


class ImageCompareContextMenuProvider:
    def __init__(self, canvas, store):
        self.canvas = canvas
        self.store = store
        self._session_ctrl = None

    def attach_session_controller(self, session_ctrl) -> None:
        self._session_ctrl = session_ctrl

    def entries_for(self, request: ContextMenuRequest) -> tuple[ContextMenuEntry, ...]:
        if request.session_type != "image_compare":
            return ()
        if request.source_widget is not self.canvas:
            return ()
        if request.target.kind != "image_compare_slot":
            return ()
        slot = self._slot_number(request)
        if slot is None or not self._path_for(slot):
            return ()
        return (
            ContextMenuAction(
                "image_compare.copy_path",
                self._tr("action.context_copy_path", "Copy path"),
                icon=AppIcon.COPY,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.duplicate_image",
                self._tr("action.context_duplicate", "Duplicate"),
                icon=AppIcon.ADD,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.show_properties",
                self._tr("action.context_properties", "Properties"),
                icon=AppIcon.PHOTO,
                data=slot,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.remove_image",
                self._tr("action.context_remove", "Remove"),
                icon=AppIcon.DELETE,
                danger=True,
                data=slot,
            ),
        )

    def execute(
        self, action_id: str, request: ContextMenuRequest, data: object
    ) -> bool:
        if not action_id.startswith("image_compare."):
            return False
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

    def _remove_image(self, slot: int) -> None:
        ctrl = self._session_ctrl
        if ctrl is not None and hasattr(ctrl, "remove_current_image_from_list"):
            ctrl.remove_current_image_from_list(slot)
            return
        document_store_ops.clear_image_slot_data(self.store, slot)
        self.store.emit_state_change("document")
        self.canvas.update()

    def _slot_number(
        self, request: ContextMenuRequest, value: object = None
    ) -> int | None:
        raw = value if value is not None else request.target.id
        try:
            slot = int(raw)
        except (TypeError, ValueError):
            return None
        return slot if slot in (1, 2) else None

    def _path_for(self, slot: int) -> str:
        document = self.store.get_session_state_slot("document")
        return getattr(document, f"image{slot}_path", None) or ""

    def _display_name_for(self, slot: int) -> str:
        document = self.store.get_session_state_slot("document")
        try:
            return document.get_current_display_name(slot)
        except Exception:
            path = self._path_for(slot)
            return Path(path).name if path else ""

    def _show_properties(self, slot: int) -> None:
        path = self._path_for(slot)
        name = self._display_name_for(slot)
        image = getattr(self.store.get_session_state_slot("document"), f"original_image{slot}", None)
        rating = self._rating_for(slot)
        lang = get_current_language() or "en"
        side_key = (
            "image_properties.side_left" if slot == 1 else "image_properties.side_right"
        )
        side_fallback = "Left" if slot == 1 else "Right"
        side_text = tr(side_key, lang)
        if side_text == side_key:
            side_text = side_fallback
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

    def _begin_duplicate(self, source_slot: int) -> None:
        document = self.store.get_session_state_slot("document")
        image = getattr(document, f"original_image{source_slot}", None)
        path = self._path_for(source_slot)
        name = self._display_name_for(source_slot)
        if image is None and not path:
            return
        canvas = self.canvas
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
            document_store_ops.set_current_image_data(self.store, target, image, path, name)
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
