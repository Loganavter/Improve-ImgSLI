"""Unit tests for NavigationManager and NavigationSection implementations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from PySide6.QtCore import Qt
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


def _make_section(*, owns_fn=None, navigate_fn=None, focus_first_fn=None, focus_last_fn=None):
    """Build a cheap NavigationSection-conforming object for testing."""
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
        """Create a fresh manager for each test."""
        from core.navigation import NavigationManager
        # Reset singleton so tests are isolated.
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
        # Should not raise.
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

    def test_event_filter_delegates_to_owning_section(self):
        handled = []
        widget = QWidget()
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: (handled.append(k) or True),
        )
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        # Patch QApplication.focusWidget to return our widget.
        original = QApplication.focusWidget
        QApplication.focusWidget = staticmethod(lambda: widget)
        try:
            result = self.manager.eventFilter(None, event)
        finally:
            QApplication.focusWidget = original
        assert result is True
        assert handled == [Qt.Key.Key_Down]

    def test_event_filter_returns_false_when_no_focus(self):
        section = _make_section(owns_fn=lambda w: True)
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        original = QApplication.focusWidget
        QApplication.focusWidget = staticmethod(lambda: None)
        try:
            result = self.manager.eventFilter(None, event)
        finally:
            QApplication.focusWidget = original
        assert result is False

    def test_event_filter_tries_next_section_when_first_declines(self):
        widget = QWidget()
        focus_calls = []

        second = _make_section(
            owns_fn=lambda w: False,
            focus_first_fn=lambda: (focus_calls.append("first") or True),
        )
        first = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,  # decline
        )
        self.manager.register(first)
        self.manager.register(second)

        event = _FakeKeyEvent(Qt.Key.Key_Down)
        original = QApplication.focusWidget
        QApplication.focusWidget = staticmethod(lambda: widget)
        try:
            result = self.manager.eventFilter(None, event)
        finally:
            QApplication.focusWidget = original
        assert result is True
        assert focus_calls == ["first"]

    def test_event_filter_no_neighbor_on_boundary(self):
        widget = QWidget()
        # Only one section, at the boundary — should return False.
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        original = QApplication.focusWidget
        QApplication.focusWidget = staticmethod(lambda: widget)
        try:
            result = self.manager.eventFilter(None, event)
        finally:
            QApplication.focusWidget = original
        assert result is False


# ---------------------------------------------------------------------------
# NavigationManager cross-section routing
# ---------------------------------------------------------------------------

class TestCrossSectionRouting:
    def setup_method(self):
        from core.navigation import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    def test_down_at_last_item_yields_to_next_section(self):
        widget = QWidget()
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
        original = QApplication.focusWidget
        QApplication.focusWidget = staticmethod(lambda: widget)
        try:
            result = self.manager.eventFilter(None, event)
        finally:
            QApplication.focusWidget = original
        assert result is True
        assert focus_calls == ["bottom_first"]

    def test_up_at_first_item_yields_to_prev_section(self):
        widget = QWidget()
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
        original = QApplication.focusWidget
        QApplication.focusWidget = staticmethod(lambda: widget)
        try:
            result = self.manager.eventFilter(None, event)
        finally:
            QApplication.focusWidget = original
        assert result is True
        assert focus_calls == ["top_last"]

    def test_left_right_between_tabs_not_consumed(self):
        """Left/Right in tab strip should fall through to QTabBar."""
        widget = QWidget()
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: False,
        )
        self.manager.register(section)
        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event = _FakeKeyEvent(key)
            original = QApplication.focusWidget
            QApplication.focusWidget = staticmethod(lambda: widget)
            try:
                result = self.manager.eventFilter(None, event)
            finally:
                QApplication.focusWidget = original
            assert result is False


# ---------------------------------------------------------------------------
# SessionPickerSection
# ---------------------------------------------------------------------------

class TestSessionPickerSection:
    def _make_page(self, card_labels=None):
        """Build a minimal page with _card_entries()."""
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

    def test_navigate_always_yields(self):
        section, _ = self._make_strip()
        for key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right):
            assert section.navigate(key, MagicMock()) is False

    def test_focus_first(self):
        section, strip = self._make_strip()
        assert section.focus_first() is True
        strip.setFocus.assert_called_once()

    def test_focus_last(self):
        section, strip = self._make_strip()
        assert section.focus_last() is True
        strip.setFocus.assert_called_once()
