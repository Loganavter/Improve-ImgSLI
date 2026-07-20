from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtGui import QCursor

_dbg = logging.getLogger("ImproveImgSLI.flyout")  # TEMP debug


class _PressProbe(QObject):  # TEMP debug: who receives left presses while flyout is open
    def __init__(self, get_flyout):
        super().__init__()
        self._get_flyout = get_flyout

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            try:
                button = event.button()
            except Exception:
                button = None
            if button == Qt.MouseButton.LeftButton:
                flyout = self._get_flyout()
                if flyout is not None and flyout.isVisible():
                    from PySide6.QtWidgets import QWidget
                    inside = flyout is watched or (
                        isinstance(watched, QWidget) and flyout.isAncestorOf(watched)
                    )
                    _dbg.debug(
                        "[DBG-MARQUEE] app press target=%s.%s inside_flyout=%s",
                        type(watched).__name__, watched.objectName(), inside,
                    )
        return False


class FlyoutController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget
        self._context_menu_provider = None
        flyout = getattr(manager.host, "unified_flyout", None)
        from PySide6.QtWidgets import QApplication
        self._press_probe = _PressProbe(lambda: getattr(self.manager.host, "unified_flyout", None))
        QApplication.instance().installEventFilter(self._press_probe)
        if flyout is not None and hasattr(flyout, "set_list_anchors"):
            left = getattr(widget, "combo_image1", None)
            right = getattr(widget, "combo_image2", None)
            if left is not None and right is not None:
                flyout.set_list_anchors(left, right)
        self._install_context_menu()

    def _sync_flyout_anchors(self) -> None:
        flyout = getattr(self.manager.host, "unified_flyout", None)
        if flyout is None or not hasattr(flyout, "set_list_anchors"):
            return
        left = getattr(self.widget, "combo_image1", None)
        right = getattr(self.widget, "combo_image2", None)
        if left is not None and right is not None:
            flyout.set_list_anchors(left, right)

    def _install_context_menu(self) -> None:
        from tabs.image_compare.ui.context_menu import ImageCompareContextMenuProvider
        from ui.context_menu.manager import install_context_menu_provider

        host = self.manager.host
        store = getattr(host, "store", None)
        if store is None:
            return
        canvas = getattr(self.widget, "image_label", None)
        flyout = getattr(host, "unified_flyout", None)
        provider = ImageCompareContextMenuProvider(
            canvas, store, flyout=flyout, ui_manager=host
        )
        sessions = getattr(getattr(host, "main_controller", None), "sessions", None)
        if sessions is not None:
            provider.attach_session_controller(sessions)
        self._context_menu_provider = install_context_menu_provider(provider)
        if canvas is not None and hasattr(canvas, "set_context_menu_provider"):
            canvas.set_context_menu_provider(provider)
        if flyout is not None and hasattr(flyout, "item_context_menu_requested"):
            flyout.item_context_menu_requested.connect(self._on_item_context_menu)

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
        from sli_ui_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout:
            time_since_close = time.monotonic() - host.unified_flyout.last_close_timestamp
            is_same_list = host.unified_flyout.source_list_num == image_number
            if (
                host.unified_flyout.last_close_mode == FlyoutMode.DOUBLE
                and time_since_close < 0.2
            ) or (is_same_list and time_since_close < 0.2):
                return

        if host.unified_flyout is not None and host.unified_flyout.isVisible():
            if host.unified_flyout.mode == FlyoutMode.DOUBLE:
                self.widget.combo_image1.setFlyoutOpen(False)
                self.widget.combo_image2.setFlyoutOpen(False)
                host.unified_flyout.start_closing_animation()
                return

            if (
                host.unified_flyout.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_RIGHT)
                and host.unified_flyout.source_list_num == image_number
            ):
                button = self.widget.combo_image1 if image_number == 1 else self.widget.combo_image2
                button.setFlyoutOpen(False)
                host.unified_flyout.start_closing_animation()
                return

        document = host.store.get_session_state_slot("document")
        target_list = document.image_list1 if image_number == 1 else document.image_list2
        if len(target_list) == 0:
            return

        button = self.widget.combo_image1 if image_number == 1 else self.widget.combo_image2
        other_button = self.widget.combo_image2 if image_number == 1 else self.widget.combo_image1
        other_button.setFlyoutOpen(False)
        button.setFlyoutOpen(True)

        if host.unified_flyout is not None:
            host.unified_flyout.showAsSingle(image_number, button)

        QTimer.singleShot(0, self.sync_flyout_combo_status)

    def sync_flyout_combo_status(self):
        from sli_ui_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout.mode == FlyoutMode.DOUBLE:
            self.widget.combo_image1.setFlyoutOpen(True)
            self.widget.combo_image2.setFlyoutOpen(True)

    def repopulate_flyouts(self):
        from sli_ui_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout and host.unified_flyout.isVisible():
            document = host.store.get_session_state_slot("document")
            host.unified_flyout.populate(1, document.image_list1)
            host.unified_flyout.populate(2, document.image_list2)
            if host.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(
                    0, lambda: host.unified_flyout.refreshGeometry(immediate=False)
                )

    def on_flyout_closed(self, image_number: int):
        host = self.manager.host
        button = self.widget.combo_image1 if image_number == 1 else self.widget.combo_image2
        button.setFlyoutOpen(False)

    def on_unified_flyout_closed(self):
        from sli_ui_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout is not None:
            host.unified_flyout.mode = FlyoutMode.HIDDEN
        self.widget.combo_image1.setFlyoutOpen(False)
        self.widget.combo_image2.setFlyoutOpen(False)
        self.on_flyout_closed(1)
        self.on_flyout_closed(2)
