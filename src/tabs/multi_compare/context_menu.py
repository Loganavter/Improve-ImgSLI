from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox

from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuEntry, ContextMenuSeparator

from tabs.multi_compare.models import CompareSlot, find_path
from tabs.multi_compare.scene import actions
from ui.context_menu.models import ContextMenuRequest
from ui.icon_manager import AppIcon


class MultiCompareContextMenuProvider:
    def __init__(self, widget):
        self.widget = widget

    def entries_for(self, request: ContextMenuRequest) -> tuple[ContextMenuEntry, ...]:
        if request.session_type != "multi_compare":
            return ()
        if request.source_widget is not self.widget.canvas:
            return ()
        if request.target.kind != "multi_compare_slot":
            return ()
        slot = self._slot(request)
        if slot is None:
            return ()
        return (
            ContextMenuAction(
                "multi_compare.rename_slot",
                self._tr("context.rename", "Rename"),
                icon=AppIcon.TEXT_MANIPULATOR,
                data=slot.id,
            ),
            ContextMenuAction(
                "multi_compare.duplicate_slot",
                self._tr("context.duplicate", "Duplicate"),
                icon=AppIcon.ADD,
                enabled=slot.image is not None
                and len(self.widget.state.slots) < self.widget.state.max_slots,
                data=slot.id,
            ),
            ContextMenuAction(
                "multi_compare.show_slot_properties",
                self._tr("context.properties", "Properties"),
                icon=AppIcon.PHOTO,
                data=slot.id,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "multi_compare.remove_slot",
                self._tr("context.remove", "Remove"),
                icon=AppIcon.DELETE,
                danger=True,
                data=slot.id,
            ),
        )

    def execute(self, action_id: str, request: ContextMenuRequest, data: object) -> bool:
        if not action_id.startswith("multi_compare."):
            return False
        slot = self._slot(request, slot_id=data)
        if slot is None:
            return True
        if action_id == "multi_compare.rename_slot":
            self._rename_slot(slot)
            return True
        if action_id == "multi_compare.duplicate_slot":
            self._duplicate_slot(slot)
            return True
        if action_id == "multi_compare.show_slot_properties":
            self._show_properties(slot)
            return True
        if action_id == "multi_compare.remove_slot":
            self.widget.remove_slot(slot.id)
            return True
        return False

    def _slot(self, request: ContextMenuRequest, slot_id: object = None) -> CompareSlot | None:
        sid = slot_id if slot_id is not None else request.target.id
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return None
        return next((slot for slot in self.widget.state.slots if slot.id == sid), None)

    def _rename_slot(self, slot: CompareSlot) -> None:
        text, ok = QInputDialog.getText(
            self.widget,
            self._tr("context.rename", "Rename"),
            self._tr("context.name", "Name"),
            Qt.TextInputMode.Normal,
            slot.label,
        )
        if ok:
            self.widget.store.dispatch(actions.rename_slot(slot.id, text.strip()))

    def _duplicate_slot(self, slot: CompareSlot) -> None:
        if slot.image is None or self.widget.state.root is None:
            return
        path = find_path(self.widget.state.root, slot.id)
        image = slot.image.copy() if hasattr(slot.image, "copy") else slot.image
        self.widget.store.dispatch(
            actions.add_slot(
                path=slot.path or Path(),
                image=image,
                label=slot.label,
                target_path=tuple(path or ()),
                side="right",
                target_root=False,
            )
        )

    def _show_properties(self, slot: CompareSlot) -> None:
        parts = [
            f"{self._tr('context.name', 'Name')}: {slot.label or '-'}",
            f"{self._tr('context.path', 'Path')}: {slot.path or '-'}",
        ]
        if slot.image is not None:
            height, width = slot.image.shape[:2]
            channels = slot.image.shape[2] if slot.image.ndim == 3 else 1
            parts.append(
                f"{self._tr('context.size', 'Size')}: {width} x {height}, {channels} ch"
            )
        QMessageBox.information(
            self.widget,
            self._tr("context.properties", "Properties"),
            "\n".join(parts),
        )

    def _tr(self, key: str, default: str) -> str:
        translate = getattr(self.widget, "_translate", None)
        if callable(translate):
            return translate(key, default)
        return default
