from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from core.constants import AppConstants
from sli_ui_toolkit.managers import DecisionJournal, DelayedActionTimer


_HOVER_ZONE_PADDING_PX = 10


class MagnifierSettingsHoverController(QObject):
    """Hover over the magnifier group -> show the magnifier sliders flyout.

    Tab-local, self-contained (unlike ``MagnifierVisibilityController``, it
    does not go through ``UIManager``/``TransientUIManager``): the toolbar,
    the flyout and ``magnifier_group_container`` all already live on the
    same ``ImageCompareWidget``, so it wires its own event filter directly.

    Not gated on ``btn_magnifier.isChecked()`` -- the sliders are still
    useful to preview/adjust before turning the magnifier on. The hover
    trigger is a padded zone around the magnifier group
    (``magnifier_group_container``), not the whole toolbar row: the flyout
    opens when the cursor is inside the group or within
    ``_HOVER_ZONE_PADDING_PX`` px around it, and always anchors to the
    magnifier group itself for positioning.
    """

    def __init__(self, widget) -> None:
        super().__init__(widget)
        self.widget = widget
        self._hover_timer = DelayedActionTimer(self._show, parent=widget)
        self._mode_picker_flyouts_wired: set = set()
        self._group_buttons: set = set()
        # Decision journal (shared toolkit helper): every show/hide/schedule
        # lands here with cursor pos + zone reason — one log excerpt shows
        # the full causal chain for "panel hangs open" post-mortems.
        self._journal = DecisionJournal("magnifier-hover")
        self._wire()

    def _note(self, what: str, detail: str = "") -> None:
        try:
            pos = QCursor.pos()
            detail = f"{detail} cursor={pos.x()},{pos.y()}".strip()
        except Exception:
            pass
        self._journal.note(what, detail)

    def describe_state(self) -> dict:
        """Snapshot for diagnostics (UI inspector hook)."""
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        try:
            visible = bool(flyout.isVisible()) if flyout is not None else False
        except Exception:
            visible = False
        try:
            focus_name = type(QApplication.focusWidget()).__name__
        except Exception:
            focus_name = "?"
        timer = getattr(flyout, "_auto_hide", None)
        return {
            "visible": visible,
            "timer_active": bool(timer._timer.isActive()) if timer is not None else False,
            "focus": focus_name,
            "zone": self._combined_reason(),
            "journal": self._journal.snapshot(),
        }

    def _wire(self) -> None:
        widget = self.widget
        toolbar = getattr(widget, "checkbox_widget", None)
        group = getattr(widget, "magnifier_group_container", None)
        flyout = getattr(widget, "magnifier_settings_flyout", None)
        if toolbar is None or group is None or flyout is None:
            return
        toolbar.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        toolbar.installEventFilter(self)
        group.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        group.installEventFilter(self)
        flyout.installEventFilter(self)
        # The zone-based hover check (_cursor_in_group_zone) only reacts to
        # mouse position, so Tab/keyboard focus landing on a button inside
        # the group never opened this panel -- Qt delivers FocusIn/FocusOut
        # to the focused widget itself, not to ancestor containers via
        # installEventFilter, so each button needs its own filter (mirrors
        # MagnifierVisibilityController._wire_button in transient_magnifier.py).
        from sli_ui_toolkit.managers import NavigationManager

        nav = NavigationManager.get_instance()
        for child in group.findChildren(QWidget):
            if child.focusPolicy() != Qt.FocusPolicy.NoFocus:
                child.installEventFilter(self)
                self._group_buttons.add(child)
                # Один вызов фасада вместо link_below+side комбо. Top-кнопки
                # (btn_magnifier -> PanelVisibility, ColorSettingsButton ->
                # ColorOptions) тоже линкуем вниз: реестр per-side, above-линки
                # при этом не затираются — Up идёт в верхнюю панель, Down в нижнюю.
                from sli_ui_toolkit.managers import bind_flyout as _bind

                _bind(child, flyout, side="below")
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
        # btn_diff_mode / btn_channel_mode (view_group_container, adjacent
        # to the magnifier group's hover zone) each open a ModePicker
        # dropdown lazily, on first click -- unlike the color-options
        # flyouts above, there is no flyout instance yet at _wire() time to
        # link. Opening it while this panel is already showing (the cursor
        # crossed into the zone to reach the button already triggered it)
        # makes Qt recompute hover state against the new topmost popup,
        # firing a Leave on the toolbar that schedules this panel's hide --
        # with the dropdown unlinked, the cursor landing on it doesn't count
        # as "inside" and the panel closes out from under the still-open pick.
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
            "btn_divider_width",
            "btn_magnifier_divider_width",
            "btn_magnifier_guides",
            "btn_magnifier_guides_width",
        ):
            button = getattr(widget, attr, None)
            if button is not None and hasattr(button, "valueChanged"):
                button.valueChanged.connect(
                    lambda _value, b=button: self._link_scroll_value_flyout(b)
                )

    def eventFilter(self, watched, event) -> bool:
        widget = getattr(self, "widget", None)
        if widget is None:
            return False
        if watched in (
            getattr(widget, "checkbox_widget", None),
            getattr(widget, "magnifier_group_container", None),
        ):
            self._handle_hover_event(event)
        elif watched is getattr(widget, "magnifier_settings_flyout", None):
            self._handle_flyout_event(event)
        elif watched in self._group_buttons:
            self._handle_button_focus_event(event)
        return False

    def _handle_hover_event(self, event) -> None:
        et = event.type()
        if et in (
            QEvent.Type.HoverEnter,
            QEvent.Type.HoverMove,
            QEvent.Type.Enter,
        ):
            if self._cursor_in_group_zone():
                self._cancel_hide()
                flyout = getattr(self.widget, "magnifier_settings_flyout", None)
                if flyout is None or not flyout.isVisible():
                    self._hover_timer.stop()
                    self._show()
                else:
                    self._hover_timer.stop()
                    self._cancel_hide()
            else:
                self._hover_timer.stop()
                # Binary without timer for cursor as well (user request).
                # Here reason is flyout/linked ("group" is impossible — the
                # branch above already excluded the group zone): arm the
                # backstop, which hides once the cursor is truly outside
                # (a bare cancel would orphan the panel on travel through
                # unwatched surfaces: linked dropdown, native CSD).
                reason = self._combined_reason()
                if reason is None:
                    self._note("hover-move:outside", "")
                    self._hide_immediately()
                else:
                    self._note(f"hover-move:inside-{reason}", "")
                    self._schedule_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            self._hover_timer.stop()
            reason = self._combined_reason()
            if reason is None:
                self._note("leave:outside", "")
                self._hide_immediately()
            else:
                # Leave fires on widget exit but the sampled cursor may still
                # sit in the padding rim (no second Leave fires for the rim
                # itself): arm the backstop, which hides on real departure
                # and is canceled by jitter back in. A bare cancel would
                # orphan the panel on travel through unwatched space.
                self._note(f"leave:inside-{reason}", "")
                self._schedule_hide()

    def _handle_button_focus_event(self, event) -> None:
        et = event.type()
        if et == QEvent.Type.FocusIn:
            reason = getattr(event, "reason", lambda: None)()
            is_keyboard = reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            )
            if is_keyboard:
                self._cancel_hide()
                flyout = getattr(self.widget, "magnifier_settings_flyout", None)
                if flyout is None or not flyout.isVisible():
                    self._hover_timer.stop()
                    # Binary without timer for keyboard (user request)
                    self._show()
                else:
                    self._hover_timer.stop()
                    self._cancel_hide()
        elif et == QEvent.Type.FocusOut:
            self._hover_timer.stop()
            # Down from a group button can move focus straight into this
            # panel's own content (NavigationManager.extension_below /
            # BaseFlyout.focus_first_child) -- that's still "inside" the
            # combined group+panel unit, not a reason to auto-hide. Without
            # this check, the button's FocusOut alone would schedule a
            # hide that nothing then cancels (the mouse-hover Enter that
            # normally cancels it never fires for a keyboard-only move),
            # closing the panel out from under the focus that just entered it.
            # Also, if PanelVisibilityFlyout is open via keyboard (Enter) and
            # has focus, keep MagnifierSettingsFlyout open as well — they
            # are meant to coexist when magnifier is enabled via keyboard.
            new_focus = QApplication.focusWidget()
            flyout = getattr(self.widget, "magnifier_settings_flyout", None)
            panel_flyout = getattr(self.widget, "magnifier_visibility_flyout", None)
            if panel_flyout is not None and getattr(panel_flyout, "_keyboard_navigation_active", False):
                # Panel flyout open via keyboard — keep settings flyout open
                return
            # Top flyouts (PanelVisibility, ColorOptions) are part of the same
            # magnifier unit — entering them via Down should not hide the bottom
            # panel, otherwise the bottom would flicker when navigating to top.
            top_inside = False
            try:
                for attr in ("magnifier_visibility_flyout",):
                    tf = getattr(self.widget, attr, None)
                    if tf is not None and tf.isAncestorOf(new_focus):
                        top_inside = True
                        break
                for attr in ("btn_magnifier_color_settings", "btn_magnifier_color_settings_beginner"):
                    btn = getattr(self.widget, attr, None)
                    tf = getattr(btn, "flyout", None) if btn is not None else None
                    if tf is not None and tf.isAncestorOf(new_focus):
                        top_inside = True
                        break
            except Exception:
                pass
            still_inside = new_focus is not None and (
                new_focus in self._group_buttons
                or (flyout is not None and flyout.isAncestorOf(new_focus))
                or top_inside
            )
            if not still_inside:
                # Immediate hide when focus leaves group+flyout or ring disappears
                # (user request: "сразу как пропадает focus ring")
                try:
                    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

                    has_ring = any(
                        getattr(btn, "_keyboard_focus", False) and btn.hasFocus()
                        for btn in self._group_buttons
                    )
                    if not has_ring or not NavigationManager.get_instance().last_input_was_keyboard():
                        self._hide_immediately()
                        return
                except Exception:
                    pass
                self._hide_immediately()

    def _cursor_in_group_zone(self) -> bool:
        group = getattr(self.widget, "magnifier_group_container", None)
        if group is None:
            return False
        local = group.mapFromGlobal(QCursor.pos())
        zone = group.rect().adjusted(
            -_HOVER_ZONE_PADDING_PX,
            -_HOVER_ZONE_PADDING_PX,
            _HOVER_ZONE_PADDING_PX,
            _HOVER_ZONE_PADDING_PX,
        )
        return zone.contains(local)

    def _combined_reason(self) -> str | None:
        """Which part of the combined group+panel unit holds the cursor.

        Returns 'group' (padded hover zone), 'flyout' (panel body),
        'linked' (a FlyoutManager-linked sibling: dropdowns, color-options,
        scroll pills), or None (outside — safe to hide immediately).
        """
        if self._cursor_in_group_zone():
            return "group"
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is not None and flyout.isVisible():
            try:
                if flyout.contains_global(QCursor.pos()):
                    return "flyout"
            except Exception:
                pass
            # Linked siblings are part of the safe zone (see
            # _link_sibling_flyouts) but carry no event filter of their own:
            # leaving the cursor on one with no backstop timer pending
            # orphans the panel open — no later event ever closes it.
            try:
                from sli_ui_toolkit.managers import FlyoutManager

                manager = FlyoutManager.get_instance()
                for child in manager.linked_children(flyout):
                    try:
                        contains_global = getattr(child, "contains_global", None)
                        if child.isVisible() and contains_global and contains_global(QCursor.pos()):
                            return "linked"
                    except Exception:
                        continue
            except Exception:
                pass
        return None

    def _is_cursor_in_combined_zone(self) -> bool:
        return self._combined_reason() is not None

    def _hide_immediately(self) -> None:
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is not None and flyout.isVisible():
            self._note("hide:immediate", "")
            flyout.hide()

    def _handle_flyout_event(self, event) -> None:
        et = event.type()
        if et in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            self._cancel_hide()
        elif et in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            if not self._is_cursor_in_combined_zone():
                self._hide_immediately()
            else:
                self._schedule_hide()

    def _show(self) -> None:
        widget = self.widget
        flyout = getattr(widget, "magnifier_settings_flyout", None)
        group = getattr(widget, "magnifier_group_container", None)
        if flyout is None or group is None:
            return
        self._link_sibling_flyouts(flyout)
        self._refresh_slider_labels()
        # show_for_group() opens with grab_focus=False (see its own
        # comment): keyboard focus deliberately stays wherever it already
        # is -- on a group toolbar button, or nowhere in particular for a
        # mouse-hover open -- instead of being stolen onto the panel's own
        # first slider, so arrow-key/Tab navigation across the whole group
        # keeps working while this panel is open.
        flyout.show_for_group(group)
        flyout.cancel_auto_hide()
        self._note("show", "")

    def _refresh_slider_labels(self) -> None:
        # The three sliders' real values get applied via signal-blocked
        # ("quiet") setters when syncing from store state, specifically to
        # avoid firing valueChanged back into the store -- but that also
        # means ValueSliderRow's own value label, which only updates
        # reactively off that same signal, never catches up and is stuck
        # showing whatever the slider's value was at construction time
        # (its un-initialized default, i.e. "0"). Force each row to
        # re-read the slider's actual current value right before this
        # panel becomes visible.
        widget = self.widget
        for attr in ("value_row_slider_size", "value_row_slider_capture", "value_row_slider_speed"):
            row = getattr(widget, attr, None)
            if row is not None:
                row.refresh()

    def _link_sibling_flyouts(self, flyout) -> None:
        """Make every other toolbar flyout part of this panel's family.

        ``AnchoredFlyoutAutoHide`` (see this panel's own auto-hide, wired in
        ``magnifier_settings_flyout.py``) treats a linked child's own body as
        "still inside" this panel's safe zone -- without linking, hovering
        from the magnifier group onto e.g. the font-settings flyout (opened
        by its own button) reads as "cursor left the panel", and this panel
        auto-hides right out from under whatever the user is actually doing
        in that other flyout.
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
            try:
                focus_name = type(QApplication.focusWidget()).__name__
            except Exception:
                focus_name = "?"
            self._note("hide:schedule-backstop", f"focus={focus_name}")
            flyout.schedule_auto_hide(AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS)

    def _cancel_hide(self) -> None:
        flyout = getattr(self.widget, "magnifier_settings_flyout", None)
        if flyout is None:
            return
        # Journal (and flag-gated log) only when something was actually
        # pending — HoverMove storms would otherwise flood both.
        timer = getattr(flyout, "_auto_hide", None)
        if timer is None or bool(timer._timer.isActive()):
            self._note("hide:cancel", "")
        flyout.cancel_auto_hide()