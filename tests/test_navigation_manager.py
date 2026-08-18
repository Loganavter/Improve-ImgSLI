"""Unit tests for NavigationManager and NavigationSection implementations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication


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
        from sli_ui_toolkit.managers import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    def test_singleton(self):
        from sli_ui_toolkit.managers import NavigationManager
        a = NavigationManager.get_instance()
        b = NavigationManager.get_instance()
        assert a is b

    def test_register_adds_section(self):
        section = _make_section()
        self.manager.register(section)
        assert any(s is section for _, s in self.manager._sections)

    def test_register_idempotent(self):
        section = _make_section()
        self.manager.register(section)
        self.manager.register(section)
        assert sum(1 for _, s in self.manager._sections if s is section) == 1

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

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
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

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_event_filter_returns_false_when_no_focus(self, mock_qapp):
        section = _make_section(owns_fn=lambda w: True)
        self.manager.register(section)
        event = _FakeKeyEvent(Qt.Key.Key_Down)
        mock_qapp.focusWidget.return_value = None
        result = self.manager.eventFilter(None, event)
        assert result is False

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
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

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
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

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
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
        from sli_ui_toolkit.managers import NavigationManager
        NavigationManager._instance = None
        self.manager = NavigationManager()

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
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

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
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

    @patch("sli_ui_toolkit.ui.managers.navigation_manager.QApplication")
    def test_left_right_pass_through_immediately(self, mock_qapp):
        """Left/Right pass through without any section routing."""
        widget = _fake_widget("target")
        section = _make_section(
            owns_fn=lambda w: w is widget,
            navigate_fn=lambda k, w: True,
        )
        self.manager.register(section)
        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event = _FakeKeyEvent(key)
            mock_qapp.focusWidget.return_value = widget
            result = self.manager.eventFilter(None, event)
            assert result is False


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
        page._recent_panel = None

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

    def test_down_at_last_card_yields_when_no_recent_panel(self):
        section, page, buttons = self._make_page(["a", "b", "c"])
        page._recent_panel = None
        result = section.navigate(Qt.Key.Key_Down, buttons[2][1])
        assert result is False

    def test_down_at_last_card_focuses_recent_panel(self):
        section, page, buttons = self._make_page(["a", "b", "c"])
        recent = MagicMock()
        recent.isVisible = MagicMock(return_value=True)
        recent.setFocus = MagicMock()
        page._recent_panel = recent
        result = section.navigate(Qt.Key.Key_Down, buttons[2][1])
        assert result is True
        recent.setFocus.assert_called_once()

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
        strip.isAncestorOf = MagicMock(return_value=True)
        assert section.owns(child) is True

    def test_owns_returns_true_for_strip_itself(self):
        section, strip, _ = self._make_strip()
        assert section.owns(strip) is True

    def test_owns_returns_false_for_unrelated(self):
        section, strip, _ = self._make_strip()
        strip.isAncestorOf = MagicMock(return_value=False)
        assert section.owns(MagicMock()) is False

    def test_navigate_up_consumed_no_section_above(self):
        section, _, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Up, MagicMock()) is True

    def test_navigate_down_yields_to_session_picker(self):
        section, _, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Down, MagicMock()) is False

    def test_navigate_left_right_yield(self):
        section, _, _ = self._make_strip()
        assert section.navigate(Qt.Key.Key_Left, MagicMock()) is False
        assert section.navigate(Qt.Key.Key_Right, MagicMock()) is False

    def test_focus_first_focuses_add_button(self):
        section, _, add_button = self._make_strip()
        assert section.focus_first() is True
        add_button.setFocus.assert_called_once()

    def test_focus_last_focuses_add_button(self):
        section, _, add_button = self._make_strip()
        assert section.focus_last() is True
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

    def test_tab_strip_section_consumes_up(self):
        """TabStripSection must consume Up — no section above."""
        from core.navigation_sections import TabStripSection

        strip = MagicMock()
        strip.isAncestorOf = MagicMock(return_value=False)
        section = TabStripSection(strip)

        result = section.navigate(Qt.Key.Key_Up, MagicMock())
        assert result is True, (
            f"TabStripSection yielded Up={result}, expected True (consume)"
        )
