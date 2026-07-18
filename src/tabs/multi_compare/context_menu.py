from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSeparator,
)

from plugins.image_properties.plugin import open_image_properties_dialog
from sli_ui_toolkit.i18n import get_current_language
from sli_ui_toolkit.i18n import tr as app_tr
from tabs.multi_compare.models import CompareSlot, leaves
from tabs.multi_compare.scene import actions
from ui.context_menu.models import ContextMenuRequest
from tabs.multi_compare.icons import Icon


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
                icon=Icon.TEXT_MANIPULATOR,
                data=slot.id,
            ),
            ContextMenuAction(
                "multi_compare.duplicate_slot",
                self._tr("context.duplicate", "Duplicate"),
                icon=Icon.ADD,
                enabled=slot.image is not None
                and len(self.widget.state.slots) < self.widget.state.max_slots,
                data=slot.id,
            ),
            ContextMenuAction(
                "multi_compare.show_slot_properties",
                self._tr("context.properties", "Properties"),
                icon=Icon.PHOTO,
                data=slot.id,
            ),
            ContextMenuAction(
                "multi_compare.carry_slot",
                self._tr("context.carry_image", "Move"),
                icon=Icon.PHOTO,
                enabled=bool(slot.path),
                data=slot.id,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "multi_compare.remove_slot",
                self._tr("context.remove", "Remove"),
                icon=Icon.DELETE,
                danger=True,
                data=slot.id,
            ),
        )

    def execute(
        self, action_id: str, request: ContextMenuRequest, data: object
    ) -> bool:
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
        if action_id == "multi_compare.carry_slot":
            self._begin_carry(slot)
            return True
        if action_id == "multi_compare.remove_slot":
            self.widget.remove_slot(slot.id)
            return True
        return False

    def _slot(
        self, request: ContextMenuRequest, slot_id: object = None
    ) -> CompareSlot | None:
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
            QLineEdit.EchoMode.Normal,
            slot.label,
        )
        if ok:
            self.widget.store.dispatch(actions.rename_slot(slot.id, text.strip()))

    def _duplicate_slot(self, slot: CompareSlot) -> None:
        if slot.image is None or self.widget.state.root is None:
            return
        self.widget.begin_pending_duplicate(slot.id)

    def _begin_carry(self, slot: CompareSlot) -> None:
        if not slot.path:
            return
        from events.image_carry import begin_image_carry

        begin_image_carry([slot.path], image=slot.image)

    def _show_properties(self, slot: CompareSlot) -> None:
        ordered = [leaf.slot_id for leaf in leaves(self.widget.state.root)]
        total = len(ordered)
        try:
            position = ordered.index(slot.id) + 1
            position_text = f"{position} / {total}"
        except ValueError:
            position_text = str(slot.id)
        open_image_properties_dialog(
            path=slot.path,
            display_name=slot.label,
            image=slot.image,
            app_rows=(("image_properties.position", "Position", position_text),),
            language=get_current_language() or "en",
            tr_func=app_tr,
        )

    def _tr(self, key: str, default: str) -> str:
        translate = getattr(self.widget, "_translate", None)
        if callable(translate):
            return translate(key, default)
        return default
