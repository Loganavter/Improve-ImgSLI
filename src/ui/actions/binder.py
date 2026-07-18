"""Install QShortcuts for catalog actions (effective shortcuts)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from ui.actions.keymap import effective_shortcut, normalize_sequence
from ui.actions.registry import ActionRegistry, get_action_registry

if TYPE_CHECKING:
    from core.actions.types import ActionDescriptor

logger = logging.getLogger("ImproveImgSLI")

_binder: "ActionShortcutBinder | None" = None


def get_action_shortcut_binder() -> "ActionShortcutBinder":
    global _binder
    if _binder is None:
        _binder = ActionShortcutBinder()
    return _binder


def resync_action_shortcuts(
    window: QWidget | None,
    *,
    active_tab: str | None = None,
    overrides: Mapping[str, str] | None = None,
    registry: ActionRegistry | None = None,
) -> None:
    """Central resync entry used after catalog or override changes."""
    if window is None:
        return
    store_overrides = overrides
    if store_overrides is None:
        store = getattr(getattr(window, "presenter", None), "store", None)
        if store is None:
            store = getattr(window, "store", None)
        settings = getattr(store, "settings", None) if store is not None else None
        store_overrides = getattr(settings, "keyboard_overrides", None) or {}
    if active_tab is None:
        try:
            from tabs.registry import get_shared_tab_registry

            tab = get_shared_tab_registry().get_active_tab()
            active_tab = getattr(tab, "session_type", None) if tab is not None else None
        except Exception:
            active_tab = None
    get_action_shortcut_binder().resync(
        window,
        registry=registry or get_action_registry(),
        overrides=store_overrides,
        active_tab=active_tab,
    )


class ActionShortcutBinder:
    """First-registered chord wins; later conflicts are skipped and logged."""

    def __init__(self) -> None:
        self._shortcuts: list = []
        self._claimed: dict[str, str] = {}

    def clear(self) -> None:
        for shortcut in self._shortcuts:
            try:
                # Unbind immediately — deleteLater alone can leave a duplicate
                # chord live until the event loop runs, so two actions briefly
                # share one key or neither fires (Qt ambiguity).
                shortcut.activated.disconnect()
            except Exception:
                pass
            try:
                shortcut.setEnabled(False)
                shortcut.setKey(QKeySequence())
                shortcut.setParent(None)
                shortcut.deleteLater()
            except Exception:
                pass
        self._shortcuts.clear()
        self._claimed.clear()

    def resync(
        self,
        window: QWidget,
        *,
        registry: ActionRegistry,
        overrides: Mapping[str, str] | None,
        active_tab: str | None,
    ) -> None:
        from PySide6.QtGui import QShortcut

        self.clear()
        actions = registry.list_for(active_tab=active_tab)
        for action in actions:
            chord = effective_shortcut(action, overrides)
            if not chord or action.run is None:
                continue
            portable = normalize_sequence(chord)
            if not portable:
                continue
            if portable in self._claimed:
                logger.warning(
                    "Shortcut conflict: %s already claimed by %s; skipping %s",
                    portable,
                    self._claimed[portable],
                    action.action_id,
                )
                continue
            shortcut = QShortcut(QKeySequence(portable), window)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.setAutoRepeat(False)
            run = action.run
            action_id = action.action_id
            shortcut.activated.connect(
                lambda checked=False, r=run, aid=action_id: self._invoke(r, aid)
            )
            self._shortcuts.append(shortcut)
            self._claimed[portable] = action_id

    @staticmethod
    def _invoke(run, action_id: str) -> None:
        focused = QApplication.focusWidget()
        if _is_text_input(focused):
            return
        try:
            run()
        except Exception:
            logger.exception("Action shortcut failed for %s", action_id)


def _is_text_input(widget: QWidget | None) -> bool:
    if widget is None:
        return False
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
        return True
    # Toolkit CustomLineEdit subclasses QLineEdit — covered above.
    try:
        from sli_ui_toolkit.widgets import CustomLineEdit

        if isinstance(widget, CustomLineEdit):
            return True
    except Exception:
        pass
    return False
