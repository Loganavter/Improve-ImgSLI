from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt

from core.constants import AppConstants
from sli_ui_toolkit.managers import DelayedActionTimer


class MagnifierSettingsHoverController(QObject):
    """Hover over the toolbar -> show the magnifier sliders flyout.

    Tab-local, self-contained (unlike ``MagnifierVisibilityController``, it
    does not go through ``UIManager``/``TransientUIManager``): the toolbar,
    the flyout and ``magnifier_group_container`` all already live on the
    same ``ImageCompareWidget``, so it wires its own event filter directly.

    Not gated on ``btn_magnifier.isChecked()`` -- the sliders are still
    useful to preview/adjust before turning the magnifier on. The hover
    trigger is the whole toolbar row (``checkbox_widget``), not just the
    magnifier group, but the flyout always anchors to the magnifier group
    itself for positioning.
    """

    def __init__(self, widget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._hover_timer = DelayedActionTimer(self._show, parent=widget)
        self._mode_picker_flyouts_wired: set = set()
        self._wire()

    def _wire(self) -> None:
        widget = self.widget
        toolbar = getattr(widget, "checkbox_widget", None)
        group = getattr(widget, "magnifier_group_container", None)
        flyout = getattr(widget, "magnifier_settings_flyout", None)
        if toolbar is None or group is None or flyout is None:
            return
        toolbar.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        toolbar.installEventFilter(self)
        flyout.installEventFilter(self)
        # The color-options flyouts (btn_magnifier_color_settings[_beginner])
        # already exist at this point (built earlier in the same assemble()
        # pass, before this controller) -- other toolbar flyouts
        # (font_settings_flyout, magnifier_visibility_flyout) are wired in
        # later by app-level presenter code, so they're picked up lazily in
        # _link_sibling_flyouts() instead, called from every _show().
        for attr in ("btn_magnifier_color_settings", "btn_magnifier_color_settings_beginner"):
            btn = getattr(widget, attr, None)
            color_flyout = getattr(btn, "flyout", None) if btn is not None else None
            if color_flyout is not None:
                # IconActionFlyout.hide()s itself right after emitting
                # actionTriggered (a color option was picked, e.g. opening a
                # QColorDialog next) -- same shape as the interpolation
                # dropdown closing after a choice (see
                # InterpolationFlyoutController.apply_choice /
                # _cancel_settings_auto_hide). Without this, this panel's own
                # pending hide (scheduled when the hover left onto the
                # color-options popup) fires while the color dialog is open,
                # closing the panel out from under it.
                color_flyout.actionTriggered.connect(
                    lambda _action_id: self._cancel_settings_auto_hide()
                )
        # btn_diff_mode / btn_channel_mode (view_group_container, also part
        # of this same hover-triggering toolbar row) each open a ModePicker
        # dropdown lazily, on first click -- unlike the color-options
        # flyouts above, there is no flyout instance yet at _wire() time to
        # link. Opening it while this panel is already showing (hovering
        # the toolbar to reach the button already triggered it) makes Qt
        # recompute hover state against the new topmost popup, firing a
        # Leave on the toolbar that schedules this panel's hide -- with the
        # dropdown unlinked, the cursor landing on it doesn't count as
        # "inside" and the panel closes out from under the still-open pick.
        # Re-link right after each click (same call stack as ModePicker's
        # own _on_clicked, so the flyout it just created/showed already
        # exists) -- comfortably before schedule_auto_hide's delay elapses.
        for attr in ("btn_diff_mode_picker", "btn_channel_mode_picker"):
            picker = getattr(widget, attr, None)
            button = getattr(picker, "_button", None) if picker is not None else None
            if button is not None:
                button.clicked.connect(
                    lambda _checked=False, p=picker: self._link_mode_picker_flyout(p)
                )
        # ScrollValueButtons on the same toolbar row (width/orientation
        # scroll-nudge controls) show their own _ScrollValueFlyout lazily,
        # on first wheelEvent -- not yet created at _wire() time either.
        # valueChanged fires every time _show_flyout() also runs, so it's
        # the same "re-link right as it's created/shown" hook as the mode
        # pickers' clicked above.
        for attr in (
            "btn_magnifier_orientation",
            "btn_orientation",
            "btn_magnifier_guides",
            "btn_divider_width",
            "btn_magnifier_divider_width",
            "btn_magnifier_guides_width",
        ):
            button = getattr(widget, attr, None)
            if button is not None and hasattr(button, "valueChanged"):
                button.valueChanged.connect(
                    lambda _value, b=button: self._link_scroll_value_flyout(b)
                )

    def eventFilter(self, watched, event) -> bool:
        widget = self.widget
        if watched is getattr(widget, "checkbox_widget", None):
            self._handle_toolbar_event(event)
        elif watched is getattr(widget, "magnifier_settings_flyout", None):
            self._handle_flyout_event(event)
        return False

    def _handle_toolbar_event(self, event) -> None:
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            self._hover_timer.stop()
            self._hover_timer.start(AppConstants.TRANSIENT_HOVER_OPEN_DELAY_MS)
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            self._hover_timer.stop()
            self._schedule_hide()

    def _handle_flyout_event(self, event) -> None:
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            self._cancel_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            self._schedule_hide()

    def _show(self) -> None:
        widget = self.widget
        flyout = getattr(widget, "magnifier_settings_flyout", None)
        group = getattr(widget, "magnifier_group_container", None)
        if flyout is None or group is None:
            return
        self._link_sibling_flyouts(flyout)
        flyout.show_for_group(group)
        flyout.cancel_auto_hide()

    def _link_sibling_flyouts(self, flyout) -> None:
        """Make every other toolbar flyout part of this panel's family.

        ``AnchoredFlyoutAutoHide`` (see this panel's own auto-hide, wired in
        ``magnifier_settings_flyout.py``) treats a linked child's own body as
        "still inside" this panel's safe zone -- without linking, hovering
        from the toolbar onto e.g. the font-settings flyout (also opened by
        hovering this same toolbar row, see this class's docstring) reads as
        "cursor left the panel", and this panel auto-hides right out from
        under whatever the user is actually doing in that other flyout.
        Same fix already applied to ``combo_interpolation``'s dropdown, see
        ``InterpolationFlyoutController.show``. Re-run on every ``_show()``
        (cheap/idempotent, see ``FlyoutManager.link``) rather than once in
        ``_wire()`` since ``font_settings_flyout``/``magnifier_visibility_flyout``
        are attached to the widget later, by app-level presenter code, not
        yet available when this controller is constructed.
        """
        from sli_ui_toolkit.managers import FlyoutManager

        widget = self.widget
        manager = FlyoutManager.get_instance()
        siblings = [
            getattr(widget, "font_settings_flyout", None),
            getattr(widget, "magnifier_visibility_flyout", None),
        ]
        for attr in ("btn_magnifier_color_settings", "btn_magnifier_color_settings_beginner"):
            btn = getattr(widget, attr, None)
            siblings.append(getattr(btn, "flyout", None) if btn is not None else None)
        for sibling in siblings:
            if sibling is not None:
                manager.link(flyout, sibling)

    def _link_mode_picker_flyout(self, picker) -> None:
        flyout = getattr(picker, "_flyout", None)
        settings_flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is None or settings_flyout is None:
            return
        from sli_ui_toolkit.managers import FlyoutManager

        FlyoutManager.get_instance().link(settings_flyout, flyout)
        # Picking a row hides the dropdown itself (SimpleOptionsFlyout.item_chosen
        # -> ModePicker._on_item_chosen -> _hide_flyout_if_open), same
        # close-immediately-after-choosing shape as the color-options icons
        # and the interpolation dropdown -- cancel this panel's pending
        # hide so that close doesn't leave it to auto-hide right after.
        if flyout not in self._mode_picker_flyouts_wired:
            self._mode_picker_flyouts_wired.add(flyout)
            flyout.item_chosen.connect(lambda _index: self._cancel_settings_auto_hide())

    def _link_scroll_value_flyout(self, button) -> None:
        flyout = getattr(button, "_flyout", None)
        settings_flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is None or settings_flyout is None:
            return
        from sli_ui_toolkit.managers import FlyoutManager

        FlyoutManager.get_instance().link(settings_flyout, flyout)

    def _cancel_settings_auto_hide(self) -> None:
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is not None:
            flyout.cancel_auto_hide()

    def _schedule_hide(self) -> None:
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is not None:
            flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)

    def _cancel_hide(self) -> None:
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is not None:
            flyout.cancel_auto_hide()
