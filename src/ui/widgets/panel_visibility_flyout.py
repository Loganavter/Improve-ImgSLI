"""Host-owned panel-visibility flyout.

Generic ``IndexedToggleFlyout`` with 3 slots (left/center/right). The icon
is required from the caller — this widget has NO dependency on any tab
package or knowledge of which feature it's toggling.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import IndexedToggleFlyout


class PanelVisibilityFlyout(IndexedToggleFlyout):
    _nav_side = "above"
    _nav_mode = "preview"
    _nearest_focus = True  # Up→ближайший к якорю, не всегда левый
    _nav_exit = "up"  # любой Up→якорь (у toggle уже так, но явно)

    def __init__(self, parent_widget: QWidget, *, slot_icon: str):
        super().__init__(parent_widget, slot_count=3, slot_icon=slot_icon)
        self.btn_left = self.buttons[0]
        self.btn_center = self.buttons[1]
        self.btn_right = self.buttons[2]
        self.btn_laser = None
        self._keyboard_navigation_active = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Only activate keyboard navigation if opened via keyboard (Enter)
        # — hover opens should not intercept arrow keys.
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

            if NavigationManager.get_instance().last_input_was_keyboard():
                self._keyboard_navigation_active = True
            else:
                self._keyboard_navigation_active = False
        except Exception:
            self._keyboard_navigation_active = False

    def hideEvent(self, event) -> None:
        self._keyboard_navigation_active = False
        super().hideEvent(event)

    def focus_first_child(self) -> bool:
        self._keyboard_navigation_active = True
        return super().focus_first_child()

    def focus_last_child(self) -> bool:
        self._keyboard_navigation_active = True
        return super().focus_last_child()

    def keyPressEvent(self, event) -> None:
        # No keyboard handling — pure hover preview, arrow/Enter/Esc go to toolbar
        super().keyPressEvent(event)

    def set_mode_and_states(
        self,
        show_center: bool,
        left_on: bool,
        center_on: bool,
        right_on: bool,
        laser_on: bool = True,
    ):

        active_states = [left_on, center_on, right_on]
        display_numbers = [1, 2, 3]
        self.set_slots(active_states, display_numbers=display_numbers)
        self.btn_center.setVisible(show_center)
        if show_center:
            self.btn_right.set_display_number(3)
        else:
            self.btn_right.set_display_number(2)
