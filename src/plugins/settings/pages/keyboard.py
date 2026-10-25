"""Keyboard shortcuts settings page — edit action_id overrides."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from plugins.settings.keymap_defaults import collect_keymap_defaults
from plugins.settings.nav_rows import page_nav_builder, register_page_navigation
from plugins.settings.pages.keyboard_metrics import (
    GROUP_BODY_MARGIN_V_PX,
    GROUP_BODY_SPACING_PX,
    GROUPS_SPACING_PX,
    ROW_SPACING_PX,
    connect_design_metrics,
)
from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group
from plugins.settings.typography import (
    SETTINGS_BODY_PX,
    SettingsGroupWidget,
    settings_body_label,
)
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.widgets import Button, CustomLineEdit
from ui.actions.keymap import (
    effective_shortcut_for_id,
    keymap_entry_rank,
    normalize_sequence,
)
from ui.actions.keymap_uniqueness import verify_unique_or_log
from ui.actions.search_index import PROP_GROUP
from ui.icon_manager import AppIcon

KEYBOARD = group(
    "settings.keyboard",
    "settings.keyboard_search",
    "settings.keyboard_reset",
    "settings.keyboard_reset_all",
)
KEYBOARD_PLATFORM = group("settings.keyboard_group_platform")
KEYBOARD_IC = group("settings.keyboard_group_image_compare")
KEYBOARD_MC = group("settings.keyboard_group_multi_compare")
SEARCH = SearchIndex.of(KEYBOARD, KEYBOARD_PLATFORM, KEYBOARD_IC, KEYBOARD_MC)


def _tr(dialog, key: str, fallback: str) -> str:
    text = dialog._tr(key, dialog.current_language)
    return fallback if text == key else text


class _ShortcutCaptureButton(Button):
    #: Designed cell — all capture buttons share it regardless of chord text.
    _CELL_W = 140
    _CELL_H = 28

    def __init__(self, parent=None):
        super().__init__(
            text="",
            variant="secondary",
            size=(self._CELL_W, self._CELL_H),
            parent=parent,
        )
        self._chord = ""
        self._listening = False
        self._on_changed = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def setText(self, text: str) -> None:
        super().setText(text)
        # The base class clears fixed min/max on the first empty→text
        # transition; without re-pinning, heights stretch after wrapped
        # (two-line) labels and widths follow the chord text.
        self.setFixedSize(scaled_px(self._CELL_W), scaled_px(self._CELL_H))

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def set_chord(self, chord: str | None) -> None:
        self._chord = chord or ""
        self._listening = False
        self.setText(self._chord or "—")

    def mousePressEvent(self, event) -> None:
        self._listening = True
        self.setText("…")
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self._listening:
            # Button's own keyPressEvent turns Space/Enter into a plain
            # click, but this button's "start listening" behavior lives in
            # mousePressEvent (see above) and is not wired to the clicked
            # signal — without this branch, Tab/arrow focus + Enter did
            # nothing and the capture row was mouse-only.
            if event.key() in (
                Qt.Key.Key_Space,
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            ):
                self._listening = True
                self.setText("…")
                event.accept()
                return
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (
            Qt.Key.Key_Escape,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
        ):
            self._commit("")
            event.accept()
            return
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            event.accept()
            return
        seq = QKeySequence(event.keyCombination())
        chord = normalize_sequence(seq.toString(QKeySequence.SequenceFormat.PortableText))
        self._commit(chord)
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self._listening:
            self._listening = False
            self.setText(self._chord or "—")
        super().focusOutEvent(event)

    def _commit(self, chord: str) -> None:
        self._listening = False
        self._chord = chord
        self.setText(self._chord or "—")
        if self._on_changed is not None:
            self._on_changed(self._chord)



def build(dialog, p):
    from ui.actions.keymap import (
        exclusive_overrides,
        repair_legacy_cross_tab_unbounds,
    )

    dialog.page_keyboard, layout = dialog._create_scrollable_page()
    builder = page_nav_builder(dialog, tag="settings-keyboard")
    defaults = collect_keymap_defaults()
    defaults_map = {
        entry.action_id: (entry.default_shortcut, entry.owner_tab)
        for entry in defaults.all_entries()
    }
    # Repair before display: a profile poisoned by the old all-tabs conflict
    # ranking must show the chord as active for its owner instead of "—", and
    # the repaired map is what the dialog carries into the apply path.
    overrides = exclusive_overrides(
        defaults_map,
        repair_legacy_cross_tab_unbounds(
            defaults_map,
            dict(getattr(p, "keyboard_overrides", None) or {}),
        ),
    )
    # The page is the one surface where a user assigns chords, so its own
    # starting state must already satisfy the invariant (a hand-edited
    # profile is repaired by ``exclusive_overrides`` above; a duplicate the
    # resolver could not fix is a defect and is named here).
    verify_unique_or_log(defaults_map, overrides, source="settings keyboard build")
    dialog._keyboard_overrides = overrides
    dialog._keyboard_capture_rows = {}
    dialog._keyboard_action_labels = []
    dialog._keyboard_reset_buttons = []
    dialog._keyboard_owner_groups = []
    dialog._keyboard_filter_rows = []
    dialog._keyboard_group_layouts: list[QVBoxLayout] = []

    search = CustomLineEdit(parent=dialog.page_keyboard)
    search.setPlaceholderText(
        _tr(dialog, "settings.keyboard_search", "Filter shortcuts…")
    )
    KEYBOARD.tag_member(search, "settings.keyboard_search")
    dialog._keyboard_search = search
    # The filter is the page's FIRST navigation row: it is wrapped by
    # builder.row() here, before the chord rows are extended below, so
    # Down from the page top walks filter → chord rows → Reset all in
    # visual order. Adding it straight to the page layout (what the
    # nav-coverage audit found as finding F2) left it outside every row
    # the section owns, so no arrow key could reach it.
    layout.addWidget(builder.row(search))

    groups_host = QWidget(dialog.page_keyboard)
    groups_layout = QVBoxLayout(groups_host)
    groups_layout.setContentsMargins(0, 0, 0, 0)
    groups_layout.setSpacing(scaled_px(GROUPS_SPACING_PX))
    dialog._keyboard_groups_layout = groups_layout
    layout.addWidget(groups_host)

    owner_titles = {
        None: _tr(dialog, "settings.keyboard_group_platform", "Platform"),
    }
    owner_group_keys = {
        None: KEYBOARD_PLATFORM.title_key,
    }
    try:
        from core.store import INITIAL_WORKSPACE_SESSION_TYPE
        from tabs.registry import TabRegistry

        for tab in TabRegistry().list_tabs():
            session_type = tab.session_type
            if session_type == INITIAL_WORKSPACE_SESSION_TYPE:
                continue
            # Also skip tabs that are bootstrap-default but not the
            # initial workspace type (defensive; is_bootstrap_default is
            # reserved for session_picker — see TabContract).
            if getattr(tab, "is_bootstrap_default", False):
                continue
            group_key = f"settings.keyboard_group_{session_type}"
            owner_titles[session_type] = _tr(
                dialog, group_key, tab.display_name
            )
            owner_group_keys[session_type] = group_key
    except Exception:
        pass

    by_owner: dict[str | None, list] = {}
    for entry in defaults.all_entries():
        by_owner.setdefault(entry.owner_tab, []).append(entry)

    row_widgets: list[tuple[QWidget, object, object]] = []
    dialog._keyboard_filter_rows = row_widgets
    # Uniform rows: two BODY lines. Single-line labels would leave 28px
    # rows next to 44px wrapped ones and the rhythm falls apart.
    _row_min_height = QFontMetrics(ui_font(pixel_size=SETTINGS_BODY_PX)).lineSpacing() * 2

    def _refresh_capture_labels() -> None:
        for entry in defaults.all_entries():
            cap = dialog._keyboard_capture_rows.get(entry.action_id)
            if cap is None:
                continue
            current = effective_shortcut_for_id(
                entry.action_id,
                default=entry.default_shortcut,
                overrides=dialog._keyboard_overrides,
            )
            cap.set_chord(current)

    def _verify(source: str) -> None:
        """Invariant gate for every path that writes the page's override map.

        A duplicate binding can only appear here through resolver damage
        (``steal_chord_in_overrides`` / ``exclusive_overrides`` are supposed
        to make it impossible), so the reaction is a loud ERROR plus the map
        the resolver produced — the user's edit still applies, and the defect
        is not hidden behind "the first chord wins".
        """
        verify_unique_or_log(
            defaults_map, dialog._keyboard_overrides, source=f"settings keyboard {source}"
        )

    def _set_override(action_id: str, default: str | None, chord: str) -> None:
        from ui.actions.keymap import steal_chord_in_overrides

        dialog._keyboard_overrides = steal_chord_in_overrides(
            action_id=action_id,
            chord=chord,
            defaults=defaults_map,
            overrides=dialog._keyboard_overrides,
        )
        _verify(f"capture {action_id}={chord or '<unbound>'}")
        _refresh_capture_labels()

    for owner, entries in by_owner.items():
        group_title = owner_titles.get(owner, owner or "Platform")
        group = SettingsGroupWidget(group_title)
        group_key = owner_group_keys.get(owner)
        if group_key:
            group.setProperty(PROP_GROUP, group_key)
            dialog._keyboard_owner_groups.append((group, group_key))
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(
            0, scaled_px(GROUP_BODY_MARGIN_V_PX), 0, scaled_px(GROUP_BODY_MARGIN_V_PX)
        )
        group_layout.setSpacing(scaled_px(GROUP_BODY_SPACING_PX))
        dialog._keyboard_group_layouts.append(group_layout)
        for entry in entries:
            row = QWidget()
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.setMinimumHeight(_row_min_height)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(scaled_px(ROW_SPACING_PX))

            label_text = _tr(dialog, entry.label_key, entry.label_key)
            name = settings_body_label(label_text)
            name.setWordWrap(True)
            row_layout.addWidget(name, 1)
            dialog._keyboard_action_labels.append((name, entry.label_key))

            current = effective_shortcut_for_id(
                entry.action_id,
                default=entry.default_shortcut,
                overrides=dialog._keyboard_overrides,
            )
            capture = _ShortcutCaptureButton(parent=row)
            capture.set_chord(current)
            capture.set_on_changed(
                lambda chord, aid=entry.action_id, default=entry.default_shortcut: _set_override(
                    aid, default, chord
                )
            )
            row_layout.addWidget(capture, 0)

            reset = Button(
                text=_tr(dialog, "settings.keyboard_reset", "Reset"),
                variant="ghost",
                size=(72, 28),
                parent=row,
            )
            dialog._keyboard_reset_buttons.append(reset)

            def _reset(
                aid=entry.action_id,
                default=entry.default_shortcut,
                cap=capture,
            ):
                from ui.actions.keymap import steal_chord_in_overrides

                # Reset to default, but still steal that chord from others.
                dialog._keyboard_overrides.pop(aid, None)
                dialog._keyboard_overrides = steal_chord_in_overrides(
                    action_id=aid,
                    chord=default,
                    defaults=defaults_map,
                    overrides=dialog._keyboard_overrides,
                )
                _verify(f"reset {aid}")
                _refresh_capture_labels()

            reset.clicked.connect(_reset)
            row_layout.addWidget(reset, 0)

            group_layout.addWidget(row)
            dialog._keyboard_capture_rows[entry.action_id] = capture
            row_widgets.append((row, group, entry))

        group.add_layout(group_layout)
        groups_layout.addWidget(group)

    # Arrow-key row navigation goes through the app-wide NavigationManager
    # (same mechanism the main window's tabs/toolbars use — see
    # ToolbarRowsSection), not a page-local event filter: NavigationManager
    # owns arrow-key consumption on QApplication exclusively (see its own
    # docstring's Contract) — a widget-level filter would never even see the
    # key, since NavigationManager's QApplication-level filter runs first
    # and, if no registered section claims the focused widget, simply
    # yields to native Qt delivery (a bare QScrollArea then just scrolls).
    # Each row already holds two focusable buttons (capture + reset), so
    # ToolbarRowsSection's Left/Right-within-row, Up/Down-between-rows model
    # applies directly; row_widgets is the same list the search filter
    # toggles visibility on, so hidden rows drop out of navigation too.
    # Rows are already real QWidgets (built directly above, not from a bare
    # control/layout) so they go through extend() rather than builder.row()
    # (which would re-wrap and re-parent them out of group_layout).
    builder.extend([row for row, _group, _entry in row_widgets])

    reset_all = Button(
        text=_tr(dialog, "settings.keyboard_reset_all", "Reset all shortcuts"),
        variant="secondary",
        size=(200, 32),
        parent=dialog.page_keyboard,
    )
    KEYBOARD.tag_member(reset_all, "settings.keyboard_reset_all")
    dialog._keyboard_reset_all = reset_all

    def _reset_all() -> None:
        from ui.actions.keymap import exclusive_overrides

        dialog._keyboard_overrides.clear()
        # Re-apply exclusivity across defaults so two actions cannot keep the
        # same built-in chord after a full reset.
        dialog._keyboard_overrides = exclusive_overrides(defaults_map, {})
        _verify("reset all")
        _refresh_capture_labels()

    reset_all.clicked.connect(_reset_all)
    # Reset all is the page's LAST navigation row: same builder, same row
    # container mechanism as the chord rows (no bespoke section), appended
    # after them so Down continues past the last chord into it. It must be
    # declared before register_page_navigation(), which snapshots the
    # builder's rows — the old code added the button straight to the page
    # layout after that snapshot, leaving it owned by no section (finding
    # F2). HBox + trailing stretch keeps the button left-aligned exactly
    # where the page layout used to place it.
    reset_all_layout = QHBoxLayout()
    reset_all_layout.setContentsMargins(0, 0, 0, 0)
    reset_all_layout.addWidget(reset_all, 0)
    reset_all_layout.addStretch(1)
    layout.addWidget(builder.row(reset_all_layout))

    register_page_navigation(dialog, dialog.page_keyboard, builder)

    def _filter(text: str) -> None:
        needle = (text or "").strip()
        visible_groups: dict[object, bool] = {}
        group_titles = {
            group: title
            for group, title_key in getattr(dialog, "_keyboard_owner_groups", ()) or ()
            for title in (_tr(dialog, title_key, title_key),)
        }
        for row, group, entry in row_widgets:
            current = effective_shortcut_for_id(
                entry.action_id,  # type: ignore[attr-defined]  # dynamic keymap row object
                default=entry.default_shortcut,  # type: ignore[attr-defined]
                overrides=dialog._keyboard_overrides,
            )
            extras = (
                group_titles.get(group, ""),
                current or "",
                entry.owner_tab or "platform",  # type: ignore[attr-defined]  # dynamic keymap row object
            )
            show = keymap_entry_rank(
                entry, needle, extra_search_terms=extras
            ) is not None
            row.setVisible(show)
            if show:
                visible_groups[group] = True
            else:
                visible_groups.setdefault(group, False)
        for group, any_visible in visible_groups.items():
            group.setVisible(bool(any_visible))  # type: ignore[attr-defined]  # group objects are dynamic

    search.textChanged.connect(_filter)
    layout.addStretch(1)
    connect_design_metrics(dialog)
    dialog.pages_stack.addWidget(dialog.page_keyboard)


def refresh_language(dialog) -> None:
    """Retranslate keyboard page chrome after a live language switch."""
    if getattr(dialog, "page_keyboard", None) is None:
        return

    search = getattr(dialog, "_keyboard_search", None)
    if search is not None:
        search.setPlaceholderText(
            _tr(dialog, "settings.keyboard_search", "Filter shortcuts…")
        )

    reset_all = getattr(dialog, "_keyboard_reset_all", None)
    if reset_all is not None:
        reset_all.setText(
            _tr(dialog, "settings.keyboard_reset_all", "Reset all shortcuts")
        )

    reset_label = _tr(dialog, "settings.keyboard_reset", "Reset")
    for button in getattr(dialog, "_keyboard_reset_buttons", ()) or ():
        button.setText(reset_label)

    for group, title_key in getattr(dialog, "_keyboard_owner_groups", ()) or ():
        fallback = title_key.rsplit(".", 1)[-1].replace("_", " ").title()
        group.set_title(_tr(dialog, title_key, fallback))

    filter_rows = getattr(dialog, "_keyboard_filter_rows", None)
    labels = getattr(dialog, "_keyboard_action_labels", ()) or ()
    for name, label_key in labels:
        name.setText(_tr(dialog, label_key, label_key))

    if search is not None and filter_rows is not None:
        # Re-run filter so group visibility stays correct after title/label change.
        search.textChanged.emit(search.text())

SECTION = SettingsSection(
    section_id="builtin.keyboard",
    title_key="settings.keyboard",
    icon=AppIcon.ENTER,
    build=build,
    owner_tab=None,
    order=25,
    action_description_key="action.settings.keyboard_desc",
    search=SEARCH,
)