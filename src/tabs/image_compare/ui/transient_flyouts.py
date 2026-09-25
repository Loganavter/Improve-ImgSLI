from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor


class FlyoutController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget
        self._context_menu_provider = None
        self._sync_flyout_anchors()
        self._install_context_menu()

    def _sync_flyout_anchors(self) -> None:
        """Re-read the list anchors from the current combo widgets.

        Runs lazily on every ``show_flyout`` (and once at construction), so
        anchors are never cached across a tab switch that hid the flyout —
        the next show re-syncs from whatever combos exist now. Fail-open:
        missing manager/host/widget refs never crash the show path.
        """
        try:
            manager = getattr(self, "manager", None)
            host = getattr(manager, "host", None)
            flyout = getattr(host, "unified_flyout", None)
        except Exception:
            return
        if flyout is None or not hasattr(flyout, "set_list_anchors"):
            return
        try:
            widget = getattr(self, "widget", None)
            left = getattr(widget, "combo_image1", None)
            right = getattr(widget, "combo_image2", None)
        except Exception:
            return
        if left is not None and right is not None:
            try:
                flyout.set_list_anchors(left, right)
            except Exception:
                pass

    def _install_context_menu(self) -> None:
        from tabs.image_compare.ui.context_menu import (
            ensure_image_compare_context_menu,
        )

        host = self.manager.host
        store = getattr(host, "store", None)
        if store is None:
            return
        canvas = getattr(self.widget, "image_label", None)
        flyout = getattr(host, "unified_flyout", None)
        sessions = getattr(getattr(host, "main_controller", None), "sessions", None)
        # Find-or-create: the provider is installed eagerly at canvas-wiring
        # time; reuse it (attaching this controller's flyout) instead of
        # registering a second provider, which would duplicate menu entries.
        provider = ensure_image_compare_context_menu(
            canvas, store, sessions=sessions, ui_manager=host, flyout=flyout
        )
        self._context_menu_provider = provider
        if flyout is not None and hasattr(flyout, "item_context_menu_requested"):
            # find-or-create may run again (e.g. late controller construction
            # after the eager wiring install): connect each flyout once.
            if getattr(self, "_item_menu_connected_flyout", None) is not flyout:
                previous = getattr(self, "_item_menu_connected_flyout", None)
                if previous is not None:
                    try:
                        previous.item_context_menu_requested.disconnect(
                            self._on_item_context_menu
                        )
                    except (TypeError, RuntimeError):
                        pass
                flyout.item_context_menu_requested.connect(
                    self._on_item_context_menu
                )
                self._item_menu_connected_flyout = flyout

    def _on_item_context_menu(self, list_num: int, index: int) -> None:
        from ui.context_menu.manager import open_context_menu
        from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget

        flyout = getattr(self.manager.host, "unified_flyout", None)
        if flyout is None:
            return
        global_pos = QCursor.pos()
        open_context_menu(
            ContextMenuRequest(
                source_widget=flyout,
                global_pos=global_pos,
                local_pos=flyout.mapFromGlobal(global_pos),
                session_type="image_compare",
                target=ContextMenuTarget(
                    kind="image_compare_list_item",
                    id=(list_num, index),
                    payload={"list_num": list_num, "index": index},
                ),
            )
        )

    def show_flyout(self, image_number: int):
        self._sync_flyout_anchors()
        from ui.widgets.unified_list_picker import FlyoutMode

        host = getattr(getattr(self, "manager", None), "host", None)
        widget = getattr(self, "widget", None)
        if host is None or widget is None:
            return
        unified = getattr(host, "unified_flyout", None)
        if unified is not None:
            try:
                time_since_close = time.monotonic() - unified.last_close_timestamp
                is_same_list = unified.source_list_num == image_number
                last_close_mode = unified.last_close_mode
            except Exception:
                return
            if (
                last_close_mode == FlyoutMode.DOUBLE
                and time_since_close < 0.2
            ) or (is_same_list and time_since_close < 0.2):
                return

        try:
            unified_visible = (
                bool(unified.isVisible()) if unified is not None else False
            )
        except Exception:
            return
        if unified is not None and unified_visible:
            if unified.mode == FlyoutMode.DOUBLE:
                widget.combo_image1.setFlyoutOpen(False)
                widget.combo_image2.setFlyoutOpen(False)
                unified.start_closing_animation()
                return

            if (
                unified.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_RIGHT)
                and unified.source_list_num == image_number
            ):
                button = widget.combo_image1 if image_number == 1 else widget.combo_image2
                button.setFlyoutOpen(False)
                unified.start_closing_animation()
                return

        document = host.store.get_session_state_slot("document")
        target_list = document.image_list1 if image_number == 1 else document.image_list2
        if len(target_list) == 0:
            return

        button = widget.combo_image1 if image_number == 1 else widget.combo_image2
        other_button = widget.combo_image2 if image_number == 1 else widget.combo_image1
        other_button.setFlyoutOpen(False)
        button.setFlyoutOpen(True)

        if unified is not None:
            unified.showAsSingle(image_number, button)

        QTimer.singleShot(0, self.sync_flyout_combo_status)

    def sync_flyout_combo_status(self):
        from ui.widgets.unified_list_picker import FlyoutMode

        host = getattr(getattr(self, "manager", None), "host", None)
        unified = getattr(host, "unified_flyout", None) if host is not None else None
        if unified is None:
            return
        try:
            is_double = unified.mode == FlyoutMode.DOUBLE
        except Exception:
            return
        if is_double:
            widget = getattr(self, "widget", None)
            if widget is None:
                return
            try:
                widget.combo_image1.setFlyoutOpen(True)
                widget.combo_image2.setFlyoutOpen(True)
            except Exception:
                pass

    def repopulate_flyouts(self):
        from ui.widgets.unified_list_picker import FlyoutMode

        host = self.manager.host
        if host.unified_flyout and host.unified_flyout.isVisible():
            document = host.store.get_session_state_slot("document")
            host.unified_flyout.populate(
                1,
                document.image_list1,
                current_index=getattr(document, "current_index1", -1),
            )
            host.unified_flyout.populate(
                2,
                document.image_list2,
                current_index=getattr(document, "current_index2", -1),
            )
            if host.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(
                    0, lambda: host.unified_flyout.refreshGeometry(immediate=False)
                )

    def on_flyout_closed(self, image_number: int):
        host = self.manager.host
        button = self.widget.combo_image1 if image_number == 1 else self.widget.combo_image2
        button.setFlyoutOpen(False)

    def on_unified_flyout_closed(self):
        from ui.widgets.unified_list_picker import FlyoutMode

        host = self.manager.host
        if host.unified_flyout is not None:
            host.unified_flyout.mode = FlyoutMode.HIDDEN
        self.widget.combo_image1.setFlyoutOpen(False)
        self.widget.combo_image2.setFlyoutOpen(False)
        self.on_flyout_closed(1)
        self.on_flyout_closed(2)