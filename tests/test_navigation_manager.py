"""Unit tests for NavigationManager and NavigationSection implementations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from PySide6.QtCore import QEvent, Qt


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
    section.focus_first = focus_first_fn or (lambda: False)
    section.focus_last = focus_last_fn or (lambda: False)
    return section


# ---------------------------------------------------------------------------
# NavigationManager basics
# ---------------------------------------------------------------------------

class TestNavigationManager:
    def setup_method(self):
        from core.navigation import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    def test_singleton(self):
        from core.navigation import NavigationManager
        a = NavigationManager.get_instance()
        b = NavigationManager.get_instance()
        assert a is b

    def test_register_adds_section(self):
        section = _make_section()
        self.manager.register(section)
        assert section in self.manager._sections

    def test_register_idempotent(self):
        section = _make_section()
        self.manager.register(section)
        self.manager.register(section)
        assert self.manager._sections.count(section) == 1

    def test_unregister_removes_section(self):
        section = _make_section()
        self.manager.register(section)
        self.manager.unregister(section)
        assert section not in self.manager._sections

    def test_unregister_unknown_section_is_noop(self):
        section = _make_section()
        self.manager.unregister(section)

    def test_event_filter_ignores_non_keypress(self):
        section = _make_section(owns_fn=lambda w: True, navigate_fn=lambda k, w: True)
        self.manager.register(section)
        event = SimpleNamespace(type=lambda: QEvent.Type.MouseButtonPress)
        assert self.manager.eventFilter(None, event) is False

    def test_event_filter_ignores_non_arrow_keys(self):
        section = _make_section(owns_fn=lambda w: True, navigate_fn=lambda k, w: True)
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_A)
        assert self.manager.eventFilter(None, event) is False

    @patch("core.navigation.QApplication")
    def test_event_filter_delegates_to_owning_section(self, mock_qapp):
        handled = []
        widget = _fake_widget("target")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: (handled.append(k) or True),
        )
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert handled == [Qt.Key.Key_Down]

    @patch("core.navigation.QApplication")
    def test_event_filter_returns_false_when_no_focus(self, mock_qapp):
        section = _make_section(owns_fn=lambda w: True)
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = None
        result = self.manager.eventFilter(None, event)
        assert result is False

    @patch("core.navigation.QApplication")
    def test_event_filter_tries_next_section_when_first_declines(self, mock_qapp):
        widget = _fake_widget("target")
        focus_calls = []

        second = _make_section(
            owns_fn=lambda w: False,
            focus_first_fn=lambda: (focus_calls.append("first") or True),
        )
        first = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(first)
        self.manager.register(second)

        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert focus_calls == ["first"]

    @patch("core.navigation.QApplication")
    def test_event_filter_consumes_when_no_neighbor(self, mock_qapp):
        """Section declines and no neighbor exists — event is consumed."""
        widget = _fake_widget("target")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True

    @patch("core.navigation.QApplication")
    def test_event_filter_passes_through_when_no_section_owns(self, mock_qapp):
        """No section claims the widget — event passes through."""
        widget = _fake_widget("unowned")
        section = _make_section(owns_fn=lambda w: False)
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is False


# ---------------------------------------------------------------------------
# NavigationManager cross-section routing
# ---------------------------------------------------------------------------

class TestCrossSectionRouting:
    def setup_method(self):
        from core.navigation import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    @patch("core.navigation.QApplication")
    def test_down_at_last_item_yields_to_next_section(self, mock_qapp):
        widget = _fake_widget("target")
        focus_calls = []

        top = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        bottom = _make_section(
            owns_fn=lambda w: False,
            focus_first_fn=lambda: (focus_calls.append("bottom_first") or True),
        )
        self.manager.register(top)
        self.manager.register(bottom)

        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert focus_calls == ["bottom_first"]

    @patch("core.navigation.QApplication")
    def test_up_at_first_item_yields_to_prev_section(self, mock_qapp):
        widget = _fake_widget("target")
        focus_calls = []

        top = _make_section(
            owns_fn=lambda w: False,
            focus_last_fn=lambda: (focus_calls.append("top_last") or True),
        )
        bottom = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(top)
        self.manager.register(bottom)

        event = _FakeKeyEvent(Qt.Key.Key_Up)
        mock_qapp.focusWidget.return_value = widget
        result = self.manager.eventFilter(None, event)
        assert result is True
        assert focus_calls == ["top_last"]

    @patch("core.navigation.QApplication")
    def test_left_right_pass_through_when_section_yields(self, mock_qapp):
        """Left/Right from a yielding section are consumed (no neighbor)."""
        widget = _fake_widget("target")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(section)
        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event = _FakeKeyEvent(key)
            mock_qapp.focusWidget.return_value = widget
            result = self.manager.eventFilter(None, event)
            # No neighbor → consumed (prevents re-delivery loop)
            assert result is True


# ---------------------------------------------------------------------------
# SessionPickerSection
# ---------------------------------------------------------------------------

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

        section = SessionPickerSection(page)
        return section, page, buttons

    def test_owns_returns_true_for_descendant(self):
        section, page, _ = self._make_page()
        child = MagicMock()
        page.isAncestorOf = MagicMock(return_value=True)
        assert section.owns(child) is True

    def test_owns_returns_true_for_page_itself(self):
        section, page, _ = self._make_page()
        assert section.owns(page) is True

    def test_owns_returns_false_for_unrelated(self):
        section, page, _ = self._make_page()
        page.isAncestorOf = MagicMock(return_value=False)
        assert section.owns(MagicMock()) is False

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

    def test_down_at_last_card_yields(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        result = section.navigate(Qt.Key.Key_Down, buttons[2][1])
        assert result is False

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
        assert section.focus_first() is True
        buttons[0][1].setFocus.assert_called_once()

    def test_focus_first_empty(self):
        section, _, _ = self._make_page([])
        assert section.focus_first() is False

    def test_focus_last(self):
        section, _, buttons = self._make_page(["a", "b", "c"])
        assert section.focus_last() is True
        buttons[2][1].setFocus.assert_called_once()

    def test_focus_last_empty(self):
        section, _, _ = self._make_page([])
        assert section.focus_last() is False


# ---------------------------------------------------------------------------
# TabStripSection
# ---------------------------------------------------------------------------

class TestTabStripSection:
    def _make_strip(self):
        from core.navigation_sections import TabStripSection

        strip = MagicMock()
        strip.setFocus = MagicMock()
        strip.isAncestorOf = MagicMock(return_value=False)
        section = TabStripSection(strip)
        return section, strip

    def test_owns_returns_true_for_descendant(self):
        section, strip = self._make_strip()
        child = MagicMock()
        strip.isAncestorOf = MagicMock(return_value=True)
        assert section.owns(child) is True

    def test_owns_returns_true_for_strip_itself(self):
        section, strip = self._make_strip()
        assert section.owns(strip) is True

    def test_owns_returns_false_for_unrelated(self):
        section, strip = self._make_strip()
        strip.isAncestorOf = MagicMock(return_value=False)
        assert section.owns(MagicMock()) is False

    def test_navigate_up_consumed_no_section_above(self):
        """Up on tab strip is consumed — no section above."""
        section, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Up, MagicMock()) is True

    def test_navigate_down_yields_to_session_picker(self):
        """Down on tab strip yields — session picker is below."""
        section, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Down, MagicMock()) is False

    def test_navigate_left_right_yield(self):
        """Left/Right yield — not handled by NavigationManager."""
        section, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Left, MagicMock()) is False
        assert section.navigate(Qt.Key.Key_Right, MagicMock()) is False

    def test_focus_first(self):
        section, strip = self._make_strip()
        assert section.focus_first() is True
        strip.setFocus.assert_called_once()

    def test_focus_last(self):
        section, strip = self._make_strip()
        assert section.focus_last() is True
        strip.setFocus.assert_called_once()
