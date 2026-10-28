"""Find Action dialog — list, filter, keyboard, run / reveal / learn more.
Audit-Meta: pattern=qdialog-wiring size=exempt reason="one QDialog layout/signal wiring — list/filter/keyboard/pulse with scaled_px"
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor
from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.pending_settle import PendingSettle, settle_on_paint
from sli_ui_toolkit.widgets import CustomLineEdit, SurfaceScrollArea, Text
from tabs.registry import get_shared_tab_registry
from ui.actions.palette.common import (
    current_keyboard_overrides as _current_keyboard_overrides,
    target_is_revealable,
    tr_action,
)
from ui.actions.palette.row import ActionPaletteRow
from ui.actions.registry import get_action_registry
from core.log_names import APP_LOGGER_NAME
from utils.resource_loader import resource_path

logger = logging.getLogger(APP_LOGGER_NAME)

_DIALOG_WIDTH = 560
_DIALOG_HEIGHT = 420# Filter on the keystroke, like GIMP's action search
# (``app/widgets/gimpsearchpopup.c``: ``keyword_entry_key_release_event``
# rebuilds and selects row 0 on every key release - no debounce at all). The
# reload is now cheap because rows are reused (~1 ms for a 70-action catalog),
# so a timer only added the feeling of a sticky search box. 0 = coalesce the
# burst that arrives inside one event-loop turn, do not delay a keystroke.
_RELOAD_DEBOUNCE_MS = 0

#: Row height in design px (must match ``row._ROW_HEIGHT``); the layout gap is
#: read through ``scaled_px`` at use time so it follows a UI-scale change.
_ROW_HEIGHT = 48
#: Extra rows materialized above/below the viewport (scroll stays smooth).
_VIRTUAL_OVERSCAN = 3


def _is_valid(obj) -> bool:
    """Shiboken liveness check for deferred callbacks (same shape as combo_reveal).

    Ripple-then-accept timers (`singleShot`) may fire after qtbot teardown
    destroyed this dialog; calling `accept()` on the dead wrapper raises
    inside the event loop and segfaults/poisons a later test's
    `_process_events`. Fail open when shiboken itself is unavailable.
    """
    if obj is None:
        return False
    try:
        import shiboken6

        return bool(shiboken6.isValid(obj))
    except Exception:
        return True


def _active_tab_type() -> str | None:
    try:
        tab = get_shared_tab_registry().get_active_tab()
        return getattr(tab, "session_type", None) if tab is not None else None
    except Exception:
        logger.debug("[find-action] _active_tab_type failed", exc_info=True)
        return None


def open_help_page(
    page: str,
    anchor: str | None = None,
    *,
    video_url: str | None = None,
    learn_more_url: str | None = None,
) -> None:
    try:
        registry = get_shared_tab_registry()
        context = getattr(registry, "_context", None)
        if context is not None and hasattr(context, "call_service"):
            context.call_service(
                "show_help_dialog",
                page=page,
                anchor=anchor,
                video_url=video_url,
                learn_more_url=learn_more_url,
            )
            return
        tab = registry.get_active_tab()
        widget = getattr(tab, "_widget", None) if tab is not None else None
        widget_context = getattr(widget, "_context", None) if widget is not None else None
        if widget_context is not None and hasattr(widget_context, "call_service"):
            widget_context.call_service(
                "show_help_dialog",
                page=page,
                anchor=anchor,
                video_url=video_url,
                learn_more_url=learn_more_url,
            )
            return
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        for widget in app.topLevelWidgets():  # ALLOWED: system-wide help fallback — walks top-levels generically for dialogs.show_help_dialog, not tab-specific
            presenter = getattr(widget, "presenter", None)
            ui_manager = getattr(presenter, "ui_manager", None) if presenter else None
            dialogs = getattr(ui_manager, "dialogs", None)
            if dialogs is not None and hasattr(dialogs, "show_help_dialog"):
                dialogs.show_help_dialog(
                    page=page,
                    anchor=anchor,
                    video_url=video_url,
                    learn_more_url=learn_more_url,
                )
                return
    except Exception:
        pass


class FindActionDialog(ThemedDialog):
    """Searchable action palette — Enter runs, Esc closes, ↑↓ moves selection.

    A non-modal independent top-level window (same scheme as ``HelpDialog``):
    ``Qt.Window`` flag + ``NonModal``, shown with ``show()`` — never blocks
    the parent window, so the user can keep working while the palette is
    open. Transient-parented to the focused/main window so the compositor
    activates it freely under xdg-activation.
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
        # Non-modal window like HelpDialog: keep the transient parent and the
        # Window flag (see _apply_non_modal_window_flags) — never blocks the
        # owner, activates freely under xdg-activation.
        super().__init__(parent)
        self._find_action_nav_section = None
        self._topic = topic
        self._preselect_action_id = preselect_action_id
        self._auto_pulse = auto_pulse
        self._auto_pulse_done = False
        self._active_tab_override = active_tab
        self._actions: list[ActionDescriptor] = []
        self._rows: list[ActionPaletteRow] = []
        # Live rows keyed by action id: a keystroke re-orders/hides these
        # instead of destroying and rebuilding a composite widget per action
        # (measured: 300 actions = 0.9-2.6 s per keystroke before reuse).
        self._rows_by_id: dict[str, ActionPaletteRow] = {}
        # Materialized window state. Rows are widgets with painter layers
        # (~2.7 ms each), so only the visible slice exists: the spacers carry
        # the rest of the list's scroll extent.
        self._window_start = 0
        self._materializing = False
        self._pitch_cache = 0
        self._current_index = -1
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(_RELOAD_DEBOUNCE_MS)
        self._reload_timer.timeout.connect(self._reload)
        # First-show row layout: the host settles AFTER the viewport, so a
        # 0-timer ran one frame late (rows laid out after the first paint).
        # The paint boundary runs it before those pixels go out.
        self._row_settle = PendingSettle()

        title = tr_action("menu.find_action", "Find Action")
        self.setObjectName("FindActionDialog")
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setWindowTitle(title)
        self._apply_non_modal_window_flags()
        self.setSizeGripEnabled(False)
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)

        self._build_ui(query)
        settle_on_paint(self, self._row_settle)
        self.setMinimumSize(scaled_px(480), scaled_px(320))
        # Design size scaled like the minimum, so the two never disagree at
        # scale > 1.0 (an unscaled resize gets clamped to the scaled minimum).
        self.resize(scaled_px(_DIALOG_WIDTH), scaled_px(_DIALOG_HEIGHT))
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=title, resizable=True)
        # decorate_dialog (frameless) preserves flags — re-assert Window bits.
        self._apply_non_modal_window_flags()
        self.installEventFilter(self)
        self._app_filter_installed = False
        self._setup_find_action_navigation()
        self._reload()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Keep search focused so the first typed character uses the active
        # keyboard layout / input method (not a Latin Key_A→'a' fallback).
        self._search.setFocus(Qt.FocusReason.OtherFocusReason)
        self._maybe_auto_pulse()

    def _setup_find_action_navigation(self) -> None:
        """Нормальный мапинг навигации через NavigationManager (как в Help/Settings)."""
        try:
            from sli_ui_toolkit.managers import NavigationManager
            from sli_ui_toolkit.ui.managers.navigation_sections import AutoNavigationSection

            if self._find_action_nav_section is not None:
                return
            # Dialog как Auto-контейнер: поиск StrongFocus (search + ряды) → Up/Down/Left/Right
            section = AutoNavigationSection(self, tag="find-action")
            NavigationManager.get_instance().register(self, section)
            self._find_action_nav_section = section
        except Exception:
            pass

    def _teardown_find_action_navigation(self) -> None:
        try:
            from sli_ui_toolkit.managers import NavigationManager

            if self._find_action_nav_section is not None:
                NavigationManager.get_instance().unregister(self)
                self._find_action_nav_section = None
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._search.setFocus(Qt.FocusReason.OtherFocusReason)
        self._install_app_event_filter()

    def hideEvent(self, event) -> None:
        self._release_app_event_filter()
        self._teardown_find_action_navigation()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._release_app_event_filter()
        self._teardown_find_action_navigation()
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

    def _apply_non_modal_window_flags(self) -> None:
        """Force a non-modal independent window, same scheme as HelpDialog.

        ``Qt.Window`` (never Dialog·Popup·Tool hints) + ``NonModal``: the
        palette never blocks its owner. No maximize/minimize hints — unlike
        Help, the palette is a small fixed-size window.
        """
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
        root.setContentsMargins(scaled_px(14), 0, scaled_px(14), scaled_px(12))
        root.setSpacing(scaled_px(10))
        # Gap under the custom title bar (top margin stays 0 — see decorate_dialog).
        root.addSpacing(scaled_px(8))

        self._search = CustomLineEdit(parent=self)
        self._search.setObjectName("palette-search")
        self._search.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._search.setPlaceholderText(
            tr_action("action.palette.search_placeholder", "Search actions…")
        )
        if query:
            self._search.setText(query)
        self._search.textChanged.connect(self._schedule_reload)
        self._search.installEventFilter(self)
        root.addWidget(self._search)

        self._scroll = SurfaceScrollArea(self)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._list_host = QWidget(self._scroll)
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(scaled_px(2))
        self._list_layout.addStretch(1)
        self._top_spacer = QWidget(self._list_host)
        self._bottom_spacer = QWidget(self._list_host)
        for spacer in (self._top_spacer, self._bottom_spacer):
            spacer.setFixedHeight(0)
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._list_layout.insertWidget(0, self._top_spacer)
        self._list_layout.insertWidget(1, self._bottom_spacer)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, 1)
        # The overlay scrollbar reserves its gutter asynchronously after show:
        # once overflow is detected the toolkit applies viewport margins, the
        # viewport/host shrink, but this layout does not re-run — rows stay
        # wider than the viewport (right chrome clipped) until the first
        # manual resize. Re-activate on every viewport resize instead.
        self._scroll.viewport().installEventFilter(self)

        self._empty = Text(
            tr_action("action.palette.empty", "No matching actions"),
            mode="plain",
            variant="caption",
            pixel_size=14,
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
        self._active_tab = active_tab
        self._current_index = -1
        # Prune only rows whose action left the catalog (tab closed, plugin
        # unloaded) - an empty *filter* must not destroy the row cache, or the
        # next backspace rebuilds every one of them (measured 80 ms for 300).
        catalog_ids = {
            action.action_id
            for action in registry.list_for(active_tab=active_tab, topic=self._topic)
        }
        for action_id in [k for k in self._rows_by_id if k not in catalog_ids]:
            self._list_layout.removeWidget(self._rows_by_id.pop(action_id))

        has_rows = bool(self._actions)
        self._scroll.setVisible(has_rows)
        self._empty.setVisible(not has_rows)
        # A query change always shows its best match first: materialize from the
        # top and put the scroll back there (GIMP's search popup selects row 0
        # after every rebuild).
        self._window_start = 0
        self._scroll_to_top()
        self._materialize(0)

        index = 0
        if has_rows and self._preselect_action_id:
            for i, action in enumerate(self._actions):
                if action.action_id == self._preselect_action_id:
                    index = i
                    break
        self._set_current_index(index if has_rows else -1)
        if has_rows and index == 0:
            self._scroll_to_top()

    # -- virtual list: only the visible slice is materialized ----------------

    def _row_pitch(self) -> int:
        """Row height + layout spacing, measured once from a live row."""
        if self._pitch_cache <= 0:
            measured = 0
            for row in self._rows_by_id.values():
                if _is_valid(row):
                    measured = row.sizeHint().height()
                    if measured > 0:
                        break
            self._pitch_cache = max(
                scaled_px(_ROW_HEIGHT) + scaled_px(2), measured + scaled_px(2)
            )
        return self._pitch_cache

    def _visible_capacity(self) -> int:
        pitch = max(1, self._row_pitch())
        viewport = self._scroll.viewport().height()
        rows = max(1, (viewport + pitch - 1) // pitch)
        return rows + 2 * _VIRTUAL_OVERSCAN

    def _materialize(self, start: int) -> None:
        """Materialize the window of rows around *start*; park the rest."""
        if self._materializing:
            return
        self._materializing = True
        try:
            self._materialize_inner(start)
        finally:
            self._materializing = False

    def _materialize_inner(self, start: int) -> None:
        pitch = self._row_pitch()
        total = len(self._actions)
        if total == 0:
            for row in self._rows:
                row.setVisible(False)
            self._rows = []
            self._top_spacer.setFixedHeight(0)
            self._bottom_spacer.setFixedHeight(0)
            self._window_start = 0
            return
        capacity = min(total, self._visible_capacity())
        start = max(0, min(int(start), total - capacity))
        window = self._actions[start : start + capacity]
        self._window_start = start

        keyboard_overrides = _current_keyboard_overrides()
        materialized: list[ActionPaletteRow] = []
        for index, action in enumerate(window):
            row = self._rows_by_id.get(action.action_id)
            if row is None or not _is_valid(row):
                row = ActionPaletteRow(
                    action,
                    query=self._search.text(),
                    active_tab=self._active_tab,
                    keyboard_overrides=keyboard_overrides,
                    parent=self._list_host,
                )
                row.rowActivated.connect(self._run_action_id)
                row.rowRevealRequested.connect(self._reveal_action_id)
                row.learnMoreRequested.connect(self._learn_more_action_id)
                self._rows_by_id[action.action_id] = row
            materialized.append(row)
            # Order: [top spacer][rows...][bottom spacer][stretch] - the row goes
            # BETWEEN the spacers, right after the previous one. Inserting it
            # after the bottom spacer (index+2) put the whole unmaterialized
            # remainder above the visible rows and the list read as empty.
            self._list_layout.insertWidget(index + 1, row)
            row.setVisible(True)

        window_ids = set(id(row) for row in materialized)
        for row in self._rows_by_id.values():
            if id(row) not in window_ids and _is_valid(row):
                row.setVisible(False)
        self._rows = materialized
        # Keep the bottom spacer last (before the stretch) after the inserts.
        self._list_layout.insertWidget(len(materialized) + 1, self._bottom_spacer)
        self._top_spacer.setFixedHeight(start * pitch)
        self._bottom_spacer.setFixedHeight((total - start - capacity) * pitch)
        # Keep the cache bounded on very large catalogs: rows outside the window
        # are parked, and only their excess is dropped.
        if len(self._rows_by_id) > max(8, 6 * capacity):
            for action_id in [
                a.action_id for a in self._actions if a.action_id not in
                {act.action_id for act in window}
            ][: len(self._rows_by_id) - 6 * capacity]:
                row = self._rows_by_id.pop(action_id, None)
                if row is not None:
                    self._list_layout.removeWidget(row)

    def _on_scroll(self, value: int) -> None:
        if self._materializing or not self._actions:
            return
        pitch = max(1, self._row_pitch())
        self._materialize(int(value) // pitch)

    def _set_current_index(self, index: int) -> None:
        if not self._actions:
            self._current_index = -1
            return
        if index < 0:
            self._current_index = -1
            for row in self._rows:
                row.set_current(False)
            return
        index = max(0, min(index, len(self._actions) - 1))
        self._current_index = index
        if not self._row_is_materialized(index):
            self._materialize(index)
            self._scroll_to_index(index)
        current_id = self._actions[index].action_id
        for row in self._rows:
            row.set_current(getattr(row, "action_id", None) == current_id)
        return
        for i, row in enumerate(self._rows):
            row.set_current(i == index)
        self._scroll_to_index(self._current_index)

    def _row_is_materialized(self, index: int) -> bool:
        if not (0 <= index < len(self._actions)) or not self._rows:
            return False
        action_id = self._actions[index].action_id
        return any(getattr(row, "action_id", None) == action_id for row in self._rows)

    def _scroll_to_index(self, index: int) -> None:
        if not _is_valid(self._scroll):
            return
        pitch = max(1, self._row_pitch())
        bar = self._scroll.verticalScrollBar()
        bar.setValue(max(bar.minimum(), min(index * pitch, bar.maximum())))

    def _scroll_to_top(self) -> None:
        """Put the results back at the top after a query change.

        GIMP's search popup rebuilds its results on every key release and then
        selects row 0 (``gimpsearchpopup.c``), which also returns the list to
        the top. "Ensure visible" is not the same thing: a list that is already
        scrolled down keeps its position when row 0 is merely re-selected, so
        the new best match could sit above the viewport.
        """
        if not _is_valid(self._scroll):
            return
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.minimum())
        # The rows were just re-ordered/hidden; their geometry lands on the next
        # layout pass, after which the scrollbar range can still shift.
        QTimer.singleShot(0, self._reassert_scroll_top)

    def _reassert_scroll_top(self) -> None:
        if not _is_valid(self) or not _is_valid(self._scroll):
            return
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.minimum())

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

        def _accept_and_run() -> None:
            if not _is_valid(self):
                return
            # Non-modal window with WA_DeleteOnClose (see show_command_palette):
            # close() deletes the palette; accept() would only hide it.
            self.close()
            # Defer until the palette has closed — otherwise combo/menu
            # overlays opened by ``run`` are killed by the dialog's Hide/Close
            # events (ComboBox installs an app-wide filter while expanded).
            QTimer.singleShot(0, run)

        # Wait for the row's own click ripple to finish before close()
        # destroys this dialog -- otherwise the ripple
        # never gets to play at all, same rationale as
        # Button(defer_click=DEFER_CLICK_AWAIT_RIPPLE) /
        # ContextMenuAction.defer_trigger.
        from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms

        QTimer.singleShot(get_ripple_duration_ms(), _accept_and_run)

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
        self.close()
        from ui.actions.reveal import reveal_action_target

        # Defer until the palette has closed and the main window can
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
        video_url = getattr(action, "video_url", None)
        learn_more_url = getattr(action, "learn_more_url", None)
        self.close()
        QTimer.singleShot(
            0,
            lambda p=page, a=anchor, v=video_url, l=learn_more_url: open_help_page(
                p, a, video_url=v, learn_more_url=l
            ),
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

    def _activate_row_layout(self) -> None:
        """Re-run the row layout so rows match the host width.

        Idempotent no-op when the layout is already valid — safe to call
        from viewport Resize/Show and from a deferred tick.
        """
        try:
            host_layout = getattr(self, "_list_layout", None)
            if host_layout is not None:
                host_layout.invalidate()
                host_layout.activate()
        except RuntimeError:
            pass

    def eventFilter(self, obj, event):
        # Viewport shrinks/grows when the overlay scrollbar reserves or
        # releases its gutter — the list layout does not follow on its own
        # (see _build_ui), so re-activate it here. Both immediate (steady
        # state: typing across the overflow boundary) and deferred via
        # singleShot(0) (first show: the gutter lands between the initial
        # Resize and Show with no second Resize, and the host settles after
        # the viewport). No-op when valid.
        scroll = getattr(self, "_scroll", None)
        if scroll is not None and obj is scroll.viewport() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._activate_row_layout()
            self._row_settle.schedule(self, self._activate_row_layout)
        # Синхронизируем current_index с фактическим фокусом (NavigationManager двигает фокус на Button-ряд)
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QWidget):
            # Находим ряд по виджету (row Button или его предок)
            for idx, row in enumerate(self._rows):
                if obj is row or row.isAncestorOf(obj):
                    if self._current_index != idx:
                        self._set_current_index(idx)
                    break
        if event.type() == QEvent.Type.KeyPress:
            # App-wide filter must ignore keys belonging to other windows;
            # widget filters on ``self`` / ``_search`` always pass this check.
            if isinstance(obj, QWidget) and obj.window() is not self:
                return super().eventFilter(obj, event)
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                # Нормальный мапинг через NavigationManager: даём менеджеру шанс обработать Down/Up
                try:
                    from sli_ui_toolkit.managers import NavigationManager

                    mgr = NavigationManager.get_instance()
                    focused = QApplication.focusWidget()
                    # Если менеджер владеет фокусом (наш Auto-секция), пусть он двигает
                    if focused is not None and mgr.should_intercept(key, focused):
                        return False
                    # Если фокус на поиске или в списке — отдаём менеджеру
                    if self.isAncestorOf(focused) if focused is not None else False:
                        # Проверяем что наш Auto-секция владеет фокусом — без обращения к приватному _sections (C6)
                        sec = getattr(self, "_find_action_nav_section", None)
                        if sec is not None and sec.owns(focused):
                            return False
                except Exception:
                    pass
                # Фолбек — старый список
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
                self.close()
                return True
            if self._redirect_typeahead_to_search(event):
                return True
        return super().eventFilter(obj, event)
