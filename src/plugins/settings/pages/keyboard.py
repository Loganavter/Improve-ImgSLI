"""Keyboard shortcuts settings page — edit action_id overrides."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from plugins.settings.registry import SettingsSection
from plugins.settings.search import SearchIndex, group
from sli_ui_toolkit.widgets import Button, CustomGroupWidget, CustomLineEdit
from ui.actions.keymap import (
    KeymapDefaultsRegistry,
    effective_shortcut_for_id,
    keymap_entry_rank,
    normalize_sequence,
)
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
    text = dialog.tr(key, dialog.current_language)
    return fallback if text == key else text


def _collect_defaults() -> KeymapDefaultsRegistry:
    registry = KeymapDefaultsRegistry()
    from ui.actions.platform import contribute_platform_keymap_defaults

    contribute_platform_keymap_defaults(registry)
    try:
        from tabs.registry import TabRegistry

        tabs = TabRegistry()
        tabs.discover()
        tabs.notify_all("contribute_keymap_defaults", registry)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Failed to collect tab keymap defaults for Settings → Keyboard"
        )
    return registry


class _ShortcutCaptureButton(Button):
    def __init__(self, parent=None):
        super().__init__(
            text="",
            variant="secondary",
            size=(140, 28),
            parent=parent,
        )
        self._chord = ""
        self._listening = False
        self._on_changed = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
    from ui.actions.keymap import exclusive_overrides

    dialog.page_keyboard, layout = dialog._create_scrollable_page()
    defaults = _collect_defaults()
    defaults_map = {
        entry.action_id: (entry.default_shortcut, entry.owner_tab)
        for entry in defaults.all_entries()
    }
    overrides = exclusive_overrides(
        defaults_map,
        dict(getattr(p, "keyboard_overrides", None) or {}),
    )
    dialog._keyboard_overrides = overrides
    dialog._keyboard_capture_rows = {}
    dialog._keyboard_action_labels = []
    dialog._keyboard_reset_buttons = []
    dialog._keyboard_owner_groups = []
    dialog._keyboard_filter_rows = []

    search = CustomLineEdit(parent=dialog.page_keyboard)
    search.setPlaceholderText(
        _tr(dialog, "settings.keyboard_search", "Filter shortcuts…")
    )
    KEYBOARD.tag_member(search, "settings.keyboard_search")
    dialog._keyboard_search = search
    layout.addWidget(search)

    groups_host = QWidget(dialog.page_keyboard)
    groups_layout = QVBoxLayout(groups_host)
    groups_layout.setContentsMargins(0, 0, 0, 0)
    groups_layout.setSpacing(10)
    layout.addWidget(groups_host)

    owner_titles = {
        None: _tr(dialog, "settings.keyboard_group_platform", "Platform"),
    }
    owner_group_keys = {
        None: KEYBOARD_PLATFORM.title_key,
    }
    try:
        from tabs.registry import TabRegistry

        for tab in TabRegistry().list_tabs():
            session_type = tab.session_type
            if session_type == "session_picker":
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

    def _set_override(action_id: str, default: str | None, chord: str) -> None:
        from ui.actions.keymap import steal_chord_in_overrides

        dialog._keyboard_overrides = steal_chord_in_overrides(
            action_id=action_id,
            chord=chord,
            defaults=defaults_map,
            overrides=dialog._keyboard_overrides,
        )
        _refresh_capture_labels()

    for owner, entries in by_owner.items():
        group_title = owner_titles.get(owner, owner or "Platform")
        group = CustomGroupWidget(group_title)
        group_key = owner_group_keys.get(owner)
        if group_key:
            group.setProperty(PROP_GROUP, group_key)
            dialog._keyboard_owner_groups.append((group, group_key))
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.setSpacing(4)
        for entry in entries:
            row = QWidget()
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            label_text = _tr(dialog, entry.label_key, entry.label_key)
            name = QLabel(label_text)
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
                _refresh_capture_labels()

            reset.clicked.connect(_reset)
            row_layout.addWidget(reset, 0)

            group_layout.addWidget(row)
            dialog._keyboard_capture_rows[entry.action_id] = capture
            row_widgets.append((row, group, entry))

        group.add_layout(group_layout)
        groups_layout.addWidget(group)

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
        _refresh_capture_labels()

    reset_all.clicked.connect(_reset_all)
    layout.addWidget(reset_all, 0, Qt.AlignmentFlag.AlignLeft)

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
                entry.action_id,
                default=entry.default_shortcut,
                overrides=dialog._keyboard_overrides,
            )
            extras = (
                group_titles.get(group, ""),
                current or "",
                entry.owner_tab or "platform",
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
            group.setVisible(bool(any_visible))

    search.textChanged.connect(_filter)
    layout.addStretch(1)
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
