from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.constants import AppConstants
from sli_ui_toolkit.i18n import tr

_INTERP_LABEL_KEYS: dict[str, str] = {
    "NEAREST": "magnifier.nearest_neighbor",
    "BILINEAR": "magnifier.bilinear",
    "BICUBIC": "magnifier.bicubic",
    "LANCZOS": "magnifier.lanczos",
    "EWA_LANCZOS": "magnifier.ewa_lanczos",
}


class InterpolationFlyoutController:
    def __init__(self, manager, widget):
        self.manager = manager
        self.widget = widget

    def toggle(self):
        host = self.manager.host
        if host._interp_popup_open:
            self.close()
            return
        self.show()

    def open(self):
        """Open the options list (never toggle-close). Find Action path."""
        self.show()

    def show(self):
        from sli_ui_toolkit.widgets import SimpleOptionsFlyout

        # Find Action / cold open: combo lives on magnifier_settings_panel,
        # which is hidden until the magnifier is on — same idea as
        # FontSettingsController._ensure_text_settings_chrome.
        self.ensure_panel_visible()

        host = self.manager.host
        if host._interp_flyout is None:
            host._interp_flyout = SimpleOptionsFlyout(host.parent_widget)
            host._interp_flyout.closed.connect(self.on_closed)
            host._interp_flyout.item_chosen.connect(self.apply_choice)
            # combo_interpolation lives inside magnifier_settings_flyout's
            # own content -- link them so AnchoredFlyoutAutoHide (see its
            # MagnifierSettingsHoverController) treats the cursor moving
            # onto this dropdown as still "inside", not a reason to
            # auto-hide the settings panel out from under an in-progress
            # pick. See sli_ui_toolkit's flyout_timer_service.py.
            settings_flyout = getattr(self.widget, "magnifier_settings_flyout", None)
            if settings_flyout is not None:
                from sli_ui_toolkit.managers import FlyoutManager

                FlyoutManager.get_instance().link(settings_flyout, host._interp_flyout)

        lang = host.store.settings.current_language
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        labels = [
            tr(
                _INTERP_LABEL_KEYS.get(
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

        item_height = 34
        from sli_ui_toolkit.managers import ui_font

        item_font = ui_font()
        combo = getattr(self.widget, "combo_interpolation", None)
        if combo is not None:
            if hasattr(combo, "getItemHeight"):
                item_height = combo.getItemHeight()
            if hasattr(combo, "getItemFont"):
                item_font = combo.getItemFont()

        host._interp_flyout.set_row_height(item_height)
        host._interp_flyout.set_row_font(item_font)
        host._interp_flyout.populate(labels, current_index)

        if combo is not None:
            combo.setFlyoutOpen(True)

        # Already open (Find Action ensure_visible again): refresh rows only —
        # show_below would toggle-close on the same anchor.
        if (
            host._interp_popup_open
            and host._interp_flyout.isVisible()
            and getattr(host._interp_flyout, "_anchor_widget", None) is combo
        ):
            return

        def _do_show():
            if host._interp_flyout is not None and combo is not None:
                host._interp_flyout.show_below(combo)
                host._interp_popup_open = True

        QTimer.singleShot(0, _do_show)

    def index_for_data(self, data: object) -> int:
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        try:
            return method_keys.index(data)
        except ValueError:
            return -1

    def choose_index(self, index: int) -> None:
        self.apply_choice(index)

    def choose_data(self, data: object) -> None:
        index = self.index_for_data(data)
        if index < 0:
            return
        self.apply_choice(index)

    def row_widget(self, index: int):
        host = self.manager.host
        flyout = getattr(host, "_interp_flyout", None)
        if flyout is None:
            return None
        getter = getattr(flyout, "row_widget", None)
        if callable(getter):
            return getter(index)
        layout = getattr(flyout, "_rows_layout", None)
        if layout is None:
            return None
        if not (0 <= index < max(0, layout.count() - 1)):
            return None
        item = layout.itemAt(index)
        return item.widget() if item is not None else None

    def apply_choice(self, idx: int):
        host = self.manager.host
        method_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        try:
            combo = getattr(self.widget, "combo_interpolation", None)
            if combo is not None and 0 <= idx < combo.count():
                combo.setCurrentIndex(idx)
                controller = getattr(host, "main_controller", None)
                if controller is not None:
                    if hasattr(controller, "on_interpolation_changed"):
                        controller.on_interpolation_changed(idx)
                    elif getattr(controller, "sessions", None) is not None:
                        controller.sessions.on_interpolation_changed(idx)
            elif 0 <= idx < len(method_keys) and getattr(host, "store", None) is not None:
                host.store.viewport.render_config.interpolation_method = method_keys[idx]
                if hasattr(host.store, "emit_state_change"):
                    host.store.emit_state_change()
        finally:
            self.close()

    def close(self):
        host = self.manager.host
        if host._interp_flyout is not None:
            host._interp_flyout.hide()
        combo = getattr(self.widget, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        host._interp_popup_open = False
        self._cancel_settings_auto_hide()

    def on_closed(self):
        host = self.manager.host
        combo = getattr(self.widget, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        host._interp_popup_open = False
        self._cancel_settings_auto_hide()

    def _cancel_settings_auto_hide(self) -> None:
        """Drop any pending hover-leave auto-hide on magnifier_settings_flyout.

        The dropdown opens well below the settings panel/toolbar, so by the
        time it closes (e.g. right after picking an item) the cursor is
        nowhere near either safe zone AnchoredFlyoutAutoHide checks -- its
        still-pending timer (scheduled by the earlier hover-leave onto the
        dropdown, deferred only while the dropdown itself stayed visible,
        see FlyoutManager.link() in show() above) would otherwise fire
        within its retry window and close the panel right out from under
        the selection. Cancelling here "pins" it open until the next real
        hover/click elsewhere re-establishes normal auto-hide.
        """
        settings_flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if settings_flyout is not None:
            settings_flyout.cancel_auto_hide()

    def has_focus_inside(self, new_widget) -> bool:
        if new_widget is None:
            return False
        host = self.manager.host
        for anchor in (getattr(self.widget, "combo_interpolation", None), host._interp_flyout):
            if anchor is None:
                continue
            parent = new_widget
            while parent is not None:
                if parent is anchor:
                    return True
                parent = parent.parent()
        return False

    def ensure_panel_visible(self) -> None:
        """Show magnifier_settings_panel (sliders + ``combo_interpolation`` row).

        Shared by the interpolation flyout's cold-open path and by the
        magnifier slider Find Action rows, which anchor to the same panel.
        """
        widget = self.widget
        panel = getattr(widget, "magnifier_settings_panel", None)
        combo = getattr(widget, "combo_interpolation", None)
        if self._is_alive_and_visible(panel) and self._is_alive_and_visible(combo):
            return

        opener = getattr(widget, "open_magnifier_settings_flyout", None)
        if callable(opener):
            opener()

        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    @staticmethod
    def _is_alive_and_visible(widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.isVisible())
        except RuntimeError:
            return False
