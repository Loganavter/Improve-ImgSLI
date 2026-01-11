import logging
import time

from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, Qt, QTimer, QEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from core.constants import AppConstants
from core.events import (
    ViewportToggleMagnifierPartEvent,
    SettingsChangeLanguageEvent,
    SettingsUIModeChangedEvent,
)
from core.plugin_system.ui_integration import PluginUIRegistry
from toolkit.managers.font_manager import FontManager
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class UIManager(QObject):
    def __init__(self, store, main_controller, ui, parent_widget, plugin_ui_registry: PluginUIRegistry | None = None):
        super().__init__(parent_widget)
        self.store = store
        self.main_controller = main_controller
        self.ui = ui
        self.parent_widget = parent_widget
        self.app_ref = parent_widget
        self.plugin_ui_registry = plugin_ui_registry
        self.event_bus = main_controller.event_bus if main_controller else None

        self._active_message_boxes = []

        from toolkit.widgets.composite.unified_flyout import FlyoutMode, UnifiedFlyout
        self.unified_flyout = UnifiedFlyout(self.store, self.main_controller, self.parent_widget)

        self.font_settings_flyout: Optional[Any] = None
        self._font_anchor_widget: Optional[Any] = None
        self._is_modal_active = False

        if self.unified_flyout is not None:
            self.unified_flyout.closing_animation_finished.connect(self._on_unified_flyout_closed)

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
            if hasattr(self.ui, 'btn_diff_mode') and self.ui.btn_diff_mode is not None:
                try:
                    self._original_diff_show_menu = self.ui.btn_diff_mode.show_menu

                    def wrapped_diff_show_menu():
                        result = self._original_diff_show_menu()
                        if hasattr(self.ui.btn_diff_mode, '_menu_visible') and self.ui.btn_diff_mode._menu_visible:
                            self._diff_mode_popup_open = True
                            self._diff_mode_last_open_ts = time.monotonic()
                        return result

                    self.ui.btn_diff_mode.show_menu = wrapped_diff_show_menu
                except AttributeError as e:
                    logger.warning(f"UIManager.__init__: btn_diff_mode.show_menu not available: {e}")

            if hasattr(self.ui, 'btn_channel_mode') and self.ui.btn_channel_mode is not None:
                try:
                    self._original_channel_show_menu = self.ui.btn_channel_mode.show_menu

                    def wrapped_channel_show_menu():
                        result = self._original_channel_show_menu()
                        if hasattr(self.ui.btn_channel_mode, '_menu_visible') and self.ui.btn_channel_mode._menu_visible:
                            self._channel_mode_popup_open = True
                            self._channel_mode_last_open_ts = time.monotonic()
                        return result

                    self.ui.btn_channel_mode.show_menu = wrapped_channel_show_menu
                except AttributeError as e:
                    logger.warning(f"UIManager.__init__: btn_channel_mode.show_menu not available: {e}")

        from toolkit.widgets.composite.magnifier_visibility_flyout import MagnifierVisibilityFlyout
        self.magnifier_visibility_flyout = MagnifierVisibilityFlyout(self.parent_widget)
        self._magn_popup_open: bool = False
        self._magn_popup_last_open_ts: float = 0.0
        self._magn_hover_timer = QTimer(self)
        self._magn_hover_timer.setSingleShot(True)
        self._magn_hover_timer.timeout.connect(lambda: self._show_magnifier_visibility_flyout(reason="hover"))

        if self.ui is not None and hasattr(self.ui, 'btn_magnifier') and self.ui.btn_magnifier is not None:
            self.ui.btn_magnifier.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.ui.btn_magnifier.installEventFilter(self)
            self.magnifier_visibility_flyout.installEventFilter(self)
            self.ui.btn_magnifier.toggled.connect(self._on_magnifier_toggle_with_hover)

        if self.main_controller is not None and self.event_bus is not None:
            self.magnifier_visibility_flyout.btn_left.toggled.connect(
                lambda checked: self.event_bus.emit(ViewportToggleMagnifierPartEvent('left', not checked))
            )
            self.magnifier_visibility_flyout.btn_right.toggled.connect(
                lambda checked: self.event_bus.emit(ViewportToggleMagnifierPartEvent('right', not checked))
            )
            self.magnifier_visibility_flyout.btn_center.toggled.connect(
                lambda checked: self.event_bus.emit(ViewportToggleMagnifierPartEvent('center', not checked))
            )

        font_manager = FontManager.get_instance()
        if font_manager is not None:
            font_manager.font_changed.connect(self._on_font_changed)

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_app_focus_changed)

    def get_plugin_action(self, action_id: str) -> Callable[..., Any] | None:
        if self.plugin_ui_registry:
            return self.plugin_ui_registry.get_action(action_id)
        return None

    def set_modal_dialog_active(self, active: bool):
        self._is_modal_active = active

    def show_flyout(self, image_number: int):
        from toolkit.widgets.composite.unified_flyout import FlyoutMode

        if self.unified_flyout:
            time_since_close = time.monotonic() - self.unified_flyout.last_close_timestamp
            is_same_list = (self.unified_flyout.source_list_num == image_number)

            if is_same_list and time_since_close < 0.2:
                return

        if self.unified_flyout is not None and self.unified_flyout.isVisible():
            if self.unified_flyout.mode == FlyoutMode.DOUBLE:
                self.ui.combo_image1.setFlyoutOpen(False)
                self.ui.combo_image2.setFlyoutOpen(False)
                self.unified_flyout.start_closing_animation()
                return

            if (self.unified_flyout.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_RIGHT) and
                self.unified_flyout.source_list_num == image_number):
                button = self.ui.combo_image1 if image_number == 1 else self.ui.combo_image2
                button.setFlyoutOpen(False)
                self.unified_flyout.start_closing_animation()
                return

        target_list = self.store.document.image_list1 if image_number == 1 else self.store.document.image_list2
        if len(target_list) == 0:
            return

        button = self.ui.combo_image1 if image_number == 1 else self.ui.combo_image2
        other_button = self.ui.combo_image2 if image_number == 1 else self.ui.combo_image1
        other_button.setFlyoutOpen(False)
        button.setFlyoutOpen(True)

        if self.unified_flyout is not None:
            self.unified_flyout.showAsSingle(image_number, button)

        QTimer.singleShot(0, self._sync_flyout_combo_status)

    def _sync_flyout_combo_status(self):
        from toolkit.widgets.composite.unified_flyout import FlyoutMode
        if self.unified_flyout.mode == FlyoutMode.DOUBLE:
            self.ui.combo_image1.setFlyoutOpen(True)
            self.ui.combo_image2.setFlyoutOpen(True)

    def toggle_interpolation_flyout(self):
        if self._interp_popup_open:
            self._close_interpolation_flyout()
            return
        self.show_interpolation_flyout()

    def show_interpolation_flyout(self):
        from toolkit.widgets.composite.simple_options_flyout import SimpleOptionsFlyout

        if self._interp_flyout is None:
            self._interp_flyout = SimpleOptionsFlyout(self.parent_widget)
            self._interp_flyout.closed.connect(self._on_interpolation_flyout_closed_event)

        lang = self.store.settings.current_language
        labels: list[str] = []

        try:
            from shared.image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False

        interp_translation_map = {
            "NEAREST": "magnifier.nearest_neighbor",
            "BILINEAR": "magnifier.bilinear",
            "BICUBIC": "magnifier.bicubic",
            "LANCZOS": "magnifier.lanczos",
            "EWA_LANCZOS": "magnifier.ewa_lanczos",
        }

        method_keys = [k for k in AppConstants.INTERPOLATION_METHODS_MAP.keys() if k != "EWA_LANCZOS" or WAND_AVAILABLE]
        for key in method_keys:
            translation_key = interp_translation_map.get(key, f"magnifier.{AppConstants.INTERPOLATION_METHODS_MAP[key].lower().replace(' ', '_')}")
            labels.append(tr(translation_key, lang))

        try:
            target_key = getattr(self.store.viewport, "interpolation_method", AppConstants.DEFAULT_INTERPOLATION_METHOD)
            if target_key not in method_keys:
                target_key = (
                    AppConstants.DEFAULT_INTERPOLATION_METHOD
                    if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys
                    else (method_keys[0] if method_keys else AppConstants.DEFAULT_INTERPOLATION_METHOD)
                )
                self.store.viewport.interpolation_method = target_key
                self.store.emit_state_change()
            current_index = method_keys.index(target_key) if method_keys else 0
        except (AttributeError, ValueError, IndexError) as e:
            logger.warning(f"UIManager.show_interpolation_flyout: error getting interpolation method: {e}")
            current_index = 0

        if self._interp_flyout is not None:
            try:
                self._interp_flyout.item_chosen.disconnect()
            except TypeError:

                pass

            item_height = 34
            item_font = QApplication.font()
            if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
                if hasattr(self.ui.combo_interpolation, 'getItemHeight'):
                    item_height = self.ui.combo_interpolation.getItemHeight()
                if hasattr(self.ui.combo_interpolation, 'getItemFont'):
                    item_font = self.ui.combo_interpolation.getItemFont()

            self._interp_flyout.set_row_height(item_height)
            self._interp_flyout.set_row_font(item_font)
            self._interp_flyout.populate(labels, current_index)
            self._interp_flyout.item_chosen.connect(self._apply_interpolation_choice)

            if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
                self.ui.combo_interpolation.setFlyoutOpen(True)

                self._interp_last_open_ts = time.monotonic()

            def _do_show():
                if self._interp_flyout is not None and hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
                    self._interp_flyout.show_below(self.ui.combo_interpolation)
                    self._interp_popup_open = True

                    self._interp_last_open_ts = time.monotonic()
                else:
                    logger.warning("UIManager.show_interpolation_flyout: _interp_flyout or combo_interpolation is None")
            QTimer.singleShot(0, _do_show)

    def _apply_interpolation_choice(self, idx: int):
        try:
            if 0 <= idx < self.ui.combo_interpolation.count():
                self.ui.combo_interpolation.setCurrentIndex(idx)
                if self.main_controller:
                    if self.main_controller and self.main_controller.session_ctrl:
                        self.main_controller.session_ctrl.on_interpolation_changed(idx)
        finally:
            self._close_interpolation_flyout()

    def _close_interpolation_flyout(self):
        if self._interp_flyout is not None:
            self._interp_flyout.hide()
        if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
            self.ui.combo_interpolation.setFlyoutOpen(False)
        self._interp_popup_open = False

    def _on_interpolation_flyout_closed_event(self):
        if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
            self.ui.combo_interpolation.setFlyoutOpen(False)
        self._interp_popup_open = False

    def toggle_font_settings_flyout(self, anchor_widget=None):
        if self._font_popup_open:
            self.hide_font_settings_flyout()
        else:
            self.show_font_settings_flyout(anchor_widget=anchor_widget)

    def show_font_settings_flyout(self, anchor_widget=None):
        if not self.font_settings_flyout:
            return

        if anchor_widget is None:
            anchor_widget = getattr(self.ui, "btn_color_picker", None)
        self._font_anchor_widget = anchor_widget

        self.font_settings_flyout.set_values(
            self.store.viewport.font_size_percent,
            self.store.viewport.font_weight,
            self.store.viewport.file_name_color,
            self.store.viewport.file_name_bg_color,
            self.store.viewport.draw_text_background,
            self.store.viewport.text_placement_mode,
            getattr(self.store.viewport, 'text_alpha_percent', 100),
            self.store.settings.current_language
        )
        if anchor_widget is not None:
            self.font_settings_flyout.show_top_left_of(anchor_widget)
            if hasattr(anchor_widget, "setFlyoutOpen"):
                anchor_widget.setFlyoutOpen(True)
        self._font_popup_open = True
        self._font_popup_last_open_ts = time.monotonic()

    def hide_font_settings_flyout(self):
        if self.font_settings_flyout is not None:
            self.font_settings_flyout.hide()
        if self._font_anchor_widget is not None and hasattr(self._font_anchor_widget, "setFlyoutOpen"):
            self._font_anchor_widget.setFlyoutOpen(False)
        self._font_popup_open = False
        self._font_anchor_widget = None

    def repopulate_flyouts(self):
        from toolkit.widgets.composite.unified_flyout import FlyoutMode
        if self.unified_flyout and self.unified_flyout.isVisible():
            self.unified_flyout.populate(1, self.store.document.image_list1)
            self.unified_flyout.populate(2, self.store.document.image_list2)
            if self.unified_flyout.mode == FlyoutMode.DOUBLE:

                if self.unified_flyout and self.unified_flyout.mode.name == "DOUBLE":
                    QTimer.singleShot(0, lambda: self.unified_flyout.refreshGeometry(immediate=False))

    def _on_font_changed(self):
        self.repopulate_visible_flyouts()
        if hasattr(self.ui, 'reapply_button_styles'):
            self.ui.reapply_button_styles()
        if self.parent_widget is not None:
            self.parent_widget.update()

    def _on_flyout_item_chosen(self, index: int):
        pass

    def _on_flyout_closed(self, image_number: int):
        button = self.ui.combo_image1 if image_number == 1 else self.ui.combo_image2
        button.setFlyoutOpen(False)

    def _on_unified_flyout_closed(self):
        from toolkit.widgets.composite.unified_flyout import FlyoutMode
        if self.unified_flyout is not None:
            self.unified_flyout.mode = FlyoutMode.HIDDEN
        self.ui.combo_image1.setFlyoutOpen(False)
        self.ui.combo_image2.setFlyoutOpen(False)
        self._on_flyout_closed(1)
        self._on_flyout_closed(2)

    def _update_magnifier_flyout_states(self):
        try:
            show_center = getattr(self.store.viewport, "diff_mode", "off") != "off"
            left_on = getattr(self.store.viewport, "magnifier_visible_left", True)
            center_on = getattr(self.store.viewport, "magnifier_visible_center", True)
            right_on = getattr(self.store.viewport, "magnifier_visible_right", True)
            self.magnifier_visibility_flyout.set_mode_and_states(show_center, left_on, center_on, right_on)
        except Exception:
            pass

    def _on_magnifier_toggle_with_hover(self, checked: bool):
        if not hasattr(self.ui, 'btn_magnifier') or self.ui.btn_magnifier is None:
            return
        btn = self.ui.btn_magnifier
        if btn.underMouse():
            if checked:
                QTimer.singleShot(0, lambda: self._show_magnifier_visibility_flyout(reason="hover"))
            else:
                self._hide_magnifier_visibility_flyout()

    def _show_magnifier_visibility_flyout(self, reason: str = "hover"):

        try:
            use_magnifier = getattr(self.store.viewport, "use_magnifier", False)
        except AttributeError:
            use_magnifier = False

        if hasattr(self.store.viewport, 'view_state'):
            try:
                use_magnifier = getattr(self.store.viewport.view_state, "use_magnifier", use_magnifier)
            except AttributeError:
                pass

        if not use_magnifier:
            return
        self._update_magnifier_flyout_states()

        hover_delay_ms = 0 if reason != "hover" else 0
        if hasattr(self.ui, 'btn_magnifier') and self.ui.btn_magnifier is not None:
            self.magnifier_visibility_flyout.show_for_button(self.ui.btn_magnifier, self.parent_widget, hover_delay_ms=hover_delay_ms)
            self._magn_popup_open = True
            self._magn_popup_last_open_ts = time.monotonic()

            if reason == "wheel":
                self.magnifier_visibility_flyout.schedule_auto_hide(1200)
            else:
                self.magnifier_visibility_flyout.cancel_auto_hide()

    def _hide_magnifier_visibility_flyout(self):
        self.magnifier_visibility_flyout.hide()
        self._magn_popup_open = False

    def eventFilter(self, watched, event):
        if not hasattr(self.ui, 'btn_magnifier') or self.ui.btn_magnifier is None:
            return super().eventFilter(watched, event)

        btn = self.ui.btn_magnifier
        if watched is btn:
            et = event.type()
            if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                self._magn_hover_timer.stop()

                try:
                    use_magnifier = getattr(self.store.viewport, "use_magnifier", False)
                except AttributeError:
                    use_magnifier = False
                if hasattr(self.store.viewport, 'view_state'):
                    try:
                        use_magnifier = getattr(self.store.viewport.view_state, "use_magnifier", use_magnifier)
                    except AttributeError:
                        pass
                if use_magnifier:
                    def _do_show():
                        self._show_magnifier_visibility_flyout(reason="hover")
                    try:
                        self._magn_hover_timer.timeout.disconnect()
                    except TypeError:

                        pass
                    self._magn_hover_timer.timeout.connect(_do_show)
                    self._magn_hover_timer.start(150)
                else:
                    self.magnifier_visibility_flyout.hide()
                return False
            elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
                self.magnifier_visibility_flyout.schedule_auto_hide(1000)
                return False
            elif et == QEvent.Type.Wheel:

                try:
                    use_magnifier = getattr(self.store.viewport, "use_magnifier", False)
                except AttributeError:
                    use_magnifier = False
                if hasattr(self.store.viewport, 'view_state'):
                    try:
                        use_magnifier = getattr(self.store.viewport.view_state, "use_magnifier", use_magnifier)
                    except AttributeError:
                        pass
                if not use_magnifier:
                    return True
                self._show_magnifier_visibility_flyout(reason="wheel")
                return True
            else:
                return False

        if watched is self.magnifier_visibility_flyout:
            et = event.type()
            if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                self.magnifier_visibility_flyout.cancel_auto_hide()
                return False
            elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):

                self.magnifier_visibility_flyout.schedule_auto_hide(1000)
                return False
            else:
                return False

        return super().eventFilter(watched, event)

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        if self._is_modal_active:
            return

        if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
            local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
            combo_rect = self.ui.combo_interpolation.rect()
            combo_rect.moveTo(self.ui.combo_interpolation.mapTo(self.parent_widget, combo_rect.topLeft()))
            if combo_rect.contains(local_pos):
                return

        if self.magnifier_visibility_flyout is not None and self.magnifier_visibility_flyout.isVisible():
            if hasattr(self.ui, 'btn_magnifier') and self.ui.btn_magnifier is not None:
                local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
                btn_rect = self.ui.btn_magnifier.rect()
                btn_rect.moveTo(self.ui.btn_magnifier.mapTo(self.parent_widget, btn_rect.topLeft()))
                inside_btn = btn_rect.contains(local_pos)
                inside_fly = self.magnifier_visibility_flyout.contains_global(global_pos)
                if not inside_btn and not inside_fly:
                    self._hide_magnifier_visibility_flyout()

        if self._font_popup_open and (time.monotonic() - self._font_popup_last_open_ts) > 0.12:
            flyout_global_rect = QRect(
                self.font_settings_flyout.mapToGlobal(QPoint(0, 0)),
                self.font_settings_flyout.size()
            )

            anchor = self._font_anchor_widget or getattr(self.ui, "btn_color_picker", None)
            button_rect = anchor.geometry() if anchor else QRect()
            if anchor:
                button_rect.moveTo(anchor.mapToGlobal(QPoint(0, 0)))

            if not flyout_global_rect.contains(global_pos.toPoint()) and not button_rect.contains(global_pos.toPoint()):
                self.hide_font_settings_flyout()

        if hasattr(self, '_interp_last_open_ts') and self._interp_last_open_ts > 0:
            time_since_open = time.monotonic() - self._interp_last_open_ts
            if time_since_open < 0.15:
                return

        if self._diff_mode_popup_open:
            if (time.monotonic() - self._diff_mode_last_open_ts) > 0.12:
                if self.ui.btn_diff_mode.is_menu_visible():
                    local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
                    btn_rect = self.ui.btn_diff_mode.rect()
                    btn_rect.moveTo(self.ui.btn_diff_mode.mapTo(self.parent_widget, btn_rect.topLeft()))
                    menu_rect = self.ui.btn_diff_mode.menu.geometry()

                    if not btn_rect.contains(local_pos) and not menu_rect.contains(global_pos.toPoint()):
                        self.ui.btn_diff_mode.hide_menu()
                        self._diff_mode_popup_open = False
                else:
                    self._diff_mode_popup_open = False

        if self._channel_mode_popup_open:
            if (time.monotonic() - self._channel_mode_last_open_ts) > 0.12:
                if self.ui.btn_channel_mode.is_menu_visible():
                    local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
                    btn_rect = self.ui.btn_channel_mode.rect()
                    btn_rect.moveTo(self.ui.btn_channel_mode.mapTo(self.parent_widget, btn_rect.topLeft()))
                    menu_rect = self.ui.btn_channel_mode.menu.geometry()

                    if not btn_rect.contains(local_pos) and not menu_rect.contains(global_pos.toPoint()):
                        self.ui.btn_channel_mode.hide_menu()
                        self._channel_mode_popup_open = False
                else:
                    self._channel_mode_popup_open = False

        if self.unified_flyout is None or not self.unified_flyout.isVisible():
            if self._interp_popup_open and self._interp_flyout is not None:
                if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
                    local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
                    btn_rect = self.ui.combo_interpolation.rect()
                    btn_rect.moveTo(self.ui.combo_interpolation.mapTo(self.parent_widget, btn_rect.topLeft()))
                    if btn_rect.contains(local_pos):
                        return

                flyout_contains = self._interp_flyout.geometry().contains(global_pos.toPoint())
                if not flyout_contains:
                    self._close_interpolation_flyout()
            return

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

        is_click_on_flyout_child = _is_click_on_widget_or_children(self.unified_flyout, global_pos.toPoint())

        is_click_on_scrollbar = False
        if hasattr(self.unified_flyout, 'panel_left'):
            for panel_name, panel in [('left', self.unified_flyout.panel_left), ('right', self.unified_flyout.panel_right)]:
                if hasattr(panel, 'list_view'):
                    if hasattr(panel.list_view, 'custom_v_scrollbar'):
                        scrollbar = panel.list_view.custom_v_scrollbar
                        if scrollbar.isVisible():
                            scrollbar_global_pos = scrollbar.mapToGlobal(QPoint(0, 0))
                            scrollbar_global_rect = QRect(scrollbar_global_pos, scrollbar.size())
                            is_click_on_scrollbar = scrollbar_global_rect.contains(global_pos.toPoint())
                            if is_click_on_scrollbar:
                                return

        if not is_click_on_any_button and not is_click_inside_flyout and not is_click_on_flyout_child:
            self.unified_flyout.start_closing_animation()
            self.ui.combo_image1.setFlyoutOpen(False)
            self.ui.combo_image2.setFlyoutOpen(False)

        if self._interp_popup_open and self._interp_flyout:
            time_since_open = time.monotonic() - self._interp_last_open_ts

            if time_since_open < 0.12:
                return

            if hasattr(self.ui, 'combo_interpolation') and self.ui.combo_interpolation is not None:
                combo_local_pos = self.parent_widget.mapFromGlobal(global_pos.toPoint())
                combo_rect = self.ui.combo_interpolation.rect()
                combo_rect.moveTo(self.ui.combo_interpolation.mapTo(self.parent_widget, combo_rect.topLeft()))
                if combo_rect.contains(combo_local_pos):
                    return

            flyout_contains = self._interp_flyout.geometry().contains(global_pos.toPoint())
            if not flyout_contains:
                self._close_interpolation_flyout()

    def show_help_dialog(self):
        from toolkit.dialogs.help_dialog import HelpDialog

        if self._help_dialog is None:
            sections = [
                ("help.help_section_introduction", "introduction"),
                ("help.help_section_file_management", "file-management"),
                ("help.help_section_basic_comparison", "comparison"),
                ("magnifier.help_section_magnifier_tool", "magnifier"),
                ("help.help_section_exporting_results", "export"),
                ("help.help_section_settings", "settings"),
                ("help.help_section_hotkeys", "hotkeys"),
            ]
            self._help_dialog = HelpDialog(sections, self.store.settings.current_language, "Improve-ImgSLI", parent=self.parent_widget)

        if self._help_dialog is not None:
            if getattr(self._help_dialog, 'current_language', None) != self.store.settings.current_language:
                if hasattr(self._help_dialog, 'update_language'):
                    self._help_dialog.update_language(self.store.settings.current_language)
                else:
                    self._help_dialog.current_language = self.store.settings.current_language

            self._help_dialog.show()
            self._help_dialog.raise_()
            self._help_dialog.activateWindow()

    def show_settings_dialog(self):
        from plugins.settings.dialog import SettingsDialog

        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                current_language=self.store.settings.current_language,
                current_theme=self.store.settings.theme,
                current_max_length=self.store.viewport.max_name_length,
                min_limit=AppConstants.MIN_NAME_LENGTH_LIMIT,
                max_limit=AppConstants.MAX_NAME_LENGTH_LIMIT,
                debug_mode_enabled=self.store.settings.debug_mode_enabled,
                system_notifications_enabled=getattr(self.store.settings, 'system_notifications_enabled', True),
                current_resolution_limit=self.store.viewport.display_resolution_limit,
                parent=self.parent_widget,
                tr_func=tr,
                current_ui_font_mode=getattr(self.store.settings, 'ui_font_mode', 'builtin'),
                current_ui_font_family=getattr(self.store.settings, 'ui_font_family', ''),
                current_ui_mode=getattr(self.store.settings, 'ui_mode', 'beginner'),
                optimize_magnifier_movement=self.store.viewport.optimize_magnifier_movement,
                movement_interpolation_method=self.store.viewport.render_config.magnifier_movement_interpolation_method,
                optimize_laser_smoothing=self.store.viewport.optimize_laser_smoothing,
                interpolation_method=self.store.viewport.interpolation_method,
                auto_calculate_psnr=self.store.viewport.auto_calculate_psnr,
                auto_calculate_ssim=self.store.viewport.auto_calculate_ssim,
                auto_crop_black_borders=getattr(self.store.settings, 'auto_crop_black_borders', True),
                current_video_fps=getattr(self.store.settings, 'video_recording_fps', 60),
                store=self.store,
            )

            self._settings_dialog.accepted.connect(lambda: self._apply_settings(self._settings_dialog.get_settings()))
            self._settings_dialog.destroyed.connect(lambda: setattr(self, "_settings_dialog", None))

        if self._settings_dialog is not None:
            self._settings_dialog.show()
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()

    def show_export_dialog(self, preview_image: object | None, suggested_filename: str = ""):
        from plugins.export.dialog import ExportDialog
        dialog = ExportDialog(
            store=self.store,
            parent=None,
            tr_func=tr,
            preview_image=preview_image,
            suggested_filename=suggested_filename
        )
        return dialog.exec(), dialog.get_export_options()

    def show_non_modal_message(self, icon, title: str, text: str):
        msg_box = QMessageBox(self.parent_widget)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowType.Window)
        msg_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        msg_box.setModal(False)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)

        self.app_ref.theme_manager.apply_theme_to_dialog(msg_box)

        self._active_message_boxes.append(msg_box)
        msg_box.finished.connect(lambda: self._active_message_boxes.remove(msg_box))

        msg_box.show()
        msg_box.raise_()
        msg_box.activateWindow()

    def _apply_settings(self, settings):
        (
            new_lang, new_theme, new_max_length, new_debug, new_sys_notif,
            new_res_limit, new_ui_font_mode, new_ui_font_family,
            new_optimize_movement, new_mag_interp, new_optimize_laser, new_laser_interp,
            new_auto_psnr, new_auto_ssim, new_auto_crop, new_ui_mode, new_video_fps
        ) = settings

        theme_changed = new_theme != self.store.settings.theme
        if theme_changed:
            if self.main_controller is not None and self.main_controller.presenter is not None:
                self.main_controller.presenter.main_window_app.apply_application_theme(new_theme)

        if new_res_limit != self.store.viewport.display_resolution_limit:
            self.store.viewport.display_resolution_limit = new_res_limit

        if new_max_length != self.store.viewport.max_name_length:
            self.store.viewport.max_name_length = new_max_length

        debug_changed = new_debug != self.store.settings.debug_mode_enabled
        if debug_changed:
            self.store.settings.debug_mode_enabled = new_debug

        if getattr(self.store.settings, "system_notifications_enabled", True) != new_sys_notif:
            self.store.settings.system_notifications_enabled = new_sys_notif
            self.store.emit_state_change("settings")

        lang_changed = new_lang != self.store.settings.current_language
        if lang_changed:
            if self.event_bus is not None:
                self.event_bus.emit(SettingsChangeLanguageEvent(new_lang))
            elif self.main_controller is not None and self.main_controller.event_bus is not None:
                self.main_controller.event_bus.emit(SettingsChangeLanguageEvent(new_lang))
            if self._settings_dialog is not None:
                self._settings_dialog.update_language(new_lang)

        font_mode_normalized = "system_default" if new_ui_font_mode == "system" else new_ui_font_mode
        font_mode_changed = font_mode_normalized != getattr(self.store.settings, "ui_font_mode", "builtin")
        font_family_changed = (new_ui_font_family or "") != (getattr(self.store.settings, "ui_font_family", "") or "")

        if font_mode_changed or font_family_changed:
            self.store.settings.ui_font_mode = font_mode_normalized
            self.store.settings.ui_font_family = new_ui_font_family or ""

            FontManager.get_instance().apply_from_state(self.store)
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(app.styleSheet())
            if self.main_controller is not None and self.main_controller.settings_manager is not None:
                self.main_controller.settings_manager._save_setting("ui_font_mode", self.store.settings.ui_font_mode)
                self.main_controller.settings_manager._save_setting("ui_font_family", self.store.settings.ui_font_family)

            if self.main_controller is not None and self.main_controller.presenter is not None:
                try:
                    main_window = self.main_controller.presenter.main_window_app
                    if hasattr(main_window, 'font_path_absolute'):
                        main_window.font_path_absolute = FontManager.get_instance().get_font_path_for_image_text(self.store)
                except Exception:
                    pass

        vp = self.store.viewport

        if new_optimize_movement != vp.optimize_magnifier_movement:
            vp.optimize_magnifier_movement = new_optimize_movement

        if new_mag_interp != vp.render_config.magnifier_movement_interpolation_method:
            vp.render_config.magnifier_movement_interpolation_method = new_mag_interp
            vp.render_config.movement_interpolation_method = new_mag_interp
            vp.movement_interpolation_method = new_mag_interp
            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            if self.main_controller is not None and self.main_controller.settings_manager is not None:
                self.main_controller.settings_manager._save_setting("magnifier_movement_interpolation_method", new_mag_interp)
            if self.main_controller is not None:
                self.main_controller.update_requested.emit()

        if new_optimize_laser != vp.optimize_laser_smoothing:
            vp.optimize_laser_smoothing = new_optimize_laser

        if new_laser_interp != vp.render_config.laser_smoothing_interpolation_method:
            vp.render_config.laser_smoothing_interpolation_method = new_laser_interp
            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            if self.main_controller is not None and self.main_controller.settings_manager is not None:
                self.main_controller.settings_manager._save_setting("laser_smoothing_interpolation_method", new_laser_interp)
            if self.main_controller is not None:
                self.main_controller.update_requested.emit()

        if new_auto_psnr != self.store.viewport.auto_calculate_psnr:
            self.store.viewport.auto_calculate_psnr = new_auto_psnr

        if new_auto_ssim != self.store.viewport.auto_calculate_ssim:
            self.store.viewport.auto_calculate_ssim = new_auto_ssim

        if getattr(self.store.settings, "auto_crop_black_borders", True) != new_auto_crop:
            self.store.settings.auto_crop_black_borders = new_auto_crop

        ui_mode_changed = getattr(self.store.settings, "ui_mode", "beginner") != new_ui_mode
        if ui_mode_changed:
            self.store.settings.ui_mode = new_ui_mode
            if self.main_controller is not None and self.main_controller.settings_manager is not None:
                self.main_controller.settings_manager._save_setting("ui_mode", new_ui_mode)

            if self.event_bus is not None:
                self.event_bus.emit(SettingsUIModeChangedEvent(new_ui_mode))
            elif self.main_controller is not None and self.main_controller.event_bus is not None:
                self.main_controller.event_bus.emit(SettingsUIModeChangedEvent(new_ui_mode))

        if getattr(self.store.settings, "video_recording_fps", 60) != new_video_fps:
            self.store.settings.video_recording_fps = new_video_fps
            if self.main_controller is not None and self.main_controller.settings_manager is not None:
                self.main_controller.settings_manager._save_setting("video_recording_fps", new_video_fps)

        self.store.emit_state_change()

        if self.main_controller:
            self.main_controller._trigger_metrics_calculation_if_needed()

        if debug_changed:
            QMessageBox.information(
                self.parent_widget,
                tr("common.information", self.store.settings.current_language),
                tr("misc.restart_the_application_for_the_debug_log_setting_to_take_full_effect", self.store.settings.current_language),
            )

    def repopulate_visible_flyouts(self):
        if self.unified_flyout and self.unified_flyout.isVisible():
            self.repopulate_flyouts()

    def _on_app_focus_changed(self, old_widget, new_widget):
        if new_widget is None:
            if self.parent_widget.isActiveWindow():
                return

        if self.unified_flyout is not None and self.unified_flyout.isVisible() and getattr(self.unified_flyout, '_is_refreshing', False):
            return

        if self.unified_flyout is not None and self.unified_flyout.isVisible() and new_widget is not None:
            def _is_widget_child_of_flyout(widget, flyout):
                if widget is None:
                    return False
                parent = widget.parent()
                while parent is not None:
                    if parent == flyout:
                        return True
                    parent = parent.parent()
                return False

            if _is_widget_child_of_flyout(new_widget, self.unified_flyout):
                return

        if self.unified_flyout is not None and self.unified_flyout.isVisible():
            self.unified_flyout.start_closing_animation()
            self.ui.combo_image1.setFlyoutOpen(False)
            self.ui.combo_image2.setFlyoutOpen(False)
