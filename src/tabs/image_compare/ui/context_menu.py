# Audit-Meta: pattern=thin-owner size=exempt reason="single menu-surface aggregator — slot/list menus share entry/execute shape; per-action sections stay co-located"
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSeparator,
)

from plugins.image_properties.plugin import open_image_properties_dialog
from tabs.host_helpers import AppTextInputDialog
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
        if action_id == "image_compare.carry_image":
            self._begin_carry_slot(slot)
            return True
        if action_id == "image_compare.crop_override_slot":
            self._cycle_crop_override_slot(slot)
            return True
        if action_id == "image_compare.remove_image":
            self._remove_image(slot)
            return True
        return False

    def _slot_entries(self, slot: int) -> tuple[ContextMenuEntry, ...]:
        return (
            ContextMenuAction(
                "image_compare.copy_path",
                self._tr("image_compare.action.context_copy_path", "Copy path"),
                icon=Icon.COPY,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.duplicate_image",
                self._tr("image_compare.action.context_duplicate", "Duplicate"),
                icon=Icon.ADD,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.show_properties",
                self._tr("image_compare.action.context_properties", "Properties"),
                icon=Icon.PHOTO,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.carry_image",
                self._tr("image_compare.action.context_carry_image", "Move"),
                icon=Icon.MOVE,
                data=slot,
            ),
            ContextMenuAction(
                "image_compare.crop_override_slot",
                self._crop_override_label_for_slot(slot),
                icon=self._crop_override_icon_for_slot(slot),
                data=slot,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.remove_image",
                self._tr("image_compare.action.context_remove", "Remove"),
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
                self._tr("image_compare.action.context_rename", "Rename"),
                icon=Icon.TEXT_MANIPULATOR,
                data=ref,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.copy_path",
                self._tr("image_compare.action.context_copy_path", "Copy path"),
                icon=Icon.COPY,
                data=ref,
            ),
            ContextMenuAction(
                "image_compare.show_properties",
                self._tr("image_compare.action.context_properties", "Properties"),
                icon=Icon.PHOTO,
                data=ref,
            ),
            ContextMenuAction(
                "image_compare.carry_list_item",
                self._tr("image_compare.action.context_carry_image", "Move"),
                icon=Icon.MOVE,
                data=ref,
            ),
            ContextMenuAction(
                "image_compare.crop_override_list_item",
                self._crop_override_label(list_num, index),
                icon=self._crop_override_icon(list_num, index),
                data=ref,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_compare.remove_list_item",
                self._tr("image_compare.action.context_remove", "Remove"),
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
        if action_id == "image_compare.carry_list_item":
            self._begin_carry_list_item(list_num, index)
            return True
        if action_id == "image_compare.crop_override_list_item":
            self._cycle_crop_override_list_item(list_num, index)
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
            self._tr("image_compare.action.context_rename", "Rename"),
            self._tr("image_compare.action.context_name", "Name"),
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

    @staticmethod
    def _next_crop_override(current: bool | None) -> bool | None:
        """Cycle the tristate: Auto (None) → On (True) → Off (False) → Auto."""
        if current is None:
            return True
        if bool(current):
            return False
        return None

    def _crop_override_for_list_item(self, list_num: int, index: int) -> bool | None:
        try:
            item = self._list_item(list_num, index)
        except Exception:
            return None
        if item is None:
            return None
        value = getattr(item, "crop_override", None)
        return None if value is None else bool(value)

    def _crop_override_label(self, list_num: int, index: int) -> str:
        base = self._tr("image_compare.action.context_crop_override", "Crop")
        state = self._crop_override_for_list_item(list_num, index)
        if state is True:
            suffix = self._tr("image_compare.action.context_crop_on", "On")
        elif state is False:
            suffix = self._tr("image_compare.action.context_crop_off", "Off")
        else:
            suffix = self._tr("image_compare.action.context_crop_auto", "Auto")
        return f"{base}: {suffix}"

    def _crop_override_icon(self, list_num: int, index: int):
        state = self._crop_override_for_list_item(list_num, index)
        if state is True:
            return Icon.CROP_IN
        if state is False:
            return Icon.CROP_OUT
        return Icon.SCISSORS

    def _crop_override_label_for_slot(self, slot: int) -> str:
        try:
            document = self.store.get_session_state_slot("document")
            index = document.current_index1 if slot == 1 else document.current_index2
        except Exception:
            index = -1
        return self._crop_override_label(slot, index)

    def _crop_override_icon_for_slot(self, slot: int):
        try:
            document = self.store.get_session_state_slot("document")
            index = document.current_index1 if slot == 1 else document.current_index2
        except Exception:
            index = -1
        return self._crop_override_icon(slot, index)

    def _cycle_crop_override_list_item(self, list_num: int, index: int) -> None:
        # Rename structural pattern: controller call with (list_num, index);
        # post-action refresh via the controller's dispatch, else explicit
        # document emit + canvas update. Deliberately NOT the rating path
        # (in-place item mutation) — the override persists via
        # SetCropOverrideAction + DocumentReducer.
        try:
            item = self._list_item(list_num, index)
        except Exception:
            return
        if item is None:
            return
        nxt = self._next_crop_override(getattr(item, "crop_override", None))
        ctrl = self._session_ctrl
        if ctrl is not None and hasattr(ctrl, "set_crop_override_at_index"):
            ctrl.set_crop_override_at_index(list_num, index, nxt)
        else:
            document_store_ops.set_crop_override(self.store, list_num, index, nxt)
            self.store.emit_state_change("document")
        if self.canvas is not None:
            try:
                self.canvas.update()
            except Exception:
                pass

    def _cycle_crop_override_slot(self, slot: int) -> None:
        try:
            document = self.store.get_session_state_slot("document")
            index = document.current_index1 if slot == 1 else document.current_index2
        except Exception:
            return
        self._cycle_crop_override_list_item(slot, index)

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
            slot = int(raw)  # type: ignore[arg-type]  # raw is duck-typed
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
            list_num = int(payload.get("list_num"))  # type: ignore[arg-type]  # payload values are dynamic
            index = int(payload.get("index"))  # type: ignore[arg-type]
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

    def _peek_image(self, slot: int):
        try:
            doc = self.store.get_session_state_slot("document")
            path = getattr(doc, f"image{slot}_path", None)
            if not path:
                return None
            try:
                vp = self.store.viewport.session_data.image_state
                cand = vp.image1 if slot == 1 else vp.image2
                if cand is not None and getattr(cand, "is_open", True):
                    try:
                        if hasattr(cand, "isNull") and cand.isNull():
                            cand = None
                        elif hasattr(cand, "is_open") and not cand.is_open:
                            cand = None
                    except Exception:
                        pass
                    if cand is not None:
                        return cand
            except Exception:
                pass
            try:
                ps = self.store.get_session_state_slot("pipeline")
                if ps is not None:
                    import os

                    from tabs.image_compare.pipeline.cache import _pixel_key, _preview_key

                    for cache_dict, key_fn in ((ps.pixel, _pixel_key), (ps.preview, _preview_key)):
                        try:
                            k = key_fn(path, None, None)
                            v = cache_dict.get(k)
                            if v is not None and getattr(v, "is_open", True) and not (hasattr(v, "isNull") and v.isNull()):
                                return v
                        except Exception:
                            pass
                        try:
                            norm = os.path.normpath(path)
                            for kk, vv in cache_dict.items():
                                if kk[0] == norm and getattr(vv, "is_open", True) and not (hasattr(vv, "isNull") and vv.isNull()):
                                    return vv
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass
        return None

    def _show_properties(self, slot: int) -> None:
        path = self._path_for(slot)
        name = self._display_name_for(slot)
        image = self._peek_image(slot)
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
        image = self._peek_image(source_slot)
        path = self._path_for(source_slot)
        name = self._display_name_for(source_slot)
        if image is None and not path:
            return
        canvas = self.canvas
        if canvas is None:
            return
        parent = canvas.window()
        if parent is None:
            return
        view_state = self.store.viewport.view_state
        is_horizontal = bool(getattr(view_state, "is_horizontal", False))

        def on_dir(direction: str) -> None:
            target = 1 if direction in ("up", "left") else 2
            ctrl = self._session_ctrl
            if ctrl is not None and hasattr(ctrl, "duplicate_image_to_slot") and path:
                ctrl.duplicate_image_to_slot(source_slot, target)
                return
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

        from services.system.paste_direction_overlay import show_paste_direction_overlay

        show_paste_direction_overlay(
            parent=parent,
            image_label=canvas,
            is_horizontal=is_horizontal,
            language=get_current_language() or "en",
            on_direction=on_dir,
        )

    def _begin_carry_slot(self, slot: int) -> None:
        path = self._path_for(slot)
        if not path:
            return
        image = self._peek_image(slot)
        from events.image_carry import begin_image_carry

        begin_image_carry([path], image=image)

    def _begin_carry_list_item(self, list_num: int, index: int) -> None:
        path = self._list_item_path(list_num, index)
        if not path:
            return
        from events.image_carry import begin_image_carry

        begin_image_carry([path])

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
