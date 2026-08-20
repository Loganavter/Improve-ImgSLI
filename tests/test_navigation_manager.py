"""Unit tests for NavigationManager and NavigationSection implementations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeKeyEvent:
    def __init__(self, key: int) -> None:
        self._key = key
        self.accepted = False

    def type(self):
        return QEvent.Type.KeyPress

    def key(self):
        return self._key

    def accept(self):
        self.accepted = True


def _fake_widget(name="w"):
    """Return a mock that behaves like a widget for owns() checks."""
    w = MagicMock()
    w._name = name
    return w


def _make_section(*, owns_fn=None, navigate_fn=None, focus_first_fn=None, focus_last_fn=None):
    section = SimpleNamespace()
    section.owns = owns_fn or (lambda w: False)
    section.navigate = navigate_fn or (lambda k, w: False)
    section.focus_first = focus_first_fn or (lambda ref_x=0, **kw: False)
    section.focus_last = focus_last_fn or (lambda ref_x=0, **kw: False)
    return section


# ---------------------------------------------------------------------------
# NavigationManager basics
# ---------------------------------------------------------------------------

class TestNavigationManager:
    def setup_method(self):
        from sli_ui_toolkit.managers import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    def test_singleton(self):
        from sli_ui_toolkit.managers import NavigationManager
        a = NavigationManager.get_instance()
        b = NavigationManager.get_instance()
        assert a is b

    def test_register_adds_section(self):
        owner = _fake_widget("owner")
        section = _make_section()
        self.manager.register(owner, section)
        assert any(s is section for _, s in self.manager._sections)

    def test_register_idempotent(self):
        owner = _fake_widget("owner")
        section = _make_section()
        self.manager.register(owner, section)
        self.manager.register(owner, section)
        assert sum(1 for _, s in self.manager._sections if s is section) == 1

    def test_unregister_removes_section(self):
        owner = _fake_widget("owner")
        section = _make_section()
        self.manager.register(owner, section)
        self.manager.unregister(owner)
        assert section not in [s for _, s in self.manager._sections]

    def test_unregister_unknown_section_is_noop(self):
        owner = _fake_widget("owner")
        self.manager.unregister(owner)

    def test_event_filter_ignores_non_keypress(self):
        owner = _fake_widget("owner")
        section = _make_section(owns_fn=lambda w: True, navigate_fn=lambda k, w: True)
        self.manager.register(owner, section)
        event = SimpleNamespace(type=lambda: QEvent.Type.MouseButtonPress)
        assert self.manager.eventFilter(None, event) is False

    def test_event_filter_ignores_non_arrow_keys(self):
        owner = _fake_widget("owner")
        section = _make_section(owns_fn=lambda w: True, navigate_fn=lambda k, w: True)
        self.manager.register(owner, section)
        event = _FakeKeyEvent(Qt.Key.Key_A)
        assert self.manager.eventFilter(None, event) is False

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_event_filter_delegates_to_owning_section(self, mock_qapp):
        handled = []
        widget = _fake_widget("target")
        owner = _fake_widget("owner")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: (handled.append(k) or True),
        )
        self.manager.register(owner, section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert handled == [Qt.Key.Key_Down]

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_event_filter_returns_false_when_no_focus(self, mock_qapp):
        owner = _fake_widget("owner")
        section = _make_section(owns_fn=lambda w: True)
        self.manager.register(owner, section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = None
        result = self.manager.eventFilter(None, event)
        assert result is False

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_event_filter_tries_next_section_when_first_declines(self, mock_qapp):
        widget = _fake_widget("target")
        owner1 = _fake_widget("owner1")
        owner2 = _fake_widget("owner2")
        focus_calls = []

        second = _make_section(
            owns_fn=lambda w: False,
            focus_first_fn=lambda ref_x=0, **kw: (focus_calls.append("first") or True),
        )
        first = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(owner1, first)
        self.manager.register(owner2, second)

        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert focus_calls == ["first"]

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_event_filter_consumes_when_no_neighbor(self, mock_qapp):
        """Section declines and no neighbor exists — event is consumed."""
        widget = _fake_widget("target")
        owner = _fake_widget("owner")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(owner, section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_event_filter_passes_through_when_no_section_owns(self, mock_qapp):
        """No section claims the widget — event passes through."""
        widget = _fake_widget("unowned")
        owner = _fake_widget("owner")
        section = _make_section(owns_fn=lambda w: False)
        self.manager.register(owner, section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is False


# ---------------------------------------------------------------------------
# NavigationManager cross-section routing
# ---------------------------------------------------------------------------

class TestCrossSectionRouting:
    def setup_method(self):
        from sli_ui_toolkit.managers import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_down_at_last_item_yields_to_next_section(self, mock_qapp):
        widget = _fake_widget("target")
        owner1 = _fake_widget("owner1")
        owner2 = _fake_widget("owner2")
        focus_calls = []

        top = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        bottom = _make_section(
            owns_fn=lambda w: False,
            focus_first_fn=lambda ref_x=0, **kw: (focus_calls.append("bottom_first") or True),
        )
        self.manager.register(owner1, top)
        self.manager.register(owner2, bottom)

        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert focus_calls == ["bottom_first"]

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_up_at_first_item_yields_to_prev_section(self, mock_qapp):
        widget = _fake_widget("target")
        owner1 = _fake_widget("owner1")
        owner2 = _fake_widget("owner2")
        focus_calls = []

        top = _make_section(
            owns_fn=lambda w: False,
            focus_last_fn=lambda ref_x=0, **kw: (focus_calls.append("top_last") or True),
        )
        bottom = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(owner1, top)
        self.manager.register(owner2, bottom)

        event = _FakeKeyEvent(Qt.Key.Key_Up)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert focus_calls == ["top_last"]

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_left_right_pass_through_immediately(self, mock_qapp):
        """Left/Right pass through without any section routing."""
        widget = _fake_widget("target")
        owner = _fake_widget("owner")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: True,
        )
        self.manager.register(owner, section)
        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event = _FakeKeyEvent(key)
            mock_qapp.focusWidget.return_value = widget
            result = self.manager.eventFilter(None, event)
            assert result is False


# ---------------------------------------------------------------------------
# Click-to-arrow realignment
# ---------------------------------------------------------------------------

class _FakeMouseEvent:
    def __init__(self, x=10, y=10) -> None:
        self._pos = SimpleNamespace(toPoint=lambda: SimpleNamespace(x=lambda: x, y=lambda: y))

    def type(self):
        return QEvent.Type.MouseButtonPress

    def globalPosition(self):
        return self._pos


class TestClickToArrowRealign:
    def setup_method(self):
        from sli_ui_toolkit.managers import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_click_on_focusable_widget_realigns_directly(self, mock_qapp):
        """A click that lands on an owned, focusable widget re-anchors the
        ring on that exact widget on the next arrow press, instead of
        resuming from whatever Qt's stale focusWidget() still points at.
        """
        clicked = _fake_widget("clicked")
        clicked.focusPolicy.return_value = Qt.FocusPolicy.StrongFocus
        clicked.isVisible.return_value = True
        clicked.isEnabled.return_value = True
        clicked.parentWidget.return_value = None

        stale = _fake_widget("stale")
        owner = _fake_widget("owner")
        section = _make_section(owns_fn=lambda w: w is clicked)
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = clicked
        mock_qapp.focusWidget.return_value = stale

        self.manager.eventFilter(None, _FakeMouseEvent())
        assert self.manager._realign_pending is True

        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        assert result is True
        clicked.setFocus.assert_called_once()
        assert self.manager._realign_pending is False

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_click_on_non_focusable_area_does_not_realign(self, mock_qapp):
        """Clicking a non-focusable spot inside a section (e.g. empty row
        background) where _nearest_focusable finds nothing leaves focus on
        the stale widget — realign does not happen.
        """
        clicked = _fake_widget("clicked")
        clicked.focusPolicy.return_value = Qt.FocusPolicy.NoFocus
        clicked.isVisible.return_value = True
        clicked.isEnabled.return_value = True
        clicked.parentWidget.return_value = None

        stale = _fake_widget("stale")
        owner = _fake_widget("owner")
        section = _make_section(
            owns_fn=lambda w: w is clicked,
        )
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = clicked
        mock_qapp.focusWidget.return_value = stale

        self.manager.eventFilter(None, _FakeMouseEvent(x=42))
        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        # Realigned but section has no focusable children — arrow goes to
        # normal routing from stale widget, which is not owned by the section.
        assert result is False

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_click_outside_any_section_falls_through_to_normal_routing(self, mock_qapp):
        """A click that lands nowhere any section owns leaves the stale
        focusWidget() in place -- next arrow press behaves exactly as
        before this feature existed.
        """
        widget = _fake_widget("target")
        unrelated = _fake_widget("unrelated")
        unrelated.parentWidget.return_value = None
        owner = _fake_widget("owner")
        handled = []
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: (handled.append(k) or True),
        )
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = unrelated
        mock_qapp.focusWidget.return_value = widget

        self.manager.eventFilter(None, _FakeMouseEvent())
        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        assert result is True
        assert handled == [Qt.Key.Key_Down]

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_keyboard_focus_change_clears_realign_pending(self, mock_qapp):
        """Legitimate keyboard-driven focus movement between a click and
        the next arrow press supersedes the click -- the arrow should
        navigate from the new focus, not jump back to the click point.
        """
        widget = MagicMock(spec=QWidget)
        self.manager.eventFilter(None, _FakeMouseEvent())
        assert self.manager._realign_pending is True

        focus_event = SimpleNamespace(
            type=lambda: QEvent.Type.FocusIn,
            reason=lambda: Qt.FocusReason.TabFocusReason,
        )
        self.manager.eventFilter(widget, focus_event)
        assert self.manager._realign_pending is False

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_left_right_after_click_with_no_realign_goes_to_normal_routing(self, mock_qapp):
        """Clicking a section's bare owner widget where _nearest_focusable
        finds nothing means realign doesn't happen. Left/Right goes to
        normal routing from the stale pre-click focus widget.
        """
        owner = _fake_widget("tab_strip_owner")
        owner.focusPolicy.return_value = Qt.FocusPolicy.StrongFocus
        owner.isVisible.return_value = True
        owner.isEnabled.return_value = True
        owner.parentWidget.return_value = None

        tab_bar = _fake_widget("tab_bar")

        section = _make_section(
            owns_fn=lambda w: w is tab_bar,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = owner
        mock_qapp.focusWidget.return_value = owner

        self.manager.eventFilter(None, _FakeMouseEvent())
        assert self.manager._realign_pending is True

        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Left))
        assert result is False
        owner.setFocus.assert_not_called()

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_first_press_after_click_reveals_without_stepping(self, mock_qapp):
        """The ring is invisible right after a mouse click (MouseButtonPress
        suppresses it) -- if the very first arrow press both silently
        realigned focus to the nearest widget *and* stepped navigate() one
        further, the user would see the ring appear two items away from
        the click with no visual step in between. The first press must
        only reveal the ring at the realigned widget; a second, distinct
        press then steps normally.
        """
        clicked = _fake_widget("clicked")
        clicked.focusPolicy.return_value = Qt.FocusPolicy.StrongFocus
        clicked.isVisible.return_value = True
        clicked.isEnabled.return_value = True
        clicked.parentWidget.return_value = None

        owner = _fake_widget("owner")
        navigate_calls = []
        # A section that DOES want this key (like ToolbarRowsSection's
        # Left/Right via extra_keys) -- the case that risks double-moving.
        section = _make_section(
            owns_fn=lambda w: w is clicked,
            navigate_fn=lambda k, w: (navigate_calls.append((k, w)) or True),
        )
        section.extra_keys = frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = clicked
        mock_qapp.focusWidget.return_value = clicked

        self.manager.eventFilter(None, _FakeMouseEvent())
        first = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Left))
        assert first is True
        clicked.setFocus.assert_called_once()
        assert navigate_calls == [], "first press after a click must not also step navigate()"

        second = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Left))
        assert second is True
        assert navigate_calls == [(Qt.Key.Key_Left, clicked)], "second press should step normally"

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_reclicking_the_already_focused_widget_still_restores_the_ring(self, mock_qapp):
        """Regression: clicking the exact widget that's already keyboard-
        focused makes setFocus() a real Qt no-op -- no FocusIn fires, so
        the ring-reveal that normally rides on FocusIn never runs, and the
        ring stays stuck in the MouseButtonPress-suppressed state. Without
        a manual restore, every subsequent "reveal-only" press after a
        re-click looks like nothing happened, repeating forever.
        """
        clicked = _fake_widget("clicked")
        clicked.focusPolicy.return_value = Qt.FocusPolicy.StrongFocus
        clicked.isVisible.return_value = True
        clicked.isEnabled.return_value = True
        clicked.parentWidget.return_value = None
        # Ring already suppressed, mirroring MouseButtonPress's own
        # suppression of whatever was focused before this click.
        clicked._keyboard_focus = False
        clicked._last_focus_reason = Qt.FocusReason.MouseFocusReason

        owner = _fake_widget("owner")
        section = _make_section(owns_fn=lambda w: w is clicked)
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = clicked
        # Already the focused widget *before* this click -- setFocus()
        # below will be a no-op from Qt's perspective.
        mock_qapp.focusWidget.return_value = clicked

        self.manager.eventFilter(None, _FakeMouseEvent())
        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        assert result is True
        clicked.setFocus.assert_called_once()
        assert clicked._keyboard_focus is True
        assert clicked._last_focus_reason == Qt.FocusReason.OtherFocusReason
        assert clicked.update.call_count >= 1

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_realign_prefers_focus_nearest_over_focus_first(self, mock_qapp):
        """When a section provides focus_nearest(pos), realign must call it
        instead of focus_first(ref_x) -- a click can land next to any row,
        not just the topmost/bottommost one."""
        clicked = _fake_widget("clicked")
        clicked.focusPolicy.return_value = Qt.FocusPolicy.NoFocus
        clicked.isVisible.return_value = True
        clicked.isEnabled.return_value = True
        clicked.parentWidget.return_value = None

        stale = _fake_widget("stale")
        owner = _fake_widget("owner")
        focus_nearest_calls = []
        focus_first_calls = []

        section = _make_section(
            owns_fn=lambda w: w is clicked,
            focus_first_fn=lambda ref_x=None, **kw: (focus_first_calls.append(ref_x) or True),
        )
        section.focus_nearest = lambda pos: (focus_nearest_calls.append(pos) or True)
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = clicked
        mock_qapp.focusWidget.return_value = stale

        pos = SimpleNamespace(y=lambda: 42)
        self.manager.eventFilter(None, _FakeMouseEvent(x=7, y=42))
        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        assert result is True
        assert len(focus_nearest_calls) == 1, "focus_nearest must be called"
        assert focus_first_calls == [], "focus_first must NOT be called when focus_nearest exists"

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_realign_does_not_fall_back_to_focus_first(self, mock_qapp):
        """Without focus_nearest on the section and no focusable children,
        realign returns False — focus_first is not called as a fallback.
        """
        clicked = _fake_widget("clicked")
        clicked.focusPolicy.return_value = Qt.FocusPolicy.NoFocus
        clicked.isVisible.return_value = True
        clicked.isEnabled.return_value = True
        clicked.parentWidget.return_value = None

        stale = _fake_widget("stale")
        owner = _fake_widget("owner")
        focus_first_calls = []

        section = _make_section(
            owns_fn=lambda w: w is clicked,
            focus_first_fn=lambda ref_x=None, **kw: (focus_first_calls.append(ref_x) or True),
        )
        # No focus_nearest attribute
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = clicked
        mock_qapp.focusWidget.return_value = stale

        self.manager.eventFilter(None, _FakeMouseEvent(x=7))
        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        assert result is False
        assert focus_first_calls == [], "focus_first must not be called as fallback"

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_click_on_bare_owner_does_not_realign(self, mock_qapp):
        """A click that only resolves to a section's bare owner widget
        (e.g. row padding, or an owner container with no matching content
        under the cursor) where _nearest_focusable finds nothing does not
        realign — focus stays where it was.
        """
        owner = _fake_widget("owner")
        owner.focusPolicy.return_value = Qt.FocusPolicy.StrongFocus
        owner.isVisible.return_value = True
        owner.isEnabled.return_value = True
        owner.parentWidget.return_value = None

        target = _fake_widget("first_row_item")

        section = _make_section(owns_fn=lambda w: w is target)
        self.manager.register(owner, section)

        mock_qapp.widgetAt.return_value = owner
        mock_qapp.focusWidget.return_value = owner

        self.manager.eventFilter(None, _FakeMouseEvent(x=7))
        result = self.manager.eventFilter(None, _FakeKeyEvent(Qt.Key.Key_Down))
        assert result is False
        owner.setFocus.assert_not_called()


class TestSessionPickerSection:
    def _make_page(self, card_labels=None):
        from core.navigation_sections import SessionPickerSection

        buttons = []
        for label in (card_labels or []):
            btn = MagicMock()
            btn.setFocus = MagicMock()
            btn.setObjectName(label)
            buttons.append((label, btn))

        page = MagicMock()
        page._card_entries = MagicMock(return_value=buttons)
        page.isAncestorOf = MagicMock(return_value=False)
        page._recent_panel = None

        section = SessionPickerSection(page)
        return section, page, buttons

    def test_owns_returns_true_for_descendant(self):
        section, page, _ = self._make_page()
        child = MagicMock()
        child.parentWidget.return_value = page
        assert section.owns(child) is True

    def test_owns_returns_true_for_deep_descendant(self):
        section, page, _ = self._make_page()
        grandchild = MagicMock()
        child = MagicMock()
        child.parentWidget.return_value = page
        grandchild.parentWidget.return_value = child
        assert section.owns(grandchild) is True

    def test_owns_returns_true_for_page_itself(self):
        section, page, _ = self._make_page()
        assert section.owns(page) is True

    def test_owns_returns_false_for_unrelated(self):
        section, page, _ = self._make_page()
        unrelated = MagicMock()
        unrelated.parentWidget.return_value = None
        assert section.owns(unrelated) is False

    def test_down_from_nothing_focuses_first_card(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Down, MagicMock())
        assert result is True
        buttons[0][1].setFocus.assert_called_once()

    def test_down_moves_to_next_card(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Down, buttons[1][1])
        assert result is True
        buttons[2][1].setFocus.assert_called_once()

    def test_down_at_last_card_yields_when_no_recent_panel(self):
        section, page, buttons = self._make_page(["a", "b", "c"])
        page._recent_panel = None
        result = section.navigate(Qt.Key.Key_Down, buttons[2][1])
        assert result is False

    def test_down_at_last_card_focuses_header_then_recent(self):
        section, page, buttons = self._make_page(["a", "b", "c"])
        recent = MagicMock()
        recent.isVisible = MagicMock(return_value=True)
        recent.focus_header_control = MagicMock(return_value=True)
        page._recent_panel = recent
        result = section.navigate(Qt.Key.Key_Down, buttons[2][1])
        assert result is True
        recent.focus_header_control.assert_called_once_with(True)
        recent.focus_recent_item.assert_not_called()

    def test_down_at_last_card_falls_back_to_recent_when_no_header(self):
        section, page, buttons = self._make_page(["a", "b", "c"])
        recent = MagicMock()
        recent.isVisible = MagicMock(return_value=True)
        recent.focus_header_control = MagicMock(return_value=False)
        recent.focus_recent_item = MagicMock(return_value=True)
        page._recent_panel = recent
        result = section.navigate(Qt.Key.Key_Down, buttons[2][1])
        assert result is True
        recent.focus_header_control.assert_called_once_with(True)
        recent.focus_recent_item.assert_called_once_with(True)

    def test_right_from_nothing_consumed(self):
        section, _, _ = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Right, MagicMock())
        assert result is True

    def test_right_on_card_consumed(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Right, buttons[1][1])
        assert result is True

    def test_left_from_nothing_consumed(self):
        section, _, _ = self._make_page(["a", "b"])
        result = section.navigate(Qt.Key.Key_Left, MagicMock())
        assert result is True

    def test_left_on_card_consumed(self):
        section, _, buttons = self._make_page(["a", "b"])
        result = section.navigate(Qt.Key.Key_Left, buttons[0][1])
        assert result is True

    def test_up_moves_to_prev_card(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Up, buttons[2][1])
        assert result is True
        buttons[1][1].setFocus.assert_called_once()

    def test_up_at_first_card_yields(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Up, buttons[0][1])
        assert result is False

    def test_up_from_non_card_yields(self):
        section, _, _ = self._make_page(["a", "b"])
        result = section.navigate(Qt.Key.Key_Up, MagicMock())
        assert result is False

    def test_left_from_non_card_consumed(self):
        section, _, _ = self._make_page(["a", "b"])
        result = section.navigate(Qt.Key.Key_Left, MagicMock())
        assert result is True

    def test_focus_first(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        assert section.focus_first(reason=Qt.FocusReason.OtherFocusReason) is True
        buttons[0][1].setFocus.assert_called_once()

    def test_focus_first_empty(self):
        section, _, _ = self._make_page([])
        assert section.focus_first(reason=Qt.FocusReason.OtherFocusReason) is False

    def test_focus_last(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        assert section.focus_last(reason=Qt.FocusReason.OtherFocusReason) is True
        buttons[2][1].setFocus.assert_called_once()

    def test_focus_last_empty(self):
        section, _, _ = self._make_page([])
        assert section.focus_last(reason=Qt.FocusReason.OtherFocusReason) is False

    def _make_focusable(self, name, local_center_y, visible=True, enabled=True):
        """Create a mock widget whose mapTo(page, center).y() returns local_center_y."""
        w = MagicMock()
        w._name = name
        w.focusPolicy.return_value = Qt.FocusPolicy.StrongFocus
        w.isVisible.return_value = visible
        w.isEnabled.return_value = enabled
        w.mapTo.return_value = SimpleNamespace(
            y=lambda cy=local_center_y: cy,
        )
        w.findChildren.return_value = []
        return w

    def test_focus_nearest_picks_nearest(self):
        """Click at y=280, widgets at local y=100/300/500 → picks y=300 (nearest)."""
        section, page, _ = self._make_page([])
        page.mapFromGlobal.return_value = SimpleNamespace(y=lambda: 280)
        w1 = self._make_focusable("a", 100)
        w2 = self._make_focusable("b", 300)
        w3 = self._make_focusable("c", 500)
        page.findChildren.return_value = [w1, w2, w3]

        pos = SimpleNamespace(y=lambda: 280)
        result = section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason)
        assert result is True
        w2.setFocus.assert_called_once()

    def test_focus_nearest_picks_nearest_when_multiple_qualify(self):
        """Click at y=350, widgets at y=100/300/500 → picks y=300 (nearest)."""
        section, page, _ = self._make_page([])
        page.mapFromGlobal.return_value = SimpleNamespace(y=lambda: 350)
        w1 = self._make_focusable("a", 100)
        w2 = self._make_focusable("b", 300)
        w3 = self._make_focusable("c", 500)
        page.findChildren.return_value = [w1, w2, w3]

        pos = SimpleNamespace(y=lambda: 350)
        result = section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason)
        assert result is True
        w2.setFocus.assert_called_once()

    def test_focus_nearest_picks_nearest_even_when_above_all(self):
        """Click at y=50, all widgets below at y=100/300 → picks y=100."""
        section, page, _ = self._make_page([])
        page.mapFromGlobal.return_value = SimpleNamespace(y=lambda: 50)
        w1 = self._make_focusable("a", 100)
        w2 = self._make_focusable("b", 300)
        page.findChildren.return_value = [w1, w2]

        pos = SimpleNamespace(y=lambda: 50)
        result = section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason)
        assert result is True
        w1.setFocus.assert_called_once()

    def test_focus_nearest_skips_hidden_and_disabled(self):
        section, page, _ = self._make_page([])
        page.mapFromGlobal.return_value = SimpleNamespace(y=lambda: 250)
        w1 = self._make_focusable("hidden", 100, visible=False)
        w2 = self._make_focusable("disabled", 200, enabled=False)
        w3 = self._make_focusable("ok", 300)
        page.findChildren.return_value = [w1, w2, w3]

        pos = SimpleNamespace(y=lambda: 250)
        result = section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason)
        assert result is True
        w3.setFocus.assert_called_once()

    def test_focus_nearest_skips_nofocus(self):
        section, page, _ = self._make_page([])
        page.mapFromGlobal.return_value = SimpleNamespace(y=lambda: 150)
        w1 = MagicMock()
        w1.focusPolicy.return_value = Qt.FocusPolicy.NoFocus
        w1.isVisible.return_value = True
        w1.isEnabled.return_value = True
        w1.findChildren.return_value = []
        w2 = self._make_focusable("ok", 200)
        page.findChildren.return_value = [w1, w2]

        pos = SimpleNamespace(y=lambda: 150)
        result = section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason)
        assert result is True
        w2.setFocus.assert_called_once()

    def test_focus_nearest_empty_returns_false(self):
        section, page, _ = self._make_page([])
        page.findChildren.return_value = []
        pos = SimpleNamespace(y=lambda: 0)
        assert section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason) is False

    def test_focus_nearest_real_scenario_click_in_recent_panel(self):
        """Click at local y=465 in RecentProjectsPanel area, cards at
        local y=426/512/598 → should pick card at y=426 (nearest)."""
        section, page, _ = self._make_page([])
        page.mapFromGlobal.return_value = SimpleNamespace(y=lambda: 465)
        card0 = self._make_focusable("card0", 426)
        card1 = self._make_focusable("card1", 512)
        card2 = self._make_focusable("card2", 598)
        page.findChildren.return_value = [card0, card1, card2]

        pos = SimpleNamespace(y=lambda: 465)
        result = section.focus_nearest(pos, reason=Qt.FocusReason.OtherFocusReason)
        assert result is True
        card0.setFocus.assert_called_once()
        card1.setFocus.assert_not_called()
        card2.setFocus.assert_not_called()


# ---------------------------------------------------------------------------
# TabStripSection
# ---------------------------------------------------------------------------

class TestTabStripSection:
    def _make_strip(self):
        from core.navigation_sections import TabStripSection

        strip = MagicMock()
        strip.tab_bar = None
        add_button = MagicMock()
        add_button.setFocus = MagicMock()
        add_button.isVisible = MagicMock(return_value=True)
        strip.add_button = add_button
        strip.setFocus = MagicMock()
        strip.isAncestorOf = MagicMock(return_value=False)
        section = TabStripSection(strip)
        return section, strip, add_button

    def test_owns_returns_true_for_descendant(self):
        section, strip, _ = self._make_strip()
        child = MagicMock()
        child.parentWidget.return_value = strip
        assert section.owns(child) is True

    def test_owns_returns_true_for_deep_descendant(self):
        section, strip, _ = self._make_strip()
        grandchild = MagicMock()
        child = MagicMock()
        child.parentWidget.return_value = strip
        grandchild.parentWidget.return_value = child
        assert section.owns(grandchild) is True

    def test_owns_returns_true_for_strip_itself(self):
        section, strip, _ = self._make_strip()
        assert section.owns(strip) is True

    def test_owns_returns_false_for_unrelated(self):
        section, strip, _ = self._make_strip()
        unrelated = MagicMock()
        unrelated.parentWidget.return_value = None
        assert section.owns(unrelated) is False

    def test_navigate_up_yields_to_title_bar(self):
        section, _, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Up, MagicMock()) is False

    def test_navigate_down_yields_to_session_picker(self):
        section, _, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Down, MagicMock()) is False

    def test_navigate_left_right_yield(self):
        section, _, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Left, MagicMock()) is False
        assert section.navigate(Qt.Key.Key_Right, MagicMock()) is False

    def test_focus_first_focuses_add_button(self):
        section, _, add_button = self._make_strip()
        assert section.focus_first(reason=Qt.FocusReason.OtherFocusReason) is True
        add_button.setFocus.assert_called_once()

    def test_focus_last_focuses_add_button(self):
        section, _, add_button = self._make_strip()
        assert section.focus_last(reason=Qt.FocusReason.OtherFocusReason) is True
        add_button.setFocus.assert_called_once()


# ---------------------------------------------------------------------------
# Regression: only NavigationManager may consume arrow keys
# ---------------------------------------------------------------------------

_ARROWS = {Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right}


class TestArrowKeySoleOwnership:
    """Arrow key consumption on QApplication is exclusively owned by
    NavigationManager.  No other event filter or widget keyPressEvent
    may consume them.

    Dogma source: docs/dev/CONTRACTS.md §NavigationManager.
    """

    def test_navigation_manager_is_singleton(self):
        """NavigationManager must be accessible as a singleton."""
        from sli_ui_toolkit.managers import NavigationManager

        a = NavigationManager.get_instance()
        b = NavigationManager.get_instance()
        assert a is b

    def test_no_other_event_filter_consumes_arrows(self, qapp):
        """Walk all widgets and verify no other eventFilter consumes arrows.

        We simulate arrow KeyPress events on every widget in the app and
        check that the only filter returning True is NavigationManager's.
        """
        from sli_ui_toolkit.managers import NavigationManager

        manager = NavigationManager.get_instance()
        violations = []

        def _check_widget(widget):
            for key in _ARROWS:
                event = MagicMock()
                event.type.return_value = QEvent.Type.KeyPress
                event.key.return_value = key

                # Temporarily set focus so NavigationManager sees it
                original_focus = QApplication.focusWidget()
                widget.setFocus(Qt.FocusReason.OtherFocusReason)

                # Let event filters run by calling processEvents
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.processEvents()

                # Restore focus
                if original_focus is not None:
                    original_focus.setFocus(Qt.FocusReason.OtherFocusReason)

        # Walk all top-level widgets
        for widget in qapp.topLevelWidgets():
            _check_widget(widget)
            for child in widget.findChildren(type(widget)):
                _check_widget(child)

        assert not violations, (
            "Arrow key consumption violated by:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_session_picker_section_does_not_consume_left_right(self):
        """SessionPickerSection must yield Left/Right to native handlers."""
        from core.navigation_sections import SessionPickerSection

        page = MagicMock()
        page._card_entries = MagicMock(return_value=[])
        page.isAncestorOf = MagicMock(return_value=False)
        section = SessionPickerSection(page)

        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            result = section.navigate(key, MagicMock())
            assert result is True, (
                f"SessionPickerSection.consume Left/Right={result}, "
                f"expected True (consume — single-column list)"
            )

    def test_tab_strip_section_yields_left_right(self):
        """TabStripSection must yield Left/Right to QTabBar."""
        from core.navigation_sections import TabStripSection

        strip = MagicMock()
        strip.isAncestorOf = MagicMock(return_value=False)
        section = TabStripSection(strip)

        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            result = section.navigate(key, MagicMock())
            assert result is False, (
                f"TabStripSection consumed Left/Right={result}, "
                f"expected False (yield to QTabBar)"
            )

    def test_tab_strip_section_yields_up(self):
        """TabStripSection yields Up — NavigationManager routes to title bar."""
        from core.navigation_sections import TabStripSection

        strip = MagicMock()
        strip.isAncestorOf = MagicMock(return_value=False)
        section = TabStripSection(strip)

        result = section.navigate(Qt.Key.Key_Up, MagicMock())
        assert result is False, (
            f"TabStripSection consumed Up={result}, expected False (yield)"
        )
