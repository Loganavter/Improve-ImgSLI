from __future__ import annotations

from tabs.host_helpers import AppTextInputDialog
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
        can_duplicate = self._has_pixels(slot) and (
            len(self.widget.state.slots) < self.widget.state.max_slots
        )
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
                enabled=can_duplicate,
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
                icon=Icon.MOVE,
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
            self._remove_slot(slot)
            return True
        return False

    def _slot(
        self, request: ContextMenuRequest, slot_id: object = None
    ) -> CompareSlot | None:
        sid = slot_id if slot_id is not None else request.target.id
        try:
            sid = int(sid)  # type: ignore[arg-type]  # sid is duck-typed
        except (TypeError, ValueError):
            return None
        return next((slot for slot in self.widget.state.slots if slot.id == sid), None)

    @staticmethod
    def _cache(widget):
        canvas = getattr(widget, "canvas", None)
        return getattr(canvas, "pixel_cache", None)

    def _has_pixels(self, slot: CompareSlot) -> bool:
        """B1: tier presence resolves from the session cache, not the slot."""
        try:
            from tabs.multi_compare.pipeline.cache import resolve_slot_source

            return resolve_slot_source(self._cache(self.widget), slot) is not None
        except Exception:
            return False

    def _pixel_source(self, slot: CompareSlot):
        try:
            from tabs.multi_compare.pipeline.cache import resolve_slot_source

            return resolve_slot_source(self._cache(self.widget), slot)
        except Exception:
            return None

    def _remove_slot(self, slot: CompareSlot) -> None:
        """Removal via the controller path so inflight decodes cancel first.

        ``controller.remove_slot`` → ``preview_decode.remove_slot_with_cancel``
        (AbortSignal-style cancel-on-remove); the widget's direct dispatch
        is the headless fallback (same end state, no cancel).
        """
        try:
            ctrl = getattr(self.widget, "_controller", None)
        except Exception:
            ctrl = None
        remove = getattr(ctrl, "remove_slot", None)
        if callable(remove):
            try:
                remove(slot.id)
                return
            except Exception:
                pass
        self.widget.remove_slot(slot.id)

    def _fail(self, message: str) -> None:
        """User-visible failure signal (toast/bus, never silent, never raising).

        Routes through the controller's single error channel
        (``CoreErrorOccurredEvent`` → warning dialog by house policy);
        falls back to a loud log when no controller/bus is reachable
        (headless fakes).
        """
        try:
            ctrl = getattr(self.widget, "_controller", None)
        except Exception:
            ctrl = None
        report = getattr(ctrl, "report_user_error", None)
        if callable(report):
            try:
                report(message)
                return
            except Exception:
                pass
        import logging as _logging

        _logging.getLogger("ImproveImgSLI").warning("mc menu: %s", message)

    def _grid_full_message(self) -> str:
        try:
            max_slots = self.widget.state.max_slots
        except Exception:
            max_slots = None
        default = (
            f"Comparison grid is full ({max_slots} images max)"
            if max_slots is not None
            else "Comparison grid is full"
        )
        return self._tr("msg.compare_grid_full", default)

    def _rename_slot(self, slot: CompareSlot) -> None:
        text, ok = AppTextInputDialog.get_text(
            self.widget,
            self._tr("context.rename", "Rename"),
            self._tr("context.name", "Name"),
            slot.label,
        )
        if ok:
            self.widget.store.dispatch(actions.rename_slot(slot.id, text.strip()))

    def _duplicate_slot(self, slot: CompareSlot) -> None:
        if not self._has_pixels(slot) or self.widget.state.root is None:
            self._fail(
                self._tr(
                    "msg.compare_nothing_to_duplicate",
                    "Nothing to duplicate — this slot has no loaded image.",
                )
            )
            return
        try:
            full = len(self.widget.state.slots) >= self.widget.state.max_slots
        except Exception:
            full = False
        if full:
            # entries_for disables the action when full, but palette/keyboard
            # invocation bypasses `enabled` — signal instead of arming a
            # duplicate that begin_pending_duplicate would silently drop.
            self._fail(self._grid_full_message())
            return
        self.widget.begin_pending_duplicate(slot.id)

    def _begin_carry(self, slot: CompareSlot) -> None:
        if not slot.path:
            self._fail(
                self._tr(
                    "msg.compare_nothing_to_carry",
                    "Nothing to carry — this slot is empty.",
                )
            )
            return
        from events.image_carry import begin_image_carry

        begin_image_carry([slot.path], image=self._pixel_source(slot))

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
            image=self._pixel_source(slot),
            app_rows=(("image_properties.position", "Position", position_text),),
            language=get_current_language() or "en",
            tr_func=app_tr,
        )

    def _tr(self, key: str, default: str) -> str:
        translate = getattr(self.widget, "_translate", None)
        if callable(translate):
            return translate(key, default)
        return default