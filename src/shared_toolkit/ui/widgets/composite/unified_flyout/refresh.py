from shared_toolkit.ui.widgets.composite.unified_flyout.common import FlyoutMode

class _UnifiedFlyoutRefreshMixin:
    def _do_refresh_geometry(self):
        self.refreshGeometry(immediate=True)

    def refreshGeometry(self, immediate=False):
        if not immediate:
            self._schedule_geometry_refresh()
            return
        if not self._begin_immediate_refresh():
            return
        if self._should_abort_refresh():
            self._is_refreshing = False
            return

        list1 = self.store.document.image_list1
        list2 = self.store.document.image_list2
        if not list1 and not list2:
            self._finish_refresh_with_close()
            return
        if self._handle_mode_transitions_for_lists(list1, list2):
            self._is_refreshing = False
            return

        self.panel_left.recalculate_and_set_height()
        self.panel_right.recalculate_and_set_height()
        self._apply_refreshed_geometry()
        self._apply_style()
        self.raise_()
        self._is_refreshing = False

    def _schedule_geometry_refresh(self):
        if self._is_refreshing:
            if not self._refresh_timer.isActive():
                self._refresh_timer.start(50)
            return
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(50)

    def _begin_immediate_refresh(self) -> bool:
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
        if self._is_refreshing:
            return False
        self._is_refreshing = True
        self._apply_style()
        if self._anim and self._anim.state() == self._anim.State.Running:
            self._anim.stop()
        return True

    def _should_abort_refresh(self) -> bool:
        return not self.isVisible() or self._is_closing

    def _finish_refresh_with_close(self):
        self._is_refreshing = False
        self.start_closing_animation()

    def _handle_mode_transitions_for_lists(self, list1, list2) -> bool:
        if self.mode == FlyoutMode.DOUBLE:
            if not list1:
                self._switch_double_to_single(2)
            elif not list2:
                self._switch_double_to_single(1)
            return False
        if self.mode == FlyoutMode.SINGLE_LEFT and not list1:
            self.start_closing_animation()
            return True
        if self.mode == FlyoutMode.SINGLE_RIGHT and not list2:
            self.start_closing_animation()
            return True
        return False

    def _switch_double_to_single(self, list_num: int):
        self.mode = FlyoutMode.SINGLE_RIGHT if list_num == 2 else FlyoutMode.SINGLE_LEFT
        self.source_list_num = list_num
        if list_num == 2:
            self.panel_left.hide()
            self.panel_right.show()
            if self.main_window:
                self.main_window.ui.combo_image1.setFlyoutOpen(False)
                self.main_window.ui.combo_image2.setFlyoutOpen(True)
        else:
            self.panel_right.hide()
            self.panel_left.show()
            if self.main_window:
                self.main_window.ui.combo_image2.setFlyoutOpen(False)
                self.main_window.ui.combo_image1.setFlyoutOpen(True)

    def _apply_refreshed_geometry(self):
        if self.mode == FlyoutMode.DOUBLE:
            self.panel_left.show()
            self.panel_right.show()
            self._update_geometry_in_double_mode_internal()
            return
        self._apply_single_mode_refresh_geometry()

    def _apply_single_mode_refresh_geometry(self):
        is_left = self.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_SIMPLE)
        active_panel = self.panel_left if is_left else self.panel_right
        anchor = (
            self.main_window.ui.combo_image1
            if is_left
            else self.main_window.ui.combo_image2
        )
        active_list_num = 1 if is_left else 2
        active_panel.show()
        (self.panel_right if is_left else self.panel_left).hide()
        if hasattr(anchor, "setFlyoutOpen"):
            anchor.setFlyoutOpen(True)
        panel_size = self._calc_panel_total_size(active_list_num)
        content_rect = self._calculate_ideal_content_geometry(
            anchor, panel_size, extra_y=self.SINGLE_APPEAR_EXTRA_Y
        )
        self.setGeometry(
            content_rect.adjusted(
                -self.SHADOW_RADIUS,
                -self.SHADOW_RADIUS,
                self.SHADOW_RADIUS,
                self.SHADOW_RADIUS,
            )
        )
        self._apply_container_geometry()
        self._position_panels_for_single()
