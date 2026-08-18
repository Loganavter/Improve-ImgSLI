"""App-wide keyboard navigation manager.

Catches arrow keys on ``QApplication`` *before* any widget-specific handling
(scroll areas, tab bars, etc.), solving the ``OverlayScrollArea`` intercept
problem at its root.

Follows the same singleton + register/unregister pattern as
``sli_ui_toolkit.managers.FlyoutManager``.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from PySide6.QtCore import QEvent, Qt, QObject
from PySide6.QtWidgets import QApplication

logger = logging.getLogger("ImproveImgSLI")

_ARROWS = frozenset({Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_Right})
_EXIT_DOWN = frozenset({Qt.Key.Key_Down, Qt.Key.Key_Right})
_EXIT_UP = frozenset({Qt.Key.Key_Up, Qt.Key.Key_Left})


@runtime_checkable
class NavigationSection(Protocol):
    """Protocol for a navigable UI section (e.g. session picker, tab strip)."""

    def owns(self, widget: QObject) -> bool:
        """Return ``True`` if *widget* belongs to this section."""
        ...

    def navigate(self, key: int, widget: QObject) -> bool:
        """Handle *key* press while *widget* is focused.

        Return ``True`` if the event was consumed.
        Return ``False`` if the section wants to yield to an adjacent section.
        """
        ...

    def focus_first(self) -> bool:
        """Move focus to the first widget in this section.  Return success."""
        ...

    def focus_last(self) -> bool:
        """Move focus to the last widget in this section.  Return success."""
        ...


class NavigationManager(QObject):
    """Process-wide keyboard navigation coordinator.

    Installs an event filter on ``QApplication`` so arrow-key events are
    intercepted *before* ``QAbstractScrollArea`` (and friends) consume them.

    Sections are ordered top-to-bottom (first registered = topmost in the
    visual hierarchy).  When a section's ``navigate()`` returns ``False``
    on a boundary key (Up/Left at first item, Down/Right at last item),
    the manager delegates to the adjacent section.
    """

    _instance: NavigationManager | None = None

    @classmethod
    def get_instance(cls) -> NavigationManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self._sections: list[NavigationSection] = []
        self._event_filter_installed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, section: NavigationSection) -> None:
        if section not in self._sections:
            self._sections.append(section)
            self._install_event_filter()

    def unregister(self, section: NavigationSection) -> None:
        try:
            self._sections.remove(section)
        except ValueError:
            return
        if not self._sections:
            self._uninstall_event_filter()

    # ------------------------------------------------------------------
    # Cross-section navigation helpers
    # ------------------------------------------------------------------

    def _section_index(self, section: NavigationSection) -> int | None:
        try:
            return self._sections.index(section)
        except ValueError:
            return None

    def _neighbor(self, section: NavigationSection, direction: int) -> NavigationSection | None:
        """Return the adjacent section in *direction* (+1 = down, -1 = up)."""
        idx = self._section_index(section)
        if idx is None:
            return None
        target = idx + direction
        if 0 <= target < len(self._sections):
            return self._sections[target]
        return None

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def _install_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._event_filter_installed = True

    def _uninstall_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._event_filter_installed = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return False

        key = event.key()
        if key not in _ARROWS:
            return False

        focused = QApplication.focusWidget()
        if focused is None:
            return False

        _debug = logger.isEnabledFor(logging.DEBUG)

        for section in self._sections:
            if section.owns(focused):
                if _debug:
                    logger.debug(
                        "[nav] key=%s focused=%s section=%s",
                        key, type(focused).__name__, type(section).__name__,
                    )
                if section.navigate(key, focused):
                    if _debug:
                        logger.debug("[nav] handled by %s", type(section).__name__)
                    return True

                # Section declined — try adjacent section on boundary keys.
                if key in _EXIT_DOWN:
                    neighbor = self._neighbor(section, +1)
                    if neighbor is not None and neighbor.focus_first():
                        if _debug:
                            logger.debug(
                                "[nav] handed off DOWN to %s",
                                type(neighbor).__name__,
                            )
                        return True
                elif key in _EXIT_UP:
                    neighbor = self._neighbor(section, -1)
                    if neighbor is not None and neighbor.focus_last():
                        if _debug:
                            logger.debug(
                                "[nav] handed off UP to %s",
                                type(neighbor).__name__,
                            )
                        return True

                break

        return False
