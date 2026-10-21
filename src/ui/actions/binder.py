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

from sli_ui_toolkit.widgets import CustomLineEdit

from ui.actions.keymap import (
    aliases_for,
    binding_priority,
    effective_shortcut,
    normalize_sequence,
    resolve_chord_winners,
)
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
    try:
        from ui.actions.palette.common import set_keyboard_overrides

        set_keyboard_overrides(dict(store_overrides or {}))
    except Exception:
        pass


class ActionShortcutBinder:
    """Install one live shortcut per winning chord (shared priority scheme).

    Winners come from :func:`ui.actions.keymap.resolve_chord_winners` — the
    same ranking Settings → Keyboard uses — so the live binding, the stored
    overrides, and the Settings display agree on every conflict.
    """

    def __init__(self) -> None:
        self._shortcuts: list = []
        self._claimed: dict[str, str] = {}
        self._entries: list[tuple[str, object]] = []
        # chord -> owning action's tab (None = platform action). Lets
        # ``owns_chord`` answer per-tab questions without a registry lookup.
        self._owner_tabs: dict[str, str | None] = {}

    def owns_chord(self, chord: str, *, active_tab: str | None = None) -> bool:
        """True when this binder installed ``chord`` in the active tab's scope.

        The binder is resynced for the ACTIVE tab (see
        ``resync_action_shortcuts``), so its claimed chords are exactly the
        shortcuts that tab's focused widgets may receive. Platform actions
        (``owner_tab is None``) are installed in every tab's scope and count
        for any ``active_tab``. ``active_tab=None`` asks the plain question
        "is this chord bound at all".

        Shared-event code uses this to decide whether a key belongs to the
        shortcut map instead of the global keyboard route — e.g. Image
        Compare's ``D`` is both the divider-visibility shortcut and an
        overlay-movement key.
        """
        portable = normalize_sequence(chord)
        if not portable:
            return False
        action_id = self._claimed.get(portable)
        if action_id is None:
            return False
        if active_tab is None:
            return True
        return self._owner_tabs.get(portable) in (None, active_tab)

    def describe_claim(
        self, chord: str, *, active_tab: str | None = None
    ) -> str:
        """One-line "who claims ``chord``" report for the ``[kbd-route]`` log.

        ``owns_chord`` is a boolean and a False is indistinguishable between
        "no claim at all" (binder not resynced yet, or a resync that ran with
        another tab) and "claimed by a different tab". Live debugging needs
        that difference, and shared event code must not reach into
        ``_claimed``/``_owner_tabs`` itself — so the diagnostic lives here,
        next to the data it reports. Never used for control flow.
        """
        portable = normalize_sequence(chord)
        action_id = self._claimed.get(portable)
        owner = self._owner_tabs.get(portable)
        return (
            f"claims={len(self._claimed)} claim={action_id or '-'} "
            f"owner_tab={owner!r} "
            f"tab_match={active_tab is None or owner in (None, active_tab)}"
        )

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
        self._entries.clear()
        self._owner_tabs.clear()

    def drop_prefix(self, prefix: str) -> None:
        """Delete live shortcuts whose action id starts with ``prefix``.

        Used after catalog withdraw (dialog teardown) when no full-window
        resync is available — drops stale chords without rebuilding the
        whole binder.
        """
        if not prefix:
            return
        doomed = [
            index
            for index, (_chord, action_id) in enumerate(self._entries)
            if isinstance(action_id, str) and action_id.startswith(prefix)
        ]
        for index in reversed(doomed):
            shortcut = self._shortcuts.pop(index)
            self._entries.pop(index)
            try:
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
        if doomed:
            self._claimed = {
                chord: action_id
                for chord, action_id in self._claimed.items()
                if not action_id.startswith(prefix)
            }
            self._owner_tabs = {
                chord: owner_tab
                for chord, owner_tab in self._owner_tabs.items()
                if chord in self._claimed
            }

    def resync(
        self,
        window: QWidget,
        *,
        registry: ActionRegistry,
        overrides: Mapping[str, str] | None,
        active_tab: str | None,
    ) -> None:
        self.clear()
        # Shortcut installation must not follow toolbar visibility: in the
        # simple UI mode the divider button is hidden while its action still
        # has a live target, and dropping it here silently removed the ``D``
        # chord (Image Compare). Find Action keeps the chrome filter.
        actions = registry.list_for(active_tab=active_tab, chrome_only=False)
        # Rank through the shared scheme so the winner matches keymap /
        # Settings even when registration order disagrees with priority.
        ranked = sorted(
            enumerate(actions),
            key=lambda item: (
                binding_priority(
                    item[1].action_id, owner_tab=item[1].owner_tab
                ),
                item[0],
            ),
        )
        # chord → winning action_id across primaries and registered aliases.
        defaults = {
            action.action_id: (action.shortcut, action.owner_tab)
            for action in actions
        }
        winners = resolve_chord_winners(defaults, overrides)
        for _index, action in ranked:
            chord = effective_shortcut(action, overrides)
            if not chord or action.run is None:
                continue
            portable = normalize_sequence(chord)
            if not portable:
                continue
            if winners.get(portable) != action.action_id:
                logger.warning(
                    "Shortcut conflict: %s owned by %s; skipping %s",
                    portable,
                    winners.get(portable),
                    action.action_id,
                )
                continue
            self._install(action, portable, window)
            for alias in aliases_for(action.action_id):
                if winners.get(alias) != action.action_id:
                    continue
                if alias == portable:
                    continue
                self._install(action, alias, window, alias_of=portable)

    def _install(self, action, portable: str, window, *, alias_of: str | None = None) -> None:
        from PySide6.QtGui import QShortcut

        # The legacy redo side-installer (main-window platform actions) owns
        # Ctrl+Y when present — installing our alias as well would fire redo
        # twice. Skip only that chord, not the whole action.
        if alias_of is not None and getattr(window, "_imgsli_redo_alt_shortcut", None) is not None:
            return
        if portable in self._claimed:
            logger.warning(
                "Shortcut conflict: %s already claimed by %s; skipping %s",
                portable,
                self._claimed[portable],
                action.action_id,
            )
            return
        shortcut = QShortcut(QKeySequence(portable), window)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.setAutoRepeat(False)
        run = action.run
        action_id = action.action_id
        shortcut.activated.connect(
            lambda checked=False, r=run, aid=action_id: self._invoke(r, aid)
        )
        self._shortcuts.append(shortcut)
        self._entries.append((portable, action_id))
        self._claimed[portable] = action_id
        self._owner_tabs[portable] = getattr(action, "owner_tab", None)

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
    # CustomLineEdit is the toolkit's painted, QLineEdit-compatible field —
    # no longer a QLineEdit subclass, so it must be matched explicitly.
    return isinstance(
        widget, (QLineEdit, CustomLineEdit, QTextEdit, QPlainTextEdit)
    )