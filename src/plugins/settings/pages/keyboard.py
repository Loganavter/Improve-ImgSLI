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
from sli_ui_toolkit.widgets import Button, CustomGroupWidget, CustomLineEdit, Label
from ui.actions.keymap import (
    KeymapDefaultsRegistry,
    effective_shortcut_for_id,
    normalize_sequence,
)
from ui.actions.search_index import PROP_GROUP
from ui.icon_manager import AppIcon

KEYBOARD = group(
    "settings.keyboard",
    "settings.keyboard_hint",
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
        pass
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
    dialog.page_keyboard, layout = dialog._create_scrollable_page()
    defaults = _collect_defaults()
    overrides = dict(getattr(p, "keyboard_overrides", None) or {})
    dialog._keyboard_overrides = overrides
    dialog._keyboard_capture_rows = {}

    hint = Label(
        _tr(
            dialog,
            "settings.keyboard_hint",
            "Click a binding, then press a new shortcut. Esc / Backspace clears. "
            "Empty = unbound. Reset restores the default.",
        ),
        variant="caption",
        pixel_size=11,
        parent=dialog.page_keyboard,
    )
    KEYBOARD.tag_member(hint, "settings.keyboard_hint")
    layout.addWidget(hint)

    search = CustomLineEdit(parent=dialog.page_keyboard)
    search.setPlaceholderText(
        _tr(dialog, "settings.keyboard_search", "Filter shortcuts…")
    )
    KEYBOARD.tag_member(search, "settings.keyboard_search")
    layout.addWidget(search)

    groups_host = QWidget(dialog.page_keyboard)
    groups_layout = QVBoxLayout(groups_host)
    groups_layout.setContentsMargins(0, 0, 0, 0)
    groups_layout.setSpacing(10)
    layout.addWidget(groups_host)

    owner_titles = {
        None: _tr(dialog, "settings.keyboard_group_platform", "Platform"),
        "image_compare": _tr(
            dialog, "settings.keyboard_group_image_compare", "Image Compare"
        ),
        "multi_compare": _tr(
            dialog, "settings.keyboard_group_multi_compare", "Multi Compare"
        ),
    }
    owner_group_keys = {
        None: KEYBOARD_PLATFORM.title_key,
        "image_compare": KEYBOARD_IC.title_key,
        "multi_compare": KEYBOARD_MC.title_key,
    }

    by_owner: dict[str | None, list] = {}
    for entry in defaults.all_entries():
        by_owner.setdefault(entry.owner_tab, []).append(entry)

    row_widgets: list[tuple[str, QWidget, object]] = []

    def _set_override(action_id: str, default: str | None, chord: str) -> None:
        normalized = normalize_sequence(chord)
        default_norm = normalize_sequence(default)
        if normalized == default_norm:
            dialog._keyboard_overrides.pop(action_id, None)
        elif not normalized:
            dialog._keyboard_overrides[action_id] = ""
        else:
            dialog._keyboard_overrides[action_id] = normalized

    for owner, entries in by_owner.items():
        group = CustomGroupWidget(owner_titles.get(owner, owner or "Platform"))
        group_key = owner_group_keys.get(owner)
        if group_key:
            group.setProperty(PROP_GROUP, group_key)
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

            def _reset(
                aid=entry.action_id,
                default=entry.default_shortcut,
                cap=capture,
            ):
                dialog._keyboard_overrides.pop(aid, None)
                cap.set_chord(normalize_sequence(default) or None)

            reset.clicked.connect(_reset)
            row_layout.addWidget(reset, 0)

            group_layout.addWidget(row)
            dialog._keyboard_capture_rows[entry.action_id] = capture
            row_widgets.append((label_text.lower(), row, group))

        group.add_layout(group_layout)
        groups_layout.addWidget(group)

    reset_all = Button(
        text=_tr(dialog, "settings.keyboard_reset_all", "Reset all shortcuts"),
        variant="secondary",
        size=(200, 32),
        parent=dialog.page_keyboard,
    )
    KEYBOARD.tag_member(reset_all, "settings.keyboard_reset_all")

    def _reset_all() -> None:
        dialog._keyboard_overrides.clear()
        for entry in defaults.all_entries():
            cap = dialog._keyboard_capture_rows.get(entry.action_id)
            if cap is not None:
                cap.set_chord(normalize_sequence(entry.default_shortcut) or None)

    reset_all.clicked.connect(_reset_all)
    layout.addWidget(reset_all, 0, Qt.AlignmentFlag.AlignLeft)

    def _filter(text: str) -> None:
        needle = (text or "").strip().lower()
        visible_groups: dict[object, bool] = {}
        for label, row, group in row_widgets:
            show = not needle or needle in label
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
