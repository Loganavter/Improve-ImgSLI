import logging
import time
from typing import Any, Callable, Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, QTimer

from domain.qt_adapters import color_to_qcolor
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.constants import AppConstants
from core.events import (
    ViewportToggleMagnifierPartEvent,
)
from core.plugin_system.ui_integration import PluginUIRegistry
from resources.translations import tr
from shared_toolkit.ui.managers.font_manager import FontManager
from ui.managers.dialog_manager import DialogManager
from ui.managers.message_manager import MessageManager
from ui.managers.transient_ui_manager import TransientUIManager

logger = logging.getLogger("ImproveImgSLI")

class UIManager(QObject):
    def __init__(
        self,
        store,
        main_controller,
        ui,
        parent_widget,
        plugin_ui_registry: PluginUIRegistry | None = None,
    ):
        super().__init__(parent_widget)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.parent_widget = parent_widget
        self.app_ref = parent_widget
        self.plugin_ui_registry = plugin_ui_registry
        self.event_bus = main_controller.event_bus if main_controller else None
        self._settings_application_service = None

        self._active_message_boxes = []

        from shared_toolkit.ui.widgets.composite.unified_flyout import UnifiedFlyout

        self.unified_flyout = UnifiedFlyout(
            self.store, self.main_controller, self.parent_widget
        )

        self.font_settings_flyout: Optional[Any] = None
        self._font_anchor_widget: Optional[Any] = None
        self._is_modal_active = False

        if self.unified_flyout is not None:
            self.unified_flyout.closing_animation_finished.connect(
                self._on_unified_flyout_closed
            )

        self._help_dialog: Optional[Any] = None
        self._settings_dialog: Optional[Any] = None

        self._interp_flyout: Optional[Any] = None
        self._interp_popup_open: bool = False
        self._interp_last_open_ts: float = 0.0

        self._font_popup_open: bool = False
        self._font_popup_last_open_ts: float = 0.0

        self._diff_mode_popup_open: bool = False
        self._diff_mode_last_open_ts: float = 0.0
        self._channel_mode_popup_open: bool = False
        self._channel_mode_last_open_ts: float = 0.0

        if self.ui is not None:
            if hasattr(self.ui, "btn_diff_mode") and self.ui.btn_diff_mode is not None:
                try:
                    self._original_diff_show_menu = self.ui.btn_diff_mode.show_menu

                    def wrapped_diff_show_menu():
                        result = self._original_diff_show_menu()
                        if (
                            hasattr(self.ui.btn_diff_mode, "_menu_visible")
                            and self.ui.btn_diff_mode._menu_visible
                        ):
                            self._diff_mode_popup_open = True
                            self._diff_mode_last_open_ts = time.monotonic()
                        return result

                    self.ui.btn_diff_mode.show_menu = wrapped_diff_show_menu
                except AttributeError as e:
                    logger.warning(
                        f"UIManager.__init__: btn_diff_mode.show_menu not available: {e}"
                    )

            if (
                hasattr(self.ui, "btn_channel_mode")
                and self.ui.btn_channel_mode is not None
            ):
                try:
                    self._original_channel_show_menu = (
                        self.ui.btn_channel_mode.show_menu
                    )

                    def wrapped_channel_show_menu():
                        result = self._original_channel_show_menu()
                        if (
                            hasattr(self.ui.btn_channel_mode, "_menu_visible")
                            and self.ui.btn_channel_mode._menu_visible
                        ):
                            self._channel_mode_popup_open = True
                            self._channel_mode_last_open_ts = time.monotonic()
                        return result

                    self.ui.btn_channel_mode.show_menu = wrapped_channel_show_menu
                except AttributeError as e:
                    logger.warning(
                        f"UIManager.__init__: btn_channel_mode.show_menu not available: {e}"
                    )

        from shared_toolkit.ui.widgets.composite.magnifier_visibility_flyout import (
            MagnifierVisibilityFlyout,
        )

        self.magnifier_visibility_flyout = MagnifierVisibilityFlyout(self.parent_widget)
        self._magn_popup_open: bool = False
        self._magn_popup_last_open_ts: float = 0.0
        self._magn_hover_timer = QTimer(self)
        self._magn_hover_timer.setSingleShot(True)
        self._magn_hover_timer.timeout.connect(
            lambda: self._show_magnifier_visibility_flyout(reason="hover")
        )

        if (
            self.ui is not None
            and hasattr(self.ui, "btn_magnifier")
            and self.ui.btn_magnifier is not None
        ):
            self.ui.btn_magnifier.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.ui.btn_magnifier.installEventFilter(self)
            self.magnifier_visibility_flyout.installEventFilter(self)
            self.ui.btn_magnifier.toggled.connect(self._on_magnifier_toggle_with_hover)

        if self.main_controller is not None:
            viewport_ctrl = getattr(self.main_controller, "viewport_ctrl", None)

            if self.event_bus is not None:

                self.magnifier_visibility_flyout.btn_left.toggled.connect(
                    lambda checked: self.event_bus.emit(
                        ViewportToggleMagnifierPartEvent("left", not checked)
                    )
                )
                self.magnifier_visibility_flyout.btn_right.toggled.connect(
                    lambda checked: self.event_bus.emit(
                        ViewportToggleMagnifierPartEvent("right", not checked)
                    )
                )
                self.magnifier_visibility_flyout.btn_center.toggled.connect(
                    lambda checked: self.event_bus.emit(
                        ViewportToggleMagnifierPartEvent("center", not checked)
                    )
                )
            elif viewport_ctrl is not None and hasattr(
                viewport_ctrl, "toggle_magnifier_part"
            ):

                self.magnifier_visibility_flyout.btn_left.toggled.connect(
                    lambda checked: viewport_ctrl.toggle_magnifier_part(
                        "left", not checked
                    )
                )
                self.magnifier_visibility_flyout.btn_right.toggled.connect(
                    lambda checked: viewport_ctrl.toggle_magnifier_part(
                        "right", not checked
                    )
                )
                self.magnifier_visibility_flyout.btn_center.toggled.connect(
                    lambda checked: viewport_ctrl.toggle_magnifier_part(
                        "center", not checked
                    )
                )
            else:
                logger.warning(
                    "UIManager: Cannot connect magnifier visibility flyout buttons - no event_bus or viewport_ctrl available"
                )

        font_manager = FontManager.get_instance()
        if font_manager is not None:
            font_manager.font_changed.connect(self._on_font_changed)

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_app_focus_changed)
        self._dialog_manager = DialogManager(self)
        self._message_manager = MessageManager(self)
        self._transient_ui_manager = TransientUIManager(self)

    def get_plugin_action(self, action_id: str) -> Callable[..., Any] | None:
        if self.plugin_ui_registry:
            return self.plugin_ui_registry.get_action(action_id)
        return None

    def set_modal_dialog_active(self, active: bool):
        self._is_modal_active = active

    def show_flyout(self, image_number: int):
        self._transient_ui_manager.show_flyout(image_number)

    def _sync_flyout_combo_status(self):
        self._transient_ui_manager.sync_flyout_combo_status()

    def toggle_interpolation_flyout(self):
        self._transient_ui_manager.toggle_interpolation_flyout()

    def show_interpolation_flyout(self):
        self._transient_ui_manager.show_interpolation_flyout()

    def _apply_interpolation_choice(self, idx: int):
        self._transient_ui_manager.apply_interpolation_choice(idx)

    def _close_interpolation_flyout(self):
        self._transient_ui_manager.close_interpolation_flyout()

    def _on_interpolation_flyout_closed_event(self):
        self._transient_ui_manager.on_interpolation_flyout_closed_event()

    def toggle_font_settings_flyout(self, anchor_widget=None):
        self._transient_ui_manager.toggle_font_settings_flyout(anchor_widget)

    def show_font_settings_flyout(self, anchor_widget=None):
        self._transient_ui_manager.show_font_settings_flyout(anchor_widget)

    def hide_font_settings_flyout(self):
        self._transient_ui_manager.hide_font_settings_flyout()

    def repopulate_flyouts(self):
        self._transient_ui_manager.repopulate_flyouts()

    def _on_font_changed(self):
        self._transient_ui_manager.on_font_changed()

    def _on_flyout_item_chosen(self, index: int):
        pass

    def _on_flyout_closed(self, image_number: int):
        self._transient_ui_manager.on_flyout_closed(image_number)

    def _on_unified_flyout_closed(self):
        self._transient_ui_manager.on_unified_flyout_closed()

    def _update_magnifier_flyout_states(self):
        self._transient_ui_manager.update_magnifier_flyout_states()

    def _on_magnifier_toggle_with_hover(self, checked: bool):
        self._transient_ui_manager.on_magnifier_toggle_with_hover(checked)

    def _show_magnifier_visibility_flyout(self, reason: str = "hover"):
        self._transient_ui_manager.show_magnifier_visibility_flyout(reason)

    def _hide_magnifier_visibility_flyout(self):
        self._transient_ui_manager.hide_magnifier_visibility_flyout()

    def eventFilter(self, watched, event):
        if self._transient_ui_manager.event_filter(watched, event):
            return True
        return super().eventFilter(watched, event)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        self._transient_ui_manager.close_all_flyouts_if_needed(global_pos)

    def _map_global_to_parent(self, global_pos: QPointF) -> QPoint:
        return self.parent_widget.mapFromGlobal(global_pos.toPoint())

    def _widget_rect_in_parent(self, widget) -> QRect:
        rect = widget.rect()
        rect.moveTo(widget.mapTo(self.parent_widget, rect.topLeft()))
        return rect

    def _is_inside_interpolation_anchor(self, global_pos: QPointF) -> bool:
        combo = getattr(self.ui, "combo_interpolation", None)
        if combo is None:
            return False
        return self._widget_rect_in_parent(combo).contains(
            self._map_global_to_parent(global_pos)
        )

    def _close_magnifier_visibility_if_needed(self, global_pos: QPointF) -> None:
        if (
            self.magnifier_visibility_flyout is None
            or not self.magnifier_visibility_flyout.isVisible()
        ):
            return
        btn = getattr(self.ui, "btn_magnifier", None)
        if btn is None:
            return
        inside_btn = self._widget_rect_in_parent(btn).contains(
            self._map_global_to_parent(global_pos)
        )
        inside_fly = self.magnifier_visibility_flyout.contains_global(global_pos)
        if not inside_btn and not inside_fly:
            self._hide_magnifier_visibility_flyout()

    def _close_font_flyout_if_needed(self, global_pos: QPointF) -> None:
        if not (
            self._font_popup_open
            and (time.monotonic() - self._font_popup_last_open_ts) > 0.12
            and self.font_settings_flyout is not None
        ):
            return
        flyout_global_rect = QRect(
            self.font_settings_flyout.mapToGlobal(QPoint(0, 0)),
            self.font_settings_flyout.size(),
        )
        anchor = self._font_anchor_widget or getattr(self.ui, "btn_color_picker", None)
        button_rect = QRect()
        if anchor:
            button_rect = anchor.geometry()
            button_rect.moveTo(anchor.mapToGlobal(QPoint(0, 0)))
        if not flyout_global_rect.contains(
            global_pos.toPoint()
        ) and not button_rect.contains(global_pos.toPoint()):
            self.hide_font_settings_flyout()

    def _is_interpolation_grace_period_active(self) -> bool:
        if not (hasattr(self, "_interp_last_open_ts") and self._interp_last_open_ts > 0):
            return False
        return (time.monotonic() - self._interp_last_open_ts) < 0.15

    def _close_button_menu_if_needed(
        self, global_pos: QPointF, open_attr: str, opened_at_attr: str, button
    ) -> None:
        if not getattr(self, open_attr, False):
            return
        if (time.monotonic() - getattr(self, opened_at_attr, 0.0)) <= 0.12:
            return
        if button is None or not button.is_menu_visible():
            setattr(self, open_attr, False)
            return

        local_pos = self._map_global_to_parent(global_pos)
        btn_rect = self._widget_rect_in_parent(button)
        menu_widget = button.menu
        menu_rect = QRect(menu_widget.mapToGlobal(QPoint(0, 0)), menu_widget.size())

        if not btn_rect.contains(local_pos) and not menu_rect.contains(
            global_pos.toPoint()
        ):
            button.hide_menu()
            setattr(self, open_attr, False)

    def _close_interpolation_flyout_if_needed(self, global_pos: QPointF) -> None:
        if not (self._interp_popup_open and self._interp_flyout is not None):
            return
        if self._is_inside_interpolation_anchor(global_pos):
            return
        flyout_contains = (
            self._interp_flyout.contains_global(global_pos.toPoint())
            if hasattr(self._interp_flyout, "contains_global")
            else QRect(
                self._interp_flyout.mapToGlobal(QPoint(0, 0)),
                self._interp_flyout.size(),
            ).contains(global_pos.toPoint())
        )
        if not flyout_contains:
            self._close_interpolation_flyout()

        local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
        flyout_rect_local = self.unified_flyout.geometry()

        button_rects = []
        for btn in (self.ui.combo_image1, self.ui.combo_image2):
            rect = btn.rect()
            rect.moveTo(btn.mapTo(self.parent_widget, rect.topLeft()))
            button_rects.append(rect)

        is_click_on_any_button = any(r.contains(local_pos) for r in button_rects)
        is_click_inside_flyout = flyout_rect_local.contains(local_pos)

        def _is_click_on_widget_or_children(widget, global_pos_point):
            if not widget or not widget.isVisible():
                return False

            local_pos_for_widget = widget.mapFromGlobal(global_pos_point)

            if not widget.rect().contains(local_pos_for_widget):
                return False

            child_at_point = widget.childAt(local_pos_for_widget)
            if child_at_point:

                return True

            return True

        is_click_on_flyout_child = _is_click_on_widget_or_children(
            self.unified_flyout, global_pos.toPoint()
        )

        is_click_on_scrollbar = False
        if hasattr(self.unified_flyout, "panel_left"):
            for panel_name, panel in [
                ("left", self.unified_flyout.panel_left),
                ("right", self.unified_flyout.panel_right),
            ]:
                if hasattr(panel, "list_view"):
                    if hasattr(panel.list_view, "custom_v_scrollbar"):
                        scrollbar = panel.list_view.custom_v_scrollbar
                        if scrollbar.isVisible():
                            scrollbar_global_pos = scrollbar.mapToGlobal(QPoint(0, 0))
                            scrollbar_global_rect = QRect(
                                scrollbar_global_pos, scrollbar.size()
                            )
                            is_click_on_scrollbar = scrollbar_global_rect.contains(
                                global_pos.toPoint()
                            )
                            if is_click_on_scrollbar:
                                return

        if (
            not is_click_on_any_button
            and not is_click_inside_flyout
            and not is_click_on_flyout_child
        ):
            self.unified_flyout.start_closing_animation()
            self.ui.combo_image1.setFlyoutOpen(False)
            self.ui.combo_image2.setFlyoutOpen(False)

        if self._interp_popup_open and self._interp_flyout:
            time_since_open = time.monotonic() - self._interp_last_open_ts

            if time_since_open < 0.12:
                return

            if (
                hasattr(self.ui, "combo_interpolation")
                and self.ui.combo_interpolation is not None
            ):
                combo_local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
                combo_rect = self.ui.combo_interpolation.rect()
                combo_rect.moveTo(
                    self.ui.combo_interpolation.mapTo(
                        self.parent_widget, combo_rect.topLeft()
                    )
                )
                if combo_rect.contains(combo_local_pos):
                    return

            flyout_contains = (
                self._interp_flyout.contains_global(global_pos.toPoint())
                if hasattr(self._interp_flyout, "contains_global")
                else QRect(
                    self._interp_flyout.mapToGlobal(QPoint(0, 0)),
                    self._interp_flyout.size(),
                ).contains(global_pos.toPoint())
            )
            if not flyout_contains:
                self._close_interpolation_flyout()

    def show_help_dialog(self):
        self._dialog_manager.show_help_dialog()

    def show_settings_dialog(self):
        self._dialog_manager.show_settings_dialog()

    def show_export_dialog(
        self,
        dialog_state,
        preview_image: object | None,
        suggested_filename: str = "",
        on_set_favorite_dir=None,
    ):
        return self._dialog_manager.show_export_dialog(
            dialog_state, preview_image, suggested_filename, on_set_favorite_dir
        )

    def show_non_modal_message(self, icon, title: str, text: str):
        self._message_manager.show_non_modal_message(icon, title, text)

    def repopulate_visible_flyouts(self):
        if self.unified_flyout and self.unified_flyout.isVisible():
            self.repopulate_flyouts()

    def hide_transient_same_window_ui(self):
        self._transient_ui_manager.hide_transient_same_window_ui()

    def _on_app_focus_changed(self, old_widget, new_widget):
        self._transient_ui_manager.on_app_focus_changed(old_widget, new_widget)
