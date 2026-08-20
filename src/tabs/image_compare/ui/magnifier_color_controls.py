from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor

from core.constants import AppConstants
from domain.qt_adapters import ensure_visible_qcolor
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.icons import Icon

from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.widgets import (
    Button,
    IconAction,
    IconActionFlyout,
)


class MagnifierColorOptionsFlyout(IconActionFlyout):
    def __init__(self, parent=None, current_language: str = "en", store=None):
        self.current_language = current_language
        self.store = store
        super().__init__(
            parent,
            actions=self._build_actions(),
        )
        self.update_state()

    def _build_actions(self):
        return [
            IconAction(
                "capture",
                Icon.CAPTURE_AREA_COLOR,
                tr("image_compare.magnifier.capture_ring", self.current_language),
                visible=self._is_capture_active(),
            ),
            IconAction(
                "laser",
                Icon.MAGNIFIER_GUIDES,
                tr("image_compare.label.guides", self.current_language),
                visible=self._is_laser_active(),
            ),
            IconAction(
                "border",
                Icon.MAGNIFIER_BORDER_COLOR,
                tr("image_compare.label.border", self.current_language),
                visible=self._is_magnifier_active(),
            ),
            IconAction(
                "divider",
                Icon.VERTICAL_SPLIT,
                tr("image_compare.ui.choose_magnifier_divider_line_color", self.current_language),
                visible=self._is_divider_active(),
            ),
        ]

    def _is_magnifier_active(self):
        if not self.store:
            return False
        cmd = registry().get_feature_command_by_alias("overlay.enabled")
        return bool(cmd(self.store)) if cmd is not None else False

    def _is_capture_active(self):
        if not self._is_magnifier_active():
            return False
        return getattr(
            self.store.viewport.render_config,
            "show_capture_area_on_main_image",
            True,
        )

    def _is_laser_active(self):
        return self._is_magnifier_active()

    def _is_divider_active(self):
        if not self._is_magnifier_active():
            return False
        cmd = registry().get_feature_command_by_alias("overlay.active_combined")
        return bool(cmd(self.store)) if cmd is not None else False

    def has_visible_actions(self) -> bool:
        return self._is_magnifier_active()

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.set_actions(self._build_actions())

    def update_state(self):
        is_active = self._is_magnifier_active()
        self.set_action_state("capture", visible=self._is_capture_active())
        self.set_action_state("laser", visible=self._is_laser_active())
        self.set_action_state("border", visible=is_active)
        self.set_action_state("divider", visible=self._is_divider_active())
        super().update_state()


class ColorSettingsButton(Button):
    smartColorSetRequested = Signal()
    colorOptionClicked = Signal(str)
    elementHovered = Signal(str)
    elementHoverEnded = Signal()

    def __init__(self, parent=None, current_language: str = "en", store=None):
        super().__init__(
            Icon.DIVIDER_COLOR,
            show_underline=True,
            underline_thickness=2.0,
            parent=parent,
        )
        self.current_language = current_language
        self.store = store
        self.flyout = MagnifierColorOptionsFlyout(
            parent,
            current_language=current_language,
            store=store,
        )
        self._hide_timer = None
        self.clicked.connect(self.smartColorSetRequested.emit)
        self.flyout.actionTriggered.connect(self.colorOptionClicked.emit)
        if self.store:
            self.store.state_changed.connect(self._on_store_state_changed)
            self._update_underline_colors()

    def refresh_visual_state(self):
        self._update_underline_colors()
        self.flyout.update_state()

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.flyout.update_language(lang_code)

    def set_store(self, store):
        if self.store:
            try:
                self.store.state_changed.disconnect(self._on_store_state_changed)
            except Exception:
                pass
        self.store = store
        self.flyout.store = store
        if self.store:
            self.store.state_changed.connect(self._on_store_state_changed)
            self.refresh_visual_state()

    def _update_underline_colors(self):
        if not self.store:
            return

        enabled_cmd = registry().get_feature_command_by_alias("overlay.enabled")
        use_mag = bool(enabled_cmd(self.store)) if enabled_cmd is not None else False
        if not use_mag:
            self.setShowUnderline(False)
            return
        self.setShowUnderline(True)

        state_cmd = registry().get_feature_command_by_alias("overlay.active_state")
        active_state = state_cmd(self.store) if state_cmd is not None else None

        capture_cmd = registry().get_feature_command_by_alias("capture.widget_state")
        vp = self.store.viewport
        capture_state = capture_cmd(vp.view_state) if capture_cmd is not None else None

        guides_cmd = registry().get_feature_command_by_alias("guides.widget_state")
        guides_state = guides_cmd(vp.view_state) if guides_cmd is not None else None

        def _dict_col(key, fallback: QColor, default_alpha=255):
            col = active_state.get(key) if active_state is not None else None
            c = (
                ensure_visible_qcolor(col)
                if hasattr(col, "r")
                else ensure_visible_qcolor(fallback)
            )
            c.setAlpha(max(1, int(default_alpha)))
            return c

        def _dict_col_with_state_fallback(key, state_color, default_alpha=255):
            col = active_state.get(key) if active_state is not None else None
            if hasattr(col, "r"):
                c = ensure_visible_qcolor(col)
            elif state_color is not None and hasattr(state_color, "r"):
                c = ensure_visible_qcolor(state_color)
            else:
                c = QColor(255, 255, 255, 255)
            c.setAlpha(max(1, int(default_alpha)))
            return c

        capture_color = (
            getattr(capture_state, "color", None) if capture_state is not None else None
        )
        guides_color = (
            getattr(guides_state, "color", None) if guides_state is not None else None
        )

        col_capture = _dict_col_with_state_fallback("capture_color", capture_color, 230)
        col_laser = _dict_col_with_state_fallback("guides_color", guides_color, 230)
        col_border = _dict_col("border_color", QColor(255, 255, 255), 230)
        col_divider = _dict_col("divider_color", QColor(255, 255, 255), 230)

        combined_cmd = registry().get_feature_command_by_alias("overlay.active_combined")
        is_combined = bool(combined_cmd(self.store)) if combined_cmd is not None else False

        show_lasers = active_state is not None
        show_divider = bool(
            is_combined
            and active_state is not None
            and active_state.get("divider_visible", False)
            and active_state.get("divider_thickness", 0) > 0
        )

        zones = [
            (True, col_capture),
            (show_lasers, col_laser),
            (True, col_border),
            (show_divider, col_divider),
        ]
        self.setUnderlineColor([color for condition, color in zones if condition])

    def _on_store_state_changed(self, domain: str):
        if domain == "settings" or domain == "viewport" or domain.startswith("viewport."):
            self.refresh_visual_state()
            if self.flyout.isVisible():
                if self.flyout.has_visible_actions():
                    self.flyout.show_aligned(
                        self, "top-center", "bottom-center", toggle=False
                    )
                else:
                    self.flyout.hide()

    def _group_anchor(self):
        # Anchor to the whole magnifier group, not just this button,
        # so keyboard navigation on sibling ScrollValueButtons inside the
        # same group doesn't hide the color flyout (still inside group).
        parent = self.parentWidget()
        # Walk up to find the ButtonGroup container (magnifier_group_container)
        while parent is not None:
            if parent.objectName() == "magnifier_group" or "magnifier" in parent.objectName().lower():
                return parent
            # Fallback: use the direct parent that is a ButtonGroup
            from sli_ui_toolkit.widgets import ButtonGroup

            if isinstance(parent, ButtonGroup):
                return parent
            parent = parent.parentWidget()
        return self

    def enterEvent(self, event):
        super().enterEvent(event)
        # Hover no longer opens the color flyout — only explicit Enter/click
        # (keyPressEvent Enter or mousePress) does. Hover still emits for
        # magnifier group zone tracking, but not for flyout show.
        self.elementHovered.emit("magnifier")

    def leaveEvent(self, event):
        self.elementHoverEnded.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        # Click explicitly opens — same as Enter
        if event.button() == event.button().LeftButton:
            self.flyout.update_state()
            if self.flyout.has_visible_actions():
                anchor = self._group_anchor()
                self.flyout.show_aligned(
                    anchor, "top-center", "bottom-center", toggle=False
                )
                self.flyout.cancel_auto_hide()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Focus alone no longer opens — only Enter (handled in keyPressEvent)
        pass

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Keep flyout open if focus moves within same magnifier group
        try:
            from PySide6.QtWidgets import QApplication

            new_focus = QApplication.focusWidget()
            anchor = self._group_anchor()
            flyout = self.flyout
            still_inside = new_focus is not None and (
                (anchor is not None and anchor.isAncestorOf(new_focus))
                or (flyout is not None and flyout.isAncestorOf(new_focus))
                or new_focus is anchor
            )
            if still_inside:
                return
        except Exception:
            pass
        self.elementHoverEnded.emit()
        self.flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.flyout.update_state()
            if self.flyout.has_visible_actions():
                anchor = self._group_anchor()
                self.flyout.show_aligned(
                    anchor, "top-center", "bottom-center", toggle=False
                )
                self.flyout.cancel_auto_hide()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape and self.flyout.isVisible():
            self.flyout.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.elementHoverEnded.emit()
        # Keep flyout open if focus moves to sibling inside same magnifier group
        # (e.g. ScrollValueButton in same row) — only hide when truly leaving
        # the group+flyout unit.
        try:
            from PySide6.QtWidgets import QApplication

            new_focus = QApplication.focusWidget()
            anchor = self._group_anchor()
            flyout = self.flyout
            still_inside = new_focus is not None and (
                (anchor is not None and anchor.isAncestorOf(new_focus))
                or (flyout is not None and flyout.isAncestorOf(new_focus))
                or new_focus is anchor
            )
            if still_inside:
                return
        except Exception:
            pass
        self.flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)
