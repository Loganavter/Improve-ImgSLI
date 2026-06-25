from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuEntry, ContextMenuSeparator

from resources.translations import get_current_language, tr
from ui.context_menu.models import ContextMenuRequest
from ui.icon_manager import AppIcon


class ImageCompareContextMenuProvider:
    def __init__(self, canvas, store):
        self.canvas = canvas
        self.store = store

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

    def execute(self, action_id: str, request: ContextMenuRequest, data: object) -> bool:
        if not action_id.startswith("image_compare."):
            return False
        slot = self._slot_number(request, data)
        if slot is None:
            return True
        if action_id == "image_compare.copy_path":
            QApplication.clipboard().setText(self._path_for(slot) or "")
            return True
        if action_id == "image_compare.show_properties":
            self._show_properties(slot)
            return True
        if action_id == "image_compare.remove_image":
            self.store.clear_image_slot_data(slot)
            self.store.emit_state_change("document")
            self.canvas.update()
            return True
        return False

    def _slot_number(self, request: ContextMenuRequest, value: object = None) -> int | None:
        raw = value if value is not None else request.target.id
        try:
            slot = int(raw)
        except (TypeError, ValueError):
            return None
        return slot if slot in (1, 2) else None

    def _path_for(self, slot: int) -> str:
        document = self.store.document
        return getattr(document, f"image{slot}_path", None) or ""

    def _display_name_for(self, slot: int) -> str:
        document = self.store.document
        try:
            return document.get_current_display_name(slot)
        except Exception:
            path = self._path_for(slot)
            return Path(path).name if path else ""

    def _show_properties(self, slot: int) -> None:
        path = self._path_for(slot)
        name = self._display_name_for(slot)
        image = getattr(self.store.document, f"original_image{slot}", None)
        parts = [
            f"{self._tr('action.context_name', 'Name')}: {name or '-'}",
            f"{self._tr('action.context_path', 'Path')}: {path or '-'}",
        ]
        size = getattr(image, "size", None)
        if size:
            parts.append(
                f"{self._tr('action.context_size', 'Size')}: {size[0]} x {size[1]}"
            )
        QMessageBox.information(
            self.canvas,
            self._tr("action.context_properties", "Properties"),
            "\n".join(parts),
        )

    def _tr(self, key: str, default: str) -> str:
        text = tr(key, get_current_language() or "en")
        return default if text == key else text
