from ui.widgets.unified_list_picker.debug import double_geom_debug
from ui.widgets.unified_list_picker.common import (
    FlyoutMode,
    _UnifiedFlyoutBase,
    items_for_list,
)

class _UnifiedFlyoutRefreshMixin(_UnifiedFlyoutBase):
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

        list1 = items_for_list(self._document(), 1)
        list2 = items_for_list(self._document(), 2)
        double_geom_debug(
            "refresh mode=%s n1=%s n2=%s",
            getattr(self.mode, "name", self.mode),
            len(list1),
            len(list2),
        )
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
                self._refresh_timer.start(100)
            return
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(100)

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
                double_geom_debug("DOUBLE→SINGLE_RIGHT (list1 empty)")
                self._switch_double_to_single(2)
            elif not list2:
                double_geom_debug("DOUBLE→SINGLE_LEFT (list2 empty)")
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
        def _safe_set(anchor, value: bool) -> None:
            if anchor is not None and hasattr(anchor, "setFlyoutOpen"):
                anchor.setFlyoutOpen(value)

        if list_num == 2:
            self.panel_left.hide()
            self.panel_right.show()
            _safe_set(self.anchor_for_list(1), False)
            _safe_set(self.anchor_for_list(2), True)
        else:
            self.panel_right.hide()
            self.panel_left.show()
            _safe_set(self.anchor_for_list(2), False)
            _safe_set(self.anchor_for_list(1), True)

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
        anchor = self.anchor_for_list(1 if is_left else 2)
        if anchor is None:
            return
        active_list_num = 1 if is_left else 2
        active_panel.show()
        (self.panel_right if is_left else self.panel_left).hide()
        if hasattr(anchor, "setFlyoutOpen"):
            anchor.setFlyoutOpen(True)
        geometry, _start_pos, _end_pos = self._build_single_mode_geometry(
            anchor,
            active_list_num,
        )
        self.setGeometry(geometry)
        self._apply_container_geometry()
        self._position_panels_for_single()