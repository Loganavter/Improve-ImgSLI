from __future__ import annotations

import time

from PyQt6.QtCore import QTimer

class FlyoutController:
    def __init__(self, manager):
        self.manager = manager

    def show_flyout(self, image_number: int):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

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
                host.ui.combo_image1.setFlyoutOpen(False)
                host.ui.combo_image2.setFlyoutOpen(False)
                host.unified_flyout.start_closing_animation()
                return

            if (
                host.unified_flyout.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_RIGHT)
                and host.unified_flyout.source_list_num == image_number
            ):
                button = host.ui.combo_image1 if image_number == 1 else host.ui.combo_image2
                button.setFlyoutOpen(False)
                host.unified_flyout.start_closing_animation()
                return

        target_list = host.store.document.image_list1 if image_number == 1 else host.store.document.image_list2
        if len(target_list) == 0:
            return

        button = host.ui.combo_image1 if image_number == 1 else host.ui.combo_image2
        other_button = host.ui.combo_image2 if image_number == 1 else host.ui.combo_image1
        other_button.setFlyoutOpen(False)
        button.setFlyoutOpen(True)

        if host.unified_flyout is not None:
            host.unified_flyout.showAsSingle(image_number, button)

        QTimer.singleShot(0, self.sync_flyout_combo_status)

    def sync_flyout_combo_status(self):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout.mode == FlyoutMode.DOUBLE:
            host.ui.combo_image1.setFlyoutOpen(True)
            host.ui.combo_image2.setFlyoutOpen(True)

    def repopulate_flyouts(self):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout and host.unified_flyout.isVisible():
            host.unified_flyout.populate(1, host.store.document.image_list1)
            host.unified_flyout.populate(2, host.store.document.image_list2)
            if host.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(
                    0, lambda: host.unified_flyout.refreshGeometry(immediate=False)
                )

    def on_flyout_closed(self, image_number: int):
        host = self.manager.host
        button = host.ui.combo_image1 if image_number == 1 else host.ui.combo_image2
        button.setFlyoutOpen(False)

    def on_unified_flyout_closed(self):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        host = self.manager.host
        if host.unified_flyout is not None:
            host.unified_flyout.mode = FlyoutMode.HIDDEN
        host.ui.combo_image1.setFlyoutOpen(False)
        host.ui.combo_image2.setFlyoutOpen(False)
        self.on_flyout_closed(1)
        self.on_flyout_closed(2)
