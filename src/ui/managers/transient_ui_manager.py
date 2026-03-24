import time

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QTimer
from PyQt6.QtWidgets import QApplication

from core.constants import AppConstants
from core.events import ViewportToggleMagnifierPartEvent
from domain.qt_adapters import color_to_qcolor
from resources.translations import tr

class TransientUIManager:
    def __init__(self, host):
        self.host = host

    def show_flyout(self, image_number: int):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        if self.host.unified_flyout:
            time_since_close = (
                time.monotonic() - self.host.unified_flyout.last_close_timestamp
            )
            is_same_list = self.host.unified_flyout.source_list_num == image_number

            if (
                self.host.unified_flyout.last_close_mode == FlyoutMode.DOUBLE
                and time_since_close < 0.2
            ) or (is_same_list and time_since_close < 0.2):
                return

        if self.host.unified_flyout is not None and self.host.unified_flyout.isVisible():
            if self.host.unified_flyout.mode == FlyoutMode.DOUBLE:
                self.host.ui.combo_image1.setFlyoutOpen(False)
                self.host.ui.combo_image2.setFlyoutOpen(False)
                self.host.unified_flyout.start_closing_animation()
                return

            if (
                self.host.unified_flyout.mode
                in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_RIGHT)
                and self.host.unified_flyout.source_list_num == image_number
            ):
                button = (
                    self.host.ui.combo_image1
                    if image_number == 1
                    else self.host.ui.combo_image2
                )
                button.setFlyoutOpen(False)
                self.host.unified_flyout.start_closing_animation()
                return

        target_list = (
            self.host.store.document.image_list1
            if image_number == 1
            else self.host.store.document.image_list2
        )
        if len(target_list) == 0:
            return

        button = (
            self.host.ui.combo_image1 if image_number == 1 else self.host.ui.combo_image2
        )
        other_button = (
            self.host.ui.combo_image2 if image_number == 1 else self.host.ui.combo_image1
        )
        other_button.setFlyoutOpen(False)
        button.setFlyoutOpen(True)

        if self.host.unified_flyout is not None:
            self.host.unified_flyout.showAsSingle(image_number, button)

        QTimer.singleShot(0, self.sync_flyout_combo_status)

    def sync_flyout_combo_status(self):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        if self.host.unified_flyout.mode == FlyoutMode.DOUBLE:
            self.host.ui.combo_image1.setFlyoutOpen(True)
            self.host.ui.combo_image2.setFlyoutOpen(True)

    def toggle_interpolation_flyout(self):
        if self.host._interp_popup_open:
            self.close_interpolation_flyout()
            return
        self.show_interpolation_flyout()

    def show_interpolation_flyout(self):
        from shared_toolkit.ui.widgets.composite.simple_options_flyout import (
            SimpleOptionsFlyout,
        )
        if self.host._interp_flyout is None:
            self.host._interp_flyout = SimpleOptionsFlyout(self.host.parent_widget)
            self.host._interp_flyout.closed.connect(
                self.on_interpolation_flyout_closed_event
            )

        lang = self.host.store.settings.current_language
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
        method_keys = [
            k
            for k in AppConstants.INTERPOLATION_METHODS_MAP.keys()
            if k != "EWA_LANCZOS" or WAND_AVAILABLE
        ]
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
                self.host.store.viewport,
                "interpolation_method",
                AppConstants.DEFAULT_INTERPOLATION_METHOD,
            )
            if target_key not in method_keys:
                target_key = (
                    AppConstants.DEFAULT_INTERPOLATION_METHOD
                    if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys
                    else (
                        method_keys[0]
                        if method_keys
                        else AppConstants.DEFAULT_INTERPOLATION_METHOD
                    )
                )
                self.host.store.viewport.interpolation_method = target_key
                self.host.store.emit_state_change()
            current_index = method_keys.index(target_key) if method_keys else 0
        except (AttributeError, ValueError, IndexError):
            current_index = 0

        try:
            self.host._interp_flyout.item_chosen.disconnect()
        except TypeError:
            pass

        item_height = 34
        item_font = QApplication.font()
        combo = getattr(self.host.ui, "combo_interpolation", None)
        if combo is not None:
            if hasattr(combo, "getItemHeight"):
                item_height = combo.getItemHeight()
            if hasattr(combo, "getItemFont"):
                item_font = combo.getItemFont()

        self.host._interp_flyout.set_row_height(item_height)
        self.host._interp_flyout.set_row_font(item_font)
        self.host._interp_flyout.populate(labels, current_index)
        self.host._interp_flyout.item_chosen.connect(self.apply_interpolation_choice)

        if combo is not None:
            combo.setFlyoutOpen(True)
            self.host._interp_last_open_ts = time.monotonic()

        def _do_show():
            if self.host._interp_flyout is not None and combo is not None:
                self.host._interp_flyout.show_below(combo)
                self.host._interp_popup_open = True
                self.host._interp_last_open_ts = time.monotonic()

        QTimer.singleShot(0, _do_show)

    def apply_interpolation_choice(self, idx: int):
        try:
            combo = getattr(self.host.ui, "combo_interpolation", None)
            if combo is not None and 0 <= idx < combo.count():
                combo.setCurrentIndex(idx)
                if self.host.main_controller and self.host.main_controller.session_ctrl:
                    self.host.main_controller.session_ctrl.on_interpolation_changed(idx)
        finally:
            self.close_interpolation_flyout()

    def close_interpolation_flyout(self):
        if self.host._interp_flyout is not None:
            self.host._interp_flyout.hide()
        combo = getattr(self.host.ui, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        self.host._interp_popup_open = False

    def on_interpolation_flyout_closed_event(self):
        combo = getattr(self.host.ui, "combo_interpolation", None)
        if combo is not None:
            combo.setFlyoutOpen(False)
        self.host._interp_popup_open = False

    def toggle_font_settings_flyout(self, anchor_widget=None):
        if self.host._font_popup_open:
            self.hide_font_settings_flyout()
        else:
            self.show_font_settings_flyout(anchor_widget=anchor_widget)

    def show_font_settings_flyout(self, anchor_widget=None):
        if not self.host.font_settings_flyout:
            return
        if anchor_widget is None:
            anchor_widget = getattr(self.host.ui, "btn_color_picker", None)
        self.host._font_anchor_widget = anchor_widget
        self.host.font_settings_flyout.set_values(
            self.host.store.viewport.font_size_percent,
            self.host.store.viewport.font_weight,
            color_to_qcolor(self.host.store.viewport.file_name_color),
            color_to_qcolor(self.host.store.viewport.file_name_bg_color),
            self.host.store.viewport.draw_text_background,
            self.host.store.viewport.text_placement_mode,
            getattr(self.host.store.viewport, "text_alpha_percent", 100),
            self.host.store.settings.current_language,
        )
        if anchor_widget is not None:
            self.host.font_settings_flyout.show_top_left_of(anchor_widget)
            if hasattr(anchor_widget, "setFlyoutOpen"):
                anchor_widget.setFlyoutOpen(True)
        self.host._font_popup_open = True
        self.host._font_popup_last_open_ts = time.monotonic()

    def hide_font_settings_flyout(self):
        if self.host.font_settings_flyout is not None:
            self.host.font_settings_flyout.hide()
        if self.host._font_anchor_widget is not None and hasattr(
            self.host._font_anchor_widget, "setFlyoutOpen"
        ):
            self.host._font_anchor_widget.setFlyoutOpen(False)
        self.host._font_popup_open = False
        self.host._font_anchor_widget = None

    def repopulate_flyouts(self):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode
        if self.host.unified_flyout and self.host.unified_flyout.isVisible():
            self.host.unified_flyout.populate(1, self.host.store.document.image_list1)
            self.host.unified_flyout.populate(2, self.host.store.document.image_list2)
            if self.host.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(
                    0, lambda: self.host.unified_flyout.refreshGeometry(immediate=False)
                )

    def on_font_changed(self):
        self.host.repopulate_visible_flyouts()
        if hasattr(self.host.ui, "reapply_button_styles"):
            self.host.ui.reapply_button_styles()
        if self.host.parent_widget is not None:
            self.host.parent_widget.update()

    def on_flyout_closed(self, image_number: int):
        button = self.host.ui.combo_image1 if image_number == 1 else self.host.ui.combo_image2
        button.setFlyoutOpen(False)

    def on_unified_flyout_closed(self):
        from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode
        if self.host.unified_flyout is not None:
            self.host.unified_flyout.mode = FlyoutMode.HIDDEN
        self.host.ui.combo_image1.setFlyoutOpen(False)
        self.host.ui.combo_image2.setFlyoutOpen(False)
        self.on_flyout_closed(1)
        self.on_flyout_closed(2)

    def update_magnifier_flyout_states(self):
        try:
            show_center = getattr(self.host.store.viewport, "diff_mode", "off") != "off"
            left_on = getattr(self.host.store.viewport, "magnifier_visible_left", True)
            center_on = getattr(self.host.store.viewport, "magnifier_visible_center", True)
            right_on = getattr(self.host.store.viewport, "magnifier_visible_right", True)
            self.host.magnifier_visibility_flyout.set_mode_and_states(
                show_center, left_on, center_on, right_on
            )
        except Exception:
            pass

    def on_magnifier_toggle_with_hover(self, checked: bool):
        btn = getattr(self.host.ui, "btn_magnifier", None)
        if btn is None:
            return
        if btn.underMouse():
            if checked:
                QTimer.singleShot(0, lambda: self.show_magnifier_visibility_flyout(reason="hover"))
            else:
                self.hide_magnifier_visibility_flyout()

    def show_magnifier_visibility_flyout(self, reason: str = "hover"):
        use_magnifier = getattr(self.host.store.viewport, "use_magnifier", False)
        if hasattr(self.host.store.viewport, "view_state"):
            use_magnifier = getattr(
                self.host.store.viewport.view_state, "use_magnifier", use_magnifier
            )
        if not use_magnifier:
            return
        self.update_magnifier_flyout_states()
        btn = getattr(self.host.ui, "btn_magnifier", None)
        if btn is not None:
            self.host.magnifier_visibility_flyout.show_for_button(
                btn, self.host.parent_widget, hover_delay_ms=0
            )
            self.host._magn_popup_open = True
            self.host._magn_popup_last_open_ts = time.monotonic()
            if reason == "wheel":
                self.host.magnifier_visibility_flyout.schedule_auto_hide(1200)
            else:
                self.host.magnifier_visibility_flyout.cancel_auto_hide()

    def hide_magnifier_visibility_flyout(self):
        self.host.magnifier_visibility_flyout.hide()
        self.host._magn_popup_open = False

    def event_filter(self, watched, event):
        btn = getattr(self.host.ui, "btn_magnifier", None)
        if btn is None:
            return False
        if watched is btn:
            et = event.type()
            if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                self.host._magn_hover_timer.stop()
                use_magnifier = getattr(self.host.store.viewport, "use_magnifier", False)
                if hasattr(self.host.store.viewport, "view_state"):
                    use_magnifier = getattr(
                        self.host.store.viewport.view_state,
                        "use_magnifier",
                        use_magnifier,
                    )
                if use_magnifier:
                    def _do_show():
                        self.show_magnifier_visibility_flyout(reason="hover")
                    try:
                        self.host._magn_hover_timer.timeout.disconnect()
                    except TypeError:
                        pass
                    self.host._magn_hover_timer.timeout.connect(_do_show)
                    self.host._magn_hover_timer.start(150)
                else:
                    self.host.magnifier_visibility_flyout.hide()
                return False
            if et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
                self.host.magnifier_visibility_flyout.schedule_auto_hide(1000)
                return False
            if et == QEvent.Type.Wheel:
                use_magnifier = getattr(self.host.store.viewport, "use_magnifier", False)
                if hasattr(self.host.store.viewport, "view_state"):
                    use_magnifier = getattr(
                        self.host.store.viewport.view_state,
                        "use_magnifier",
                        use_magnifier,
                    )
                if not use_magnifier:
                    return True
                self.show_magnifier_visibility_flyout(reason="wheel")
                return True
            return False

        if watched is self.host.magnifier_visibility_flyout:
            et = event.type()
            if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                self.host.magnifier_visibility_flyout.cancel_auto_hide()
            elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
                self.host.magnifier_visibility_flyout.schedule_auto_hide(1000)
            return False
        return False

    def _map_global_to_parent(self, global_pos: QPointF) -> QPoint:
        return self.host.parent_widget.mapFromGlobal(global_pos.toPoint())

    def _widget_rect_in_parent(self, widget) -> QRect:
        rect = widget.rect()
        rect.moveTo(widget.mapTo(self.host.parent_widget, rect.topLeft()))
        return rect

    def _is_inside_interpolation_anchor(self, global_pos: QPointF) -> bool:
        combo = getattr(self.host.ui, "combo_interpolation", None)
        return combo is not None and self._widget_rect_in_parent(combo).contains(
            self._map_global_to_parent(global_pos)
        )

    def close_all_flyouts_if_needed(self, global_pos: QPointF):
        if self.host._is_modal_active or self._is_inside_interpolation_anchor(global_pos):
            return
        self._close_magnifier_visibility_if_needed(global_pos)
        self._close_font_flyout_if_needed(global_pos)
        if self._is_interpolation_grace_period_active():
            return
        self._close_button_menu_if_needed(
            global_pos, "_diff_mode_popup_open", "_diff_mode_last_open_ts", getattr(self.host.ui, "btn_diff_mode", None)
        )
        self._close_button_menu_if_needed(
            global_pos, "_channel_mode_popup_open", "_channel_mode_last_open_ts", getattr(self.host.ui, "btn_channel_mode", None)
        )
        if self.host.unified_flyout is None or not self.host.unified_flyout.isVisible():
            self._close_interpolation_flyout_if_needed(global_pos)
            return
        self._close_unified_flyout_if_needed(global_pos)
        if self.host._interp_popup_open and self.host._interp_flyout:
            if (time.monotonic() - self.host._interp_last_open_ts) >= 0.12:
                combo = getattr(self.host.ui, "combo_interpolation", None)
                if combo is not None:
                    combo_local_pos = self.host.parent_widget.mapFromGlobal(global_pos.toPoint())
                    combo_rect = combo.rect()
                    combo_rect.moveTo(combo.mapTo(self.host.parent_widget, combo_rect.topLeft()))
                    if combo_rect.contains(combo_local_pos):
                        return
                flyout_contains = (
                    self.host._interp_flyout.contains_global(global_pos.toPoint())
                    if hasattr(self.host._interp_flyout, "contains_global")
                    else QRect(self.host._interp_flyout.mapToGlobal(QPoint(0, 0)), self.host._interp_flyout.size()).contains(global_pos.toPoint())
                )
                if not flyout_contains:
                    self.close_interpolation_flyout()

    def _close_magnifier_visibility_if_needed(self, global_pos: QPointF):
        if self.host.magnifier_visibility_flyout is None or not self.host.magnifier_visibility_flyout.isVisible():
            return
        btn = getattr(self.host.ui, "btn_magnifier", None)
        if btn is None:
            return
        inside_btn = self._widget_rect_in_parent(btn).contains(self._map_global_to_parent(global_pos))
        inside_fly = self.host.magnifier_visibility_flyout.contains_global(global_pos)
        if not inside_btn and not inside_fly:
            self.hide_magnifier_visibility_flyout()

    def _close_font_flyout_if_needed(self, global_pos: QPointF):
        if not (
            self.host._font_popup_open
            and (time.monotonic() - self.host._font_popup_last_open_ts) > 0.12
            and self.host.font_settings_flyout is not None
        ):
            return
        flyout_global_rect = QRect(
            self.host.font_settings_flyout.mapToGlobal(QPoint(0, 0)),
            self.host.font_settings_flyout.size(),
        )
        anchor = self.host._font_anchor_widget or getattr(self.host.ui, "btn_color_picker", None)
        button_rect = QRect()
        if anchor:
            button_rect = anchor.geometry()
            button_rect.moveTo(anchor.mapToGlobal(QPoint(0, 0)))
        if not flyout_global_rect.contains(global_pos.toPoint()) and not button_rect.contains(global_pos.toPoint()):
            self.hide_font_settings_flyout()

    def _is_interpolation_grace_period_active(self) -> bool:
        return bool(
            hasattr(self.host, "_interp_last_open_ts")
            and self.host._interp_last_open_ts > 0
            and (time.monotonic() - self.host._interp_last_open_ts) < 0.15
        )

    def _close_button_menu_if_needed(self, global_pos: QPointF, open_attr: str, opened_at_attr: str, button):
        if not getattr(self.host, open_attr, False):
            return
        if (time.monotonic() - getattr(self.host, opened_at_attr, 0.0)) <= 0.12:
            return
        if button is None or not button.is_menu_visible():
            setattr(self.host, open_attr, False)
            return
        local_pos = self._map_global_to_parent(global_pos)
        btn_rect = self._widget_rect_in_parent(button)
        menu_widget = button.menu
        menu_rect = QRect(menu_widget.mapToGlobal(QPoint(0, 0)), menu_widget.size())
        if not btn_rect.contains(local_pos) and not menu_rect.contains(global_pos.toPoint()):
            button.hide_menu()
            setattr(self.host, open_attr, False)

    def _close_interpolation_flyout_if_needed(self, global_pos: QPointF):
        if not (self.host._interp_popup_open and self.host._interp_flyout is not None):
            return
        if self._is_inside_interpolation_anchor(global_pos):
            return
        flyout_contains = (
            self.host._interp_flyout.contains_global(global_pos.toPoint())
            if hasattr(self.host._interp_flyout, "contains_global")
            else QRect(self.host._interp_flyout.mapToGlobal(QPoint(0, 0)), self.host._interp_flyout.size()).contains(global_pos.toPoint())
        )
        if not flyout_contains:
            self.close_interpolation_flyout()

    def _close_unified_flyout_if_needed(self, global_pos: QPointF):
        local_pos = self.host.parent_widget.mapFromGlobal(global_pos.toPoint())
        flyout_rect_local = self.host.unified_flyout.geometry()
        button_rects = []
        for btn in (self.host.ui.combo_image1, self.host.ui.combo_image2):
            rect = btn.rect()
            rect.moveTo(btn.mapTo(self.host.parent_widget, rect.topLeft()))
            button_rects.append(rect)
        is_click_on_any_button = any(r.contains(local_pos) for r in button_rects)
        is_click_inside_flyout = flyout_rect_local.contains(local_pos)
        is_click_on_flyout_child = self._is_click_on_widget_or_children(
            self.host.unified_flyout, global_pos.toPoint()
        )
        if hasattr(self.host.unified_flyout, "panel_left"):
            for panel in [self.host.unified_flyout.panel_left, self.host.unified_flyout.panel_right]:
                if hasattr(panel, "list_view") and hasattr(panel.list_view, "custom_v_scrollbar"):
                    scrollbar = panel.list_view.custom_v_scrollbar
                    if scrollbar.isVisible():
                        scrollbar_global_rect = QRect(scrollbar.mapToGlobal(QPoint(0, 0)), scrollbar.size())
                        if scrollbar_global_rect.contains(global_pos.toPoint()):
                            return
        if not is_click_on_any_button and not is_click_inside_flyout and not is_click_on_flyout_child:
            self.host.unified_flyout.start_closing_animation()
            self.host.ui.combo_image1.setFlyoutOpen(False)
            self.host.ui.combo_image2.setFlyoutOpen(False)

    def _is_click_on_widget_or_children(self, widget, global_pos_point):
        if not widget or not widget.isVisible():
            return False
        local_pos_for_widget = widget.mapFromGlobal(global_pos_point)
        return widget.rect().contains(local_pos_for_widget)

    def hide_transient_same_window_ui(self):
        try:
            if self.host.unified_flyout is not None and self.host.unified_flyout.isVisible():
                self.host.unified_flyout.start_closing_animation()
                self.host.ui.combo_image1.setFlyoutOpen(False)
                self.host.ui.combo_image2.setFlyoutOpen(False)
        except Exception:
            pass
        try:
            if self.host._interp_popup_open and self.host._interp_flyout is not None:
                self.close_interpolation_flyout()
        except Exception:
            pass
        try:
            if self.host._font_popup_open and self.host.font_settings_flyout is not None:
                self.hide_font_settings_flyout()
        except Exception:
            pass
        try:
            if self.host._magn_popup_open and self.host.magnifier_visibility_flyout is not None:
                self.hide_magnifier_visibility_flyout()
        except Exception:
            pass
        try:
            overlay_layer = getattr(self.host.parent_widget, "overlay_layer", None)
            if overlay_layer is not None:
                overlay_layer.hide_all_popups()
        except Exception:
            pass
        try:
            from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
            PathTooltip.get_instance().hide_tooltip()
        except Exception:
            pass
        try:
            from events.drag_drop_handler import DragAndDropService
            service = DragAndDropService.get_instance()
            if service.is_dragging():
                service.cancel_drag()
        except Exception:
            pass

    def on_app_focus_changed(self, old_widget, new_widget):
        if new_widget is None and self.host.parent_widget.isActiveWindow():
            return
        if (
            self.host.unified_flyout is not None
            and self.host.unified_flyout.isVisible()
            and getattr(self.host.unified_flyout, "_is_refreshing", False)
        ):
            return
        if (
            self.host.unified_flyout is not None
            and self.host.unified_flyout.isVisible()
            and new_widget is not None
        ):
            parent = new_widget.parent()
            while parent is not None:
                if parent == self.host.unified_flyout:
                    return
                parent = parent.parent()
        self.hide_transient_same_window_ui()
