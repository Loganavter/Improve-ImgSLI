from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.constants import AppConstants
from resources.translations import tr

class InterpolationFlyoutController:
    def __init__(self, manager):
        self.manager = manager

    def toggle(self):
        host = self.manager.host
        if host._interp_popup_open:
            self.close()
            return
        self.show()

    def show(self):
        from shared_toolkit.ui.widgets.composite.simple_options_flyout import (
            SimpleOptionsFlyout,
        )

        host = self.manager.host
        if host._interp_flyout is None:
            host._interp_flyout = SimpleOptionsFlyout(host.parent_widget)
            host._interp_flyout.closed.connect(self.on_closed)

        lang = host.store.settings.current_language

        interp_translation_map = {
            "NEAREST": "magnifier.nearest_neighbor",
            "BILINEAR": "magnifier.bilinear",
            "BICUBIC": "magnifier.bicubic",
            "LANCZOS": "magnifier.lanczos",
            "EWA_LANCZOS": "magnifier.ewa_lanczos",
        }
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        labels = [
            tr(
                interp_translation_map.get(
                    key,
                    f"magnifier.{AppConstants.INTERPOLATION_METHODS_MAP[key].lower().replace(' ', '_')}",
                ),
                lang,
            )
            for key in method_keys
        ]

        try:
            target_key = getattr(
                host.store.viewport.render_config,
                "interpolation_method",
                AppConstants.DEFAULT_INTERPOLATION_METHOD,
            )
            if target_key not in method_keys:
                target_key = (
                    AppConstants.DEFAULT_INTERPOLATION_METHOD
                    if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys
                    else method_keys[0]
                )
                host.store.viewport.render_config.interpolation_method = target_key
                host.store.emit_state_change()
            current_index = method_keys.index(target_key) if method_keys else 0
        except (AttributeError, ValueError, IndexError):
            current_index = 0

        try:
            host._interp_flyout.item_chosen.disconnect()
        except TypeError:
            pass

        item_height = 34
        item_font = QApplication.font()
        combo = getattr(host.ui, "combo_interpolation", None)
        if combo is not None:
            if hasattr(combo, "getItemHeight"):
                item_height = combo.getItemHeight()
            if hasattr(combo, "getItemFont"):
                item_font = combo.getItemFont()

        host._interp_flyout.set_row_height(item_height)
        host._interp_flyout.set_row_font(item_font)
        host._interp_flyout.populate(labels, current_index)
        host._interp_flyout.item_chosen.connect(self.apply_choice)

        if combo is not None:
            combo.setFlyoutOpen(True)
            host._interp_last_open_ts = time.monotonic()

        def _do_show():
            if host._interp_flyout is not None and combo is not None:
                host._interp_flyout.show_below(combo)
                host._interp_popup_open = True
                host._interp_last_open_ts = time.monotonic()

        QTimer.singleShot(0, _do_show)

    def apply_choice(self, idx: int):
        host = self.manager.host
        try:
            combo = getattr(host.ui, "combo_interpolation", None)
            if combo is not None and 0 <= idx < combo.count():
                combo.setCurrentIndex(idx)
                controller = getattr(host, "main_controller", None)
                if controller is not None:
                    if hasattr(controller, "on_interpolation_changed"):
                        controller.on_interpolation_changed(idx)
                    elif getattr(controller, "sessions", None) is not None:
                        controller.sessions.on_interpolation_changed(idx)
        finally:
            self.close()

    def close(self):
        host = self.manager.host
        if host._interp_flyout is not None:
            host._interp_flyout.hide()
        combo = getattr(host.ui, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        host._interp_popup_open = False

    def on_closed(self):
        host = self.manager.host
        combo = getattr(host.ui, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        host._interp_popup_open = False
