"""Find Action dialog — list, filter, keyboard, run / reveal / learn more."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor
from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.widgets import CustomLineEdit, Label, MinimalistScrollBar
from tabs.registry import get_shared_tab_registry
from ui.actions.palette.common import (
    current_keyboard_overrides as _current_keyboard_overrides,
    target_is_revealable,
    tr_action,
)
from ui.actions.palette.row import ActionPaletteRow
from ui.actions.registry import get_action_registry
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

_DIALOG_WIDTH = 560
_DIALOG_HEIGHT = 420
# Coalesce fast typing into one rebuild instead of tearing down/recreating
# every row (Button widgets with painter layers) on each keystroke.
_RELOAD_DEBOUNCE_MS = 90


def _active_tab_type() -> str | None:
    try:
        tab = get_shared_tab_registry().get_active_tab()
        return getattr(tab, "session_type", None) if tab is not None else None
    except Exception:
        logger.debug("[find-action] _active_tab_type failed", exc_info=True)
        return None


def open_help_page(page: str, anchor: str | None = None) -> None:
    try:
        registry = get_shared_tab_registry()
        context = getattr(registry, "_context", None)
        if context is not None and hasattr(context, "call_service"):
            context.call_service("show_help_dialog", page=page, anchor=anchor)
            return
        tab = registry.get_active_tab()
        widget = getattr(tab, "_widget", None) if tab is not None else None
        widget_context = getattr(widget, "_context", None) if widget is not None else None
        if widget_context is not None and hasattr(widget_context, "call_service"):
            widget_context.call_service("show_help_dialog", page=page, anchor=anchor)
            return
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            presenter = getattr(widget, "presenter", None)
            ui_manager = getattr(presenter, "ui_manager", None) if presenter else None
            dialogs = getattr(ui_manager, "dialogs", None)
            if dialogs is not None and hasattr(dialogs, "show_help_dialog"):
                dialogs.show_help_dialog(page=page, anchor=anchor)
                return
    except Exception:
        pass


class FindActionDialog(ThemedDialog):
    """Searchable action palette — Enter runs, Esc closes, ↑↓ moves selection.

    Always a top-level ``Window`` (no parent / no Dialog·Popup·Tool hints) so
    the compositor does not treat it as a transient popup of the main window.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        query: str = "",
        topic: str | None = None,
        preselect_action_id: str | None = None,
        auto_pulse: bool = False,
        active_tab: str | None = None,
    ) -> None:
        # Keep parentless so Wayland/X11 do not create a transient-for link.
        del parent
        super().__init__(None)
        self._topic = topic
        self._preselect_action_id = preselect_action_id
        self._auto_pulse = auto_pulse
        self._auto_pulse_done = False
        self._active_tab_override = active_tab
        self._actions: list[ActionDescriptor] = []
        self._rows: list[ActionPaletteRow] = []
        self._current_index = -1
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(_RELOAD_DEBOUNCE_MS)
        self._reload_timer.timeout.connect(self._reload)

        title = tr_action("menu.find_action", "Find Action")
        self.setObjectName("FindActionDialog")
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setWindowTitle(title)
        self._apply_independent_window_flags()
        self.setSizeGripEnabled(False)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._build_ui(query)
        self.setMinimumSize(480, 320)
        self.resize(_DIALOG_WIDTH, _DIALOG_HEIGHT)
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=title, resizable=True)
        # decorate_dialog / frameless may reintroduce Dialog bits — strip again.
        self._apply_independent_window_flags()
        self.installEventFilter(self)
        self._app_filter_installed = False
        self._reload()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Keep search focused so the first typed character uses the active
        # keyboard layout / input method (not a Latin Key_A→'a' fallback).
        self._search.setFocus(Qt.FocusReason.OtherFocusReason)
        self._maybe_auto_pulse()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._search.setFocus(Qt.FocusReason.OtherFocusReason)
        self._install_app_event_filter()

    def hideEvent(self, event) -> None:
        self._release_app_event_filter()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._release_app_event_filter()
        super().closeEvent(event)

    def _install_app_event_filter(self) -> None:
        if self._app_filter_installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._app_filter_installed = True

    def _release_app_event_filter(self) -> None:
        if not self._app_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._app_filter_installed = False

    def _is_typeahead_event(self, event) -> bool:
        """True when a printable key should jump focus into the search field."""
        mods = event.modifiers()
        if mods & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        text = event.text()
        if text and text.isprintable():
            return True
        # text() can be empty when focus is not on an input widget; still treat
        # letter/digit keys as typeahead so we can focus+forward the event.
        key = event.key()
        return (
            Qt.Key.Key_A <= key <= Qt.Key.Key_Z
            or Qt.Key.Key_0 <= key <= Qt.Key.Key_9
        )

    def _redirect_typeahead_to_search(self, event) -> bool:
        if self.focusWidget() is self._search:
            return False
        if not self._is_typeahead_event(event):
            return False
        self._search.setFocus(Qt.FocusReason.OtherFocusReason)
        text = event.text()
        if text and text.isprintable():
            # Layout-aware Unicode from the platform (Cyrillic, etc.).
            self._search.insert(text)
            return True
        # Never synthesize Latin from key() — that forces English on the first
        # character when text() is empty (common before the line edit is focused).
        from PySide6.QtGui import QKeyEvent

        clone = QKeyEvent(
            QEvent.Type.KeyPress,
            event.key(),
            event.modifiers(),
            event.nativeScanCode(),
            event.nativeVirtualKey(),
            event.nativeModifiers(),
            event.text(),
            event.isAutoRepeat(),
            event.count(),
        )
        QApplication.sendEvent(self._search, clone)
        return True

    def _apply_independent_window_flags(self) -> None:
        """Force a normal top-level window, not a dialog/popup transient."""
        flags = self.windowFlags()
        # Qt::ToolTip (0x00001000) — numeric literal avoids WindowType.ToolTip in
        # source; flag is cleared so the palette is not a tooltip-class window.
        _tooltip_window_flag = 0x00001000
        flags &= ~(
            Qt.WindowType.Dialog
            | Qt.WindowType.Sheet
            | Qt.WindowType.Drawer
            | Qt.WindowType.Tool
            | _tooltip_window_flag
            | Qt.WindowType.Popup
            | Qt.WindowType.WindowStaysOnTopHint
        )
        flags |= (
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowFlags(flags)

    def _build_ui(self, query: str) -> None:
        root = QVBoxLayout(self)
        # Top margin must stay 0: decorate_dialog adds CustomTitleBar.HEIGHT to
        # the existing top inset, so any >0 value becomes a gap under chrome.
        root.setContentsMargins(14, 0, 14, 12)
        root.setSpacing(10)
        # Gap under the custom title bar (top margin stays 0 — see decorate_dialog).
        root.addSpacing(8)

        self._search = CustomLineEdit(parent=self)
        self._search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search.setPlaceholderText(
            tr_action("action.palette.search_placeholder", "Search actions…")
        )
        if query:
            self._search.setText(query)
        self._search.textChanged.connect(self._schedule_reload)
        self._search.installEventFilter(self)
        root.addWidget(self._search)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBar(MinimalistScrollBar(parent=self._scroll))
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._list_host = QWidget(self._scroll)
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, 1)

        self._empty = Label(
            tr_action("action.palette.empty", "No matching actions"),
            variant="caption",
            pixel_size=12,
            color_token="list_item.text.rating",
            parent=self,
        )
        self._empty.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._empty.hide()
        root.addWidget(self._empty)

    def _schedule_reload(self) -> None:
        """Debounce rebuilds while typing — see ``_RELOAD_DEBOUNCE_MS``."""
        self._reload_timer.start()

    def _reload(self) -> None:
        self._reload_timer.stop()
        query = self._search.text()
        active_tab = self._active_tab_override
        if active_tab is None:
            active_tab = _active_tab_type()
        registry = get_action_registry()
        self._actions = registry.list_for(
            active_tab=active_tab,
            query=query,
            topic=self._topic,
        )
        while self._rows:
            row = self._rows.pop()
            self._list_layout.removeWidget(row)
            row.deleteLater()

        # Resolved once per rebuild instead of once per row — this used to
        # walk every top-level widget for each of the ~50-70 rows shown when
        # the palette is empty.
        keyboard_overrides = _current_keyboard_overrides()
        for action in self._actions:
            row = ActionPaletteRow(
                action,
                query=query,
                active_tab=active_tab,
                keyboard_overrides=keyboard_overrides,
                parent=self._list_host,
            )
            row.rowActivated.connect(self._run_action_id)
            row.rowRevealRequested.connect(self._reveal_action_id)
            row.learnMoreRequested.connect(self._learn_more_action_id)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._rows.append(row)

        has_rows = bool(self._rows)
        self._scroll.setVisible(has_rows)
        self._empty.setVisible(not has_rows)
        # Default-select the first row for the left accent tick + Enter target.
        # Hover wash is mouse-only (see RowBackgroundLayer) so this is not a
        # permanent "hovered" look.
        index = 0
        if has_rows and self._preselect_action_id:
            for i, action in enumerate(self._actions):
                if action.action_id == self._preselect_action_id:
                    index = i
                    break
        self._set_current_index(index if has_rows else -1)

    def _set_current_index(self, index: int) -> None:
        if not self._rows:
            self._current_index = -1
            return
        if index < 0:
            self._current_index = -1
            for row in self._rows:
                row.set_current(False)
            return
        index = max(0, min(index, len(self._rows) - 1))
        self._current_index = index
        for i, row in enumerate(self._rows):
            row.set_current(i == index)
        self._scroll_to_current()

    def _scroll_to_current(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._rows):
            return
        row = self._rows[self._current_index]
        self._scroll.ensureWidgetVisible(row, 0, 8)

    def _move_selection(self, delta: int) -> None:
        if not self._rows:
            return
        if self._current_index < 0:
            self._set_current_index(0 if delta > 0 else len(self._rows) - 1)
            return
        self._set_current_index(self._current_index + delta)

    def _run_selected(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._actions):
            return
        self._run_action_id(self._actions[self._current_index].action_id)

    def _run_action_id(self, action_id: str) -> None:
        if not action_id:
            return
        action = get_action_registry().get(action_id)
        if action is None or action.run is None:
            return
        run = action.run
        self.accept()
        # Defer until the modal palette has closed — otherwise combo/menu
        # overlays opened by ``run`` are killed by the dialog's Hide/Close
        # events (ComboBox installs an app-wide filter while expanded).
        QTimer.singleShot(0, run)

    def _reveal_selected(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._actions):
            return
        self._reveal_action_id(self._actions[self._current_index].action_id)

    def _reveal_action_id(self, action_id: str) -> None:
        if not action_id:
            return
        action = get_action_registry().get(action_id)
        if action is None:
            return
        target = getattr(action, "target", None)
        if not target_is_revealable(target):
            return
        self.accept()
        from ui.actions.reveal import reveal_action_target

        # Defer until the modal palette has closed and the main window can
        # show title-bar menus / draw overlays again.
        QTimer.singleShot(0, lambda t=target: reveal_action_target(t))

    def _learn_more_selected(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._actions):
            return
        self._learn_more_action_id(self._actions[self._current_index].action_id)

    def _learn_more_action_id(self, action_id: str) -> None:
        if not action_id:
            return
        action = get_action_registry().get(action_id)
        if action is None:
            return
        page = getattr(action, "help_page", None)
        if not page:
            return
        anchor = getattr(action, "help_anchor", None)
        self.accept()
        QTimer.singleShot(
            0,
            lambda p=page, a=anchor: open_help_page(p, a),
        )

    def _maybe_auto_pulse(self) -> None:
        if self._auto_pulse_done or not self._auto_pulse:
            return
        if self._current_index < 0 or self._current_index >= len(self._actions):
            return
        action = self._actions[self._current_index]
        target = getattr(action, "target", None)
        widget = getattr(target, "widget", None) if target is not None else None
        if widget is None:
            return
        self._auto_pulse_done = True
        from ui.actions.widget_pulse import pulse_widget

        QTimer.singleShot(0, lambda w=widget: pulse_widget(w))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            # App-wide filter must ignore keys belonging to other windows;
            # widget filters on ``self`` / ``_search`` always pass this check.
            if isinstance(obj, QWidget) and obj.window() is not self:
                return super().eventFilter(obj, event)
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._move_selection(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if mods & Qt.KeyboardModifier.ControlModifier:
                    self._learn_more_selected()
                elif mods & Qt.KeyboardModifier.ShiftModifier:
                    self._reveal_selected()
                else:
                    self._run_selected()
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
            if self._redirect_typeahead_to_search(event):
                return True
        return super().eventFilter(obj, event)
